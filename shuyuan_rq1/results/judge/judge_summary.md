# Extract task (SQuAD): token F1 vs two LLM judges

100 questions per model. Judges answer CORRECT/WRONG against the SQuAD reference answers (temperature 0).

| model | mean F1 | exact match | judge gpt-oss-20b | judge Qwen3.8 27B | judges agree |
|---|---|---|---|---|---|
| Llama 3.2 3B | 0.83 | 0.66 | 0.93 | 0.91 | 98% |
| Qwen3 1.7B, think off | 0.55 | 0.23 | 0.95 | 0.93 | 98% |
| Qwen3 1.7B, think on | 0.44 | 0.11 | 0.96 | 0.96 | 98% |
| gpt-oss-120b (cloud) | 0.88 | 0.71 | 1.00 | 0.99 | 99% |

- Token F1 badly underrates Qwen: 40-53 of its 100 replies have F1 < 0.5 but both judges call them correct (full-sentence answers).
  Llama and the cloud have only 7-9 such cases. With the judges, all four models are within 0.09 of each other on extract.
- The two judges come from different families and agree on 98-99% of replies, with no sign that either favours
  its own family. Cohen's kappa is 0.74-0.86 for the local models; for the cloud it is 0.00 only because both
  judges mark almost every reply correct (kappa breaks down when one class is ~100%).
- Caveat: the judges are lenient (e.g. "MSPs" accepted for "a small number of MSPs"). Spot-check some of the
  F1 < 0.5 / judge-correct rows in judge_gptoss.csv before quoting the numbers.
