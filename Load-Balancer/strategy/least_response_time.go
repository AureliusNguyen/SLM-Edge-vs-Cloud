// Use when: Avoid a swapping replica taking 2 seconds while peers finish in 20ms.
// Example: A fast 503 is penalized rather than rewarded and old penalties decay to allow recovery.
// Pros: EWMA smooths noisy samples and combines latency with the number of outstanding requests.
// Cons: Client backpressure affects measured durations and health probes are still needed for readiness.
package strategy

import (
	"context"
	"errors"
	"math"
	"sync"
	"time"
)

type LatencyOptions struct {
	InitialLatency time.Duration // default 50ms for an unsampled backend
	Smoothing      float64       // EWMA sample weight, (0,1]. Default 0.2
	FailurePenalty time.Duration // minimum sample for errors/5xx. Default 1s
	Decay          time.Duration // stale samples return toward initial latency, default 30s
}

type latencyState struct {
	active     uint64
	ewma       float64
	lastSample time.Time
}

// LeastResponseTime minimizes EWMA latency * (in-flight requests + 1).
// Use health probes for recovery. Passive latency alone cannot prove readiness.
type LeastResponseTime struct {
	mu      sync.Mutex
	states  map[BackendID]*latencyState
	options LatencyOptions
	next    uint64
}

func NewLeastResponseTime(options LatencyOptions) (*LeastResponseTime, error) {

	if options.InitialLatency == 0 {
		options.InitialLatency = 50 * time.Millisecond
	}

	if options.Smoothing == 0 {
		options.Smoothing = 0.2
	}

	if options.FailurePenalty == 0 {
		options.FailurePenalty = time.Second
	}

	if options.Decay == 0 {
		options.Decay = 30 * time.Second
	}

	if options.InitialLatency < 0 || options.Decay < 0 || options.FailurePenalty < options.InitialLatency || math.IsNaN(options.Smoothing) || options.Smoothing <= 0 || options.Smoothing > 1 {

		return nil, errors.New("invalid latency options: require positive initial latency, smoothing in (0,1], and penalty >= initial latency")
	}

	return &LeastResponseTime{states: make(map[BackendID]*latencyState), options: options}, nil
}

func (l *LeastResponseTime) state(id BackendID) *latencyState {
	s := l.states[id]

	if s == nil {
		s = &latencyState{ewma: float64(l.options.InitialLatency)}
		l.states[id] = s
	}

	return s
}

func (l *LeastResponseTime) Pick(ctx context.Context, _ Input, c Candidates) (Selection, error) {
	pickErr := check(ctx, c)

	if pickErr != nil {

		return Selection{}, pickErr
	}

	l.mu.Lock()
	start := int(l.next % uint64(c.Len()))
	l.next++
	best := c.At(start)
	score := math.Inf(1)

	for offset := range c.Len() {
		id := c.At((start + offset) % c.Len())
		s := l.state(id)
		latency := s.ewma

		if !s.lastSample.IsZero() {
			baseline := float64(l.options.InitialLatency)
			latency = baseline + (latency-baseline)*math.Exp(-float64(time.Since(s.lastSample))/float64(l.options.Decay))
		}

		candidateScore := latency * (float64(s.active) + 1)

		if candidateScore < score {
			best, score = id, candidateScore
		}

	}

	l.state(best).active++
	l.mu.Unlock()
	var once sync.Once

	return Selection{BackendID: best, Done: func(result Result) {
		once.Do(func() {
			l.mu.Lock()
			defer l.mu.Unlock()
			s := l.state(best)
			s.active--
			// Client cancellation is not evidence that the backend is slow.

			if errors.Is(result.Err, context.Canceled) {

				return
			}

			sample := float64(result.Duration)

			if sample < 1 {
				sample = 1
			}

			if (result.Err != nil || result.StatusCode >= 500) && sample < float64(l.options.FailurePenalty) {
				sample = float64(l.options.FailurePenalty)
			}

			s.ewma += l.options.Smoothing * (sample - s.ewma)
			s.lastSample = time.Now()
		})
	}}, nil
}
