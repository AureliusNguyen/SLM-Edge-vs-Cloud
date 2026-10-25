// Use when: Validate proxy integration after changing rewriting, eligibility, or completion handling.
// Example: Tests cover a failed POST attempt, a panicking transport, and all-down hash routing.
// Pros: Local HTTP servers exercise actual forwarding while injected transports make failures deterministic.
// Cons: Loopback tests require local socket access and do not model deployment-specific network partitions.
package loadbalancer

import (
	"context"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/AureliusNguyen/SLM-Edge-vs-Cloud/Load-Balancer/strategy"
)

type pickerFunc func(context.Context, strategy.Input, strategy.Candidates) (strategy.Selection, error)

func (f pickerFunc) Pick(ctx context.Context, input strategy.Input, c strategy.Candidates) (strategy.Selection, error) {

	return f(ctx, input, c)
}

type transportFunc func(*http.Request) (*http.Response, error)

func (f transportFunc) RoundTrip(r *http.Request) (*http.Response, error) {

	return f(r)
}

func newBalancer(t *testing.T, config Config) *Balancer {
	t.Helper()
	b, err := New(config)

	if err != nil {
		t.Fatal(err)
	}

	t.Cleanup(b.CloseIdleConnections)

	return b
}

func TestProxyPreservesTargetAndRequestSemantics(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, err := io.ReadAll(r.Body)

		if err != nil {
			t.Error(err)
		}

		if r.Method != http.MethodPost || string(body) != "payload" {
			t.Errorf("lost method/body: %s %q", r.Method, body)
		}

		if r.URL.Path != "/base/api/item" || r.URL.Query().Get("fixed") != "1" || r.URL.Query().Get("q") != "2" {
			t.Errorf("lost base path or query: %s", r.URL)
		}

		if r.Header.Get("X-Forwarded-For") != "192.0.2.1" {
			t.Errorf("spoofed forwarding chain: %q", r.Header.Get("X-Forwarded-For"))
		}

		if r.Header.Get("X-Forwarded-Host") != "client.example" || r.Header.Get("X-Forwarded-Proto") != "http" {
			t.Errorf("incorrect forwarding headers: %v", r.Header)
		}

		if r.Host == "client.example" {
			t.Error("upstream host was not rewritten")
		}

		w.WriteHeader(http.StatusCreated)
		_, _ = io.WriteString(w, "created")
	}))

	defer upstream.Close()
	var observed strategy.Result

	b := newBalancer(t, Config{
		Backends: []Backend{{ID: "a", URL: upstream.URL + "/base?fixed=1"}},
		Picker:   strategy.NewRoundRobin(),
		OnResult: func(_ context.Context, id strategy.BackendID, result strategy.Result) {

			if id != "a" {
				t.Errorf("observed wrong backend: %s", id)
			}

			observed = result
		},
	})

	r := httptest.NewRequest(http.MethodPost, "http://client.example/api/item?q=2", strings.NewReader("payload"))
	r.Header.Set("X-Forwarded-For", "spoofed")
	r.Header.Set("X-Forwarded-Host", "spoofed")
	r.Header.Set("Forwarded", "for=spoofed")
	w := httptest.NewRecorder()
	b.ServeHTTP(w, r)

	if w.Code != http.StatusCreated || w.Body.String() != "created" {
		t.Fatalf("unexpected response %d %s", w.Code, w.Body.String())
	}

	if observed.Err != nil || observed.StatusCode != http.StatusCreated || observed.Duration <= 0 {
		t.Fatalf("invalid result: %+v", observed)
	}

}

