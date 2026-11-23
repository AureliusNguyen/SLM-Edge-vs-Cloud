# Extract task: token F1 vs LLM judge

Judge: qwen/qwen3.8-27b (temperature 0, reasoning effort none, CORRECT/WRONG against the SQuAD reference answers).

| model | n | mean F1 | exact (F1=1) | judge correct | F1<0.5 but judge correct | F1=1 but judge wrong |
|---|---|---|---|---|---|---|
| llama | 100 | 0.83 | 0.66 | 0.91 | 8 | 0 |
| cloud | 100 | 0.88 | 0.71 | 0.99 | 7 | 0 |
| qwen_nothink | 100 | 0.55 | 0.23 | 0.93 | 40 | 0 |
| qwen_think | 100 | 0.44 | 0.11 | 0.96 | 53 | 0 |
| phi35 | 100 | 0.84 | 0.66 | 0.93 | 6 | 0 |
| gemma2 | 100 | 0.84 | 0.68 | 0.96 | 10 | 0 |

Unclear judge replies (counted as wrong): 0.
The last two columns are where F1 and the judge disagree; read a few of them in the CSV to check the judge.
