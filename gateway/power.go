package main

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"os/exec"
	"strconv"
	"strings"
	"sync"
	"time"
)

// Device power measured inside the gateway, the same sources as rq2/rq2_measure.py:
//
//	lhm     CPU package power from LibreHardwareMonitor's web server (Windows)
//	nvidia  GPU power from nvidia-smi
//
// A background loop samples total power. At start-up the gateway measures idle power; the
// energy of a request is the power above idle integrated over the request. When several
// requests are in flight, each sample interval's extra energy is split evenly between them.

type powerSource interface {
	name() string
	watts(ctx context.Context) (float64, error)
}

type lhmSource struct {
	url, sensor string
	client      *http.Client
}

func (l lhmSource) name() string { return "lhm" }

func (l lhmSource) watts(ctx context.Context) (float64, error) {
	req, _ := http.NewRequestWithContext(ctx, "GET", strings.TrimRight(l.url, "/")+"/data.json", nil)
	resp, err := l.client.Do(req)

	if err != nil {
		return 0, err
	}

	defer resp.Body.Close()
	var root lhmNode

	if err := json.NewDecoder(resp.Body).Decode(&root); err != nil {
		return 0, err
	}

	if w, ok := root.find(l.sensor); ok {
		return w, nil
	}

	return 0, fmt.Errorf("no %q power sensor in LibreHardwareMonitor", l.sensor)
}

type lhmNode struct {
	Text     string    `json:"Text"`
	Value    string    `json:"Value"`
	Children []lhmNode `json:"Children"`
}

// find returns the first sensor with this name whose value is in watts.
func (n lhmNode) find(sensor string) (float64, bool) {

	if n.Text == sensor && strings.HasSuffix(n.Value, " W") {
		w, err := strconv.ParseFloat(strings.Replace(strings.TrimSuffix(n.Value, " W"), ",", ".", 1), 64)

		return w, err == nil
	}

	for _, c := range n.Children {

		if w, ok := c.find(sensor); ok {
			return w, true
		}

	}

	return 0, false
}

type nvidiaSource struct{}

func (nvidiaSource) name() string { return "nvidia" }

func (nvidiaSource) watts(ctx context.Context) (float64, error) {
	out, err := exec.CommandContext(ctx, "nvidia-smi", "--query-gpu=power.draw", "--format=csv,noheader,nounits").Output()

	if err != nil {
		return 0, err
	}

	total := 0.0

	for _, line := range strings.Fields(string(out)) {
		w, err := strconv.ParseFloat(line, 64)

		if err != nil {
			return 0, fmt.Errorf("nvidia-smi: %q", line)
		}

		total += w
	}

	return total, nil
}

type powerSample struct {
	at       time.Time
	watts    float64
	inFlight int
}

type powerMeter struct {
	sources  []powerSource
	interval time.Duration

	mu       sync.Mutex
	samples  []powerSample // the last few minutes
	idle     float64
	inFlight int
}

func newPowerMeter(spec, lhmURL, lhmSensor string, interval time.Duration) (*powerMeter, error) {
	m := &powerMeter{interval: interval}

	for _, s := range strings.Split(spec, ",") {
		switch strings.TrimSpace(s) {
		case "", "none":
		case "lhm":
			m.sources = append(m.sources, lhmSource{url: lhmURL, sensor: lhmSensor, client: &http.Client{Timeout: 2 * time.Second}})
		case "nvidia":
			m.sources = append(m.sources, nvidiaSource{})
		default:
			return nil, fmt.Errorf("unknown power source %q (lhm, nvidia or none)", s)
		}
	}

	if len(m.sources) == 0 {
		return nil, nil
	}

	for _, s := range m.sources {

		if _, err := s.watts(context.Background()); err != nil {
			return nil, fmt.Errorf("power source %s: %w", s.name(), err)
		}

	}

	return m, nil
}

func (m *powerMeter) names() string {
	var n []string

	for _, s := range m.sources {
		n = append(n, s.name())
	}

	return strings.Join(n, "+")
}

func (m *powerMeter) read(ctx context.Context) float64 {
	total := 0.0

	for _, s := range m.sources {

		if w, err := s.watts(ctx); err == nil {
			total += w
		}

	}

	return total
}

// run samples power until ctx is done.
func (m *powerMeter) run(ctx context.Context) {
	tick := time.NewTicker(m.interval)
	defer tick.Stop()

	for {
		w := m.read(ctx)
		m.mu.Lock()
		m.samples = append(m.samples, powerSample{at: time.Now(), watts: w, inFlight: m.inFlight})

		if len(m.samples) > 3000 {
			m.samples = append([]powerSample(nil), m.samples[len(m.samples)-2000:]...)
		}

		m.mu.Unlock()

		select {
		case <-ctx.Done():
			return
		case <-tick.C:
		}
	}
}

// measureIdle averages power over d before any request arrives.
func (m *powerMeter) measureIdle(d time.Duration) float64 {
	start := time.Now()
	time.Sleep(d)
	m.mu.Lock()
	defer m.mu.Unlock()
	sum, n := 0.0, 0

	for _, s := range m.samples {

		if s.at.After(start) {
			sum += s.watts
			n++
		}

	}

	if n > 0 {
		m.idle = sum / float64(n)
	}

	return m.idle
}

func (m *powerMeter) begin() {
	m.mu.Lock()
	m.inFlight++
	m.mu.Unlock()
}

func (m *powerMeter) end() {
	m.mu.Lock()
	m.inFlight--
	m.mu.Unlock()
}

// extraJoules waits until a sample after t1 exists, then integrates the power above idle
// over [t0, t1], each interval split between the requests in flight during it.
func (m *powerMeter) extraJoules(t0, t1 time.Time) float64 {
	deadline := time.Now().Add(5 * m.interval)

	for time.Now().Before(deadline) {
		m.mu.Lock()
		last := m.samples[len(m.samples)-1].at
		m.mu.Unlock()

		if last.After(t1) {
			break
		}

		time.Sleep(m.interval / 2)
	}

	m.mu.Lock()
	defer m.mu.Unlock()

	return integrate(m.samples, m.idle, t0, t1)
}

// integrate is the trapezoid integral of (watts - idle) / in-flight over [t0, t1].
func integrate(samples []powerSample, idle float64, t0, t1 time.Time) float64 {
	joules := 0.0

	for i := 1; i < len(samples); i++ {
		a, b := samples[i-1], samples[i]
		lo, hi := maxTime(a.at, t0), minTime(b.at, t1)

		if !hi.After(lo) {
			continue
		}

		share := b.inFlight

		if share < 1 {
			share = 1
		}

		joules += ((a.watts+b.watts)/2 - idle) * hi.Sub(lo).Seconds() / float64(share)
	}

	return joules
}

func maxTime(a, b time.Time) time.Time {

	if a.After(b) {
		return a
	}

	return b
}

func minTime(a, b time.Time) time.Time {

	if a.Before(b) {
		return a
	}

	return b
}
