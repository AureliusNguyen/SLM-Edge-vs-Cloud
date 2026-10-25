// Use when: Mix 10ms reads with 30-second downloads across interchangeable workers.
// Example: A worker already serving two long downloads loses to a worker with no outstanding requests.
// Pros: Atomic reservation prevents simultaneous picks from all observing the same idle worker.
// Cons: Scans all candidates and request counts do not represent TCP connections or CPU cost.
package strategy

import (
	"context"
	"sync"
)

// LeastConnections counts in-flight requests (not TCP connections).
// Equal-load ties rotate so sequential traffic does not all hit the first backend.
type LeastConnections struct {
	mu     sync.Mutex
	active map[BackendID]uint64
	next   uint64
}

func NewLeastConnections() *LeastConnections {

	return &LeastConnections{active: make(map[BackendID]uint64)}
}

func (l *LeastConnections) Pick(ctx context.Context, _ Input, c Candidates) (Selection, error) {
	pickErr := check(ctx, c)

	if pickErr != nil {

		return Selection{}, pickErr
	}

	l.mu.Lock()
	start := int(l.next % uint64(c.Len()))
	best := start
	l.next++

	for offset := range c.Len() {
		i := (start + offset) % c.Len()
		id := c.At(i)

		if l.active[id] < l.active[c.At(best)] {
			best = i
		}

	}

	id := c.At(best)
	l.active[id]++
	l.mu.Unlock()
	var once sync.Once

	return Selection{BackendID: id, Done: func(Result) {
		once.Do(func() {
			l.mu.Lock()
			defer l.mu.Unlock()
			l.active[id]--

			if l.active[id] == 0 {
				delete(l.active, id)
			}

		})
	}}, nil
}
