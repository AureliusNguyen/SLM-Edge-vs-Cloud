@echo off
REM Cloud runs (gpt-oss-120b on Groq). In a command window in this folder:
REM   set GROQ_API_KEY=your_key
REM   run_cloud.bat wifi        (on Wi-Fi)
REM   run_cloud.bat hotspot     (laptop on a phone hotspot)
cd /d %~dp0
if "%GROQ_API_KEY%"=="" (echo Set GROQ_API_KEY first & goto :eof)
if "%1"=="" (echo Give the network name: run_cloud.bat wifi  or  run_cloud.bat hotspot & goto :eof)
python rq2_measure.py --tier cloud --label cloud --profile gpu --network %1 --power lhm,nvidia -n 20 --max-tokens 4096 --csv rq2_cloud_%1.csv
python rq2.py rq2_*.csv --out rq2
pause
