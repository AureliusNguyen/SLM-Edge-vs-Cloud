package main

import (
	"context"
	"strings"
	"testing"

	"github.com/AureliusNguyen/SLM-Edge-vs-Cloud/Load-Balancer/strategy"
)

func testRouter(t *testing.T, localUp bool) *router {
	t.Helper()
	r, err := newRouter(defaultProfiles, map[strategy.BackendID]func() bool{
		"local": func() bool { return localUp },
		"cloud": func() bool { return true },
	})

	if err != nil {
		t.Fatal(err)
	}

	return r
}

func TestRoute(t *testing.T) {
	cases := []struct {
		name, task, forced string
		localUp            bool
		want               strategy.BackendID
		reason             string
	}{
		{"easy task goes to lower-carbon local", "yesno", "", true, "local", "picked local (0.0135 g) over cloud (0.0960 g)"},
		{"math is gated to cloud", "math", "", true, "cloud", "needs cloud; picked cloud (0.0960 g)"},
		{"unknown task is gated to cloud", "", "", true, "cloud", "quality gate"},
		{"easy task uses cloud when local is down", "yesno", "", false, "cloud", "ok locally; picked cloud (0.0960 g)"},
		{"forced local ignores the gate", "math", "local", true, "local", "forced"},
		{"forced local never falls back", "yesno", "local", false, "local", "forced"},
	}

	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			got, reason, err := testRouter(t, c.localUp).route(context.Background(), c.task, c.forced)

			if err != nil {
				t.Fatal(err)
			}

			if got != c.want || !strings.Contains(reason, c.reason) {
				t.Fatalf("got %q (%s), want %q (%s)", got, reason, c.want, c.reason)
			}

		})
	}

}

func TestRouteErrors(t *testing.T) {
	_, _, err := testRouter(t, true).route(context.Background(), "yesno", "mars")

	if err == nil {
		t.Fatal("unknown forced tier was accepted")
	}

	r, err := newRouter(defaultProfiles, map[strategy.BackendID]func() bool{
		"local": func() bool { return true },
		"cloud": func() bool { return false },
	})

	if err != nil {
		t.Fatal(err)
	}

	_, _, err = r.route(context.Background(), "math", "")

	if err == nil {
		t.Fatal("math with cloud down should fail, not run locally")
	}

}
