// Use when: Rotate across four equal API servers serving similarly sized 20ms JSON requests.
// Example: With a, b, c eligible, successive requests get a, b, c, a.
// Pros: Predictable equal turns with constant-time atomic scheduling.
// Cons: A node busy with a 30-second upload still receives equal traffic and no session affinity is preserved.
package strategy

import (
	"context"
	"sync/atomic"
)

// RoundRobin gives equal turns to eligible backends, regardless of request cost.
type RoundRobin struct{ next atomic.Uint64 }

func NewRoundRobin() *RoundRobin {

	return &RoundRobin{}
}

func (r *RoundRobin) Pick(ctx context.Context, _ Input, c Candidates) (Selection, error) {
	pickErr := check(ctx, c)

	if pickErr != nil {

		return Selection{}, pickErr
	}

	i := (r.next.Add(1) - 1) % uint64(c.Len())

	return Selection{BackendID: c.At(int(i))}, nil
}
