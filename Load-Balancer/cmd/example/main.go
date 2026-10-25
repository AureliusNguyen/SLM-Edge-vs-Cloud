// Use when: Run a local two-backend proxy with -strategy power-of-two and /healthz probes.
// Example: Change -key-header to a trusted tenant header when demonstrating cache affinity.
// Pros: Shows listener deadlines, stable identities, health lifecycles, and graceful signal shutdown.
// Cons: Example membership is fixed and workload-specific weights, metrics, and ranges belong in application configuration.
package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"log"
	"net/http"
	"net/url"
	"os"
	"os/signal"
	"strings"
	"sync"
	"syscall"
	"time"

	loadbalancer "github.com/AureliusNguyen/SLM-Edge-vs-Cloud/Load-Balancer"
	"github.com/AureliusNguyen/SLM-Edge-vs-Cloud/Load-Balancer/strategy"
)

func main() {
	err := run()

	if err != nil {
		log.Print(err)
		os.Exit(1)
	}

}

func run() error {
	addr := flag.String("addr", ":8000", "HTTP listen address")
	backendList := flag.String("backends", "a=http://127.0.0.1:9001,b=http://127.0.0.1:9002", "comma-separated stable-id=URL backends")
	name := flag.String("strategy", "power-of-two", "round-robin, random, least-connections, power-of-two, least-response-time, simple-hash, consistent-hash")
	keyHeader := flag.String("key-header", "", "header supplying the routing key. Default is URL path")
	healthPath := flag.String("health-path", "/healthz", "readiness endpoint path. Empty disables probes")
	flag.Parse()
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	var backends []loadbalancer.Backend
	var ids []strategy.BackendID
	var checks []*loadbalancer.HTTPHealthCheck

	for _, entry := range strings.Split(*backendList, ",") {
		parts := strings.SplitN(strings.TrimSpace(entry), "=", 2)

		if len(parts) != 2 {

			return fmt.Errorf("invalid backend %q: expected id=URL", entry)
		}

		backend := loadbalancer.Backend{ID: strategy.BackendID(parts[0]), URL: parts[1]}

		if *healthPath != "" {
			target, err := url.Parse(backend.URL)

			if err != nil {

				return err
			}

			target.Path, target.RawPath, target.RawQuery, target.Fragment = *healthPath, "", "", ""
			check, err := loadbalancer.NewHTTPHealthCheck(target.String(), 2*time.Second, time.Second)

			if err != nil {

				return err
			}

			backend.Ready = check.Ready
			checks = append(checks, check)
		}

		backends = append(backends, backend)
		ids = append(ids, backend.ID)
	}

	candidates, err := strategy.NewCandidates(ids...)

	if err != nil {

		return err
	}

	picker, err := makePicker(*name, candidates)

	if err != nil {

		return err
	}

	config := loadbalancer.Config{Backends: backends, Picker: picker}

	if *keyHeader != "" {
		config.Key = func(r *http.Request) (string, error) {
			key := r.Header.Get(*keyHeader)

			if key == "" {

				return "", errors.New("missing routing header")
			}

			return key, nil
		}
	}

	balancer, err := loadbalancer.New(config)

	if err != nil {

		return err
	}

	defer balancer.CloseIdleConnections()
	probeCtx, cancelProbes := context.WithCancel(ctx)
	var probes sync.WaitGroup

	for _, check := range checks {
		probes.Add(1)
		go func() {
			defer probes.Done()
			check.Run(probeCtx)
		}()
	}

	defer func() {
		cancelProbes()
		probes.Wait()
	}()
	server := &http.Server{
		Addr: *addr, Handler: balancer,
		ReadHeaderTimeout: 5 * time.Second, IdleTimeout: 60 * time.Second,
	}
	serveErr := make(chan error, 1)
	go func() { serveErr <- server.ListenAndServe() }()
	log.Printf("listening on %s using %s", *addr, *name)
	select {
	case err := <-serveErr:

		if errors.Is(err, http.ErrServerClosed) {

			return nil
		}

		return err
	case <-ctx.Done():
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		shutdownErr := server.Shutdown(shutdownCtx)

		if shutdownErr != nil {
			_ = server.Close()

			return shutdownErr
		}

		return nil
	}
}

func makePicker(name string, backends strategy.Candidates) (strategy.Picker, error) {
	switch name {
	case "round-robin":

		return strategy.NewRoundRobin(), nil
	case "random":

		return strategy.NewRandom(), nil
	case "least-connections":

		return strategy.NewLeastConnections(), nil
	case "power-of-two":

		return strategy.NewPowerOfTwo(), nil
	case "least-response-time":

		return strategy.NewLeastResponseTime(strategy.LatencyOptions{})
	case "simple-hash":

		return strategy.NewSimpleHash(), nil
	case "consistent-hash":

		return strategy.NewConsistentHash(backends, 128)
	default:

		return nil, fmt.Errorf("unknown strategy %q", name)
	}
}
