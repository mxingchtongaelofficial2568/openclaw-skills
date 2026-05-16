"""TerraMind flood inference — 4 real timesteps, 12-band S2 + S1 RTC + DEM.

Usage:
    python run_terramind.py                          # use default model path
    python run_terramind.py --model /path/to/model.pt  # specify local model
    python run_terramind.py --model ./models/terramind.pt

Model lookup order:
    1. --model CLI argument (highest priority)
    2. MODEL_PATH variable (set below)
    3. <script_dir>/TerraMind_v1_base_ImpactMesh_flood.pt  (default)
"""
import argparse, sys, torch, numpy as np, zarr, rasterio, os
from pathlib import Path

# =====================================================================
# Modifiable paths and parameters — change these before running
# =====================================================================

# Model checkpoint: can be absolute or relative path to any .pt file.
# Override via CLI: python run_terramind.py --model /your/path/model.pt
MODEL_PATH = None  # None = auto-detect in script directory

DATA_DIR = Path("data") / "Poyang_SingleTile"
OUT_DIR = Path("data") / "Poyang_SingleTile" / "output"

S2_PATH = DATA_DIR / "S2_4t" / "sample_001_S2_4t.zarr.zip"
S1_PATH = DATA_DIR / "S1_4t" / "sample_001_S1_4t.zarr.zip"
DEM_PATH = DATA_DIR / "DEM" / "dem_50RMT.npy"

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

# ===== Inference parameters =====
CROP_SIZE = 256
STRIDE = 208
DELTA = 8
BATCH_SIZE = 8
FLOOD_THRESHOLD = 0.5

# ===== Geospatial reference for the tile =====
TILE_CRS = "EPSG:32650"
TILE_ORIGIN_X = 399960.0
TILE_ORIGIN_Y = 3300000.0
TILE_RESOLUTION = 30

# ===== Normalization statistics (FROZEN — do not modify unless re-training) =====
S2_MEAN = np.array([1390.458,1503.317,1718.197,1853.91,2199.1,2779.975,2987.011,3083.234,3132.22,3162.988,2424.884,1857.648], dtype=np.float32)
S2_STD  = np.array([2106.761,2141.107,2038.973,2134.138,2085.321,1889.926,1820.257,1871.918,1753.829,1797.379,1434.261,1334.311], dtype=np.float32)
S1_MEAN = np.array([-10.93, -17.329], dtype=np.float32)
S1_STD  = np.array([4.391, 4.459], dtype=np.float32)
DEM_MEAN = np.float32(670.665)
DEM_STD  = np.float32(951.272)


def _resolve_model_path(cli_path=None):
    """Resolve model checkpoint path. Priority: CLI arg > MODEL_PATH const > default."""
    candidates = []
    if cli_path:
        candidates.append(Path(cli_path))
    if MODEL_PATH:
        candidates.append(Path(MODEL_PATH))
    # Default: look in script directory
    script_dir = Path(os.path.dirname(os.path.abspath(__file__)))
    default = script_dir / "TerraMind_v1_base_ImpactMesh_flood.pt"
    candidates.append(default)

    for p in candidates:
        if p.exists():
            return p
    raise FileNotFoundError(
        f"Cannot find model checkpoint. Tried:\n" +
        "\n".join(f"  - {p}" for p in candidates) +
        "\n\nDownload from HuggingFace:\n" +
        "  huggingface-cli download terramind/TerraMind-v1-base-ImpactMesh-flood \\\n" +
        "      TerraMind_v1_base_ImpactMesh_flood.pt --local-dir .\n" +
        "\nOr specify a local path:\n" +
        "  python run_terramind.py --model /path/to/model.pt"
    )


