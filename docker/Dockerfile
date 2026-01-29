# Chatterbox TTS Docker Image for RunPod
# Pre-installs chatterbox-tts and downloads model for fast startup

FROM runpod/pytorch:2.1.0-py3.10-cuda11.8.0-devel-ubuntu22.04

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV HF_HOME=/root/.cache/huggingface

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# Install Python packages
RUN pip install --no-cache-dir \
    chatterbox-tts \
    soundfile \
    numpy \
    scipy

# Pre-download the Chatterbox model by running a minimal inference
# This caches the model in the image (~1.5GB)
RUN python3 -c "\
from chatterbox.tts import ChatterboxTTS; \
import torch; \
print('Downloading Chatterbox model...'); \
model = ChatterboxTTS.from_pretrained(device='cpu'); \
print('Model cached successfully!'); \
"

# Create workspace directory
WORKDIR /workspace

# Default command (RunPod will override this)
CMD ["python3", "-c", "print('Chatterbox TTS ready!')"]
