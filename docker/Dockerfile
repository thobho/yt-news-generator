# Chatterbox TTS Docker Image for RunPod Serverless
# Uses lightweight CUDA base + installs only what's needed

FROM nvidia/cuda:11.8.0-runtime-ubuntu22.04

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV DEBIAN_FRONTEND=noninteractive
ENV HF_HOME=/root/.cache/huggingface

# Install Python 3.10 and system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 \
    python3-pip \
    python3.10-venv \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# Install Python packages
RUN pip install --no-cache-dir \
    torch torchaudio --index-url https://download.pytorch.org/whl/cu118

RUN pip install --no-cache-dir \
    chatterbox-tts \
    soundfile \
    runpod

# Pre-download the Multilingual Chatterbox model (~1.5GB cached in image)
RUN python3 -c "\
from chatterbox.mtl_tts import ChatterboxMultilingualTTS; \
print('Downloading Chatterbox Multilingual model...'); \
model = ChatterboxMultilingualTTS.from_pretrained(device='cpu'); \
print('Model cached successfully!'); \
"

WORKDIR /workspace
COPY handler.py /workspace/handler.py

CMD ["python3", "/workspace/handler.py"]
