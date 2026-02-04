# FLUX Schnell Docker Image for RunPod Serverless

FROM nvidia/cuda:11.8.0-runtime-ubuntu22.04

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV DEBIAN_FRONTEND=noninteractive
ENV HF_HOME=/root/.cache/huggingface
ENV TORCH_HOME=/root/.cache/torch

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 \
    python3-pip \
    python3.10-venv \
    git \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip
RUN pip install --no-cache-dir --upgrade pip

# PyTorch CUDA 11.8
RUN pip install --no-cache-dir \
    torch \
    --index-url https://download.pytorch.org/whl/cu118

# Core Python deps
RUN pip install --no-cache-dir \
    runpod \
    pillow \
    accelerate \
    safetensors \
    sentencepiece \
    protobuf \
    huggingface_hub \
    diffusers \
    transformers

WORKDIR /workspace
COPY handler.py /workspace/handler.py

CMD ["python3", "/workspace/handler.py"]
