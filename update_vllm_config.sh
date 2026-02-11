#!/bin/bash
# Update vLLM configuration in PM2 with memory optimization flags

set -e

echo "Stopping vLLM service..."
pm2 stop nanonets-ocr2-vllm

echo "Deleting old vLLM configuration..."
pm2 delete nanonets-ocr2-vllm

echo "Starting vLLM with optimized memory settings..."
pm2 start /home/user/ocr/venv/bin/python \
  --name nanonets-ocr2-vllm \
  --interpreter none \
  --cwd /home/user/ocr \
  -- -m vllm.entrypoints.openai.api_server \
  --model nanonets/Nanonets-OCR2-3B \
  --dtype bfloat16 \
  --gpu-memory-utilization 0.80 \
  --host 0.0.0.0 \
  --port 8000 \
  --enable-chunked-prefill \
  --trust-remote-code \
  --max-model-len 16000 \
  --swap-space 4 \
  --max-num-seqs 4 \
  --limit-mm-per-prompt '{"image":1}'

echo "Saving PM2 configuration..."
pm2 save

echo ""
echo "✓ vLLM updated with memory optimizations:"
echo "  - max-model-len: 16000 (unchanged, as requested)"
echo "  - swap-space: 4 GB (new)"
echo "  - limit-mm-per-prompt: image=1 (new)"
echo "  - max-num-seqs: 4 (unchanged)"
echo ""
pm2 info nanonets-ocr2-vllm
