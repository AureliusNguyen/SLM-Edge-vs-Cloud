// Use when: Run regression tests after changing strategy selection or membership behavior.
// Example: The celebrity-key tests prove hashing pins a key while load-aware pickers distribute outstanding requests.
// Pros: Concurrent tests detect reservation races and deterministic distribution tests detect clustered hash rings.
// Cons: Synthetic request counts do not replace benchmarks with real workload costs or multi-process traffic.
package strategy

import (
	"context"
	"errors"
	"fmt"
	"math"
	"sync"
	"testing"
	"time"
)

func pool(t *testing.T, ids ...BackendID) Candidates {
	t.Helper()
	c, err := NewCandidates(ids...)

	if err != nil {
		t.Fatal(err)
	}

	return c
}

func pick(t *testing.T, picker Picker, c Candidates, key string) Selection {
	t.Helper()
	s, err := picker.Pick(context.Background(), Input{Key: key}, c)

	if err != nil {
		t.Fatal(err)
	}

	if !c.Contains(s.BackendID) {
		t.Fatalf("selected ineligible backend %q", s.BackendID)
	}

	return s
}

func finish(s Selection) {

	if s.Done != nil {
		s.Done(Result{Duration: time.Millisecond, StatusCode: 200})
	}

}

func pickers(t *testing.T, c Candidates) map[string]Picker {
	t.Helper()
	weighted, err := NewWeightedRoundRobin(map[BackendID]int{"a": 4, "b": 2, "c": 1})

	if err != nil {
		t.Fatal(err)
	}

	latency, err := NewLeastResponseTime(LatencyOptions{})

	if err != nil {
		t.Fatal(err)
	}

	ring, err := NewConsistentHash(c, 128)

	if err != nil {
		t.Fatal(err)
	}

	ranges, err := NewKeyRange([]Range{{UpperBound: "m", BackendID: "a"}, {UpperBound: "t", BackendID: "b"}, {BackendID: "c"}})

	if err != nil {
		t.Fatal(err)
	}

	resource, err := NewResourceBased(func(context.Context, BackendID) (LoadSample, error) {

		return LoadSample{Value: 1, UpdatedAt: time.Now()}, nil
	}, time.Minute)

	if err != nil {
		t.Fatal(err)
	}

	carbon, err := NewCarbonAware(map[BackendID]CarbonProfile{
		"a": {EnergyWh: 2, IntensityGPerKWh: 450}, "b": {EnergyWh: 0.3, IntensityGPerKWh: 400}, "c": {EnergyWh: 1, IntensityGPerKWh: 100},
	})

	if err != nil {
		t.Fatal(err)
	}

	return map[string]Picker{
		"round-robin": NewRoundRobin(), "weighted": weighted, "random": NewRandom(),
		"least-connections": NewLeastConnections(), "power-of-two": NewPowerOfTwo(),
		"latency": latency, "resource": resource, "simple-hash": NewSimpleHash(),
		"consistent-hash": ring, "key-range": ranges, "carbon": carbon,
	}
}

func TestCandidatesAreCanonicalAndImmutable(t *testing.T) {
	ids := []BackendID{"c", "a", "b"}
	c := pool(t, ids...)
	ids[0] = "changed"
	copyIDs := c.IDs()
	copyIDs[0] = "changed"

	if c.At(0) != "a" || !c.Contains("c") || c.Contains("changed") {
		t.Fatal("candidate snapshot was mutated")
	}

	for _, invalid := range [][]BackendID{{""}, {"a", "a"}} {
		_, err := NewCandidates(invalid...)

		if err == nil {
			t.Fatalf("accepted invalid IDs %v", invalid)
		}

	}

}

func TestAllPickersHandleEmptyAndCanceledPools(t *testing.T) {
	c := pool(t, "a", "b", "c")
	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	for name, picker := range pickers(t, c) {
		t.Run(name, func(t *testing.T) {
			_, err := picker.Pick(context.Background(), Input{Key: "key"}, Candidates{})

			if !errors.Is(err, ErrNoBackend) {
				t.Fatalf("empty pool: %v", err)
			}

			_, err = picker.Pick(ctx, Input{Key: "key"}, c)

			if !errors.Is(err, context.Canceled) {
				t.Fatalf("canceled request: %v", err)
			}

		})
	}

}

