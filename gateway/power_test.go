package main

import (
	"encoding/json"
	"math"
	"testing"
	"time"
)

func TestIntegrate(t *testing.T) {
	t0 := time.Unix(1000, 0)
	at := func(s float64) time.Time { return t0.Add(time.Duration(s * float64(time.Second))) }
	samples := []powerSample{
		{at(0), 20, 1}, {at(1), 40, 1}, {at(2), 40, 2}, {at(3), 20, 1},
	}
	// idle 20 W: [0,1] avg 30 -> 10 J; [1,2] 40 -> 20 J split by 2 -> 10 J; [2,3] 30 -> 10 J
	if got := integrate(samples, 20, at(0), at(3)); math.Abs(got-30) > 1e-9 {
		t.Errorf("whole window: got %v J, want 30", got)
	}
	if got := integrate(samples, 20, at(0.5), at(1)); math.Abs(got-5) > 1e-9 {
		t.Errorf("part of an interval: got %v J, want 5", got)
	}
}

func TestLHMFind(t *testing.T) {
	var root lhmNode
	_ = json.Unmarshal([]byte(`{"Text":"Sensor","Children":[{"Text":"CPU","Children":[
		{"Text":"CPU Package","Value":"63.0 °C"},{"Text":"CPU Package","Value":"41,5 W"}]}]}`), &root)
	if w, ok := root.find("CPU Package"); !ok || w != 41.5 {
		t.Errorf("got %v %v, want the power reading, not the temperature", w, ok)
	}
}
