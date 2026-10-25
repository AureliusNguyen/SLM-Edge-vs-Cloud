// Use when: Probe an API replica whose /healthz returns 503 while its database is unavailable.
// Example: Attach checker.Ready to Backend.Ready and run checker.Run with an application lifecycle context.
// Pros: Bounded probes keep network checks out of request selection and recover on later success.
// Cons: A single failing probe removes a node immediately and custom hysteresis needs a different readiness signal.
package loadbalancer

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net/http"
	"sync/atomic"
	"time"
)

// HTTPHealthCheck is an optional active readiness probe. It starts unready and
// accepts only 2xx responses from the configured URL. Redirects are not followed.
// It is independent of the routing strategy and owns no listener.
type HTTPHealthCheck struct {
	url      string
	interval time.Duration
	timeout  time.Duration
	client   *http.Client
	ready    atomic.Bool
}

func NewHTTPHealthCheck(target string, interval, timeout time.Duration) (*HTTPHealthCheck, error) {
	_, err := parseTarget(target)

	if err != nil {

		return nil, err
	}

	if interval <= 0 || timeout <= 0 {

		return nil, errors.New("health-check interval and timeout must be positive")
	}

	return &HTTPHealthCheck{
		url: target, interval: interval, timeout: timeout,
		client: &http.Client{Transport: NewTransport(), CheckRedirect: func(*http.Request, []*http.Request) error {

			return http.ErrUseLastResponse
		}},
	}, nil
}

func (h *HTTPHealthCheck) Ready() bool {

	return h.ready.Load()
}

// Check performs one bounded probe and updates readiness. Do not overlap Check
// with Run: concurrent probes could publish results out of chronological order.
func (h *HTTPHealthCheck) Check(ctx context.Context) error {
	ctx, cancel := context.WithTimeout(ctx, h.timeout)
	defer cancel()
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, h.url, nil)

	if err != nil {
		h.ready.Store(false)

		return err
	}

	response, err := h.client.Do(request)

	if err != nil {
		h.ready.Store(false)

		return err
	}

	defer response.Body.Close()
	_, readErr := io.Copy(io.Discard, io.LimitReader(response.Body, 4096))

	if readErr != nil {
		h.ready.Store(false)

		return readErr
	}

	if response.StatusCode < 200 || response.StatusCode >= 300 {
		h.ready.Store(false)

		return fmt.Errorf("health endpoint returned HTTP %d", response.StatusCode)
	}

	contextErr := ctx.Err()

	if contextErr != nil {
		h.ready.Store(false)

		return contextErr
	}

	h.ready.Store(true)

	return nil
}

// Run probes immediately, then periodically until cancellation. Call once per
// checker. Readiness becomes false and idle probe connections close on exit.
func (h *HTTPHealthCheck) Run(ctx context.Context) {
	defer h.ready.Store(false)
	defer h.client.CloseIdleConnections()
	ticker := time.NewTicker(h.interval)
	defer ticker.Stop()

	for {
		_ = h.Check(ctx)
		select {
		case <-ctx.Done():

			return
		case <-ticker.C:
		}
	}

}
