import base64
import io

import torch
import runpod
from diffusers import FluxPipeline

# -----------------------------
# MODEL LOAD (once per worker)
# -----------------------------

device = "cuda" if torch.cuda.is_available() else "cpu"
dtype = torch.float16 if device == "cuda" else torch.float32

print(f"Loading FLUX Schnell on {device}...")
pipe = FluxPipeline.from_pretrained(
    "black-forest-labs/FLUX.1-schnell",
    torch_dtype=dtype,
).to(device)
print("FLUX Schnell loaded successfully!")


# -----------------------------
# RUNPOD HANDLER
# -----------------------------

def handler(job):
    """
    Input schema:
    {
        "prompt": str,              # required
        "num_images": int,          # default 1
        "width": int,               # default 1024
        "height": int,              # default 1024
        "steps": int                # default 4 (Schnell)
    }

    Output schema:
    {
        "images_base64": [str]      # PNG images
    }
    """
    inp = job["input"]

    prompt = inp["prompt"]
    num_images = int(inp.get("num_images", 1))
    width = int(inp.get("width", 1024))
    height = int(inp.get("height", 1024))
    steps = int(inp.get("steps", 4))

    images = pipe(
        prompt=prompt,
        num_inference_steps=steps,
        guidance_scale=0.0,
        width=width,
        height=height,
        num_images_per_prompt=num_images,
    ).images

    encoded_images = []
    for img in images:
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        encoded_images.append(
            base64.b64encode(buf.getvalue()).decode("utf-8")
        )

    return {
        "images_base64": encoded_images
    }


runpod.serverless.start({"handler": handler})
