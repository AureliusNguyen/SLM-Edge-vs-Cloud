# Hourly carbon intensity and routing (qwen_nothink, cloud estimate: low)

Grid: miso_hourly_ci_2024.csv, 8784 hours. Mean over hours 445 g/kWh; 10th / 50th / 90th percentile 353 / 448 / 528; min 247, max 632. Until now we used a fixed 420 g/kWh.

Mean by hour of day (local time, hour ending):

| hour | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 | 16 | 17 | 18 | 19 | 20 | 21 | 22 | 23 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| g/kWh | 446 | 436 | 427 | 423 | 423 | 427 | 435 | 443 | 446 | 442 | 442 | 444 | 443 | 441 | 439 | 438 | 440 | 446 | 456 | 467 | 472 | 472 | 466 | 456 |

## When is the cloud lower-carbon than running locally?

Local carbon = device Wh x grid at that hour. Cloud carbon = cloud Wh x 350 g/kWh (+ the tiny device energy while waiting). The cloud wins in an hour when the grid is above the break-even intensity.

| profile | task | local Wh | cloud Wh | break-even g/kWh | hours cloud is lower-carbon | energy-best |
|---|---|---|---|---|---|---|
| gpu | yesno | 0.0007 | 0.24 | never | 0% | local |
| gpu | classify | 0.0008 | 0.24 | 609432 | 0% | local |
| gpu | extract | 0.0028 | 0.24 | 75007 | 0% | local |
| gpu | math | 0.0333 | 0.24 | 2590 | 0% | local |
| cpu | yesno | 0.0120 | 0.24 | 9050 | 0% | local |
| cpu | classify | 0.0055 | 0.24 | 17244 | 0% | local |
| cpu | extract | 0.0179 | 0.24 | 5190 | 0% | local |
| cpu | math | 0.0637 | 0.24 | 1337 | 0% | local |
| docker-full | yesno | 0.0144 | 0.24 | 7191 | 0% | local |
| docker-full | classify | 0.0073 | 0.24 | 12488 | 0% | local |
| docker-full | extract | 0.0196 | 0.24 | 4695 | 0% | local |
| docker-full | math | 0.0629 | 0.24 | 1353 | 0% | local |
| docker-2cpu | yesno | 0.0224 | 0.24 | 4267 | 0% | local |
| docker-2cpu | classify | 0.0091 | 0.24 | 9956 | 0% | local |
| docker-2cpu | extract | 0.0256 | 0.24 | 3509 | 0% | local |
| docker-2cpu | math | 0.1023 | 0.24 | 828 | 0% | local |

## Carbon-aware routing over a year

A request arrives every hour of the year for each task. 'static' = the task rule (yes/no and extract local, classify and math cloud). 'hourly' = also send a local task to the cloud in hours when the cloud is lower-carbon, and keep a cloud task local when local is lower-carbon (quality ignored, to show the carbon side alone). Error of flat = how far the yearly carbon computed with a fixed 420 g/kWh is from the hour-by-hour value.

| profile | static g/req (hourly grid) | static g/req (flat grid) | error of flat | carbon-only hourly g/req | saving vs static |
|---|---|---|---|---|---|
| gpu | 0.0426 | 0.0425 | -0% | 0.0042 | 90% |
| cpu | 0.0455 | 0.0453 | -0% | 0.0110 | 76% |
| docker-full | 0.0459 | 0.0457 | -0% | 0.0116 | 75% |
| docker-2cpu | 0.0475 | 0.0472 | -1% | 0.0177 | 63% |

Energy-best and carbon-best disagree in an hour when the energy-best column says local but the cloud is lower-carbon in that hour, i.e. the share in the 'hours cloud is lower-carbon' column for rows marked local.
