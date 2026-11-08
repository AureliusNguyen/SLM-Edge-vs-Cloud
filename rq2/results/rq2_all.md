# RQ2 results

One row per model, device profile, network and task. Times are medians, energy and carbon are means per request.
Profile suffix: /isolated = 10 s pause after each request, so the energy includes the GPU/CPU winding down (one request on an otherwise idle device); /busy = requests back to back (marginal energy on a busy device).

| model | tier | profile | network | task | n | score | TTFT s | total s | out tokens | avg W | idle W | device Wh | device J/token | cloud Wh (est.) | gCO2e | RTT ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cloud | cloud | gpu/isolated | hotspot | yesno | 20 | 1 | 0.409 | 0.696 | 96 | 23.6 | 24.9 | -0.00177 | -0.0622 | 0.24 | 0.084 | 24.9 |
| cloud | cloud | gpu/isolated | hotspot | classify | 20 | 0.9 | 0.455 | 0.615 | 69.5 | 24.5 | 24.9 | -0.00336 | -0.152 | 0.24 | 0.084 | 24.9 |
| cloud | cloud | gpu/isolated | hotspot | extract | 20 | 0.95 | 0.428 | 0.666 | 94.5 | 25.1 | 24.9 | 0.00191 | 0.0697 | 0.24 | 0.0848 | 24.9 |
| cloud | cloud | gpu/isolated | hotspot | math | 20 | 1 | 0.412 | 1.01 | 296 | 23.7 | 24.9 | -0.00624 | -0.0663 | 0.24 | 0.084 | 24.9 |
| cloud | cloud | gpu/isolated | wifi | yesno | 20 | 1 | 0.207 | 0.417 | 96.5 | 25.5 | 23.8 | 0.00273 | 0.101 | 0.24 | 0.0851 | 12.4 |
| cloud | cloud | gpu/isolated | wifi | classify | 20 | 0.9 | 0.273 | 0.406 | 67.5 | 23.1 | 23.8 | 0.000617 | 0.0283 | 0.24 | 0.0843 | 12.4 |
| cloud | cloud | gpu/isolated | wifi | extract | 20 | 0.95 | 0.192 | 0.398 | 94.5 | 24.4 | 23.8 | 0.0017 | 0.0626 | 0.24 | 0.0847 | 12.4 |
| cloud | cloud | gpu/isolated | wifi | math | 20 | 1 | 0.257 | 0.777 | 289 | 23.6 | 23.8 | 0.000835 | 0.00961 | 0.24 | 0.0844 | 12.4 |
| llama | local | cpu/busy | wifi | yesno | 20 | 0.85 | 0.656 | 0.691 | 2 | 113 | 24.9 | 0.018 | 31.6 | - | 0.00757 | 0.4 |
| llama | local | cpu/busy | wifi | classify | 20 | 0.6 | 0.277 | 0.311 | 2 | 115 | 24.9 | 0.00804 | 13.8 | - | 0.00338 | 0.4 |
| llama | local | cpu/busy | wifi | extract | 20 | 0.83 | 0.703 | 1.01 | 6 | 106 | 24.9 | 0.0197 | 7.03 | - | 0.00828 | 0.4 |
| llama | local | cpu/busy | wifi | math | 20 | 0.75 | 0.326 | 5.57 | 139 | 77.6 | 24.9 | 0.0966 | 2.04 | - | 0.0406 | 0.4 |
| llama | local | cpu/isolated | wifi | yesno | 20 | 0.85 | 0.716 | 0.751 | 2 | 28.3 | 15.4 | 0.0329 | 57.9 | - | 0.0138 | 15.5 |
| llama | local | cpu/isolated | wifi | classify | 20 | 0.6 | 0.295 | 0.33 | 2 | 17.1 | 15.4 | 0.0129 | 22.2 | - | 0.00543 | 15.5 |
| llama | local | cpu/isolated | wifi | extract | 20 | 0.83 | 0.661 | 0.965 | 6 | 25.8 | 15.4 | 0.0261 | 9.29 | - | 0.0109 | 15.5 |
| llama | local | cpu/isolated | wifi | math | 20 | 0.75 | 0.317 | 5.13 | 139 | 99.7 | 15.4 | 0.181 | 3.82 | - | 0.076 | 15.5 |
| llama | local | cpu4/isolated | wifi | yesno | 20 | 0.85 | 1.24 | 1.28 | 2 | 39.2 | 14.2 | 0.0355 | 62.3 | - | 0.0149 | 14.5 |
| llama | local | cpu4/isolated | wifi | classify | 20 | 0.6 | 0.503 | 0.547 | 2 | 15.6 | 14.2 | 0.0136 | 23.4 | - | 0.00573 | 14.5 |
| llama | local | cpu4/isolated | wifi | extract | 20 | 0.83 | 1.2 | 1.67 | 6 | 43.3 | 14.2 | 0.04 | 14.3 | - | 0.0168 | 14.5 |
| llama | local | cpu4/isolated | wifi | math | 20 | 0.75 | 0.541 | 6.84 | 139 | 91.3 | 14.2 | 0.208 | 4.44 | - | 0.0875 | 14.5 |
| llama | local | docker-2cpu/busy | wifi | yesno | 20 | 0.85 | 2.55 | 2.62 | 2 | 70.1 | 27.8 | 0.0338 | 58 | - | 0.0142 | 15.4 |
| llama | local | docker-2cpu/busy | wifi | classify | 20 | 0.6 | 1.13 | 1.2 | 2 | 67.2 | 27.8 | 0.013 | 22.3 | - | 0.00546 | 15.4 |
| llama | local | docker-2cpu/busy | wifi | extract | 20 | 0.87 | 2.52 | 3.3 | 6 | 69.4 | 27.8 | 0.0294 | 11.5 | - | 0.0124 | 15.4 |
| llama | local | docker-2cpu/busy | wifi | math | 20 | 0.75 | 1.17 | 12.1 | 158 | 78.7 | 27.8 | 0.197 | 3.71 | - | 0.0827 | 15.4 |
| llama | local | docker-full/busy | wifi | yesno | 20 | 0.85 | 0.829 | 0.864 | 2 | 115 | 26.9 | 0.0233 | 40 | - | 0.00979 | 0.3 |
| llama | local | docker-full/busy | wifi | classify | 20 | 0.6 | 0.381 | 0.416 | 2 | 108 | 26.9 | 0.00964 | 16.5 | - | 0.00405 | 0.3 |
| llama | local | docker-full/busy | wifi | extract | 20 | 0.87 | 0.986 | 1.2 | 6 | 98.7 | 26.9 | 0.0211 | 8.21 | - | 0.00886 | 0.3 |
| llama | local | docker-full/busy | wifi | math | 20 | 0.75 | 0.464 | 6.29 | 158 | 78 | 26.9 | 0.115 | 2 | - | 0.0484 | 0.3 |
| llama | local | gpu/busy | wifi | yesno | 20 | 0.8 | 0.0825 | 0.103 | 2 | 43.8 | 15.7 | 0.000811 | 1.39 | - | 0.00034 | 15.9 |
| llama | local | gpu/busy | wifi | classify | 20 | 0.6 | 0.08 | 0.099 | 2 | 39.7 | 15.7 | 0.000675 | 1.16 | - | 0.000284 | 15.9 |
| llama | local | gpu/busy | wifi | extract | 20 | 0.83 | 0.0725 | 0.145 | 6 | 56.5 | 15.7 | 0.00214 | 0.758 | - | 0.000897 | 15.9 |
| llama | local | gpu/busy | wifi | math | 20 | 0.75 | 0.0655 | 1.4 | 141 | 121 | 15.7 | 0.052 | 1.06 | - | 0.0218 | 15.9 |
| llama | local | gpu/isolated | wifi | yesno | 20 | 0.8 | 0.342 | 0.362 | 2 | 25.5 | 17.5 | 0.0249 | 42.8 | - | 0.0105 | 15.7 |
| llama | local | gpu/isolated | wifi | classify | 20 | 0.6 | 0.322 | 0.339 | 2 | 17 | 17.5 | 0.0137 | 23.5 | - | 0.00577 | 15.7 |
| llama | local | gpu/isolated | wifi | extract | 20 | 0.83 | 0.327 | 0.418 | 6 | 17.8 | 17.5 | 0.023 | 8.15 | - | 0.00965 | 15.7 |
| llama | local | gpu/isolated | wifi | math | 20 | 0.75 | 0.316 | 1.72 | 145 | 63.4 | 17.5 | 0.0745 | 1.53 | - | 0.0313 | 15.7 |
| qwen | local | cpu/busy | wifi | yesno | 20 | 0.9 | 0.417 | 0.461 | 3 | 113 | 22.8 | 0.012 | 14.4 | - | 0.00504 | 0.2 |
| qwen | local | cpu/busy | wifi | classify | 20 | 0.3 | 0.205 | 0.226 | 2 | 110 | 22.8 | 0.00549 | 9.88 | - | 0.00231 | 0.2 |
| qwen | local | cpu/busy | wifi | extract | 20 | 0.59 | 0.444 | 0.639 | 14.5 | 115 | 22.8 | 0.0179 | 3.83 | - | 0.00751 | 0.2 |
| qwen | local | cpu/busy | wifi | math | 20 | 0.25 | 0.254 | 3.6 | 151 | 79.7 | 22.8 | 0.0637 | 1.32 | - | 0.0267 | 0.2 |
| qwen | local | cpu/isolated | wifi | yesno | 20 | 0.9 | 0.438 | 0.482 | 3 | 22.4 | 21.3 | 0.0111 | 13.4 | - | 0.00468 | 1 |
| qwen | local | cpu/isolated | wifi | classify | 20 | 0.3 | 0.225 | 0.247 | 2 | 23.5 | 21.3 | 0.00165 | 2.96 | - | 0.000692 | 1 |
| qwen | local | cpu/isolated | wifi | extract | 20 | 0.59 | 0.461 | 0.662 | 14.5 | 26.5 | 21.3 | 0.0196 | 4.2 | - | 0.00824 | 1 |
| qwen | local | cpu/isolated | wifi | math | 20 | 0.25 | 0.239 | 3.41 | 151 | 86.4 | 21.3 | 0.0981 | 2.03 | - | 0.0412 | 1 |
| qwen | local | docker-2cpu/busy | wifi | yesno | 20 | 0.9 | 1.59 | 1.67 | 3 | 71.7 | 24.9 | 0.0224 | 26.9 | - | 0.00941 | 0.7 |
| qwen | local | docker-2cpu/busy | wifi | classify | 20 | 0.3 | 0.712 | 0.753 | 2 | 68.2 | 24.9 | 0.00905 | 16.3 | - | 0.0038 | 0.7 |
| qwen | local | docker-2cpu/busy | wifi | extract | 20 | 0.55 | 1.48 | 2.1 | 14.5 | 72.4 | 24.9 | 0.0256 | 5.2 | - | 0.0108 | 0.7 |
| qwen | local | docker-2cpu/busy | wifi | math | 5 | 0.4 | 0.722 | 5.68 | 124 | 81.3 | 27.1 | 0.102 | 2.38 | - | 0.043 | 0.3 |
| qwen | local | docker-full/busy | wifi | yesno | 20 | 0.9 | 0.542 | 0.585 | 3 | 114 | 28.6 | 0.0144 | 17.3 | - | 0.00605 | 0.4 |
| qwen | local | docker-full/busy | wifi | classify | 20 | 0.3 | 0.27 | 0.292 | 2 | 116 | 28.6 | 0.00734 | 13.2 | - | 0.00308 | 0.4 |
| qwen | local | docker-full/busy | wifi | extract | 20 | 0.55 | 0.516 | 0.759 | 14.5 | 114 | 28.6 | 0.0196 | 3.97 | - | 0.00823 | 0.4 |
| qwen | local | docker-full/busy | wifi | math | 20 | 0.2 | 0.353 | 3.83 | 152 | 78.5 | 28.6 | 0.0629 | 1.26 | - | 0.0264 | 0.4 |
| qwen | local | gpu/busy | wifi | yesno | 20 | 0.9 | 0.0545 | 0.0685 | 3 | 59.4 | 23 | 0.000701 | 0.841 | - | 0.000295 | 14.8 |
| qwen | local | gpu/busy | wifi | classify | 20 | 0.3 | 0.056 | 0.0695 | 2 | 62 | 23 | 0.000755 | 1.36 | - | 0.000317 | 14.8 |
| qwen | local | gpu/busy | wifi | extract | 20 | 0.49 | 0.042 | 0.132 | 17.5 | 90.8 | 23 | 0.00282 | 0.57 | - | 0.00118 | 14.8 |
| qwen | local | gpu/busy | wifi | math | 20 | 0.25 | 0.038 | 0.948 | 153 | 123 | 23 | 0.0333 | 0.643 | - | 0.014 | 14.8 |
| qwen | local | gpu/isolated | wifi | yesno | 20 | 0.9 | 0.296 | 0.351 | 3 | 22.6 | 20.6 | 0.0222 | 26.6 | - | 0.00931 | 15 |
| qwen | local | gpu/isolated | wifi | classify | 20 | 0.3 | 0.254 | 0.344 | 2 | 21 | 20.6 | 0.0099 | 17.8 | - | 0.00416 | 15 |
| qwen | local | gpu/isolated | wifi | extract | 20 | 0.51 | 0.283 | 0.469 | 17.5 | 41 | 20.6 | 0.0666 | 12.8 | - | 0.028 | 15 |
| qwen | local | gpu/isolated | wifi | math | 20 | 0.35 | 0.273 | 1.3 | 152 | 52.1 | 20.6 | 0.0547 | 1.06 | - | 0.023 | 15 |

## Assumptions

- Device energy: measured power above the idle power taken before each run, integrated from the start of a request to the end of the pause after it.
- Cloud energy: 0.24 Wh per prompt (estimate; the provider's data center cannot be measured).
- Edge grid carbon intensity: 420 gCO2e/kWh (EPA eGRID2023 rev2, MROW subregion total output CO2e 926.6 lb/MWh (Minnesota)).
- Data-center grid carbon intensity: 350 gCO2e/kWh (EPA eGRID2023 rev2, U.S. total output CO2e 770.9 lb/MWh, since the provider's region is unknown).
- Device J/token: mean extra device energy divided by mean output tokens (as in Masthan Ali et al., E-Energy '26). It includes prompt processing, so it is high for tasks with long prompts and 2-6 token answers.
- Network transfer energy is not included.
