# Hourly carbon intensity and routing (llama, cloud estimate: low)

Grid: miso_hourly_ci_2024.csv, 8784 hours. Mean over hours 445 g/kWh; 10th / 50th / 90th percentile 353 / 448 / 528; min 247, max 632. Until now we used a fixed 420 g/kWh.

Mean by hour of day (local time, hour ending):

| hour | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 | 16 | 17 | 18 | 19 | 20 | 21 | 22 | 23 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| g/kWh | 446 | 436 | 427 | 423 | 423 | 427 | 435 | 443 | 446 | 442 | 442 | 444 | 443 | 441 | 439 | 438 | 440 | 446 | 456 | 467 | 472 | 472 | 466 | 456 |

## When is the cloud lower-carbon than running locally?

Local carbon = device Wh x grid at that hour. Cloud carbon = cloud Wh x 350 g/kWh (+ the tiny device energy while waiting). The cloud wins in an hour when the grid is above the break-even intensity.

| profile | task | local Wh | cloud Wh | break-even g/kWh | hours cloud is lower-carbon | energy-best |
|---|---|---|---|---|---|---|
| gpu | yesno | 0.0008 | 0.24 | never | 0% | local |
| gpu | classify | 0.0007 | 0.24 | 1442404 | 0% | local |
| gpu | extract | 0.0021 | 0.24 | 192630 | 0% | local |
| gpu | math | 0.0520 | 0.24 | 1643 | 0% | local |
| cpu | yesno | 0.0180 | 0.24 | 5493 | 0% | local |
| cpu | classify | 0.0080 | 0.24 | 11310 | 0% | local |
| cpu | extract | 0.0197 | 0.24 | 4663 | 0% | local |
| cpu | math | 0.0966 | 0.24 | 877 | 0% | local |
| docker-full | yesno | 0.0233 | 0.24 | 4079 | 0% | local |
| docker-full | classify | 0.0096 | 0.24 | 9308 | 0% | local |
| docker-full | extract | 0.0211 | 0.24 | 4332 | 0% | local |
| docker-full | math | 0.1153 | 0.24 | 734 | 0% | local |
| docker-2cpu | yesno | 0.0338 | 0.24 | 2703 | 0% | local |
| docker-2cpu | classify | 0.0130 | 0.24 | 6785 | 0% | local |
| docker-2cpu | extract | 0.0294 | 0.24 | 3028 | 0% | local |
| docker-2cpu | math | 0.1969 | 0.24 | 429 | 60% | local |

## Carbon-aware routing over a year

A request arrives every hour of the year for each task. 'static' = the task rule (yes/no and extract local, classify and math cloud). 'hourly' = also send a local task to the cloud in hours when the cloud is lower-carbon, and keep a cloud task local when local is lower-carbon (quality ignored, to show the carbon side alone). Error of flat = how far the yearly carbon computed with a fixed 420 g/kWh is from the hour-by-hour value.

| profile | static g/req (hourly grid) | static g/req (flat grid) | error of flat | carbon-only hourly g/req | saving vs static |
|---|---|---|---|---|---|
| gpu | 0.0425 | 0.0425 | -0% | 0.0062 | 85% |
| cpu | 0.0464 | 0.0461 | -1% | 0.0158 | 66% |
| docker-full | 0.0471 | 0.0468 | -1% | 0.0188 | 60% |
| docker-2cpu | 0.0492 | 0.0488 | -1% | 0.0286 | 42% |

Energy-best and carbon-best disagree in an hour when the energy-best column says local but the cloud is lower-carbon in that hour, i.e. the share in the 'hours cloud is lower-carbon' column for rows marked local.
