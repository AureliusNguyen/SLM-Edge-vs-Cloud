// Use when: Check readiness behavior after changing probe scheduling or response handling.
// Example: A replica changes from 200 to 503 to 204 and a redirect must never count as ready.
// Pros: Exercises recovery, deadlines, and cancellation against local HTTP endpoints.
// Cons: Single-process probes do not model clock skew or application-specific readiness dependencies.
package loadbalancer

import (
	"context"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
	"time"
)

func TestHealthCheckFailureRecoveryAndRedirects(t *testing.T) {
	var status atomic.Int64
	status.Store(200)
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Location", "/healthy")
		w.WriteHeader(int(status.Load()))
	}))
	defer upstream.Close()
	h, err := NewHTTPHealthCheck(upstream.URL, time.Second, time.Second)

	if err != nil {
		t.Fatal(err)
	}

	defer h.client.CloseIdleConnections()

	if h.Ready() {
		t.Fatal("unprobed backend was marked ready")
	}

	err = h.Check(context.Background())

	if err != nil || !h.Ready() {
		t.Fatalf("healthy endpoint rejected: %v", err)
	}

	for _, code := range []int64{503, 302} {
		status.Store(code)
		err = h.Check(context.Background())

		if err == nil || h.Ready() {
			t.Fatalf("unhealthy/redirect status %d accepted", code)
		}

	}

	status.Store(204)
	err = h.Check(context.Background())

	if err != nil || !h.Ready() {
		t.Fatalf("backend did not recover: %v", err)
	}

}

func TestHealthCheckDeadlineAndRunCancellation(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		<-r.Context().Done()
	}))
	defer upstream.Close()
	h, err := NewHTTPHealthCheck(upstream.URL, time.Hour, 50*time.Millisecond)

	if err != nil {
		t.Fatal(err)
	}

	defer h.client.CloseIdleConnections()
	err = h.Check(context.Background())

	if err == nil || h.Ready() {
		t.Fatal("hanging probe did not time out")
	}

	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan struct{})
	go func() {
		h.Run(ctx)
		close(done)
	}()
	cancel()
	select {
	case <-done:

		if h.Ready() {
			t.Fatal("stopped checker remained ready")
		}

	case <-time.After(time.Second):
		t.Fatal("cancellation did not stop probes")
	}
}

func TestHealthCheckValidatesConfiguration(t *testing.T) {

	for _, config := range []struct {
		url      string
		interval time.Duration
		timeout  time.Duration
	}{
		{"/relative", time.Second, time.Second},
		{"http://backend", 0, time.Second},
		{"http://backend", time.Second, 0},
	} {
		_, err := NewHTTPHealthCheck(config.url, config.interval, config.timeout)

		if err == nil {
			t.Fatalf("accepted invalid health configuration %+v", config)
		}

	}

}