func TestHealthFilteringAndAllDownHashSelection(t *testing.T) {
	var ready atomic.Bool
	var calls atomic.Int64
	b := newBalancer(t, Config{
		Backends: []Backend{{ID: "a", URL: "http://backend.invalid", Ready: ready.Load}},
		Picker:   strategy.NewSimpleHash(),
		Transport: transportFunc(func(r *http.Request) (*http.Response, error) {
			calls.Add(1)

			return &http.Response{StatusCode: 200, Header: make(http.Header), Body: io.NopCloser(strings.NewReader("ok"))}, nil
		}),
	})
	done := make(chan *httptest.ResponseRecorder, 1)
	go func() {
		w := httptest.NewRecorder()
		b.ServeHTTP(w, httptest.NewRequest(http.MethodGet, "/celebrity", nil))
		done <- w
	}()

	select {
	case w := <-done:

		if w.Code != http.StatusServiceUnavailable {
			t.Fatalf("all down: %d", w.Code)
		}

	case <-time.After(time.Second):
		t.Fatal("all-down hash selection did not terminate")
	}
	ready.Store(true)
	w := httptest.NewRecorder()
	b.ServeHTTP(w, httptest.NewRequest(http.MethodGet, "/celebrity", nil))

	if w.Code != 200 || calls.Load() != 1 {
		t.Fatalf("recovery failed: status=%d calls=%d", w.Code, calls.Load())
	}

}

func TestInvalidPickerSelectionIsReleased(t *testing.T) {

	for _, selected := range []strategy.BackendID{"unknown", "unready"} {
		t.Run(string(selected), func(t *testing.T) {
			completed := 0
			b := newBalancer(t, Config{
				Backends: []Backend{{ID: "ready", URL: "http://ready.invalid"}, {ID: "unready", URL: "http://unready.invalid", Ready: func() bool {
					return false
				}}},
				Picker: pickerFunc(func(context.Context, strategy.Input, strategy.Candidates) (strategy.Selection, error) {
					return strategy.Selection{BackendID: selected, Done: func(result strategy.Result) {
						completed++

						if !errors.Is(result.Err, ErrInvalidSelection) {
							t.Errorf("missing invalid-selection error: %v", result.Err)
						}

					}}, nil
				}),
			})

			w := httptest.NewRecorder()
			b.ServeHTTP(w, httptest.NewRequest(http.MethodGet, "/", nil))

			if w.Code != 503 || completed != 1 {
				t.Fatalf("invalid selection: status=%d completed=%d", w.Code, completed)
			}

		})
	}

}

func TestFailureAndPanicAlwaysReleaseWithoutRetrying(t *testing.T) {
	for _, mode := range []string{"transport", "5xx", "panic", "cancel"} {
		t.Run(mode, func(t *testing.T) {
			calls := 0
			completed := 0
			observed := 0
			var result strategy.Result
			ctx, cancel := context.WithCancel(context.Background())
			defer cancel()
			b := newBalancer(t, Config{
				Backends: []Backend{{ID: "a", URL: "http://backend.invalid"}},
				Picker: pickerFunc(func(context.Context, strategy.Input, strategy.Candidates) (strategy.Selection, error) {

					return strategy.Selection{BackendID: "a", Done: func(r strategy.Result) {
						completed++
						result = r
					}}, nil
				}),
				OnResult: func(context.Context, strategy.BackendID, strategy.Result) {

					if completed != 1 {
						t.Error("telemetry ran before releasing reservation")
					}

					observed++
				},
				Transport: transportFunc(func(r *http.Request) (*http.Response, error) {
					calls++

					if mode == "panic" {
						panic("transport panic")
					}

					if mode == "cancel" {
						cancel()

						return nil, r.Context().Err()
					}

					if mode == "transport" {

						return nil, errors.New("backend offline")
					}

					return &http.Response{StatusCode: 503, Header: make(http.Header), Body: io.NopCloser(strings.NewReader("unavailable"))}, nil
				}),
			})

			w := httptest.NewRecorder()
			panicked := false
			func() {
				defer func() {

					if recover() != nil {
						panicked = true
					}

				}()
				b.ServeHTTP(w, httptest.NewRequest(http.MethodPost, "/write", strings.NewReader("non-idempotent")).WithContext(ctx))
			}()

			if calls != 1 || completed != 1 || observed != 1 || result.Err == nil {
				t.Fatalf("lost accounting or retried POST: calls=%d completed=%d observed=%d result=%+v", calls, completed, observed, result)
			}

			if panicked != (mode == "panic") {
				t.Fatalf("panic was swallowed or introduced: %v", panicked)
			}

			if mode == "panic" && !errors.Is(result.Err, ErrRequestAborted) {
				t.Fatalf("panic outcome: %v", result.Err)
			}

			if mode == "cancel" && !errors.Is(result.Err, context.Canceled) {
				t.Fatalf("cancellation outcome: %v", result.Err)
			}

		})
	}

}

