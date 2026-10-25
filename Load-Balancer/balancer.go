// Use when: Embed a proxy under an application-owned HTTP server, such as two stateless API replicas.
// Example: Use Config.Key to route a tenant cache and Backend.Ready to exclude a draining replica.
// Pros: Preserves HTTP rewriting and releases reservations on errors and panics.
// Cons: One attempt per request and immutable membership require application-managed retry and rollout policies.
//
// Package loadbalancer provides an HTTP reverse proxy with pluggable,
// transport-independent routing strategies. It does not own an HTTP listener.
package loadbalancer

import (
	"context"
	"errors"
	"fmt"
	"net"
	"net/http"
	"net/http/httputil"
	"net/url"
	"time"

	"github.com/AureliusNguyen/SLM-Edge-vs-Cloud/Load-Balancer/strategy"
)

var (
	ErrInvalidSelection = errors.New("picker selected an ineligible backend")
	ErrRequestAborted   = errors.New("proxy attempt aborted")
)

// Backend identifies one upstream. ID must stay stable across reordering and
// membership changes. Ready, if provided, must be fast and concurrency-safe.
// nil explicitly means always eligible. Use a cached health signal, not an RPC.
type Backend struct {
	ID    strategy.BackendID
	URL   string
	Ready func() bool
}

type KeyFunc func(*http.Request) (string, error)

type Config struct {
	Backends []Backend
	Picker   strategy.Picker
	// Key defaults to URL.Path. Query parameters never override routing implicitly.
	Key KeyFunc
	// Transport must be concurrency-safe. Nil uses NewTransport.
	Transport http.RoundTripper
	// OnResult is optional telemetry, invoked after releasing the reservation.
	// It must be fast and concurrency-safe. It receives no event for failed picks.
	OnResult func(context.Context, strategy.BackendID, strategy.Result)
}

type upstream struct {
	ready func() bool
	proxy *httputil.ReverseProxy
}

// Balancer is an http.Handler safe for concurrent use. Configuration and
// membership are immutable. Construct a new handler/picker to change membership.
type Balancer struct {
	backends     map[strategy.BackendID]upstream
	all          strategy.Candidates
	picker       strategy.Picker
	key          KeyFunc
	transport    http.RoundTripper
	onResult     func(context.Context, strategy.BackendID, strategy.Result)
	hasReadiness bool
}

var _ http.Handler = (*Balancer)(nil)

type attemptKey struct{}
type attempt struct{ result strategy.Result }

type observedTransport struct {
	base http.RoundTripper
}

func (t observedTransport) RoundTrip(request *http.Request) (*http.Response, error) {
	response, err := t.base.RoundTrip(request)
	a, ok := request.Context().Value(attemptKey{}).(*attempt)

	if ok && response != nil {
		a.result.StatusCode = response.StatusCode

		if response.StatusCode >= 500 {
			a.result.Err = fmt.Errorf("upstream returned HTTP %d", response.StatusCode)
		}

	}

	return response, err
}

func New(config Config) (*Balancer, error) {

	if config.Picker == nil {

		return nil, errors.New("a picker is required")
	}

	if len(config.Backends) == 0 {

		return nil, errors.New("at least one backend is required")
	}

	ids := make([]strategy.BackendID, len(config.Backends))
	targets := make([]*url.URL, len(config.Backends))

	for i, backend := range config.Backends {
		ids[i] = backend.ID
		target, err := parseTarget(backend.URL)

		if err != nil {

			return nil, fmt.Errorf("backend %q: %w", backend.ID, err)
		}

		targets[i] = target
	}

	all, err := strategy.NewCandidates(ids...)

	if err != nil {

		return nil, err
	}

	transport := config.Transport

	if transport == nil {
		transport = NewTransport()
	}

	key := config.Key

	if key == nil {
		key = func(r *http.Request) (string, error) {

			return r.URL.Path, nil
		}
	}

	b := &Balancer{
		backends: make(map[strategy.BackendID]upstream, len(config.Backends)),
		all:      all, picker: config.Picker, key: key, transport: transport, onResult: config.OnResult,
	}

	for i, backend := range config.Backends {
		target := targets[i]

		if backend.Ready != nil {
			b.hasReadiness = true
		}

		proxy := &httputil.ReverseProxy{
			Transport: observedTransport{base: transport},
			Rewrite: func(r *httputil.ProxyRequest) {
				r.SetURL(target)
				r.SetXForwarded()
			},
			ErrorHandler: func(w http.ResponseWriter, r *http.Request, err error) {
				a, ok := r.Context().Value(attemptKey{}).(*attempt)

				if ok {
					a.result.Err = err
					a.result.StatusCode = http.StatusBadGateway
				}

				http.Error(w, "Bad gateway", http.StatusBadGateway)
			},
		}
		b.backends[backend.ID] = upstream{ready: backend.Ready, proxy: proxy}
	}

	return b, nil
}

