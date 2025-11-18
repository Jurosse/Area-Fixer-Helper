# osu! Tablet Aim Bias Analyzer

This tool analyzes your osu! replays (`.osr`) and automatically finds the matching beatmaps (`.osu`) using their MD5 hash from your `Songs` folder.

It then:

- Reconstructs your cursor path from each replay  
- Compares it to the exact hitobject positions  
- Measures your **average aim bias** (in osu! pixels and in millimeters on your tablet area)  
- Suggests a **tablet area offset** only if the bias is meaningful  
- Generates a **scatter plot** (`aim_bias_map.png`) showing where you usually hit around the circle center  

No live input, no overlays, no in-game interaction. It only works offline on existing replay files.

---

## Features

- 🔁 Automatic `.osu` lookup via **beatmap MD5** (no manual map pairing)
- 📊 Computes mean aim bias in:
  - osu! pixels (dx, dy)
  - millimeters on your tablet area (using your width/height in mm)
- 🧭 Splits errors into quadrants (top-left, top-right, bottom-left, bottom-right)
- 🎯 Suggests an area offset **only if** your bias is above a configurable threshold (default 0.25 mm)
- 🗺️ Generates `aim_bias_map.png`:
  - Hitcircle center at (0, 0)
  - Your impacts as colored `+` markers
  - Color = distance from center

---

## Requirements

- Python 3.9+ (recommended)
- `osrparse`
- `matplotlib`

You can install dependencies with:

```bash
pip install -r requirements.txt