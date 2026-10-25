// Use when: Reuse routing for an HTTP proxy or a gRPC job dispatcher without transport-specific dependencies.
// Example: A tenant-aware picker can add an input fact while round-robin continues to ignore request facts.
// Pros: Immutable candidates and optional completion callbacks avoid fake strategy lifecycle methods.
// Cons: Callers must complete reservations and local picker counts do not measure other balancer processes.
//
// Package strategy implements transport-independent backend selection.
// Pickers are safe for concurrent use and must not be copied after first use.
package strategy

import (
	"context"
	"errors"
	"fmt"
	"sort"
	"time"
)

type BackendID string

var (
	ErrNoBackend         = errors.New("no eligible backend")
	ErrMissingKey        = errors.New("routing key is required")
	ErrInvalidCandidates = errors.New("candidates do not match strategy configuration")
)

// Input contains request facts, not strategy settings or backend metrics.
// Strategies only inspect facts relevant to their algorithm.
type Input struct {
	Key string
}

// Candidates is an immutable, sorted snapshot of eligible backend identities.
// Its zero value is an empty pool. Build once and reuse while eligibility is unchanged.
type Candidates struct {
	ids []BackendID
	set map[BackendID]struct{}
}

func NewCandidates(ids ...BackendID) (Candidates, error) {
	c := Candidates{ids: append([]BackendID(nil), ids...), set: make(map[BackendID]struct{}, len(ids))}

	for _, id := range c.ids {

		if id == "" {

			return Candidates{}, errors.New("backend ID must not be empty")
		}

		_, exists := c.set[id]

		if exists {

			return Candidates{}, fmt.Errorf("duplicate backend ID %q", id)
		}

		c.set[id] = struct{}{}
	}

	sort.Slice(c.ids, func(i, j int) bool {

		return c.ids[i] < c.ids[j]
	})

	return c, nil
}

func (c Candidates) Len() int {

	return len(c.ids)
}
func (c Candidates) At(index int) BackendID {

	return c.ids[index]
}
func (c Candidates) Contains(id BackendID) bool {
	_, ok := c.set[id]

	return ok
}
func (c Candidates) IDs() []BackendID {

	return append([]BackendID(nil), c.ids...)
}

// Result describes a completed attempt. Duration includes the entire attempt,
// including streaming and client backpressure for an HTTP proxy. Err should
// describe transport failures or backend failures. HTTP adapters also set StatusCode.
type Result struct {
	Duration   time.Duration
	Err        error
	StatusCode int
}

// Selection owns any reservation created by Pick. Call Done exactly once after
// the attempt, including failures and panics. Stateless pickers leave it nil.
// Built-in Done callbacks are idempotent to protect against accidental double release.
type Selection struct {
	BackendID BackendID
	Done      func(Result)
}

// Picker chooses only from candidates. Selection and reservation must be atomic
// for load-aware algorithms. On error, no reservation may remain outstanding.
// Each balancer should own its stateful picker. Counts are local to that instance.
type Picker interface {
	Pick(context.Context, Input, Candidates) (Selection, error)
}

func check(ctx context.Context, c Candidates) error {
	err := ctx.Err()

	if err != nil {

		return err
	}

	if c.Len() == 0 {

		return ErrNoBackend
	}

	return nil
}
