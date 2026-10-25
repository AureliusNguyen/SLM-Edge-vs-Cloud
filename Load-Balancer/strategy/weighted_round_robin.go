// Use when: Give an 8-core worker four times the turns of a 2-core worker using weights 4 and 1.
// Example: Smooth scheduling interleaves the smaller worker instead of sending a single contiguous batch.
// Pros: Expresses known capacity differences and supports zero-weight draining.
// Cons: Static capacity cannot detect a large node at 95 percent CPU and scheduling scans eligible nodes.
package strategy

import (
	"context"
	"errors"
	"fmt"
	"math"
	"sync"
)

// WeightedRoundRobin uses smooth weighted scheduling to avoid contiguous bursts.
// Weights describe configured capacity, not live load. Zero disables a backend.
type WeightedRoundRobin struct {
	mu      sync.Mutex
	weights map[BackendID]int64
	current map[BackendID]int64
	last    []BackendID
}

func NewWeightedRoundRobin(weights map[BackendID]int) (*WeightedRoundRobin, error) {
	w := &WeightedRoundRobin{weights: make(map[BackendID]int64, len(weights)), current: make(map[BackendID]int64)}
	var total int64

	for id, weight := range weights {

		if id == "" || weight < 0 {

			return nil, errors.New("weights require nonempty IDs and nonnegative values")
		}

		// Leave arithmetic headroom for smooth scheduling accumulators.

		if int64(weight) > math.MaxInt64/4-total {

			return nil, errors.New("total weight is too large")
		}

		total += int64(weight)
		w.weights[id] = int64(weight)
	}

	if total == 0 {

		return nil, errors.New("at least one weight must be positive")
	}

	return w, nil
}

func (w *WeightedRoundRobin) Pick(ctx context.Context, _ Input, c Candidates) (Selection, error) {
	pickErr := check(ctx, c)

	if pickErr != nil {

		return Selection{}, pickErr
	}

	var total int64

	for _, id := range c.ids {
		weight, ok := w.weights[id]

		if !ok {

			return Selection{}, fmt.Errorf("%w: missing weight for %q", ErrInvalidCandidates, id)
		}

		total += weight
	}

	if total == 0 {

		return Selection{}, ErrNoBackend
	}

	w.mu.Lock()
	defer w.mu.Unlock()

	if !sameIDs(w.last, c.ids) {
		clear(w.current)
		w.last = append(w.last[:0], c.ids...)
	}

	var best BackendID

	for _, id := range c.ids {

		if w.weights[id] == 0 {
			continue
		}

		w.current[id] += w.weights[id]

		if best == "" || w.current[id] > w.current[best] {
			best = id
		}

	}

	w.current[best] -= total

	return Selection{BackendID: best}, nil
}

func sameIDs(a, b []BackendID) bool {

	if len(a) != len(b) {

		return false
	}

	for i := range a {

		if a[i] != b[i] {

			return false
		}

	}

	return true
}