func TestExplicitKeyExtractionAndNoImplicitQueryOverride(t *testing.T) {
	key := ""
	b := newBalancer(t, Config{
		Backends: []Backend{{ID: "a", URL: "http://backend.invalid"}},
		Picker: pickerFunc(func(_ context.Context, input strategy.Input, _ strategy.Candidates) (strategy.Selection, error) {
			key = input.Key

			return strategy.Selection{}, strategy.ErrNoBackend
		}),
	})

	b.ServeHTTP(httptest.NewRecorder(), httptest.NewRequest(http.MethodGet, "/path?key=attacker", nil))

	if key != "/path" {
		t.Fatalf("query unexpectedly overrode routing: %q", key)
	}

	b.key = func(r *http.Request) (string, error) {

		return r.Header.Get("X-Tenant-ID"), nil
	}
	r := httptest.NewRequest(http.MethodGet, "/path", nil)
	r.Header.Set("X-Tenant-ID", "tenant-42")
	b.ServeHTTP(httptest.NewRecorder(), r)

	if key != "tenant-42" {
		t.Fatalf("custom extractor ignored: %q", key)
	}

	b.key = func(*http.Request) (string, error) {

		return "", errors.New("missing tenant")
	}

	w := httptest.NewRecorder()
	b.ServeHTTP(w, r)

	if w.Code != 400 {
		t.Fatalf("invalid key status: %d", w.Code)
	}

}

func TestBalancerConcurrentWithChangingReadiness(t *testing.T) {
	var ready atomic.Bool
	ready.Store(true)
	var attempts atomic.Int64
	b := newBalancer(t, Config{
		Backends: []Backend{{ID: "a", URL: "http://a.invalid"}, {ID: "b", URL: "http://b.invalid", Ready: ready.Load}},
		Picker:   strategy.NewPowerOfTwo(),
		Transport: transportFunc(func(*http.Request) (*http.Response, error) {

			return &http.Response{StatusCode: 200, Header: make(http.Header), Body: io.NopCloser(strings.NewReader("ok"))}, nil
		}),
		OnResult: func(context.Context, strategy.BackendID, strategy.Result) { attempts.Add(1) },
	})
	var workers sync.WaitGroup

	for range 12 {
		workers.Add(1)
		go func() {
			defer workers.Done()

			for i := range 64 {
				ready.Store(i%2 == 0)
				w := httptest.NewRecorder()
				b.ServeHTTP(w, httptest.NewRequest(http.MethodGet, "/", nil))

				if w.Code != 200 {
					t.Errorf("request failed: %d", w.Code)
				}

			}

		}()
	}

	workers.Wait()

	if attempts.Load() != 12*64 {
		t.Fatalf("lost results: %d", attempts.Load())
	}

}

func TestConfigValidationAndCopies(t *testing.T) {

	for _, backends := range [][]Backend{nil, {{ID: "", URL: "http://a"}}, {{ID: "a", URL: "http://a"}, {ID: "a", URL: "http://b"}}, {{ID: "a", URL: "/relative"}}, {{ID: "a", URL: "ftp://a"}}, {{ID: "a", URL: "http://a/#fragment"}}, {{ID: "a", URL: "http://a:bad"}}} {
		_, err := New(Config{Backends: backends, Picker: strategy.NewRoundRobin()})

		if err == nil {
			t.Fatalf("accepted invalid backends: %v", backends)
		}

	}

	_, err := New(Config{Backends: []Backend{{ID: "a", URL: "http://a"}}})

	if err == nil {
		t.Fatal("accepted nil picker")
	}

	backends := []Backend{{ID: "a", URL: "http://a"}}
	b := newBalancer(t, Config{Backends: backends, Picker: strategy.NewRoundRobin()})
	backends[0].ID = "changed"

	if !b.all.Contains("a") || b.all.Contains("changed") {
		t.Fatal("caller mutation changed backend pool")
	}

}
