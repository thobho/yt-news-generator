#!/usr/bin/env python3
"""
Generate 9 Chatterbox TTS audios using different CFG / exaggeration levels.
"""

import os
from pathlib import Path
from tts_client import TTSClient

# -------- INPUT --------
TEXT = "Od początku roku złoto, licząc w dolarach, podrożało o około 27 proc. Podobnych lub większych miesięcznych zwyżek cen kruszcu w minionym stuleciu było tylko kilka. Ostatnia, z 1980 r., była zapowiedzią przesilenia na tym rynku. Jedną z przyczyn przeceny złota, która się wtedy rozpoczęła, widać także dzisiaj."
VOICE_REF_PATH = "data/voices/sample_3.wav"
OUT_DIR = Path("outputs")

CFG_WEIGHTS = [0.3, 0.5]
EXAGGERATIONS = [0.5, 0.55]
# -----------------------

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    client = TTSClient()

    for cfg in CFG_WEIGHTS:
        for ex in EXAGGERATIONS:
            # Pass parameters via environment variables
            os.environ["CHATTERBOX_CFG_WEIGHT"] = str(cfg)
            os.environ["CHATTERBOX_EXAGGERATION"] = str(ex)

            wav_bytes = client.generate(
                text=TEXT,
                voice_ref_path=VOICE_REF_PATH,
            )

            out_file = OUT_DIR / f"tts_cfg{cfg}_ex{ex}.wav"
            out_file.write_bytes(wav_bytes)

            print(f"Saved {out_file}")

if __name__ == "__main__":
    main()