func TestAllPickersConcurrent(t *testing.T) {
	c := pool(t, "a", "b", "c")

	for name, picker := range pickers(t, c) {
		t.Run(name, func(t *testing.T) {
			var workers sync.WaitGroup

			for worker := range 16 {
				workers.Add(1)
				go func() {
					defer workers.Done()

					for i := range 128 {
						s, err := picker.Pick(context.Background(), Input{Key: fmt.Sprintf("user:%d:%d", worker, i)}, c)

						if err != nil {
							t.Error(err)

							return
						}

						if !c.Contains(s.BackendID) {
							t.Errorf("ineligible %q", s.BackendID)

							return
						}

						finish(s)
						finish(s)
					}

				}()
			}

			workers.Wait()
		})
	}

}

func TestRoundRobinConcurrentFairness(t *testing.T) {
	c := pool(t, "a", "b", "c")
	r := NewRoundRobin()
	var mu sync.Mutex
	totals := make(map[BackendID]int)
	var workers sync.WaitGroup

	for range 12 {
		workers.Add(1)
		go func() {
			defer workers.Done()

			for range 100 {
				s := pick(t, r, c, "")
				mu.Lock()
				totals[s.BackendID]++
				mu.Unlock()
			}

		}()
	}

	workers.Wait()

	for _, id := range c.IDs() {

		if totals[id] != 400 {
			t.Fatalf("%s received %d requests", id, totals[id])
		}

	}

}

func TestWeightedSchedulingAndConfiguration(t *testing.T) {
	weights := map[BackendID]int{"a": 5, "b": 1, "c": 0}
	w, err := NewWeightedRoundRobin(weights)

	if err != nil {
		t.Fatal(err)
	}

	weights["a"] = 0
	c := pool(t, "a", "b", "c")
	counts := make(map[BackendID]int)
	sequence := ""

	for range 6 {
		s := pick(t, w, c, "")
		counts[s.BackendID]++
		sequence += string(s.BackendID)
	}

	if counts["a"] != 5 || counts["b"] != 1 || counts["c"] != 0 {
		t.Fatalf("weights ignored: %v", counts)
	}

	if sequence == "aaaaab" {
		t.Fatal("weighted scheduling still produces contiguous bursts")
	}

	if pick(t, w, pool(t, "b"), "").BackendID != "b" {
		t.Fatal("did not adapt to eligibility")
	}

	_, err = w.Pick(context.Background(), Input{}, pool(t, "c"))

	if !errors.Is(err, ErrNoBackend) {
		t.Fatalf("zero weight backend: %v", err)
	}

	_, err = w.Pick(context.Background(), Input{}, pool(t, "unknown"))

	if !errors.Is(err, ErrInvalidCandidates) {
		t.Fatalf("unknown backend: %v", err)
	}

	for _, invalid := range []map[BackendID]int{nil, {"a": 0}, {"a": -1}, {"": 1}} {
		_, err = NewWeightedRoundRobin(invalid)

		if err == nil {
			t.Fatalf("accepted invalid weights %v", invalid)
		}

	}

}

func TestLeastConnectionsScansEveryBackend(t *testing.T) {
	l := NewLeastConnections()
	a := pool(t, "a")
	b := pool(t, "b")
	selections := []Selection{pick(t, l, a, ""), pick(t, l, a, ""), pick(t, l, b, "")}
	s := pick(t, l, pool(t, "a", "b", "c"), "")

	if s.BackendID != "c" {
		t.Fatalf("expected idle c, got %s", s.BackendID)
	}

	finish(s)

	for _, held := range selections {
		finish(held)
	}

	if len(l.active) != 0 {
		t.Fatalf("reservations leaked: %v", l.active)
	}

}

