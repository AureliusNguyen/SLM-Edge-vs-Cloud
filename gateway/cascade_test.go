package main

import (
	"bytes"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/AureliusNguyen/SLM-Edge-vs-Cloud/Load-Balancer/strategy"
)

// fakeTier answers like an OpenAI-style server and records what it was sent.
type fakeTier struct {
	name    string
	logprob float64
	calls   int
	last    map[string]any
}

func (f *fakeTier) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	f.calls++
	_ = json.NewDecoder(r.Body).Decode(&f.last)
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]any{"choices": []any{map[string]any{
		"message":  map[string]any{"content": "answer from " + f.name},
		"logprobs": map[string]any{"content": []any{map[string]any{"logprob": f.logprob}, map[string]any{"logprob": f.logprob}}},
	}}})
}

func f64(x float64) *float64 { return &x }

func testGateway(t *testing.T, policy string, localLogprob float64) (*gateway, *fakeTier, *fakeTier, *bytes.Buffer) {
	t.Helper()
	local, cloud := &fakeTier{name: "local", logprob: localLogprob}, &fakeTier{name: "cloud"}
	logs := &bytes.Buffer{}

	return &gateway{
		router:     testRouter(t, true),
		tiers:      map[strategy.BackendID]http.Handler{"local": local, "cloud": cloud},
		models:     map[strategy.BackendID]string{"local": "slm", "cloud": "llm"},
		log:        json.NewEncoder(logs),
		policy:     policy,
		thresholds: map[string]*float64{"yesno": f64(-0.05), "classify": f64(-0.05), "extract": nil, "math": f64(-0.1)},
	}, local, cloud, logs
}

func send(g *gateway, task string) *httptest.ResponseRecorder {
	req := httptest.NewRequest("POST", "/v1/chat/completions", strings.NewReader(`{"model":"auto","messages":[{"role":"user","content":"hi"}],"logprobs":true}`))
	req.Header.Set("X-Task-Type", task)
	rec := httptest.NewRecorder()
	g.ServeHTTP(rec, req)

	return rec
}

func TestCascade(t *testing.T) {
	cases := []struct {
		name, policy, task string
		logprob            float64
		route              string
		localCalls         int
		cloudCalls         int
		reason             string
	}{
		{"task-rule never cascades", policyTaskRule, "yesno", -1, "local", 1, 0, "picked local"},
		{"confident local answer is kept", policyRuleCascade, "yesno", -0.01, "local", 1, 0, "kept local"},
		{"unsure local answer is escalated", policyRuleCascade, "yesno", -0.2, "cloud", 1, 1, "escalated to cloud"},
		{"rule+cascade leaves cloud tasks in the cloud", policyRuleCascade, "math", -0.01, "cloud", 0, 1, "needs cloud"},
		{"null threshold keeps the task in the cloud", policyRuleCascade, "extract", -0.01, "cloud", 0, 1, "cloud only"},
		{"cascade tries cloud tasks locally first", policyCascade, "classify", -0.01, "local", 1, 0, "kept local"},
		{"cascade escalates cloud tasks when unsure", policyCascade, "math", -0.5, "cloud", 1, 1, "escalated"},
		{"cascade without a threshold goes to the cloud", policyCascade, "other", -0.01, "cloud", 0, 1, "quality gate"},
	}

	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			g, local, cloud, logs := testGateway(t, c.policy, c.logprob)
			rec := send(g, c.task)

			if rec.Code != http.StatusOK {
				t.Fatalf("status %d: %s", rec.Code, rec.Body)
			}

			if got := rec.Header().Get("X-Route"); got != c.route {
				t.Errorf("X-Route = %q, want %q", got, c.route)
			}

			if !strings.Contains(rec.Header().Get("X-Route-Reason"), c.reason) {
				t.Errorf("reason %q does not contain %q", rec.Header().Get("X-Route-Reason"), c.reason)
			}

			if local.calls != c.localCalls || cloud.calls != c.cloudCalls {
				t.Errorf("calls local=%d cloud=%d, want %d and %d", local.calls, cloud.calls, c.localCalls, c.cloudCalls)
			}

			if !strings.Contains(rec.Body.String(), "answer from "+c.route) {
				t.Errorf("body is not the %s answer: %s", c.route, rec.Body)
			}

			if cloud.calls > 0 && cloud.last["logprobs"] != nil {
				t.Error("logprobs were sent to the cloud")
			}

			if cloud.calls > 0 && cloud.last["model"] != "llm" {
				t.Errorf("cloud got model %v", cloud.last["model"])
			}

			var entry struct {
				TiersCalled []string `json:"tiers_called"`
				EnergyWh    float64  `json:"energy_wh_est"`
				Grams       float64  `json:"gco2e_est"`
			}

			if err := json.Unmarshal(logs.Bytes(), &entry); err != nil {
				t.Fatal(err)
			}

			if len(entry.TiersCalled) != c.localCalls+c.cloudCalls {
				t.Errorf("tiers_called = %v", entry.TiersCalled)
			}

			want := float64(c.localCalls)*defaultProfiles["local"].EnergyWh + float64(c.cloudCalls)*defaultProfiles["cloud"].EnergyWh

			if diff := entry.EnergyWh - want; diff > 1e-9 || diff < -1e-9 {
				t.Errorf("energy_wh_est = %v, want %v", entry.EnergyWh, want)
			}
		})
	}
}

func TestMeanLogprob(t *testing.T) {
	lp, ok := meanLogprob([]byte(`{"choices":[{"logprobs":{"content":[{"logprob":-0.1},{"logprob":-0.3}]}}]}`))

	if !ok || lp > -0.199 || lp < -0.201 {
		t.Errorf("got %v %v", lp, ok)
	}

	if _, ok := meanLogprob([]byte(`{"choices":[{"message":{}}]}`)); ok {
		t.Error("no logprobs should not be ok")
	}
}

func TestLoadThresholds(t *testing.T) {
	path := filepath.Join(t.TempDir(), "thresholds.json")
	_ = os.WriteFile(path, []byte(`{"model":"llama","tol":0.02,"thresholds":{"yesno":-0.0184,"classify":null}}`), 0o644)
	thr, err := loadThresholds(path)

	if err != nil {
		t.Fatal(err)
	}

	if thr["yesno"] == nil || *thr["yesno"] != -0.0184 || thr["classify"] != nil {
		t.Errorf("got %v", thr)
	}
}

// TestCloudDelay is the injected-delay network test: -cloud-delay adds the delay to every
// cloud request, and a cancelled request stops waiting.
func TestCloudDelay(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = io.WriteString(w, "ok")
	}))
	defer server.Close()

	for _, delay := range []time.Duration{0, 150 * time.Millisecond} {
		client := &http.Client{Transport: delayed{delay: delay, base: http.DefaultTransport}}
		start := time.Now()
		resp, err := client.Get(server.URL)

		if err != nil {
			t.Fatal(err)
		}

		resp.Body.Close()

		if took := time.Since(start); took < delay || took > delay+time.Second {
			t.Errorf("delay %v: request took %v", delay, took)
		}
	}

	client := &http.Client{Transport: delayed{delay: time.Hour, base: http.DefaultTransport}, Timeout: 50 * time.Millisecond}

	if _, err := client.Get(server.URL); err == nil {
		t.Error("a request past its timeout should fail instead of waiting for the delay")
	}
}
