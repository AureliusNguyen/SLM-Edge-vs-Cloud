// Use when: Route CPU-heavy search queries using comparable queue-depth or CPU samples.
// Example: Two expensive jobs at 95 percent CPU can lose to ten cheap jobs at 10 percent CPU.
// Pros: Uses workload cost signals and excludes silent backends once their samples expire.
// Cons: Needs a concurrency-safe external metrics cache and fails closed if every sample is unusable.
package strategy

import (
	"context"
	"errors"
	"fmt"
	"math"
	"sync/atomic"
	"time"
)

type LoadSample struct {
	Value     float64 // comparable, nonnegative load in the same units across backends
	UpdatedAt time.Time
}

// LoadProvider should read a concurrency-safe local metrics cache, not perform
// a remote RPC per pick. Only resource-based routing needs this dependency.
type LoadProvider func(context.Context, BackendID) (LoadSample, error)

type ResourceBased struct {
	load   LoadProvider
	maxAge time.Duration
	next   atomic.Uint64
}

func NewResourceBased(provider LoadProvider, maxAge time.Duration) (*ResourceBased, error) {

	if provider == nil || maxAge <= 0 {

		return nil, errors.New("resource routing requires a provider and positive maximum sample age")
	}

	return &ResourceBased{load: provider, maxAge: maxAge}, nil
}

func (r *ResourceBased) Pick(ctx context.Context, _ Input, c Candidates) (Selection, error) {
	pickErr := check(ctx, c)

	if pickErr != nil {

		return Selection{}, pickErr
	}

	start := int((r.next.Add(1) - 1) % uint64(c.Len()))
	var best BackendID
	bestLoad := math.Inf(1)

	for offset := range c.Len() {
		contextErr := ctx.Err()

		if contextErr != nil {

			return Selection{}, contextErr
		}

		id := c.At((start + offset) % c.Len())
		sample, err := r.load(ctx, id)
		age := time.Since(sample.UpdatedAt)

		if err != nil || sample.UpdatedAt.IsZero() || age < 0 || age > r.maxAge || math.IsNaN(sample.Value) || math.IsInf(sample.Value, 0) || sample.Value < 0 {
			continue
		}

		if sample.Value < bestLoad {
			best, bestLoad = id, sample.Value
		}

	}

	contextErr := ctx.Err()

	if contextErr != nil {

		return Selection{}, contextErr
	}

	if best == "" {

		return Selection{}, fmt.Errorf("%w: no valid fresh load samples", ErrNoBackend)
	}

	return Selection{BackendID: best}, nil
}
