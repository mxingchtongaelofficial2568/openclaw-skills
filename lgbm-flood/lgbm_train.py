"""LightGBM flood detection — training, inference, post-processing, visualization."""
import time
import os
import numpy as np
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import cv2
import rasterio
from rasterio.transform import from_origin
import lightgbm as lgb
from sklearn.model_selection import train_test_split
from scipy.ndimage import label as ndi_label
import zarr
from zarr.storage import ZipStore

from lgbm_features import build_all_features
from lgbm_labels import generate_labels


# ===== Paths (relative to project root) =====
DATA_DIR = Path("data") / "Poyang_SingleTile"
S2_PATH = DATA_DIR / "S2_4t" / "sample_001_S2_4t.zarr.zip"   # visualization only
OUTPUT_DIR = DATA_DIR / "output"

# ===== Geospatial reference =====
TILE_CRS = "EPSG:32650"
TILE_ORIGIN_X = 399960.0
TILE_ORIGIN_Y = 3300000.0
TILE_RESOLUTION = 30

# ===== LightGBM hyperparameters (modifiable) =====
LGB_PARAMS = {
    "objective": "binary",
    "metric": "binary_logloss",
    "boosting_type": "gbdt",
    "num_leaves": 63,
    "learning_rate": 0.03,
    "feature_fraction": 0.7,
    "bagging_fraction": 0.8,
    "bagging_freq": 5,
    "verbose": -1,
    "n_jobs": 4,
    "min_child_samples": 30,
    "reg_alpha": 0.5,
    "reg_lambda": 1.0,
}
NUM_BOOST_ROUND = 500
EARLY_STOPPING = 80
LOG_EVALUATION = 50
VAL_SPLIT = 0.2
RANDOM_STATE = 42
INFERENCE_BATCH = 200000

# ===== Post-processing parameters (modifiable) =====
MORPH_OPEN_KERNEL = (3, 3)   # ellipse kernel size for opening
MIN_COMPONENT_SIZE = 30       # minimum flood patch in pixels
MORPH_CLOSE_KERNEL = (3, 3)  # rect kernel size for closing

# ===== Threshold selection =====
THR_SCAN_START = 0.20
THR_SCAN_END = 0.96
THR_SCAN_STEP = 0.01
PSEUDO_RATE_MULTIPLIER = 1.2  # pseudo_label_rate * multiplier for rate-based threshold


def _load_zarr_zip(path):
    with ZipStore(path, mode='r') as store:
        root = zarr.open(store, mode='r')
        data = np.array(root["bands"])
    return np.asarray(data, dtype=np.float32)


def _percentile_stretch(img, lower=2, upper=98):
    vmin = np.percentile(img, lower)
    vmax = np.percentile(img, upper)
    return np.clip((img - vmin) / (vmax - vmin + 1e-8), 0, 1)


def _make_truecolor(s2_data, time_idx):
    r = _percentile_stretch(s2_data[time_idx, 2])   # B4 (red)
    g = _percentile_stretch(s2_data[time_idx, 1])   # B3 (green)
    b = _percentile_stretch(s2_data[time_idx, 0])   # B2 (blue)
    return np.stack([r, g, b], axis=-1)


def _make_overlay(rgb, mask, alpha=0.5):
    overlay = rgb.copy()
    mask3 = np.stack([mask] * 3, axis=-1)
    red = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    overlay = np.where(mask3, rgb * (1 - alpha) + red * alpha, rgb)
    return overlay


def _compute_scale_pos_weight(y):
    n_neg = int((y == 0).sum())
    n_pos = int((y == 1).sum())
    if n_pos == 0:
        return 1.0
    return n_neg / n_pos


def _find_best_threshold(y_true, y_prob):
    best_f1 = 0.0
    best_thr = 0.5
    for thr in np.arange(THR_SCAN_START, THR_SCAN_END, THR_SCAN_STEP):
        pred = (y_prob >= thr).astype(int)
        tp = float(((pred == 1) & (y_true == 1)).sum())
        fp = float(((pred == 1) & (y_true == 0)).sum())
        fn = float(((pred == 0) & (y_true == 1)).sum())
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        if f1 > best_f1:
            best_f1 = f1
            best_thr = thr
    return best_thr, best_f1


def _postprocess(binary, valid_mask):
    binary = binary & valid_mask

    kernel_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, MORPH_OPEN_KERNEL)
    binary_u8 = binary.astype(np.uint8)
    binary_u8 = cv2.morphologyEx(binary_u8, cv2.MORPH_OPEN, kernel_open)

    labeled, n_labels = ndi_label(binary_u8)
    for i in range(1, n_labels + 1):
        if (labeled == i).sum() < MIN_COMPONENT_SIZE:
            binary_u8[labeled == i] = 0

    kernel_close = np.ones(MORPH_CLOSE_KERNEL, dtype=np.uint8)
    binary_u8 = cv2.morphologyEx(binary_u8, cv2.MORPH_CLOSE, kernel_close)

    return binary_u8.astype(bool)


