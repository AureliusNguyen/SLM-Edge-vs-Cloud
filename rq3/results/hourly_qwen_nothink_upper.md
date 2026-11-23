# Hourly carbon intensity and routing (qwen_nothink, cloud estimate: upper)

Grid: miso_hourly_ci_2024.csv, 8784 hours. Mean over hours 445 g/kWh; 10th / 50th / 90th percentile 353 / 448 / 528; min 247, max 632. Until now we used a fixed 420 g/kWh.

Mean by hour of day (local time, hour ending):

| hour | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 | 16 | 17 | 18 | 19 | 20 | 21 | 22 | 23 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| g/kWh | 446 | 436 | 427 | 423 | 423 | 427 | 435 | 443 | 446 | 442 | 442 | 444 | 443 | 441 | 439 | 438 | 440 | 446 | 456 | 467 | 472 | 472 | 466 | 456 |

## When is the cloud lower-carbon than running locally?

Local carbon = device Wh x grid at that hour. Cloud carbon = cloud Wh x 350 g/kWh (+ the tiny device energy while waiting). The cloud wins in an hour when the grid is above the break-even intensity.

| profile | task | local Wh | cloud Wh | break-even g/kWh | hours cloud is lower-carbon | energy-best |
|---|---|---|---|---|---|---|
| gpu | yesno | 0.0007 | 8.07 | never | 0% | local |
| gpu | classify | 0.0008 | 6.52 | 16554183 | 0% | local |
| gpu | extract | 0.0028 | 8.13 | 2539996 | 0% | local |
| gpu | math | 0.0333 | 26 | 280538 | 0% | local |
| cpu | yesno | 0.0120 | 8.07 | 304428 | 0% | local |
| cpu | classify | 0.0055 | 6.52 | 468398 | 0% | local |
| cpu | extract | 0.0179 | 8.13 | 175740 | 0% | local |
| cpu | math | 0.0637 | 26 | 144809 | 0% | local |
| docker-full | yesno | 0.0144 | 8.07 | 241901 | 0% | local |
| docker-full | classify | 0.0073 | 6.52 | 339220 | 0% | local |
| docker-full | extract | 0.0196 | 8.13 | 158977 | 0% | local |
| docker-full | math | 0.0629 | 26 | 146557 | 0% | local |
| docker-2cpu | yesno | 0.0224 | 8.07 | 143525 | 0% | local |
| docker-2cpu | classify | 0.0091 | 6.52 | 270439 | 0% | local |
| docker-2cpu | extract | 0.0256 | 8.13 | 118835 | 0% | local |
| docker-2cpu | math | 0.1023 | 26 | 89644 | 0% | local |

## Carbon-aware routing over a year

A request arrives every hour of the year for each task. 'static' = the task rule (yes/no and extract local, classify and math cloud). 'hourly' = also send a local task to the cloud in hours when the cloud is lower-carbon, and keep a cloud task local when local is lower-carbon (quality ignored, to show the carbon side alone). Error of flat = how far the yearly carbon computed with a fixed 420 g/kWh is from the hour-by-hour value.

| profile | static g/req (hourly grid) | static g/req (flat grid) | error of flat | carbon-only hourly g/req | saving vs static |
|---|---|---|---|---|---|
| gpu | 2.8458 | 2.8458 | -0% | 0.0042 | 100% |
| cpu | 2.8487 | 2.8485 | -0% | 0.0110 | 100% |
| docker-full | 2.8492 | 2.8490 | -0% | 0.0116 | 100% |
| docker-2cpu | 2.8507 | 2.8504 | -0% | 0.0177 | 99% |

Energy-best and carbon-best disagree in an hour when the energy-best column says local but the cloud is lower-carbon in that hour, i.e. the share in the 'hours cloud is lower-carbon' column for rows marked local.
