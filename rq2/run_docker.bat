@echo off
REM Docker profiles: no limits, and --cpus 2 --memory 4g (stands in for a weaker device). About 1.5 hours.
REM Needs Docker Desktop and LibreHardwareMonitor. Quit the normal Ollama first.
REM MODELS = the folder native Ollama keeps its models in (OLLAMA_MODELS), shared so nothing is downloaded twice.
REM In the 2-CPU container Ollama must use 2 threads, or decoding is ~40x slower.
cd /d %~dp0
if "%MODELS%"=="" set MODELS=%USERPROFILE%\.ollama\models
set P=--power lhm,nvidia --gap 0 --cpu-only --settle 60 --max-idle 40 -n 20
set L=--tier local --ollama http://127.0.0.1:11435 --model llama3.2:3b --label llama
set Q=--tier local --ollama http://127.0.0.1:11435 --model qwen3:1.7b --label qwen --no-think
docker rm -f rq2-ollama >nul 2>&1
docker run -d --name rq2-ollama -p 11435:11434 -v "%MODELS%":/root/.ollama/models ollama/ollama || goto :eof
timeout /t 15 >nul
python rq2_measure.py %L% --profile docker-full %P% --csv rq2_llama_dockerfull_busy.csv
python rq2_measure.py %Q% --profile docker-full %P% --csv rq2_qwen_dockerfull_busy.csv
docker rm -f rq2-ollama >nul 2>&1
docker run -d --name rq2-ollama --cpus 2 --memory 4g -p 11435:11434 -v "%MODELS%":/root/.ollama/models ollama/ollama || goto :eof
timeout /t 15 >nul
python rq2_measure.py %L% --profile docker-2cpu --threads 2 %P% --csv rq2_llama_docker2cpu_busy.csv
python rq2_measure.py %Q% --profile docker-2cpu --threads 2 %P% --csv rq2_qwen_docker2cpu_busy.csv
docker rm -f rq2-ollama >nul 2>&1
python rq2.py rq2_*.csv --out rq2
pause