func TestLoadAwareStrategiesSpreadCelebrityRequests(t *testing.T) {
	c := pool(t, "a", "b")

	for name, picker := range map[string]Picker{"least-connections": NewLeastConnections(), "power-of-two": NewPowerOfTwo()} {
		t.Run(name, func(t *testing.T) {
			var held []Selection
			var mu sync.Mutex
			var workers sync.WaitGroup
			counts := make(map[BackendID]int)

			for range 100 {
				workers.Add(1)
				go func() {
					defer workers.Done()
					s := pick(t, picker, c, "celebrity")
					mu.Lock()
					held = append(held, s)
					counts[s.BackendID]++
					mu.Unlock()
				}()
			}

			workers.Wait()

			if counts["a"] != 50 || counts["b"] != 50 {
				t.Fatalf("non-atomic reservation or repeated two-choice sample: %v", counts)
			}

			for _, s := range held {
				finish(s)
				finish(s)
			}

			single := pick(t, picker, pool(t, "a"), "celebrity")
			finish(single)
		})
	}

}

func TestLatencyScoresLoadAndPenalizesFastFailures(t *testing.T) {
	l, err := NewLeastResponseTime(LatencyOptions{Smoothing: 1})

	if err != nil {
		t.Fatal(err)
	}

	fast := pick(t, l, pool(t, "a"), "")
	fast.Done(Result{Duration: time.Millisecond})
	slow := pick(t, l, pool(t, "b"), "")
	slow.Done(Result{Duration: 100 * time.Millisecond})
	held := pick(t, l, pool(t, "a"), "")
	chosen := pick(t, l, pool(t, "a", "b"), "")

	if chosen.BackendID != "a" {
		t.Fatal("a small amount of load should not override a 100x latency difference")
	}

	chosen.Done(Result{Duration: time.Microsecond, StatusCode: 503})
	chosen.Done(Result{})
	held.Done(Result{Err: context.Canceled})
	next := pick(t, l, pool(t, "a", "b"), "")

	if next.BackendID != "b" {
		t.Fatal("fast 503 was rewarded as low latency")
	}

	finish(next)

	if l.states["a"].active != 0 || l.states["b"].active != 0 {
		t.Fatal("latency reservations leaked or double released")
	}

	// Old penalties must not permanently exclude a recovered backend.
	l.states["a"].lastSample = time.Now().Add(-time.Hour)
	l.states["b"].ewma = float64(100 * time.Millisecond)
	l.states["b"].lastSample = time.Now()
	recovered := pick(t, l, pool(t, "a", "b"), "")

	if recovered.BackendID != "a" {
		t.Fatal("old latency penalty never decays")
	}

	finish(recovered)

	for _, options := range []LatencyOptions{{Smoothing: math.NaN()}, {Smoothing: 2}, {InitialLatency: -1}, {Decay: -1}, {InitialLatency: time.Second, FailurePenalty: time.Millisecond}} {
		_, err = NewLeastResponseTime(options)

		if err == nil {
			t.Fatalf("accepted invalid latency options %+v", options)
		}

	}

}

func TestResourceRoutingRejectsUntrustworthyMetrics(t *testing.T) {
	now := time.Now()
	samples := map[BackendID]LoadSample{
		"a": {Value: 0, UpdatedAt: now.Add(-time.Hour)},
		"b": {Value: 10, UpdatedAt: now},
		"c": {Value: math.NaN(), UpdatedAt: now},
		"d": {Value: math.Inf(1), UpdatedAt: now},
		"e": {Value: -1, UpdatedAt: now},
		"f": {Value: 0, UpdatedAt: now.Add(time.Hour)},
	}
	r, err := NewResourceBased(func(_ context.Context, id BackendID) (LoadSample, error) {

		return samples[id], nil
	}, time.Minute)

	if err != nil {
		t.Fatal(err)
	}

	if pick(t, r, pool(t, "a", "b", "c", "d", "e", "f"), "").BackendID != "b" {
		t.Fatal("used invalid or stale metrics")
	}

	_, err = r.Pick(context.Background(), Input{}, pool(t, "a", "c", "d", "e", "f"))

	if !errors.Is(err, ErrNoBackend) {
		t.Fatalf("all invalid metrics: %v", err)
	}

	_, err = NewResourceBased(nil, time.Second)

	if err == nil {
		t.Fatal("accepted nil metrics provider")
	}

	_, err = NewResourceBased(r.load, 0)

	if err == nil {
		t.Fatal("accepted unbounded sample age")
	}

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	canceling, err := NewResourceBased(func(context.Context, BackendID) (LoadSample, error) {
		cancel()

		return LoadSample{Value: 0, UpdatedAt: time.Now()}, nil
	}, time.Minute)

	if err != nil {
		t.Fatal(err)
	}

	_, err = canceling.Pick(ctx, Input{}, pool(t, "a"))

	if !errors.Is(err, context.Canceled) {
		t.Fatalf("cancellation during final metrics read: %v", err)
	}

}