def run():
    t_start = time.time()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ================================================================
    # 1. Load features and labels
    # ================================================================
    print("=" * 60)
    print("Step 1: Loading features and labels")
    print("=" * 60)

    X, feat_names, valid_mask, H, W = build_all_features(verbose=True)
    labels, perm_water, nodata = generate_labels()

    train_mask = valid_mask & nodata   # (H, W) bool
    n_train_px = int(train_mask.sum())
    print(f"Training area pixels: {n_train_px}")

    X_train_all = X[train_mask.ravel()]
    y_train_all = labels[train_mask]
    print(f"Train samples before NaN removal: {X_train_all.shape[0]}")

    finite = np.isfinite(X_train_all).all(axis=1)
    X_train_all = X_train_all[finite]
    y_train_all = y_train_all[finite]
    print(f"Train samples after  NaN removal: {X_train_all.shape[0]}")

    # ================================================================
    # 2. Train LightGBM
    # ================================================================
    print("\n" + "=" * 60)
    print("Step 2: Training LightGBM")
    print("=" * 60)

    X_tr, X_val, y_tr, y_val = train_test_split(
        X_train_all, y_train_all, test_size=VAL_SPLIT, random_state=RANDOM_STATE
    )
    print(f"Train: {X_tr.shape[0]},  Val: {X_val.shape[0]}")

    scale_pos_weight = _compute_scale_pos_weight(y_tr)
    print(f"scale_pos_weight: {scale_pos_weight:.2f}")

    params = {**LGB_PARAMS, "scale_pos_weight": scale_pos_weight}

    train_data = lgb.Dataset(X_tr, label=y_tr, feature_name=feat_names)
    val_data = lgb.Dataset(X_val, label=y_val, reference=train_data, feature_name=feat_names)

    t_train_start = time.time()
    model = lgb.train(
        params,
        train_data,
        num_boost_round=NUM_BOOST_ROUND,
        valid_sets=[train_data, val_data],
        valid_names=["train", "val"],
        callbacks=[
            lgb.early_stopping(EARLY_STOPPING),
            lgb.log_evaluation(LOG_EVALUATION),
        ],
    )
    t_train_end = time.time()
    train_time = t_train_end - t_train_start
    print(f"Training completed in {train_time:.1f}s")
    print(f"Best iteration: {model.best_iteration}")

    importance = model.feature_importance(importance_type="gain")
    feat_imp = sorted(zip(feat_names, importance), key=lambda x: x[1], reverse=True)
    print("\nTop 20 feature importance:")
    for i, (name, imp) in enumerate(feat_imp[:20]):
        print(f"  {i+1:2d}. {name:30s} {imp:.2f}")

    # ================================================================
    # 3. Predict and threshold
    # ================================================================
    print("\n" + "=" * 60)
    print("Step 3: Predicting and thresholding")
    print("=" * 60)

    n_pixels = X.shape[0]
    prob_flat = np.zeros(n_pixels, dtype=np.float32)

    for start in range(0, n_pixels, INFERENCE_BATCH):
        end = min(start + INFERENCE_BATCH, n_pixels)
        batch = X[start:end]
        ok = np.isfinite(batch).all(axis=1)
        if ok.any():
            prob_flat[start:end][ok] = model.predict(batch[ok])

    prob = prob_flat.reshape(H, W)
    print(f"Probability range: [{prob.min():.4f}, {prob.max():.4f}]")

    val_probs = model.predict(X_val)

    best_thr, best_f1 = _find_best_threshold(y_val, val_probs)
    print(f"F1-optimal threshold: {best_thr:.3f}  (F1={best_f1:.4f})")

    pseudo_rate = float(y_tr.sum()) / y_tr.size
    rate_thr = float(np.quantile(val_probs, 1.0 - pseudo_rate * PSEUDO_RATE_MULTIPLIER))
    rate_thr = max(0.20, min(0.95, rate_thr))
    print(f"Rate-based threshold:  {rate_thr:.3f}  (pseudo_rate={pseudo_rate:.4f})")

    threshold = max(best_thr, rate_thr)
    print(f"Final threshold:        {threshold:.3f}")

    binary = prob >= threshold

    # ================================================================
    # 4. Post-processing
    # ================================================================
    print("\n" + "=" * 60)
    print("Step 4: Post-processing")
    print("=" * 60)

    binary = _postprocess(binary, valid_mask)

    n_flood = int(binary.sum())
    flood_pct = 100.0 * n_flood / valid_mask.sum()
    area_km2 = n_flood * TILE_RESOLUTION * TILE_RESOLUTION / 1e6
    print(f"Flood pixels: {n_flood}  ({flood_pct:.2f}% of valid area,  {area_km2:.2f} km^2)")

    # ================================================================
    # 5. Save GeoTIFF outputs
    # ================================================================
    print("\n" + "=" * 60)
    print("Step 5: Saving GeoTIFF outputs")
    print("=" * 60)

    meta = {
        "driver": "GTiff",
        "height": H,
        "width": W,
        "count": 1,
        "crs": TILE_CRS,
        "compress": "lzw",
        "transform": from_origin(TILE_ORIGIN_X, TILE_ORIGIN_Y, TILE_RESOLUTION, TILE_RESOLUTION),
    }

    binary_path = OUTPUT_DIR / "lgbm_enhanced_flood.tif"
    with rasterio.open(binary_path, "w", dtype="uint8", **meta) as dst:
        dst.write(binary.astype(np.uint8), 1)
    print(f"  Saved: {binary_path}")

    prob_path = OUTPUT_DIR / "lgbm_enhanced_prob.tif"
    with rasterio.open(prob_path, "w", dtype="float32", **meta) as dst:
        dst.write(prob.astype(np.float32), 1)
    print(f"  Saved: {prob_path}")

    # ================================================================
    # 6. Generate visualizations
    # ================================================================
    print("\n" + "=" * 60)
    print("Step 6: Generating visualizations")
    print("=" * 60)

    try:
        s2 = _load_zarr_zip(str(S2_PATH))   # (4, 12, H, W)
        print(f"S2 data shape: {s2.shape}")

        tc_pre = _make_truecolor(s2, 0)     # T0 pre-flood
        tc_post = _make_truecolor(s2, 2)    # T2 flood peak

        # --- Figure 1: 3-panel side by side ---
        fig1, axes = plt.subplots(1, 3, figsize=(18, 5), dpi=150)

        axes[0].imshow(tc_pre)
        axes[0].set_title("Pre-flood S2", fontsize=10)
        axes[0].axis("off")

        overlay1 = _make_overlay(tc_pre, binary, alpha=0.5)
        axes[1].imshow(overlay1)
        axes[1].set_title(
            f"LightGBM Flood: {n_flood} px ({area_km2:.1f} km^2)",
            fontsize=10,
        )
        axes[1].axis("off")

        axes[2].imshow(tc_post)
        axes[2].set_title("Flood peak S2", fontsize=10)
        axes[2].axis("off")

        fig1.suptitle(
            "Flood Detection | LightGBM (17 SAR+DEM features, 4 timesteps)",
            fontsize=14,
            fontweight="bold",
        )
        fig1.tight_layout()

        overlay_path = OUTPUT_DIR / "lgbm_enhanced_overlay.png"
        fig1.savefig(overlay_path, dpi=150, bbox_inches="tight")
        plt.close(fig1)
        print(f"  Saved: {overlay_path}")

        # --- Figure 2: Detail large ---
        fig2, ax2 = plt.subplots(figsize=(12, 10), dpi=200)

        overlay2 = _make_overlay(tc_pre, binary, alpha=0.55)
        ax2.imshow(overlay2)
        ax2.set_title(
            f"Flood Detection | LightGBM\n"
            f"17 features (14 SAR + 3 DEM) | 4 timesteps\n"
            f"Flood: {n_flood} px ({area_km2:.1f} km^2)",
            fontsize=10,
        )
        ax2.axis("off")

        fig2.tight_layout()
        detail_path = OUTPUT_DIR / "lgbm_enhanced_detail.png"
        fig2.savefig(detail_path, dpi=200, bbox_inches="tight")
        plt.close(fig2)
        print(f"  Saved: {detail_path}")

    except Exception as e:
        print(f"  Warning: visualization failed — {e}")
        print(f"  (S2 data needed for RGB overlay. GeoTIFFs are still saved.)")

    # ================================================================
    # 7. Print summary
    # ================================================================
    t_end = time.time()
    total_time = t_end - t_start

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Total features used : {len(feat_names)}")
    print(f"  Best threshold       : {threshold:.3f}")
    print(f"  Validation F1        : {best_f1:.4f}")
    print(f"  Flood pixel count    : {n_flood}")
    print(f"  Flood area           : {area_km2:.2f} km^2")
    print(f"  Training time        : {train_time:.1f}s")
    print(f"  Total time           : {total_time:.1f}s")
    print(f"  Output files:")
    print(f"    {binary_path}")
    print(f"    {prob_path}")
    if (OUTPUT_DIR / "lgbm_enhanced_overlay.png").exists():
        print(f"    {OUTPUT_DIR / 'lgbm_enhanced_overlay.png'}")
    if (OUTPUT_DIR / "lgbm_enhanced_detail.png").exists():
        print(f"    {OUTPUT_DIR / 'lgbm_enhanced_detail.png'}")
    print("=" * 60)


if __name__ == "__main__":
    run()
