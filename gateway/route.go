package main

import (
	"context"
	"fmt"

	"github.com/AureliusNguyen/SLM-Edge-vs-Cloud/Load-Balancer/strategy"
)

// Per-request energy and grid intensity (gCO2e/kWh), see rq2/README.md.
// Local: measured extra device energy of Llama 3.2 3B in Docker on CPU for short
// tasks (yes/no 0.023 Wh, extract 0.021 Wh). Cloud: Google's median Gemini prompt
// (0.24 Wh), an estimate; the provider's own energy cannot be measured.
// Intensity: EPA eGRID2023, MROW subregion for our machines, U.S. total for the cloud.
var defaultProfiles = map[strategy.BackendID]strategy.CarbonProfile{
	"local": {EnergyWh: 0.02, IntensityGPerKWh: 420},
	"cloud": {EnergyWh: 0.24, IntensityGPerKWh: 350},
}

// localTasks is the quality gate: task types a small local model handles well.
// Everything else (classify, math, unknown) may only go to the cloud.
// From RQ1 (100 questions per task): Llama 3.2 3B gets 0.78 on yes/no and 0.91-0.93
// on extract by LLM judges, but only 0.55 on classify and 0.73 on math.
var localTasks = map[string]bool{"yesno": true, "extract": true}

type router struct {
	picker   strategy.Picker
	profiles map[strategy.BackendID]strategy.CarbonProfile
	ready    map[strategy.BackendID]func() bool
}

func newRouter(profiles map[strategy.BackendID]strategy.CarbonProfile, ready map[strategy.BackendID]func() bool) (*router, error) {
	picker, err := strategy.NewCarbonAware(profiles)

	if err != nil {

		return nil, err
	}

	return &router{picker: picker, profiles: profiles, ready: ready}, nil
}

// route picks a tier: a forced tier as-is (no fallback), otherwise the
// lowest-carbon healthy tier that passes the quality gate.
func (r *router) route(ctx context.Context, task, forced string) (strategy.BackendID, string, error) {

	if forced != "" {
		id := strategy.BackendID(forced)

		if r.ready[id] == nil {

			return "", "", fmt.Errorf("unknown tier %q", forced)
		}

		return id, "forced", nil
	}

	allowed := []strategy.BackendID{"cloud"}
	gate := "quality gate: " + task + " needs cloud"

	if localTasks[task] {
		allowed = []strategy.BackendID{"local", "cloud"}
		gate = "quality gate: " + task + " ok locally"
	}

	var healthy []strategy.BackendID

	for _, id := range allowed {

		if r.ready[id]() {
			healthy = append(healthy, id)
		}

	}

	candidates, err := strategy.NewCandidates(healthy...)

	if err != nil {

		return "", "", err
	}

	selection, err := r.picker.Pick(ctx, strategy.Input{}, candidates)

	if err != nil {

		return "", "", fmt.Errorf("%s, no healthy tier: %w", gate, err)
	}

	reason := fmt.Sprintf("%s; picked %s (%.4f g)", gate, selection.BackendID, r.profiles[selection.BackendID].GramsCO2e())

	for _, id := range healthy {

		if id != selection.BackendID {
			reason += fmt.Sprintf(" over %s (%.4f g)", id, r.profiles[id].GramsCO2e())
		}

	}

	return selection.BackendID, reason, nil
}
