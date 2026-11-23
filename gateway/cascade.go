package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"time"

	"github.com/AureliusNguyen/SLM-Edge-vs-Cloud/Load-Balancer/strategy"
)

// Routing policies, the same as in rq3/rq3_sim.py.
//
//	task-rule     the quality gate only (localTasks may run locally, the rest go to the cloud)
//	rule+cascade  task-rule, but a local answer whose mean token log-prob is below the task's
//	              threshold is thrown away and the request is re-sent to the cloud
//	cascade       every task with a threshold is tried locally first, then escalated the same way
const (
	policyTaskRule    = "task-rule"
	policyRuleCascade = "rule+cascade"
	policyCascade     = "cascade"
)

// loadThresholds reads rq3/results/thresholds_<model>.json, written by rq3_sim.py:
// {"thresholds": {"yesno": -0.018, "classify": null, ...}}. A null threshold means the
// local model never reached cloud-level accuracy on that task, so the task stays in the cloud.
func loadThresholds(path string) (map[string]*float64, error) {
	data, err := os.ReadFile(path)

	if err != nil {
		return nil, err
	}

	var file struct {
		Thresholds map[string]*float64 `json:"thresholds"`
	}

	if err := json.Unmarshal(data, &file); err != nil {
		return nil, fmt.Errorf("%s: %w", path, err)
	}

	if len(file.Thresholds) == 0 {
		return nil, fmt.Errorf("%s: no thresholds", path)
	}

	return file.Thresholds, nil
}

// cascadeThreshold says whether this request should be tried locally first and, if so,
// with which threshold. tier is what the quality gate picked.
func (g *gateway) cascadeThreshold(task string, tier strategy.BackendID, forced string) (float64, bool) {

	if forced != "" || g.policy == policyTaskRule || g.policy == "" {
		return 0, false
	}

	thr, ok := g.thresholds[task]

	if !ok || thr == nil || !g.router.ready["local"]() {
		return 0, false
	}

	if g.policy == policyRuleCascade && tier != "local" {
		return 0, false
	}

	return *thr, true
}

// meanLogprob is the mean token log-prob of the first choice of an OpenAI-style response.
func meanLogprob(body []byte) (float64, bool) {
	var resp struct {
		Choices []struct {
			Logprobs *struct {
				Content []struct {
					Logprob *float64 `json:"logprob"`
				} `json:"content"`
			} `json:"logprobs"`
		} `json:"choices"`
	}

	if json.Unmarshal(body, &resp) != nil || len(resp.Choices) == 0 || resp.Choices[0].Logprobs == nil {
		return 0, false
	}

	sum, n := 0.0, 0

	for _, t := range resp.Choices[0].Logprobs.Content {

		if t.Logprob != nil {
			sum += *t.Logprob
			n++
		}

	}

	if n == 0 {
		return 0, false
	}

	return sum / float64(n), true
}

// call sends the request body to one tier and buffers the whole response.
func (g *gateway) call(r *http.Request, tier strategy.BackendID, body map[string]any) *httptest.ResponseRecorder {
	body["model"] = g.models[tier]

	if tier == "cloud" {
		// Groq rejects logprobs.
		delete(body, "logprobs")
		delete(body, "top_logprobs")
	} else {
		body["logprobs"] = true
	}

	payload, _ := json.Marshal(body)
	req := r.Clone(r.Context())
	req.Body = nopCloser{bytes.NewReader(payload)}
	req.ContentLength = int64(len(payload))
	rec := httptest.NewRecorder()
	g.tiers[tier].ServeHTTP(rec, req)

	return rec
}

// cascade answers locally, keeps the answer when its confidence is at or above thr, and
// otherwise asks the cloud. Returns the tier that answered, the reason, the status, and
// which tiers were called (an escalated request pays for both).
func (g *gateway) cascade(w http.ResponseWriter, r *http.Request, body map[string]any, gate string, thr float64) (int, strategy.BackendID, string, []strategy.BackendID) {
	cloudBody := map[string]any{}

	for k, v := range body {
		cloudBody[k] = v
	}

	start := time.Now()
	local := g.call(r, "local", body)
	lp, ok := meanLogprob(local.Body.Bytes())
	localMs := time.Since(start).Milliseconds()

	if local.Code == http.StatusOK && ok && lp >= thr {
		reason := fmt.Sprintf("%s; cascade: kept local, mean log-prob %.4f >= %.4f", gate, lp, thr)
		write(w, local, "local", reason)

		return local.Code, "local", reason, []strategy.BackendID{"local"}
	}

	why := fmt.Sprintf("mean log-prob %.4f < %.4f", lp, thr)

	if local.Code != http.StatusOK {
		why = fmt.Sprintf("local answered %d", local.Code)
	} else if !ok {
		why = "local reply had no log-probs"
	}

	reason := fmt.Sprintf("%s; cascade: escalated to cloud after %d ms local, %s", gate, localMs, why)
	cloud := g.call(r, "cloud", cloudBody)
	write(w, cloud, "cloud", reason)

	return cloud.Code, "cloud", reason, []strategy.BackendID{"local", "cloud"}
}

func write(w http.ResponseWriter, rec *httptest.ResponseRecorder, tier strategy.BackendID, reason string) {

	for k, vs := range rec.Header() {

		for _, v := range vs {
			w.Header().Add(k, v)
		}

	}

	w.Header().Set("X-Route", string(tier))
	w.Header().Set("X-Route-Reason", reason)
	w.WriteHeader(rec.Code)
	_, _ = w.Write(rec.Body.Bytes())
}

type nopCloser struct{ *bytes.Reader }

func (nopCloser) Close() error { return nil }
