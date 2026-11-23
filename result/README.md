# Results for the 2026-11-23 progress presentation (since the midterm)

`talk_notes_zh.md`: talk outline in Chinese (about 10 minutes, six parts) with a glossary. `FAQ.md`: questions and answers on the policies, tasks and carbon accounting.
Figures, in talk order:

| file | source |
|---|---|
| 02_system_flow.png | `make_figures.py` |
| 04_rq1_quality_all_models.png | `make_figures.py` (numbers from `shuyuan_rq1/results`) |
| 05_rq1_confidence.png | `shuyuan_rq1/results/figures/4_confidence.png` |
| 06_rq2_carbon_per_request.png, 07_rq2_latency.png | `rq2/results/rq2_all_*.png` |
| 08_rq3_policies_llama.png | `rq3/results/rq3_llama.png` |
| 09_three_models_policies.png | `make_figures.py` (from `rq3/results_extra/rq3_*.csv`) |
| 10_rq3_embodied_carbonaware.png, 10b_hourly_grid.png | `rq3/results/rq3_compare.png`, `hourly_ci.png` |
| 11_network_delay.png | `make_figures.py` (from `rq3/results_extra/rq3_*.md`) |
| 12_load_test.png | `load/results/miss_rate.png` |

Regenerate the new figures with `python result/make_figures.py`.
