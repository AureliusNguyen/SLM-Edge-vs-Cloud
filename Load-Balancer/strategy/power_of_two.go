// Use when: Distribute uneven jobs across hundreds of interchangeable workers.
// Example: Celebrity requests can use any replica, so two-choice load sampling spreads their concurrent work.
// Pros: Constant-time selection samples distinct nodes and reserves the less busy one atomically.
// Cons: May miss the global minimum and local counts do not observe traffic from other balancers.
package strategy

import (
	"context"
	"math/rand"
	"sync"
)

// PowerOfTwo samples two distinct eligible backends and reserves the less busy
// one. Selection is O(1), with counts local to this picker instance.
type PowerOfTwo struct {
	mu     sync.Mutex
	active map[BackendID]uint64
}

func NewPowerOfTwo() *PowerOfTwo {

	return &PowerOfTwo{active: make(map[BackendID]uint64)}
}

func (p *PowerOfTwo) Pick(ctx context.Context, _ Input, c Candidates) (Selection, error) {
	pickErr := check(ctx, c)

	if pickErr != nil {

		return Selection{}, pickErr
	}

	a := rand.Intn(c.Len())
	b := a

	if c.Len() > 1 {
		b = rand.Intn(c.Len() - 1)

		if b >= a {
			b++
		}

	}

	p.mu.Lock()
	id := c.At(a)

	if p.active[c.At(b)] < p.active[id] {
		id = c.At(b)
	}

	p.active[id]++
	p.mu.Unlock()
	var once sync.Once

	return Selection{BackendID: id, Done: func(Result) {
		once.Do(func() {
			p.mu.Lock()
			defer p.mu.Unlock()
			p.active[id]--

			if p.active[id] == 0 {
				delete(p.active, id)
			}

		})
	}}, nil
}
