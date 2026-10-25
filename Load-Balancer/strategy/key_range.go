// Use when: Route normalized UTC timestamp keys to explicit historical time-series shards.
// Example: An inclusive 2026-10-24 boundary owns that day while a final unbounded range owns later keys.
// Pros: Preserves ordered partition ownership and fails closed when the owning shard is unavailable.
// Cons: Todays range can become a hotspot and splitting authoritative ranges requires application-managed migration.
package strategy

import (
	"context"
	"errors"
	"sort"
)

// Range assigns keys up to and including UpperBound to BackendID.
// An empty UpperBound means positive infinity and is only allowed last.
type Range struct {
	UpperBound string
	BackendID  BackendID
}

// KeyRange routes lexicographically ordered keys to their explicit owner.
// An unavailable owner returns ErrNoBackend. Arbitrary shard failover is unsafe.
type KeyRange struct{ ranges []Range }

func NewKeyRange(ranges []Range) (*KeyRange, error) {

	if len(ranges) == 0 {

		return nil, errors.New("at least one key range is required")
	}

	for i, r := range ranges {

		if r.BackendID == "" {

			return nil, errors.New("range backend ID must not be empty")
		}

		if r.UpperBound == "" && i != len(ranges)-1 {

			return nil, errors.New("unbounded range must be last")
		}

		if i > 0 && r.UpperBound != "" && r.UpperBound <= ranges[i-1].UpperBound {

			return nil, errors.New("range upper bounds must be strictly increasing")
		}

	}

	return &KeyRange{ranges: append([]Range(nil), ranges...)}, nil
}

func (k *KeyRange) Pick(ctx context.Context, input Input, c Candidates) (Selection, error) {
	pickErr := check(ctx, c)

	if pickErr != nil {

		return Selection{}, pickErr
	}

	if input.Key == "" {

		return Selection{}, ErrMissingKey
	}

	i := sort.Search(len(k.ranges), func(i int) bool {

		return k.ranges[i].UpperBound == "" || input.Key <= k.ranges[i].UpperBound
	})

	if i == len(k.ranges) || !c.Contains(k.ranges[i].BackendID) {

		return Selection{}, ErrNoBackend
	}

	return Selection{BackendID: k.ranges[i].BackendID}, nil
}
