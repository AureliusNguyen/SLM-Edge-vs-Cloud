@echo off
rem RQ3 live check: run the router on 100 mixed questions with power measured.
rem Needs Ollama running, LibreHardwareMonitor web server on, and the Groq key set in this window:
rem   set GROQ_API_KEY=your-key
cd /d %~dp0\..
if "%GROQ_API_KEY%"=="" (
  echo GROQ_API_KEY is not set. Type: set GROQ_API_KEY=your-key   then run this again.
  exit /b 1
)
python rq3\rq3_live.py --policies task-rule,rule+cascade,cascade -n 25 --power lhm,nvidia --csv rq3\results\live_llama_gpu.csv --resume
pause
