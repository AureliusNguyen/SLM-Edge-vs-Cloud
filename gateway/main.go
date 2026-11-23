// Command gateway routes OpenAI-style chat requests to a local Ollama SLM or to
// Groq, choosing per request with a quality gate and the carbon-aware picker.
//
//	X-Task-Type: yesno | classify | extract | math | ...   (what the request is)
//	X-Force-Tier: local | cloud                  (optional, for baselines; never falls back)
//
// -policy picks task-rule (default), rule+cascade or cascade; the cascades need -thresholds
// (rq3/results/thresholds_<model>.json from rq3_sim.py). -cloud-delay adds a fixed delay to every
// cloud request, to emulate a slower network. -power lhm,nvidia measures device energy per
// request (above idle) and logs it as energy_j next to the estimates.
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
	policy := flag.String("policy", policyTaskRule, "task-rule | rule+cascade | cascade")
	thresholdsPath := flag.String("thresholds", "", "cascade thresholds JSON from rq3_sim.py (needed by the cascades)")
	cloudDelay := flag.Duration("cloud-delay", 0, "extra delay added to every cloud request, e.g. 200ms")
	powerSpec := flag.String("power", "none", "measure device power: lhm, nvidia, lhm,nvidia or none")
	lhmURL := flag.String("lhm-url", "http://127.0.0.1:8085", "LibreHardwareMonitor web server")
	lhmSensor := flag.String("lhm-sensor", "CPU Package", "LibreHardwareMonitor power sensor name")
	idleFor := flag.Duration("idle", 15*time.Second, "how long to measure idle power at start-up")
	flag.Parse()
	var thresholds map[string]*float64

	switch *policy {
	case policyTaskRule:
	case policyRuleCascade, policyCascade:
		if *thresholdsPath == "" {
			log.Fatalf("-policy %s needs -thresholds", *policy)
		}

		var err error
		thresholds, err = loadThresholds(*thresholdsPath)

		if err != nil {
			log.Fatal(err)
		}
	default:
		log.Fatalf("unknown -policy %q", *policy)
	}

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
		Transport: delayed{delay: *cloudDelay, base: bearer{key: key, base: loadbalancer.NewTransport()}},
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
		router:     r,
		tiers:      map[strategy.BackendID]http.Handler{"local": local, "cloud": cloud},
		models:     map[strategy.BackendID]string{"local": *localModel, "cloud": *cloudModel},
		log:        json.NewEncoder(logFile),
		policy:     *policy,
		thresholds: thresholds,
	}

	if g.power, err = newPowerMeter(*powerSpec, *lhmURL, *lhmSensor, 200*time.Millisecond); err != nil {
		log.Fatal(err)
	}

	if g.power != nil {
		go g.power.run(context.Background())
		log.Printf("measuring idle power (%s) for %s, keep the machine quiet ...", g.power.names(), *idleFor)
		log.Printf("idle power %.1f W", g.power.measureIdle(*idleFor))
	}
	mux := http.NewServeMux()
	mux.Handle("POST /v1/chat/completions", g)
	log.Printf("gateway on %s: local=%s (%s), cloud=groq (%s), policy %s, cloud delay %s", *addr, *ollamaURL, *localModel, *cloudModel, *policy, *cloudDelay)
	server := &http.Server{Addr: *addr, Handler: mux, ReadHeaderTimeout: 5 * time.Second}
	log.Fatal(server.ListenAndServe())
}

type gateway struct {
	router *router
	tiers  map[strategy.BackendID]http.Handler
	models map[strategy.BackendID]string
	mu     sync.Mutex
	log    *json.Encoder

	policy     string
	thresholds map[string]*float64
	power      *powerMeter // nil: no power measurement
}

func (g *gateway) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	start := time.Now()
	task, forced := r.Header.Get("X-Task-Type"), r.Header.Get("X-Force-Tier")

	if g.power != nil {
		g.power.begin()
	}

	status, tier, reason, called := g.serve(w, r, task, forced)
	end := time.Now()

	if g.power != nil {
		g.power.end()
	}

	// Estimates from the per-tier profiles (route.go), summed over every tier the request
	// used: an escalated cascade pays for the local and the cloud answer.
	wh, grams, cloudGrams := 0.0, 0.0, 0.0

	for _, id := range called {
		wh += g.router.profiles[id].EnergyWh
		grams += g.router.profiles[id].GramsCO2e()

		if id == "cloud" {
			cloudGrams += g.router.profiles[id].GramsCO2e()
		}
	}

	entry := map[string]any{
		"time": start.UTC().Format(time.RFC3339Nano), "task": task, "forced": forced, "policy": g.policyName(),
		"tier": tier, "tiers_called": called, "reason": reason, "status": status,
		"latency_ms": end.Sub(start).Milliseconds(), "energy_wh_est": wh, "gco2e_est": grams,
		"energy_j": nil, "gco2e_measured": nil,
	}

	if g.power == nil {
		g.write(entry)

		return
	}

	// Measured device energy above idle needs the next power sample, so log after the reply.
	go func() {
		joules := g.power.extraJoules(start, end)
		entry["energy_j"] = joules
		entry["power_source"] = g.power.names()
		// device energy at the edge grid's intensity, plus the cloud estimate for cloud calls
		entry["gco2e_measured"] = joules/3600*g.router.profiles["local"].IntensityGPerKWh/1000 + cloudGrams
		g.write(entry)
	}()
}

func (g *gateway) write(entry map[string]any) {
	g.mu.Lock()
	defer g.mu.Unlock()
	_ = g.log.Encode(entry)
}

func (g *gateway) policyName() string {

	if g.policy == "" {
		return policyTaskRule
	}

	return g.policy
}

func (g *gateway) serve(w http.ResponseWriter, r *http.Request, task, forced string) (int, strategy.BackendID, string, []strategy.BackendID) {
	var body map[string]any
	err := json.NewDecoder(io.LimitReader(r.Body, 1<<20)).Decode(&body)

	if err != nil {
		http.Error(w, "invalid JSON body", http.StatusBadRequest)

		return http.StatusBadRequest, "", err.Error(), nil
	}

	tier, reason, err := g.router.route(r.Context(), task, forced)

	if err != nil {
		status := http.StatusServiceUnavailable

		if forced != "" {
			status = http.StatusBadRequest
		}

		http.Error(w, err.Error(), status)

		return status, "", err.Error(), nil
	}

	streaming, _ := body["stream"].(bool)

	if thr, ok := g.cascadeThreshold(task, tier, forced); ok && !streaming {
		return g.cascade(w, r, body, reason, thr)
	}

	if g.policy != policyTaskRule && g.policy != "" && forced == "" && tier == "local" && !streaming {
		if thr, ok := g.thresholds[task]; ok && thr == nil {
			// The threshold file says this task never reaches cloud-level accuracy locally.
			tier, reason = "cloud", reason+"; cascade: no threshold for "+task+", cloud only"
		}
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

	return sw.status, tier, reason, []strategy.BackendID{tier}
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

// delayed waits before every request, to emulate a slower network to the cloud.
type delayed struct {
	delay time.Duration
	base  http.RoundTripper
}

func (d delayed) RoundTrip(r *http.Request) (*http.Response, error) {

	if d.delay > 0 {
		select {
		case <-time.After(d.delay):
		case <-r.Context().Done():
			return nil, r.Context().Err()
		}
	}

	return d.base.RoundTrip(r)
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
