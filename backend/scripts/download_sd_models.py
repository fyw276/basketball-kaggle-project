"""Download Stable Diffusion models for CatVTON using Chinese mirror."""

import os

os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "0"
os.environ["HF_HUB_DISABLE_SYMLINKS"] = "1"

from huggingface_hub import snapshot_download

models = [
    ("stabilityai/sd-vae-ft-mse", "SD VAE (~200MB)"),
    ("runwayml/stable-diffusion-inpainting", "SD Inpainting (~3.5GB)"),
]

for repo_id, desc in models:
    print(f"\n[{desc}] Downloading {repo_id}...")
    try:
        path = snapshot_download(repo_id=repo_id, resume_download=True)
        print(f"  Done: {path}")
    except Exception as e:
        print(f"  ERROR: {e}")
        print("  If this mirror fails, try manually downloading from: https://hf-mirror.com")

print("\nAll downloads complete!")
