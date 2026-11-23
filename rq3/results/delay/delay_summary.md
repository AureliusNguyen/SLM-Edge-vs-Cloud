# Live runs with an injected cloud delay

Gateway on the GPU laptop (Llama 3.2 3B local, gpt-oss-120b on Groq over Wi-Fi), 25 questions per task, `-cloud-delay` added to every cloud call. Questions Groq still rate-limited after six tries are left out (count in brackets). Score uses F1 for extract. Device energy is measured in the gateway (LibreHardwareMonitor + nvidia-smi, above idle); carbon adds 0.24 Wh per cloud call.

| policy | cloud delay | n | score | answered locally | escalated | median s | mean s | device Wh/req | gCO2e/req |
|---|---|---|---|---|---|---|---|---|---|
| task-rule | 0ms | 100 | 0.871 | 50% | 0% | 0.29 | 0.37 | 0.0011 | 0.0425 |
| rule+cascade | 0ms | 100 | 0.905 | 24% | 26% | 0.44 | 0.48 | 0.0014 | 0.0644 |
| task-rule | 300ms | 99 (1 rate-limited) | 0.870 | 51% | 0% | 0.38 | 0.50 | 0.0014 | 0.0421 |
| rule+cascade | 300ms | 67 (20 rate-limited) | 0.885 | 36% | 27% | 0.63 | 0.61 | 0.0008 | 0.0603 |
