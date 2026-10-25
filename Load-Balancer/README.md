# Load Balancer

A reusable Go HTTP reverse proxy with eleven transport-independent routing strategies. Requires Go 1.22.5 or newer and uses only the standard library.

Forked from [Distributed-Systems-Components/Load-Balancer](https://github.com/AureliusNguyen/Distributed-Systems-Components/tree/main/Load-Balancer). This copy adds the carbon-aware strategy for the edge-vs-cloud project.

## Setup

From the repository root:

```sh
cd Load-Balancer
go test -race ./...
go vet ./...
```

To use it from a separate Go module:

```sh
go get github.com/AureliusNguyen/SLM-Edge-vs-Cloud/Load-Balancer
```

## Embed in another project

This complete factory creates a proxy that your application can mount as an `http.Handler`:

```go
package api

import (
    loadbalancer "github.com/AureliusNguyen/SLM-Edge-vs-Cloud/Load-Balancer"
    "github.com/AureliusNguyen/SLM-Edge-vs-Cloud/Load-Balancer/strategy"
)

func NewProxy() (*loadbalancer.Balancer, error) {

    return loadbalancer.New(loadbalancer.Config{
        Backends: []loadbalancer.Backend{
            {ID: "api-a", URL: "http://127.0.0.1:9001"},
            {ID: "api-b", URL: "http://127.0.0.1:9002"},
        },
        Picker: strategy.NewPowerOfTwo(),
    })
}
```

Handle the returned error at startup, pass the balancer as your `http.Server.Handler`, and call `CloseIdleConnections` during shutdown. Set server deadlines suitable for your workload, such as a five-second `ReadHeaderTimeout` and a sixty-second `IdleTimeout`. The library owns no listener, global HTTP mux, signal handler, or process exit. See the [runnable example](cmd/example/main.go) for complete server and health-check lifecycle handling.

The [HTTP adapter](balancer.go) and [health probes](health.go) are independent of the [strategy contract](strategy/strategy.go). Import `strategy` directly when routing RPCs or jobs instead of HTTP traffic.

## Choose the strategy for the workload

| Strategy | Constructor | Specific good fit | Tradeoff |
| --- | --- | --- | --- |
| Round-robin | `NewRoundRobin()` | Equal API servers answering similarly sized requests | A slow upload still receives its share of new requests |
| Weighted round-robin | `NewWeightedRoundRobin(weights)` | Give an 8-core node four times the traffic of a 2-core node | Configured capacity does not reflect live CPU pressure |
| Random | `NewRandom()` | Many small requests across interchangeable stateless workers | Small batches can cluster by chance |
| Least connections | `NewLeastConnections()` | Mix of 10ms reads and 30-second downloads | Scans all eligible backends and measures requests, not actual TCP connections |
| Power of two | `NewPowerOfTwo()` | Hundreds of interchangeable workers with uneven in-flight work | Samples only two nodes, so it can miss the globally least busy node |
| Least response time | `NewLeastResponseTime(LatencyOptions{})` | One backend is swapping and has become much slower than its peers | End-to-end durations include client backpressure and need interpretation |
| Resource based | `NewResourceBased(provider, maxAge)` | CPU-heavy jobs where connection count hides actual work | Requires comparable fresh metrics from an external collector |
| Simple hash | `NewSimpleHash()` | Disposable per-user caches with infrequent pool changes | Eligibility changes remap many keys and one hot key stays on one node |
| Consistent hash | `NewConsistentHash(members, 128)` | Cache affinity while adding or removing nodes | Virtual nodes balance many keys, never a single celebrity key |
| Key range | `NewKeyRange(ranges)` | Explicit ownership of time-series or alphabetical partitions | Hot ranges need splitting and an unavailable owner fails closed |
| Carbon aware | `NewCarbonAware(profiles)` | Edge SLM vs cloud LLM where per-request energy and grid intensity differ | Static estimates ignore prompt length, live grid intensity, load, and answer quality |

All constructors are in `strategy`. Constructors that take configuration return an error. Stateless and count-only constructors cannot receive invalid configuration and return the picker directly.

### Celebrity keys

If every backend can serve a popular account, use power-of-two, least-connections, or another non-affinity policy to spread its requests. These algorithms deliberately ignore the routing key.

If you need cache affinity, consistent hashing keeps a popular account on one backend. Virtual nodes balance the overall keyspace, not traffic within one key. Cache replication, request coalescing, and an application-defined pool of replicas can address that workload. A distinct replica-aware picker can choose among those replicas without changing every existing strategy.

If the key owns authoritative state, arbitrary rerouting is incorrect. Splitting a hot partition, salting keys, adding read replicas, or changing the data model belongs to the storage/application design. Reads and writes may need different policies. `KeyRange` returns an error when the owning backend is unavailable. Hash strategies provide affinity with eligible-backend failover, so use them only when the fallback backend can actually serve the data.

## Extend without fake fields or methods

```go
type Picker interface {
    Pick(context.Context, strategy.Input, strategy.Candidates) (strategy.Selection, error)
}
```

- `Input` contains request facts. It currently contains `Key`. Adding a fact does not require existing strategies to use it or modify their own structs. Keep keyed struct literals so omitted facts retain their zero values. A strategy validates the facts it requires.
- Strategy settings belong in that strategy's constructor. Weights, virtual-node counts, range boundaries, and EWMA settings are not request fields.
- External dependencies belong in that strategy's constructor. Only resource-based routing receives a metrics provider. There is no universal `UpdateLoad` method.
- `Candidates` is a validated, immutable, canonically ordered snapshot of healthy backend IDs. Its empty value represents no eligible backends. IDs remain stable when lists are reordered.
- A successful load-aware pick reserves the selected node under the same lock used for selection. Its `Selection.Done` callback releases that reservation and receives the outcome. Stateless strategies leave `Done` nil. Built-in callbacks tolerate duplicate calls, but callers should complete each successful pick exactly once, including panic paths.

For non-HTTP projects, import `strategy` directly and complete selections around your own RPC/job execution. Reuse a candidate snapshot while membership and readiness remain unchanged. A stateful picker belongs to one balancer and tracks that instance's requests, not global traffic across multiple balancer processes.

### Strategy configuration examples

```go
weighted, err := strategy.NewWeightedRoundRobin(map[strategy.BackendID]int{
    "api-a": 4,
    "api-b": 1,
})
```

Weights must be nonnegative with at least one positive value. Zero disables a node. Unknown eligible IDs produce a configuration error. Eligibility changes reset smooth scheduling state so returning nodes do not inherit a backlog of turns.

```go
members, err := strategy.NewCandidates("cache-a", "cache-b", "cache-c")

if err != nil {

    return err
}

hash, err := strategy.NewConsistentHash(members, 128)
```

The ring uses SHA-256-derived points, virtual nodes, binary search, and stable IDs. Ineligible owners fail over clockwise. Unknown IDs are rejected. Rebuild the picker and handler when membership changes, keeping surviving backend IDs unchanged. New nodes take only their share of the hash space. Increasing virtual-node count also changes ownership, so keep that configuration consistent across balancers.

```go
ranges, err := strategy.NewKeyRange([]strategy.Range{
    {UpperBound: "m", BackendID: "shard-a"},
    {BackendID: "shard-b"},
})
```

Bounds are inclusive and compared lexicographically. The final empty bound means positive infinity. A finite final bound rejects keys beyond it. Use normalized, consistently encoded keys, such as fixed-width UTC timestamps, when lexical ordering must match domain ordering.

Carbon-aware routing scores each eligible backend as `EnergyWh * IntensityGPerKWh / 1000` grams of CO2e per request and picks the lowest; ties rotate. Every eligible backend needs a profile, otherwise the pick returns `ErrInvalidCandidates`. Values must be finite and nonnegative.

The resource provider returns `LoadSample{Value, UpdatedAt}` from a concurrency-safe local cache. It must use the same units across nodes and respect request cancellation. Stale, missing, negative, future-dated, NaN, and infinite samples are excluded. If none are usable, routing fails rather than treating a silent backend as idle.

Latency routing uses EWMA latency multiplied by in-flight requests plus one. Fast failures and HTTP 5xx receive a configurable minimum penalty. Old samples decay toward the initial estimate to let a recovered node receive traffic again. Client cancellations release counts without updating latency. Active health probes remain responsible for readiness.

## HTTP behavior and health

The default routing key is the URL path. A query parameter never overrides routing implicitly. Supply `Config.Key` to extract an application key, for example a validated tenant ID from authentication middleware. The example supports `-key-header` for trusted development traffic.

An optional `Backend.Ready` callback reads a fast, concurrency-safe readiness signal. Without one, that backend is assumed eligible. `NewHTTPHealthCheck` supplies a real bounded HTTP probe for a dedicated endpoint. It starts unready, accepts only direct 2xx responses, periodically checks through `Run(ctx)`, and clears readiness on shutdown. Point it at an actual readiness endpoint, not a redirecting homepage. Provide a custom readiness callback for other protocols or more advanced health policies.

All-down selection returns 503 without spinning. Unknown or ineligible picker selections also return 503 and release any reservation. Key extraction errors return 400. Upstream transport failures return 502. Backend responses, including 5xx, are forwarded and reported through optional `Config.OnResult`. The balancer makes one upstream attempt and does not replay non-idempotent writes. Retry budgets, idempotency, circuit breakers, rate limits, and admission limits can be layered according to the application's semantics.

The proxy preserves base paths and query strings with `Rewrite` and `SetURL`, rewrites the upstream Host, and rebuilds forwarding headers from the direct incoming connection. If deployed behind another proxy, establish that proxy's identity/trust policy explicitly before using forwarded client addresses as keys.

The default transport bounds dialing, TLS handshakes, response headers, and idle connections. There is no blanket response-body deadline, allowing streaming. Set appropriate request/body deadlines and concurrency limits at your application boundary. Active streams keep their in-flight reservation until the attempt ends. Durations include copying to slow clients, so use resource metrics or a custom picker if you need backend-only service time.

Power-of-two selection is O(1) against a prepared candidate snapshot. The HTTP adapter scans readiness callbacks when configured, which is O(n) per request. The immutable pool is reused without a scan when no readiness callbacks exist. Very large dynamic pools should publish cached candidate snapshots in their own adapter. Consistent hashing validates eligible IDs in O(n), searches in O(log ring-size), and may scan ring points to skip unavailable owners.

## Run the example

Start backends on ports 9001 and 9002 with a `/healthz` readiness endpoint, then run:

```sh
go run ./cmd/example -strategy power-of-two
```

For existing servers without a readiness endpoint:

```sh
go run ./cmd/example -backends a=http://localhost:9001,b=http://localhost:9002 -health-path ''
```

The command supports round-robin, random, least-connections, power-of-two, least-response-time, simple-hash, and consistent-hash. Configure weighted, resource-based, key-range, and carbon-aware strategies through the library because they require workload-specific settings. SIGINT/SIGTERM stops accepting traffic and allows up to ten seconds to finish requests.

## Validate

```sh
go test -race ./...
go vet ./...
```

Tests use local `httptest` servers and cover concurrent reservation/release, duplicate completion, health changes and probe cancellation, all-down routing, transport errors, panic cleanup, POST attempts, proxy rewriting, constructor validation, stale metrics, hash distribution, stable ownership, and celebrity-key behavior.

For code based on the earlier prototype, this replaces the `routeStrategies` API and `src/main.go`. Update imports to `strategy`, replace count/index configuration with stable backend IDs and candidate snapshots, and replace separate `Acquire`/`Release` calls with `Selection.Done`. The module path remains unchanged.
