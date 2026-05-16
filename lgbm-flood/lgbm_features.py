"""Minimal feature engineering — SAR + DEM only. Flood detection relies on
microwave backscatter (penetrates clouds); optical bands are excluded because
T2 flood-peak imagery is cloud-contaminated and unreliable for water detection."""
import os
import numpy as np
import cv2
import zarr
from zarr.storage import ZipStore

S1_PATH = os.path.join("data", "Poyang_SingleTile", "S1_4t", "sample_001_S1_4t.zarr.zip")
DEM_PATH = os.path.join("data", "Poyang_SingleTile", "DEM", "dem_50RMT.npy")


def _linear_to_db(x):
    db = 10.0 * np.log10(np.maximum(x, 1e-10))
    return np.maximum(db, -30.0)


def build_all_features(verbose=True):
    """
    Build 17 feature maps from S1 + DEM.

    Features:
      1-8.  VV/VH dB for T0..T3  (8 SAR backscatter features)
      9-14. VV/VH temporal deltas for pairs (0,1), (1,2), (2,3)  (6 delta features)
      15.   elevation  (DEM)
      16.   slope  (DEM gradient magnitude)
      17.   HAND  (Height Above Nearest Drainage: DEM - eroded DEM)

    Returns:
        X:            (N_pixels, 17) float32 feature matrix
        feature_names (list of str)
        valid_mask:   (H,W) bool — valid (non-permanent-water) areas
        H, W:         int — tile dimensions
    """
    if not os.path.exists(S1_PATH):
        raise FileNotFoundError(f"Missing: {S1_PATH}")
    if not os.path.exists(DEM_PATH):
        raise FileNotFoundError(f"Missing: {DEM_PATH}")

    # ---- load S1 ----
    if verbose:
        print("Loading S1 (4 timesteps) ...")
    with ZipStore(S1_PATH, mode='r') as store:
        root = zarr.open(store, mode='r')
        s1_raw = np.array(root["bands"]).astype(np.float32)   # (4, 2, H, W)
    H, W = s1_raw.shape[2], s1_raw.shape[3]

    # ---- load DEM ----
    if verbose:
        print("Loading DEM ...")
    dem = np.load(DEM_PATH).astype(np.float32)

    # ---- dB conversion ----
    s1_dB = _linear_to_db(s1_raw)

    # ---- valid mask (all 4 timesteps have 100% coverage) ----
    s1_valid = np.any(s1_raw > 0, axis=(0, 1))

    # ---- permanent water: T0 low backscatter ----
    # Thresholds must match lgbm_labels.py
    VV_PW_THR = -17.0
    VH_PW_THR = -23.0
    pw_raw = (s1_dB[0, 0] < VV_PW_THR) & (s1_dB[0, 1] < VH_PW_THR) & s1_valid
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    pw_close = cv2.morphologyEx(pw_raw.astype(np.uint8), cv2.MORPH_CLOSE, kernel)
    perm_water = cv2.dilate(pw_close, np.ones((3, 3), np.uint8), iterations=1).astype(bool)
    valid_mask = s1_valid & (~perm_water)
    if verbose:
        print(f"S1 valid:       {s1_valid.sum():,} px ({100*s1_valid.mean():.1f}%)")
        print(f"Permanent water: {perm_water.sum():,} px ({100*perm_water.mean():.1f}%)")
        print(f"Valid mask:     {valid_mask.sum():,} px ({100*valid_mask.mean():.1f}%)")

    features_2d = []
    feature_names = []

    # ---- VV/VH dB (4 timesteps) ----
    if verbose:
        print("Building VV/VH dB (4 timesteps) ...")
    for t in range(4):
        features_2d.append(s1_dB[t, 0]); feature_names.append(f"VV_dB_T{t}")
        features_2d.append(s1_dB[t, 1]); feature_names.append(f"VH_dB_T{t}")

    # ---- VV/VH temporal deltas (3 adjacent pairs) ----
    if verbose:
        print("Building VV/VH deltas (3 pairs) ...")
    for pol, idx in [("VV", 0), ("VH", 1)]:
        for t0, t1 in [(0, 1), (1, 2), (2, 3)]:
            features_2d.append(s1_dB[t1, idx] - s1_dB[t0, idx])
            feature_names.append(f"{pol}_delta_T{t0}_T{t1}")

    # ---- DEM: terrain context ----
    if verbose:
        print("Building DEM features ...")
    features_2d.append(dem);                feature_names.append("elevation")
    gy, gx = np.gradient(dem)
    features_2d.append(np.sqrt(gx**2 + gy**2)); feature_names.append("slope")
    dem_eroded = cv2.erode(dem, np.ones((5, 5), np.uint8))
    features_2d.append(dem - dem_eroded);   feature_names.append("HAND")

    # ---- stack ----
    if verbose:
        print(f"Stacking {len(features_2d)} features ...")
    X_list = [f.ravel() for f in features_2d]
    X = np.column_stack(X_list).astype(np.float32)

    if verbose:
        print(f"Feature count: {len(feature_names)}")
        print(f"X shape:       {X.shape}")

    return X, feature_names, valid_mask, H, W
