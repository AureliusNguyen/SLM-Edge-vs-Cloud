# Hourly carbon intensity and routing (llama, cloud estimate: upper)

Grid: miso_hourly_ci_2024.csv, 8784 hours. Mean over hours 445 g/kWh; 10th / 50th / 90th percentile 353 / 448 / 528; min 247, max 632. Until now we used a fixed 420 g/kWh.

Mean by hour of day (local time, hour ending):

| hour | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 | 16 | 17 | 18 | 19 | 20 | 21 | 22 | 23 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| g/kWh | 446 | 436 | 427 | 423 | 423 | 427 | 435 | 443 | 446 | 442 | 442 | 444 | 443 | 441 | 439 | 438 | 440 | 446 | 456 | 467 | 472 | 472 | 466 | 456 |

## When is the cloud lower-carbon than running locally?

Local carbon = device Wh x grid at that hour. Cloud carbon = cloud Wh x 350 g/kWh (+ the tiny device energy while waiting). The cloud wins in an hour when the grid is above the break-even intensity.

| profile | task | local Wh | cloud Wh | break-even g/kWh | hours cloud is lower-carbon | energy-best |
|---|---|---|---|---|---|---|
| gpu | yesno | 0.0008 | 8.07 | never | 0% | local |
| gpu | classify | 0.0007 | 6.52 | 39180471 | 0% | local |
| gpu | extract | 0.0021 | 8.13 | 6523073 | 0% | local |
| gpu | math | 0.0520 | 26 | 177992 | 0% | local |
| cpu | yesno | 0.0180 | 8.07 | 184787 | 0% | local |
| cpu | classify | 0.0080 | 6.52 | 307208 | 0% | local |
| cpu | extract | 0.0197 | 8.13 | 157908 | 0% | local |
| cpu | math | 0.0966 | 26 | 95048 | 0% | local |
| docker-full | yesno | 0.0233 | 8.07 | 137221 | 0% | local |
| docker-full | classify | 0.0096 | 6.52 | 252831 | 0% | local |
| docker-full | extract | 0.0211 | 8.13 | 146703 | 0% | local |
| docker-full | math | 0.1153 | 26 | 79487 | 0% | local |
| docker-2cpu | yesno | 0.0338 | 8.07 | 90914 | 0% | local |
| docker-2cpu | classify | 0.0130 | 6.52 | 184310 | 0% | local |
| docker-2cpu | extract | 0.0294 | 8.13 | 102527 | 0% | local |
| docker-2cpu | math | 0.1969 | 26 | 46420 | 0% | local |

## Carbon-aware routing over a year

A request arrives every hour of the year for each task. 'static' = the task rule (yes/no and extract local, classify and math cloud). 'hourly' = also send a local task to the cloud in hours when the cloud is lower-carbon, and keep a cloud task local when local is lower-carbon (quality ignored, to show the carbon side alone). Error of flat = how far the yearly carbon computed with a fixed 420 g/kWh is from the hour-by-hour value.

| profile | static g/req (hourly grid) | static g/req (flat grid) | error of flat | carbon-only hourly g/req | saving vs static |
|---|---|---|---|---|---|
| gpu | 2.8457 | 2.8457 | -0% | 0.0062 | 100% |
| cpu | 2.8496 | 2.8494 | -0% | 0.0158 | 99% |
| docker-full | 2.8503 | 2.8501 | -0% | 0.0188 | 99% |
| docker-2cpu | 2.8524 | 2.8520 | -0% | 0.0304 | 99% |

Energy-best and carbon-best disagree in an hour when the energy-best column says local but the cloud is lower-carbon in that hour, i.e. the share in the 'hours cloud is lower-carbon' column for rows marked local.
