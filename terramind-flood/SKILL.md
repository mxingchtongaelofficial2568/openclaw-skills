---
name: terramind-flood
description: |
  TerraMind v1 deep learning flood semantic segmentation. Performs tiled ViT inference on
  4-timestep S1+S2+DEM satellite imagery (60 input channels) to produce a flood binary mask.
  Uses a pretrained TerraMind ViT + UNetDecoder checkpoint. GPU recommended, CPU fallback
  available. Use when the user asks for TerraMind inference, deep learning flood detection,
  or ViT-based satellite image segmentation.
allowed-tools: Bash(python *), Bash(pip *)
user-invocable: true
metadata:
  version: "1.0.0"
  category: earth-observation
  sources:
    - terraTorch documentation
    - TerraMind model
    - Copernicus Sentinel-1/2
---

# TerraMind Flood Detection

Deep learning flood semantic segmentation using TerraMind v1 Base (ViT + UNetDecoder).
Pretrained on global S1+S2+DEM data. Tiled inference on 110 × 110 km areas at 30 m resolution.

## Trigger

Use this skill when the user asks to:
- Run TerraMind flood inference on Poyang Lake 2020
- Apply deep learning ViT to satellite flood detection
- Generate flood mask from 4-timestep Sentinel-1/2 + DEM
- Compare TerraMind vs LightGBM flood results

## Required Data

All data must exist under `data/Poyang_SingleTile/`:

| File | Shape | Description |
|---|---|---|
| `S2_4t/sample_001_S2_4t.zarr.zip` | (4,12,3660,3660) | Sentinel-2: 4 timesteps × 12 bands |
| `S1_4t/sample_001_S1_4t.zarr.zip` | (4,2,3660,3660) | Sentinel-1: 4 timesteps × VV/VH linear power |
| `DEM/dem_50RMT.npy` | (3660,3660) | Copernicus 30m DEM float32 |

Timesteps: T0=2020-04-26 (pre-flood S2) / 2020-04-21 (S1), T1=2020-05-26/27,
T2=2020-07-15/14 (peak flood), T3=2020-08-24/19 (recession).

## Required Model Checkpoint

The TerraMind v1 Base model weights (`TerraMind_v1_base_ImpactMesh_flood.pt`, ~642 MB).

Resolution order:
1. `--model` CLI argument (highest)
2. `<script_dir>/TerraMind_v1_base_ImpactMesh_flood.pt` (default)

Download from HuggingFace if missing:
```bash
pip install huggingface_hub
huggingface-cli download terramind/TerraMind-v1-base-ImpactMesh-flood \
    TerraMind_v1_base_ImpactMesh_flood.pt --local-dir .
```

## Workflow

### Step 0: Install dependencies

```bash
pip install torch torchvision terratorch numpy rasterio zarr requests
```

### Step 1: Download data (if missing)

Check if all three data files exist. If not:

```bash
python SKILL/terramind-flood/download_4t.py
python SKILL/terramind-flood/download_dem.py
```

### Step 2: Verify model checkpoint

Check that `TerraMind_v1_base_ImpactMesh_flood.pt` exists in the project root or
SKILL script directory. If missing, offer to download from HuggingFace.

### Step 3: Run inference

```bash
python SKILL/terramind-flood/run_terramind.py
```

With custom model path:
```bash
python SKILL/terramind-flood/run_terramind.py --model /path/to/model.pt
```

### Step 4: Verify output

Check `data/Poyang_SingleTile/output/` for:
- `terramind_flood_4t.tif` — binary flood mask (uint8 GeoTIFF)
- `terramind_prob_4t.tif` — probability map (float32 GeoTIFF)

## Model Architecture

| Component | Spec |
|---|---|
| Backbone | TerraMind v1 Base (ViT), patch_size=16, dim=768, depth=12 |
| Decoder | UNetDecoder, channels [512, 256, 128, 64] |
| Input | S2(48ch) + S1(8ch) + DEM(4ch) = 60 channels |
| Inference | Tiled: crop=256, stride=208, delta=8, batch=8 |
| GPU | CUDA recommended (~1-2 min), CPU fallback (~6-10 min) |

## Modifiable Parameters

| Parameter | Default | Meaning |
|---|---|---|
| `CROP_SIZE` | 256 | Tiled inference crop size |
| `STRIDE` | 208 | Sliding window stride |
| `BATCH_SIZE` | 8 | Inference batch size (reduce if GPU OOM) |
| `FLOOD_THRESHOLD` | 0.5 | Probability → binary threshold |

## Expected Output (Poyang 2020)

| Metric | Value |
|---|---|
| Flood area | ~2,045 km² (~17.0% of tile) |
| Inference time | ~1-2 min (GPU) / ~6-10 min (CPU) |

## Post-Training: Comparison Plots

After running both this skill and `lgbm-flood`, generate comparison figures:

```bash
python SKILL/terramind-flood/plot_comparison.py
```

## Scripts

| Script | Purpose |
|---|---|
| `download_4t.py` | Download S2 + S1 4-timestep data |
| `download_dem.py` | Download Copernicus 30m DEM |
| `run_terramind.py` | Tiled ViT inference (main pipeline) |
| `plot_comparison.py` | TerraMind vs LightGBM comparison figures |
