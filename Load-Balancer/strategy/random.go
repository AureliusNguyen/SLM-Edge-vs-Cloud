// Use when: Spread thousands of small independent requests over interchangeable stateless API workers.
// Example: A high-volume health aggregation service needs no per-client cache affinity.
// Pros: Constant-time selection without shared per-picker counters.
// Cons: Five requests can cluster on one worker by chance and a users cache does not stay warm.
package strategy

import (
	"context"
	"math/rand"
)

// Random spreads requests without affinity or shared scheduling state.
type Random struct{}

func NewRandom() *Random {

	return &Random{}
}

func (*Random) Pick(ctx context.Context, _ Input, c Candidates) (Selection, error) {
	pickErr := check(ctx, c)

	if pickErr != nil {

		return Selection{}, pickErr
	}

	return Selection{BackendID: c.At(rand.Intn(c.Len()))}, nil
}
