// Command gateway routes OpenAI-style chat requests to a local Ollama SLM or to
// Groq, choosing per request with a quality gate and the carbon-aware picker.
//
//	X-Task-Type: yesno | classify | math | ...   (what the request is)
//	X-Force-Tier: local | cloud                  (optional, for baselines; never falls back)
//
// Responses carry X-Route and X-Route-Reason. Every request is appended to a JSONL log.
package main

import (
	"bytes"
	"context"
	"encoding/json"
	"flag"
	"io"
	"log"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"

	loadbalancer "github.com/AureliusNguyen/SLM-Edge-vs-Cloud/Load-Balancer"
	"github.com/AureliusNguyen/SLM-Edge-vs-Cloud/Load-Balancer/strategy"
)

func main() {
	addr := flag.String("addr", ":8080", "listen address")
	ollamaURL := flag.String("ollama", "http://localhost:11434", "local Ollama base URL")
	localModel := flag.String("local-model", "llama3.2:3b", "Ollama model for the local tier")
	cloudModel := flag.String("cloud-model", "openai/gpt-oss-120b", "Groq model for the cloud tier")
	logPath := flag.String("log", "requests.jsonl", "JSONL request log")
	flag.Parse()
	// TrimSpace drops the \r a Windows-edited .env leaves behind.
	key := strings.TrimSpace(os.Getenv("GROQ_API_KEY"))

	if key == "" {
		log.Fatal("GROQ_API_KEY is not set")
	}

	check, err := loadbalancer.NewHTTPHealthCheck(*ollamaURL+"/", 2*time.Second, time.Second)

	if err != nil {
		log.Fatal(err)
	}

	go check.Run(context.Background())

	// CPU-only devices can take minutes to load the model and read a long prompt.
	localTransport := loadbalancer.NewTransport()
	localTransport.ResponseHeaderTimeout = 5 * time.Minute
	local, err := loadbalancer.New(loadbalancer.Config{
		Backends:  []loadbalancer.Backend{{ID: "ollama", URL: *ollamaURL, Ready: check.Ready}},
		Picker:    strategy.NewRoundRobin(),
		Transport: localTransport,
		OnResult:  logUpstreamError,
	})

	if err != nil {
		log.Fatal(err)
	}

	cloud, err := loadbalancer.New(loadbalancer.Config{
		Backends:  []loadbalancer.Backend{{ID: "groq", URL: "https://api.groq.com/openai"}},
		Picker:    strategy.NewRoundRobin(),
		Transport: bearer{key: key, base: loadbalancer.NewTransport()},
		OnResult:  logUpstreamError,
	})

	if err != nil {
		log.Fatal(err)
	}

	r, err := newRouter(defaultProfiles, map[strategy.BackendID]func() bool{
		"local": check.Ready,
		"cloud": func() bool { return true },
	})

	if err != nil {
		log.Fatal(err)
	}

	logFile, err := os.OpenFile(*logPath, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o644)

	if err != nil {
		log.Fatal(err)
	}

	defer logFile.Close()
	g := &gateway{
		router: r,
		tiers:  map[strategy.BackendID]http.Handler{"local": local, "cloud": cloud},
		models: map[strategy.BackendID]string{"local": *localModel, "cloud": *cloudModel},
		log:    json.NewEncoder(logFile),
	}
	mux := http.NewServeMux()
	mux.Handle("POST /v1/chat/completions", g)
	log.Printf("gateway on %s: local=%s (%s), cloud=groq (%s)", *addr, *ollamaURL, *localModel, *cloudModel)
	server := &http.Server{Addr: *addr, Handler: mux, ReadHeaderTimeout: 5 * time.Second}
	log.Fatal(server.ListenAndServe())
}

type gateway struct {
	router *router
	tiers  map[strategy.BackendID]http.Handler
	models map[strategy.BackendID]string
	mu     sync.Mutex
	log    *json.Encoder
}

func (g *gateway) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	start := time.Now()
	task, forced := r.Header.Get("X-Task-Type"), r.Header.Get("X-Force-Tier")
	status, tier, reason := g.serve(w, r, task, forced)
	g.mu.Lock()
	defer g.mu.Unlock()
	_ = g.log.Encode(map[string]any{
		"time": start.UTC().Format(time.RFC3339Nano), "task": task, "forced": forced,
		"tier": tier, "reason": reason, "status": status,
		"latency_ms": time.Since(start).Milliseconds(), "energy_j": nil, // not measured yet
	})
}

func (g *gateway) serve(w http.ResponseWriter, r *http.Request, task, forced string) (int, strategy.BackendID, string) {
	var body map[string]any
	err := json.NewDecoder(io.LimitReader(r.Body, 1<<20)).Decode(&body)

	if err != nil {
		http.Error(w, "invalid JSON body", http.StatusBadRequest)

		return http.StatusBadRequest, "", err.Error()
	}

	tier, reason, err := g.router.route(r.Context(), task, forced)

	if err != nil {
		status := http.StatusServiceUnavailable

		if forced != "" {
			status = http.StatusBadRequest
		}

		http.Error(w, err.Error(), status)

		return status, "", err.Error()
	}

	body["model"] = g.models[tier]

	if tier == "cloud" {
		// Groq rejects logprobs.
		delete(body, "logprobs")
		delete(body, "top_logprobs")
	}

	payload, _ := json.Marshal(body)
	r.Body = io.NopCloser(bytes.NewReader(payload))
	r.ContentLength = int64(len(payload))
	w.Header().Set("X-Route", string(tier))
	w.Header().Set("X-Route-Reason", reason)
	sw := &statusWriter{ResponseWriter: w, status: http.StatusOK}
	g.tiers[tier].ServeHTTP(sw, r)

	return sw.status, tier, reason
}

func logUpstreamError(_ context.Context, id strategy.BackendID, result strategy.Result) {

	if result.Err != nil {
		log.Printf("%s: %v", id, result.Err)
	}

}

// bearer adds the Groq API key and identifies the gateway as the client.
// Groq's Cloudflare front rejects some forwarded agents such as Python-urllib.
type bearer struct {
	key  string
	base http.RoundTripper
}

func (b bearer) RoundTrip(r *http.Request) (*http.Response, error) {
	r = r.Clone(r.Context())
	r.Header.Set("Authorization", "Bearer "+b.key)
	r.Header.Set("User-Agent", "slm-gateway/0.1")

	return b.base.RoundTrip(r)
}

type statusWriter struct {
	http.ResponseWriter
	status int
}

func (s *statusWriter) WriteHeader(code int) {
	s.status = code
	s.ResponseWriter.WriteHeader(code)
}

func (s *statusWriter) Unwrap() http.ResponseWriter {

	return s.ResponseWriter
}
