// Use when: Keep user 42 on one disposable cache backend while the eligible pool is stable.
// Example: Hash a user ID instead of the common /profile path when each user needs a separate cache entry.
// Pros: Deterministic affinity with constant-time hashing over a prepared candidate snapshot.
// Cons: Adding or losing a node remaps many keys and one celebrity key still overloads one backend.
package strategy

import (
	"context"
	"crypto/sha256"
	"encoding/binary"
)

// SimpleHash provides affinity using hash(key) modulo eligible backend count.
// Membership/health changes remap many keys. It does not split hot keys.
type SimpleHash struct{}

func NewSimpleHash() *SimpleHash {

	return &SimpleHash{}
}

func (*SimpleHash) Pick(ctx context.Context, input Input, c Candidates) (Selection, error) {
	pickErr := check(ctx, c)

	if pickErr != nil {

		return Selection{}, pickErr
	}

	if input.Key == "" {

		return Selection{}, ErrMissingKey
	}

	return Selection{BackendID: c.At(int(hash(input.Key) % uint64(c.Len())))}, nil
}

func hash(key string) uint64 {
	sum := sha256.Sum256([]byte(key))

	return binary.BigEndian.Uint64(sum[:8])
}