func parseTarget(raw string) (*url.URL, error) {
	u, err := url.Parse(raw)

	if err != nil {

		return nil, fmt.Errorf("invalid upstream URL: %w", err)
	}

	if (u.Scheme != "http" && u.Scheme != "https") || u.Hostname() == "" || u.Opaque != "" || u.Fragment != "" {

		return nil, errors.New("upstream URL must be an absolute http(s) URL without a fragment")
	}

	return u, nil
}

// NewTransport supplies connection and response-header deadlines while allowing
// long response bodies/streams. Applications may customize it before first use.
func NewTransport() *http.Transport {

	return &http.Transport{
		Proxy:                 http.ProxyFromEnvironment,
		DialContext:           (&net.Dialer{Timeout: 5 * time.Second, KeepAlive: 30 * time.Second}).DialContext,
		ForceAttemptHTTP2:     true,
		MaxIdleConns:          100,
		MaxIdleConnsPerHost:   16,
		IdleConnTimeout:       90 * time.Second,
		TLSHandshakeTimeout:   5 * time.Second,
		ResponseHeaderTimeout: 30 * time.Second,
		ExpectContinueTimeout: time.Second,
	}
}

// CloseIdleConnections releases pooled idle upstream connections. If the caller
// supplied a shared transport, this also affects other users of that transport.
func (b *Balancer) CloseIdleConnections() {
	closer, ok := b.transport.(interface{ CloseIdleConnections() })

	if ok {
		closer.CloseIdleConnections()
	}

}

func (b *Balancer) eligible() strategy.Candidates {

	if !b.hasReadiness {

		return b.all
	}

	ids := make([]strategy.BackendID, 0, b.all.Len())

	for i := range b.all.Len() {
		id := b.all.At(i)
		ready := b.backends[id].ready

		if ready == nil || ready() {
			ids = append(ids, id)
		}

	}

	if len(ids) == b.all.Len() {

		return b.all
	}

	// IDs came from a validated immutable pool, so construction cannot fail.
	candidates, _ := strategy.NewCandidates(ids...)

	return candidates
}

func (b *Balancer) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	key, err := b.key(r)

	if err != nil {
		http.Error(w, "Invalid routing key", http.StatusBadRequest)

		return
	}

	candidates := b.eligible()
	selection, err := b.picker.Pick(r.Context(), strategy.Input{Key: key}, candidates)

	if err != nil {
		status := http.StatusServiceUnavailable

		if errors.Is(err, strategy.ErrMissingKey) {
			status = http.StatusBadRequest
		}

		http.Error(w, http.StatusText(status), status)

		return
	}

	a := &attempt{}
	start := time.Now()
	finished := false
	defer func() {
		a.result.Duration = time.Since(start)

		if !finished {
			a.result.Err = r.Context().Err()

			if a.result.Err == nil {
				a.result.Err = ErrRequestAborted
			}

		}

		if selection.Done != nil {
			selection.Done(a.result)
		}

		if b.onResult != nil {
			b.onResult(r.Context(), selection.BackendID, a.result)
		}

	}()
	backend, exists := b.backends[selection.BackendID]

	if !exists || !candidates.Contains(selection.BackendID) {
		a.result.Err = ErrInvalidSelection
		a.result.StatusCode = http.StatusServiceUnavailable
		finished = true
		http.Error(w, "No eligible backend", http.StatusServiceUnavailable)

		return
	}

	backend.proxy.ServeHTTP(w, r.WithContext(context.WithValue(r.Context(), attemptKey{}, a)))
	finished = true
}
