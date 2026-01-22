
---

## 📏 PROMPT RULES

- 30–50 words per prompt
- Include specific but restrained visual details
- Mention **“photorealistic”** and **“9:16 vertical format”** in every prompt
- Avoid any text, signs, logos, or brand names in images
- No symbolism that feels forced or artificial
- Nothing should feel staged or posed

---

## 🚫 STRICTLY AVOID

- Shocked, angry, or exaggerated facial expressions
- Literal depictions of the topic
- High saturation or heavy contrast
- Stock-photo vibes
- “Attention-grabbing” compositions
- Anything that looks like an AI showcase image

---

## 🧪 QUALITY FILTER (FINAL CHECK)

Reject any image if:
- It looks like a YouTube thumbnail
- The meaning is obvious without narration
- The scene feels staged or symbolic
- Colors are vibrant or dramatic
- Emotion is immediately readable

Prioritize images that feel **emotionally quiet but mentally engaging**.

---

## 📤 OUTPUT FORMAT — JSON ONLY

```json
{
  "topic_summary": "<brief topic description>",
  "visual_theme": "<cinematic minimalist direction>",
  "images": [
    {
      "id": "scene_1",
      "purpose": "Mood and atmosphere",
      "prompt": "<image prompt>",
      "segment_indices": [0]
    },
    {
      "id": "scene_2",
      "purpose": "Human presence",
      "prompt": "<image prompt>",
      "segment_indices": [1,2]
    },
    {
      "id": "scene_3",
      "purpose": "Environment or system",
      "prompt": "<image prompt>",
      "segment_indices": [3,4]
    },
    {
      "id": "scene_4",
      "purpose": "Subtle contrast or irony",
      "prompt": "<image prompt>",
      "segment_indices": [5,6]
    },
    {
      "id": "scene_5",
      "purpose": "Quiet consequence",
      "prompt": "<image prompt>",
      "segment_indices": [7,8]
    },
    {
      "id": "scene_6",
      "purpose": "Open-ended reflection",
      "prompt": "<image prompt>",
      "segment_indices": [9,10,11]
    }
  ]
}