def run(cli_model_path=None):
    ckpt = _resolve_model_path(cli_model_path)
    print(f"Device: {DEVICE}")
    print(f"Model:  {ckpt}")

    # ---- Load S2 (4 timesteps, 12 bands) ----
    print("Loading S2...")
    store2 = zarr.storage.ZipStore(str(S2_PATH), mode="r")
    s2_data = np.array(zarr.open(store=store2, mode="r")["bands"][:], dtype=np.float32)
    store2.close()
    print(f"  S2: {s2_data.shape}")

    # ---- Load S1 (4 timesteps, 2 pol, linear power → dB) ----
    print("Loading S1 (converting to dB)...")
    store1 = zarr.storage.ZipStore(str(S1_PATH), mode="r")
    s1_linear = np.array(zarr.open(store=store1, mode="r")["bands"][:], dtype=np.float32)
    store1.close()
    print(f"  S1 linear: {s1_linear.shape}")
    s1_dB = 10 * np.log10(np.maximum(s1_linear, 1e-10))
    s1_dB[s1_linear <= 0] = -30
    s1_dB = np.maximum(s1_dB, -30)
    for t in range(s1_dB.shape[0]):
        vv_valid = s1_dB[t, 0][s1_dB[t, 0] > -30]
        vh_valid = s1_dB[t, 1][s1_dB[t, 1] > -30]
        print(f"  T{t} VV: [{vv_valid.min():.1f}, {vv_valid.max():.1f}]  VH: [{vh_valid.min():.1f}, {vh_valid.max():.1f}]")
    s1_data = s1_dB

    # ---- Load DEM ----
    print("Loading DEM...")
    dem = np.load(str(DEM_PATH)).astype(np.float32)
    print(f"  DEM: {dem.shape} [{dem.min():.1f}, {dem.max():.1f}]")

    # ---- DEM replicated to 4 timesteps ----
    dem_4t = np.tile(dem[np.newaxis, np.newaxis, :, :], (4, 1, 1, 1))

    H, W = s2_data.shape[2], s2_data.shape[3]

    # ---- Standardize ----
    s2_norm = (s2_data - S2_MEAN[np.newaxis, :, np.newaxis, np.newaxis]) / S2_STD[np.newaxis, :, np.newaxis, np.newaxis]
    s1_norm = (s1_data - S1_MEAN[np.newaxis, :, np.newaxis, np.newaxis]) / S1_STD[np.newaxis, :, np.newaxis, np.newaxis]
    dem_norm = (dem_4t - DEM_MEAN) / DEM_STD

    print(f"S2 norm: mean={s2_norm.mean():.3f} std={s2_norm.std():.3f}")
    print(f"S1 norm: mean={s1_norm.mean():.3f} std={s1_norm.std():.3f}")
    print(f"DEM norm: mean={dem_norm.mean():.3f} std={dem_norm.std():.3f}")

    # ---- Build input dict ----
    def make_tensor(arr):
        """(T, C, H, W) -> (C, T, H, W) -> (1, C, T, H, W)"""
        return torch.from_numpy(arr.transpose(1, 0, 2, 3).copy()).unsqueeze(0)

    inputs = {
        "S2L2A": make_tensor(s2_norm),
        "S1RTC": make_tensor(s1_norm),
        "DEM":    make_tensor(dem_norm),
    }
    for k, v in inputs.items():
        print(f"  {k}: {v.shape}")

    # ---- Load model ----
    from terratorch.tasks import SemanticSegmentationTask
    from terratorch.tasks.tiled_inference import tiled_inference

    print(f"Loading TerraMind from {ckpt.name}...")
    model = SemanticSegmentationTask.load_from_checkpoint(
        str(ckpt), map_location=DEVICE, strict=False)
    model.to(DEVICE)
    model.eval()
    print("Model loaded.")

    # ---- Tiled inference ----
    print(f"Running tiled inference (crop={CROP_SIZE}, stride={STRIDE}, batch={BATCH_SIZE}, delta={DELTA})...")
    with torch.no_grad():
        output = tiled_inference(
            model_forward=lambda x: model(x).output,
            input_batch=inputs,
            crop=CROP_SIZE, stride=STRIDE, delta=DELTA,
            batch_size=BATCH_SIZE, average_patches=True,
            blend_overlaps=True, verbose=True,
            device=DEVICE, padding=False,
        )

    # ---- Parse output ----
    print(f"Raw output: {output.shape}")
    if output.dim() == 4 and output.shape[1] > 1:
        prob = torch.softmax(output[0], dim=0)[1].cpu().numpy()
    elif output.dim() == 3:
        prob = output[0].cpu().numpy()
    else:
        prob = output.cpu().numpy()

    H_out, W_out = prob.shape
    pred = (prob > FLOOD_THRESHOLD).astype(np.uint8)
    print(f"Flood prob: [{prob.min():.4f}, {prob.max():.4f}]")
    print(f"Flood mask: {pred.sum():,} px ({100*pred.mean():.2f}%)")

    # ---- Save ----
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    meta = {
        "driver": "GTiff", "dtype": np.uint8,
        "height": pred.shape[0], "width": pred.shape[1], "count": 1,
        "crs": TILE_CRS, "compress": "lzw",
        "transform": rasterio.transform.from_origin(TILE_ORIGIN_X, TILE_ORIGIN_Y, TILE_RESOLUTION, TILE_RESOLUTION),
    }
    out_tif = OUT_DIR / "terramind_flood_4t.tif"
    with rasterio.open(str(out_tif), "w", **meta) as f:
        f.write(pred, 1)

    meta_f = {**meta, "dtype": np.float32}
    with rasterio.open(str(OUT_DIR / "terramind_prob_4t.tif"), "w", **meta_f) as f:
        f.write(prob.astype(np.float32), 1)

    print(f"Saved {out_tif}")
    print(f"  4-timestep | no perm water mask | YAML standardization")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TerraMind flood inference")
    parser.add_argument("--model", type=str, default=None,
                        help="Path to model checkpoint (.pt file). "
                             "If not set, uses MODEL_PATH variable or default in script directory.")
    args = parser.parse_args()
    run(cli_model_path=args.model)