func TestHashingDistributionAffinityAndMembership(t *testing.T) {
	c := pool(t, "a", "b", "c", "d")
	ring, err := NewConsistentHash(c, 128)

	if err != nil {
		t.Fatal(err)
	}

	expanded := pool(t, "a", "b", "c", "d", "e")
	larger, err := NewConsistentHash(expanded, 128)

	if err != nil {
		t.Fatal(err)
	}

	reordered, err := NewConsistentHash(pool(t, "d", "c", "b", "a"), 128)

	if err != nil {
		t.Fatal(err)
	}

	counts := make(map[BackendID]int)
	moved := 0

	for i := range 10000 {
		key := fmt.Sprintf("user:%d", i)
		original := pick(t, ring, c, key).BackendID
		counts[original]++

		if pick(t, reordered, c, key).BackendID != original {
			t.Fatal("reordering changed ownership")
		}

		newOwner := pick(t, larger, expanded, key).BackendID

		if original != newOwner {
			moved++

			if newOwner != "e" {
				t.Fatal("adding e moved a key between surviving backends")
			}

		}

	}

	for id, count := range counts {

		if count < 1500 || count > 3500 {
			t.Fatalf("hash distribution is badly imbalanced: %s=%d, all=%v", id, count, counts)
		}

	}

	if len(counts) != 4 || moved < 1000 || moved > 3000 {
		t.Fatalf("unexpected distribution/remapping: counts=%v moved=%d", counts, moved)
	}

	for _, picker := range []Picker{ring, NewSimpleHash()} {
		owner := pick(t, picker, c, "celebrity").BackendID

		for range 100 {

			if pick(t, picker, c, "celebrity").BackendID != owner {
				t.Fatal("hashing unexpectedly split a hot key")
			}

		}

		_, err = picker.Pick(context.Background(), Input{}, c)

		if !errors.Is(err, ErrMissingKey) {
			t.Fatalf("missing key: %v", err)
		}

		if pick(t, picker, pool(t, "d"), "celebrity").BackendID != "d" {
			t.Fatal("did not skip unhealthy owners")
		}

	}

	_, err = ring.Pick(context.Background(), Input{Key: "key"}, pool(t, "unknown"))

	if !errors.Is(err, ErrInvalidCandidates) {
		t.Fatalf("unknown ring member: %v", err)
	}

	_, err = NewConsistentHash(Candidates{}, 128)

	if err == nil {
		t.Fatal("accepted empty ring")
	}

	_, err = NewConsistentHash(c, 0)

	if err == nil {
		t.Fatal("accepted zero virtual nodes")
	}

}

