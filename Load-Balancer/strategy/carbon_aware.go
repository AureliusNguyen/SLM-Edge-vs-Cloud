// Use when: Choose between an edge SLM on the MISO grid and a cloud LLM in another region by estimated emissions.
// Example: 2 Wh at 450 gCO2e/kWh (0.9 g) loses to 0.3 Wh at 400 gCO2e/kWh (0.12 g).
// Pros: Makes the per-backend carbon tradeoff explicit with constant configuration and no shared counters.
// Cons: Static per-request estimates ignore prompt length, live grid intensity, load, and answer quality.
package strategy

import (
	"context"
	"errors"
	"fmt"
	"math"
	"sync/atomic"
)

// CarbonProfile is the estimated cost of serving one request on a backend.
type CarbonProfile struct {
	EnergyWh         float64 // estimated energy per request, in watt-hours
	IntensityGPerKWh float64 // carbon intensity of the grid powering the backend
}

// GramsCO2e returns the estimated emissions of one request.
func (p CarbonProfile) GramsCO2e() float64 {

	return p.EnergyWh * p.IntensityGPerKWh / 1000
}

// CarbonAware picks the eligible backend with the lowest estimated gCO2e per
// request. Equal-emission ties rotate. Selections carry no reservation.
type CarbonAware struct {
	profiles map[BackendID]CarbonProfile
	next     atomic.Uint64
}

func NewCarbonAware(profiles map[BackendID]CarbonProfile) (*CarbonAware, error) {

	if len(profiles) == 0 {

		return nil, errors.New("carbon-aware routing requires at least one backend profile")
	}

	c := &CarbonAware{profiles: make(map[BackendID]CarbonProfile, len(profiles))}

	for id, p := range profiles {

		if id == "" {

			return nil, errors.New("backend ID must not be empty")
		}

		if !finiteNonnegative(p.EnergyWh) || !finiteNonnegative(p.IntensityGPerKWh) {

			return nil, fmt.Errorf("backend %q: energy and carbon intensity must be finite and nonnegative", id)
		}

		c.profiles[id] = p
	}

	return c, nil
}

func finiteNonnegative(v float64) bool {

	return !math.IsNaN(v) && !math.IsInf(v, 0) && v >= 0
}

func (c *CarbonAware) Pick(ctx context.Context, _ Input, eligible Candidates) (Selection, error) {
	pickErr := check(ctx, eligible)

	if pickErr != nil {

		return Selection{}, pickErr
	}

	start := int((c.next.Add(1) - 1) % uint64(eligible.Len()))
	var best BackendID
	bestGrams := math.Inf(1)

	for offset := range eligible.Len() {
		id := eligible.At((start + offset) % eligible.Len())
		p, ok := c.profiles[id]

		if !ok {

			return Selection{}, fmt.Errorf("%w: no carbon profile for %q", ErrInvalidCandidates, id)
		}

		grams := p.GramsCO2e()

		if grams < bestGrams {
			best, bestGrams = id, grams
		}

	}

	return Selection{BackendID: best}, nil
}
