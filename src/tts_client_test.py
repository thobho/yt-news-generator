#!/usr/bin/env python3
"""
Generate 9 Chatterbox TTS audios using different CFG / exaggeration levels.
"""

import os
from pathlib import Path
from tts_client import TTSClient

# -------- INPUT --------
TEXT = """
Polski oficer jest sądzony za przypadkowe postrzelenie syryjskiego imigranta wadliwą bronią podczas pościgu na granicy z Białorusią.
Podporucznik ranił Syryjczyka w kręgosłup, gdy potknął się w lesie podczas pogoni. Biegły sądowy orzekł, że pistolet PM dziewięćdziesiat osiem ma wady i nie jest zabezpieczony przed wystrzałem przy upadku.
Grożą mu trzy lat więzienia, a Syryjczyk domaga się od żołnierza odszkodowania. Otrzymał azyl w Polsce.
"""
VOICE_REF_PATH = "tmp/voices/male-3.wav"
OUT_DIR = Path("outputs")

CFG_WEIGHTS = [0.2]
EXAGGERATIONS = [0.8]
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
