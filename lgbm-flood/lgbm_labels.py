"""Pseudo-labels and permanent water mask — pure SAR thresholding."""
import numpy as np
import cv2
import zarr
import os
from zarr.storage import ZipStore

S1_PATH = os.path.join("data", "Poyang_SingleTile", "S1_4t", "sample_001_S1_4t.zarr.zip")


def _load_s1():
    """Load S1 4-timestep data, return float32 linear."""
    with ZipStore(S1_PATH, mode='r') as store:
        root = zarr.open(store, mode='r')
        return np.array(root["bands"]).astype(np.float32)


def generate_labels():
    """
    SAR-only pseudo-labels for flood detection.

    Strategy:
    - T0: pre-flood baseline — used for permanent water extraction
    - T2: flood peak — used for flood detection

    Pseudo-labels combine two rules:
      1. Very low backscatter at T2 → smooth open water (peak flood)
      2. Strong backscatter drop T0→T2 → land→water transition

    Permanent water is extracted from T0 low backscatter:
      - (VV_T0 < VV_PW_THR) & (VH_T0 < VH_PW_THR) → pre-existing water body
      - Small morphological buffer to capture shoreline
      - Flood labels exclude permanent water

    Returns:
        labels:     (H,W) uint8, 1=flood, 0=non-flood
        perm_water: (H,W) bool
        nodata:     (H,W) bool — valid training area
    """
    # ===== Modifiable thresholds =====
    VV_PW_THR = -17.0    # permanent water VV threshold (dB)
    VH_PW_THR = -23.0    # permanent water VH threshold (dB)
    VV_PEAK_THR = -18.0  # flood peak VV threshold (dB)
    VH_PEAK_THR = -24.0  # flood peak VH threshold (dB)
    DVH_DROP_THR = -3.0  # VH temporal drop threshold (dB)
    DVV_DROP_THR = -2.5  # VV temporal drop threshold (dB)
    DB_FLOOR = -30.0      # minimum dB value

    T0, T2 = 0, 2

    s1 = _load_s1()
    eps = 1e-10
    s1_dB = 10 * np.log10(np.maximum(s1, eps))
    s1_dB[s1 <= 0] = DB_FLOOR
    s1_dB = np.maximum(s1_dB, DB_FLOOR)

    H, W = s1_dB.shape[2], s1_dB.shape[3]

    vv_t0 = s1_dB[T0, 0]
    vh_t0 = s1_dB[T0, 1]
    vv_t2 = s1_dB[T2, 0]
    vh_t2 = s1_dB[T2, 1]

    s1_valid = (vv_t0 > DB_FLOOR) & (vh_t0 > DB_FLOOR) & (vv_t2 > DB_FLOOR) & (vh_t2 > DB_FLOOR)
    print(f"S1 valid: {s1_valid.sum():,} px ({100*s1_valid.mean():.1f}%)")

    # ------- Permanent water: pre-flood T0 SAR -------
    pw_raw = (vv_t0 < VV_PW_THR) & (vh_t0 < VH_PW_THR) & s1_valid

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    pw_close = cv2.morphologyEx(pw_raw.astype(np.uint8), cv2.MORPH_CLOSE, kernel)
    perm_water = cv2.dilate(pw_close, np.ones((3, 3), np.uint8), iterations=1).astype(bool)

    print(f"Permanent water (T0 SAR): {perm_water.sum():,} px ({100*perm_water.mean():.1f}%)")

    # ------- Flood pseudo-labels: T0→T2 change -------
    peak_water = (vv_t2 < VV_PEAK_THR) & (vh_t2 < VH_PEAK_THR) & s1_valid
    d_vv = vv_t2 - vv_t0
    d_vh = vh_t2 - vh_t0
    strong_drop = ((d_vh < DVH_DROP_THR) | (d_vv < DVV_DROP_THR)) & s1_valid

    flood_raw = peak_water | strong_drop
    labels = (flood_raw & (~perm_water)).astype(np.uint8)
    nodata = s1_valid & (~perm_water)

    # ------- Diagnostics -------
    peak_on_land = peak_water & (~perm_water)
    drop_on_land = strong_drop & (~perm_water)
    print(f"S1 flood peak water (VV<{VV_PEAK_THR}, VH<{VH_PEAK_THR}): {peak_on_land.sum():,} px ({100*peak_on_land.mean():.1f}%)")
    print(f"S1 strong drop (dVH<{DVH_DROP_THR} | dVV<{DVV_DROP_THR}):    {drop_on_land.sum():,} px ({100*drop_on_land.mean():.1f}%)")
    print(f"SAR flood (peak | drop):               {labels.sum():,} px ({100*labels.mean():.1f}%)")
    print(f"Valid training area:                   {nodata.sum():,} px ({100*nodata.mean():.1f}%)")

    return labels, perm_water, nodata
