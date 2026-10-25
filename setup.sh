#!/usr/bin/env bash
# One-time setup for the demo: checks tools and .env, then starts the local model in Docker.
set -euo pipefail
cd "$(dirname "$0")"

MODEL=llama3.2:3b

for tool in docker go python3 curl; do
  command -v "$tool" >/dev/null || { echo "Missing $tool, install it first."; exit 1; }
done

if ! grep -q '^GROQ_API_KEY=.' .env 2>/dev/null; then
  echo "Add your Groq key first:  echo 'GROQ_API_KEY=your-key' > .env"
  exit 1
fi

if docker inspect ollama >/dev/null 2>&1; then
  docker start ollama >/dev/null
else
  docker run -d --name ollama -p 11434:11434 -v ollama:/root/.ollama ollama/ollama
fi

echo "Waiting for Ollama..."
until curl -sf localhost:11434/api/version >/dev/null; do sleep 1; done
docker exec ollama ollama pull "$MODEL"
echo "Setup done. Next: start the gateway (see README.md)."
