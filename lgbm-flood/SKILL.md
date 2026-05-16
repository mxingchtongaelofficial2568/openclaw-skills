---
name: lgbm-flood
description: |
  LightGBM-based flood detection using SAR + DEM features. Generates pseudo-labels from
  Sentinel-1 backscatter thresholds, trains a gradient boosting classifier, and outputs
  flood mask GeoTIFFs. Use when the user asks for flood mapping, SAR-based water detection,
  or LightGBM flood classification. Pure CPU, no GPU needed.
allowed-tools: Bash(python *), Bash(pip *)
user-invocable: true
metadata:
  version: "1.0.0"
  category: earth-observation
  sources:
    - LightGBM documentation
    - Copernicus Sentinel-1 RTC
    - Copernicus 30m DEM
---

# LightGBM Flood Detection

SAR + DEM 17-feature gradient boosting flood detector. Trained on pseudo-labels from
Sentinel-1 temporal backscatter thresholds. Outputs binary flood mask and probability
GeoTIFF for a 110 × 110 km tile at 30 m resolution.

## Trigger

Use this skill when the user asks to:
- Run LightGBM flood detection on Poyang Lake 2020
- Train a SAR-based flood classifier
- Generate flood mask from Sentinel-1 time series
- Compare GBDT vs deep learning flood results

## Required Data

All data must exist under `data/Poyang_SingleTile/`:

| File | Shape | Description |
|---|---|---|
| `S1_4t/sample_001_S1_4t.zarr.zip` | (4,2,3660,3660) | Sentinel-1: 4 timesteps × VV/VH linear power |
| `DEM/dem_50RMT.npy` | (3660,3660) | Copernicus 30m DEM float32 |
| `S2_4t/sample_001_S2_4t.zarr.zip` | (4,12,3660,3660) | Sentinel-2: visualization only (optional) |

Timesteps: T0=2020-04-21 (pre-flood), T1=2020-05-27 (rain), T2=2020-07-14 (peak flood),
T3=2020-08-19 (recession).

## Workflow

### Step 0: Install dependencies

```bash
pip install numpy rasterio zarr opencv-python lightgbm scikit-learn matplotlib scipy requests
```

### Step 1: Download data (if missing)

Check if `data/Poyang_SingleTile/S1_4t/sample_001_S1_4t.zarr.zip` exists. If not:

```bash
python SKILL/lgbm-flood/download_4t.py
python SKILL/lgbm-flood/download_dem.py
```

### Step 2: Generate pseudo-labels and features, then train

```bash
python SKILL/lgbm-flood/lgbm_train.py
```

This single script runs the full pipeline internally:
1. `lgbm_labels.py` — permanent-water mask + flood pseudo-labels from SAR thresholds
2. `lgbm_features.py` — 17 features: VV/VH dB (8) + temporal deltas (6) + DEM (3)
3. LightGBM training: 500 rounds, early stopping 80, F1-optimal threshold selection
4. Full-image inference + morphological post-processing
5. Save GeoTIFF + overlay PNG

### Step 3: Verify output

Check `data/Poyang_SingleTile/output/` for:
- `lgbm_enhanced_flood.tif` — binary flood mask (uint8 GeoTIFF)
- `lgbm_enhanced_prob.tif` — probability map (float32 GeoTIFF)
- `lgbm_enhanced_overlay.png` — 3-panel comparison
- `lgbm_enhanced_detail.png` — large overlay on pre-flood S2

## Modifiable Parameters

All thresholds and hyperparameters are at the top of each script. Key knobs:

| File | Parameter | Default | Meaning |
|---|---|---|---|
| `lgbm_labels.py` | `VV_PEAK_THR` | -18.0 dB | Peak-flood VV threshold (higher = fewer flood px) |
| `lgbm_labels.py` | `VH_PEAK_THR` | -24.0 dB | Peak-flood VH threshold |
| `lgbm_labels.py` | `DVH_DROP_THR` | -3.0 dB | VH temporal drop for land→water transition |
| `lgbm_train.py` | `num_leaves` | 63 | Tree complexity |
| `lgbm_train.py` | `learning_rate` | 0.03 | Boosting learning rate |
| `lgbm_train.py` | `MIN_COMPONENT_SIZE` | 30 px | Minimum flood patch (post-processing) |

## Expected Output (Poyang 2020)

| Metric | Value |
|---|---|
| Validation F1 | ~0.856 |
| Best threshold | ~0.71 |
| Flood area | ~1,906 km² (~15.8% of tile) |
| Training time | ~200 s (CPU) |

## Post-Training: Comparison Plots

After running both this skill and `terramind-flood`, generate comparison figures:

```bash
python SKILL/lgbm-flood/plot_comparison.py
```

Produces `fig1_truecolor.*`, `fig2_terramind_flood.*`, `fig3_lgbm_flood.*`,
`fig4_comparison.*` (SVG/PDF/TIFF/PNG) in the output directory.

## Scripts

| Script | Purpose |
|---|---|
| `download_4t.py` | Download S2 + S1 4-timestep data from Earth Search / Planetary Computer |
| `download_dem.py` | Download Copernicus 30m DEM from AWS |
| `lgbm_labels.py` | Generate SAR pseudo-labels + permanent water mask |
| `lgbm_features.py` | 17-dim feature engineering (SAR + DEM) |
| `lgbm_train.py` | Training, inference, post-processing, visualization (main pipeline) |
| `plot_comparison.py` | TerraMind vs LightGBM 4-panel comparison figures |