func TestKeyRangeBoundariesAndUnavailableOwner(t *testing.T) {
	ranges := []Range{{UpperBound: "m", BackendID: "a"}, {BackendID: "b"}}
	k, err := NewKeyRange(ranges)

	if err != nil {
		t.Fatal(err)
	}

	ranges[0].BackendID = "b"
	c := pool(t, "a", "b")

	for key, want := range map[string]BackendID{"a": "a", "m": "a", "n": "b", "zz": "b"} {
		got := pick(t, k, c, key).BackendID

		if got != want {
			t.Fatalf("%q: got %s want %s", key, got, want)
		}

	}

	_, err = k.Pick(context.Background(), Input{Key: "a"}, pool(t, "b"))

	if !errors.Is(err, ErrNoBackend) {
		t.Fatalf("unavailable shard owner: %v", err)
	}

	finite, err := NewKeyRange([]Range{{UpperBound: "m", BackendID: "a"}})

	if err != nil {
		t.Fatal(err)
	}

	_, err = finite.Pick(context.Background(), Input{Key: "z"}, c)

	if !errors.Is(err, ErrNoBackend) {
		t.Fatalf("out-of-range key was silently routed: %v", err)
	}

	for _, invalid := range [][]Range{nil, {{BackendID: "a"}, {UpperBound: "z", BackendID: "b"}}, {{UpperBound: "z", BackendID: "a"}, {UpperBound: "m", BackendID: "b"}}, {{UpperBound: "m"}}} {
		_, err = NewKeyRange(invalid)

		if err == nil {
			t.Fatalf("accepted invalid ranges %v", invalid)
		}

	}

}

func TestCarbonAwarePicksLowestEmissions(t *testing.T) {
	// a: 2 Wh at 450 g/kWh = 0.9 g, b: 0.3 Wh at 400 g/kWh = 0.12 g, c: 1 Wh at 100 g/kWh = 0.1 g.
	p, err := NewCarbonAware(map[BackendID]CarbonProfile{
		"a": {EnergyWh: 2, IntensityGPerKWh: 450}, "b": {EnergyWh: 0.3, IntensityGPerKWh: 400}, "c": {EnergyWh: 1, IntensityGPerKWh: 100},
	})

	if err != nil {
		t.Fatal(err)
	}

	s := pick(t, p, pool(t, "a", "b", "c"), "")

	if s.BackendID != "c" || s.Done != nil {
		t.Fatalf("got %q (reservation %v), want c without a reservation", s.BackendID, s.Done != nil)
	}

	if pick(t, p, pool(t, "a", "b"), "").BackendID != "b" {
		t.Fatal("lowest-emission eligible backend was not chosen after c became ineligible")
	}

	_, err = p.Pick(context.Background(), Input{}, pool(t, "a", "unknown"))

	if !errors.Is(err, ErrInvalidCandidates) {
		t.Fatalf("unknown backend: %v", err)
	}

	if math.Abs(p.profiles["c"].GramsCO2e()-0.1) > 1e-12 {
		t.Fatalf("1 Wh at 100 g/kWh = %v g, want 0.1 g", p.profiles["c"].GramsCO2e())
	}

}

func TestCarbonAwareTiesRotateAndConfiguration(t *testing.T) {
	p, err := NewCarbonAware(map[BackendID]CarbonProfile{"a": {EnergyWh: 1, IntensityGPerKWh: 200}, "b": {EnergyWh: 2, IntensityGPerKWh: 100}})

	if err != nil {
		t.Fatal(err)
	}

	counts := map[BackendID]int{}
	c := pool(t, "a", "b")

	for range 10 {
		counts[pick(t, p, c, "").BackendID]++
	}

	if counts["a"] != 5 || counts["b"] != 5 {
		t.Fatalf("equal-emission backends should alternate, got %v", counts)
	}

	for _, invalid := range []map[BackendID]CarbonProfile{
		nil,
		{"": {EnergyWh: 1, IntensityGPerKWh: 1}},
		{"a": {EnergyWh: -1, IntensityGPerKWh: 1}},
		{"a": {EnergyWh: 1, IntensityGPerKWh: -1}},
		{"a": {EnergyWh: math.NaN(), IntensityGPerKWh: 1}},
		{"a": {EnergyWh: 1, IntensityGPerKWh: math.Inf(1)}},
	} {
		_, err = NewCarbonAware(invalid)

		if err == nil {
			t.Fatalf("accepted invalid profiles %v", invalid)
		}

	}

}
