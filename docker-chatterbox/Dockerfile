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
    huggingface_hub \
    soundfile \
    runpod

# Pre-download model files into HF cache (download only, no loading -
# the CI runner has no GPU and the checkpoint contains CUDA tensors)
RUN python3 -c "\
from huggingface_hub import snapshot_download; \
print('Downloading Chatterbox model files...'); \
snapshot_download( \
    repo_id='ResembleAI/chatterbox', \
    repo_type='model', \
    revision='main', \
    allow_patterns=['ve.pt', 't3_mtl23ls_v2.safetensors', 's3gen.pt', 'grapheme_mtl_merged_expanded_v1.json', 'conds.pt', 'Cangjie5_TC.json'], \
); \
print('Model files cached successfully!'); \
"

WORKDIR /workspace
COPY handler.py /workspace/handler.py

CMD ["python3", "/workspace/handler.py"]
