// Use when: Grow a disposable cache pool from four nodes to five while preserving most warm entries.
// Example: Keep stable IDs cache-a and cache-b when deployment lists are reordered.
// Pros: Virtual nodes spread the keyspace and a new node takes ownership only of its own share.
// Cons: One hot key remains pinned and clockwise failover is safe only if another node can serve the data.
package strategy

import (
	"context"
	"errors"
	"fmt"
	"sort"
	"strconv"
)

type hashSlot struct {
	point   uint64
	backend BackendID
}

// ConsistentHash provides affinity with virtual nodes and stable backend IDs.
// Ineligible owners fail over clockwise. This is affinity, not data replication.
// Build a new picker for membership changes, keeping surviving IDs unchanged.
type ConsistentHash struct {
	ring    []hashSlot
	members Candidates
}

func NewConsistentHash(backends Candidates, virtualNodes int) (*ConsistentHash, error) {

	if backends.Len() == 0 || virtualNodes <= 0 {

		return nil, errors.New("consistent hashing requires backends and positive virtual-node count")
	}

	maxInt := int(^uint(0) >> 1)

	if virtualNodes > maxInt/backends.Len() {

		return nil, errors.New("hash ring size overflows int")
	}

	c := &ConsistentHash{members: backends, ring: make([]hashSlot, 0, backends.Len()*virtualNodes)}

	for _, id := range backends.ids {

		for replica := range virtualNodes {
			c.ring = append(c.ring, hashSlot{point: hash(string(id) + "\x00" + strconv.Itoa(replica)), backend: id})
		}

	}

	sort.Slice(c.ring, func(i, j int) bool {

		if c.ring[i].point == c.ring[j].point {

			return c.ring[i].backend < c.ring[j].backend
		}

		return c.ring[i].point < c.ring[j].point
	})

	return c, nil
}

func (c *ConsistentHash) Pick(ctx context.Context, input Input, eligible Candidates) (Selection, error) {
	pickErr := check(ctx, eligible)

	if pickErr != nil {

		return Selection{}, pickErr
	}

	if input.Key == "" {

		return Selection{}, ErrMissingKey
	}

	for _, id := range eligible.ids {

		if !c.members.Contains(id) {

			return Selection{}, fmt.Errorf("%w: unknown ring member %q", ErrInvalidCandidates, id)
		}

	}

	point := hash(input.Key)
	start := sort.Search(len(c.ring), func(i int) bool {

		return c.ring[i].point >= point
	})

	for offset := range len(c.ring) {
		id := c.ring[(start+offset)%len(c.ring)].backend

		if eligible.Contains(id) {

			return Selection{BackendID: id}, nil
		}

	}

	return Selection{}, ErrNoBackend
}
