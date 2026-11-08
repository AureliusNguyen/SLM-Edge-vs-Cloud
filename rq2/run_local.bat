@echo off
REM Local runs, back to back (busy mode), on the native GPU and CPU. About 30 minutes.
REM Needs Ollama running and LibreHardwareMonitor as admin with Options > Remote Web Server on.
cd /d %~dp0
set P=--power lhm,nvidia -n 20 --gap 0
python rq2_measure.py --tier local --model llama3.2:3b --label llama --profile gpu %P% --csv rq2_llama_gpu_busy.csv
python rq2_measure.py --tier local --model llama3.2:3b --label llama --profile cpu --cpu-only %P% --csv rq2_llama_cpu_busy.csv
python rq2_measure.py --tier local --model qwen3:1.7b --label qwen --no-think --profile gpu %P% --csv rq2_qwen_gpu_busy.csv
python rq2_measure.py --tier local --model qwen3:1.7b --label qwen --no-think --profile cpu --cpu-only %P% --csv rq2_qwen_cpu_busy.csv
python rq2.py rq2_*.csv --out rq2
pause
