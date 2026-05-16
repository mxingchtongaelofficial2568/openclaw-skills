"""Download 4-timestep S2 (12-band, full coverage) + S1 RTC.

Portable — runs from any working directory. All paths are relative to cwd.

Usage:
    python download_4t.py                      # download all to ./data/Poyang_SingleTile/
    python download_4t.py --s2-only             # S2 only
    python download_4t.py --s1-only             # S1 only
    python download_4t.py --data-dir ./my_data   # custom output directory
"""

import argparse, numpy as np, rasterio, zarr, requests, time as time_mod
from pathlib import Path
from rasterio.enums import Resampling
from zarr.storage import ZipStore
from numcodecs import Blosc

# ===== Modifiable parameters =====
DATA_DIR = Path("data") / "Poyang_SingleTile"

TARGET_RES = 30.0
TILE_UTM_BOUNDS = (399960.0, 3190200.0, 509760.0, 3300000.0)
left, bottom, right, top = TILE_UTM_BOUNDS
W = int((right - left) / TARGET_RES)
H = int((top - bottom) / TARGET_RES)

# Sentinel-2 STAC Item IDs (Earth Search / Element84)
S2_DATES = {
    "T0": ("2020-04-26", "S2A_50RMT_20200426_0_L2A"),
    "T1": ("2020-05-26", "S2A_50RMT_20200526_0_L2A"),
    "T2": ("2020-07-15", "S2A_50RMT_20200715_0_L2A"),
    "T3": ("2020-08-24", "S2A_50RMT_20200824_0_L2A"),
}

S2_BAND_ASSETS = ["coastal","blue","green","red","rededge1","rededge2","rededge3",
                  "nir","nir08","nir09","swir16","swir22"]

E84_ITEM = "https://earth-search.aws.element84.com/v1/collections/sentinel-2-l2a/items"
S3_E84 = "s3://sentinel-cogs/"
HTTPS_E84 = "https://sentinel-cogs.s3.us-west-2.amazonaws.com/"

# Sentinel-1 dates — all 4 must have 100% tile coverage
# T0=04-21 S1B, T3=08-19 S1B (replaced 04-27/08-25 which had 86.4% coverage)
S1_DATES = {
    "T0": ("2020-04-21", "S1B"),
    "T1": ("2020-05-27", "S1A"),
    "T2": ("2020-07-14", "S1B"),
    "T3": ("2020-08-19", "S1B"),
}

import planetary_computer as pc
PC_SEARCH = "https://planetarycomputer.microsoft.com/api/stac/v1/search"


def save_zarr(stack, path):
    if path.exists():
        path.unlink()
    with ZipStore(str(path), mode="w") as store:
        root = zarr.open(store=store, mode="w", zarr_format=2)
        root.create_array(name="bands", shape=stack.shape, dtype=np.float32,
                          chunks=(1, stack.shape[1], min(256, stack.shape[2]), min(256, stack.shape[3])),
                          compressor=Blosc(cname="zstd", clevel=3, shuffle=2))
        root["bands"][:] = stack
        zarr.consolidate_metadata(store)


def download_s2_4t():
    print("=== S2 4-timestep ===")
    s2_dir = DATA_DIR / "S2_4t"
    s2_dir.mkdir(parents=True, exist_ok=True)
    s2_path = s2_dir / "sample_001_S2_4t.zarr.zip"

    stacks = []
    for key in ["T0", "T1", "T2", "T3"]:
        date_str, item_id = S2_DATES[key]
        cache = s2_dir / f"{key}_12band.npy"
        if cache.exists():
            print(f"  {key} {date_str}: loading cached")
            stacks.append(np.load(str(cache)))
            continue

        url = f"{E84_ITEM}/{item_id}"
        resp = requests.get(url, timeout=30)
        if resp.status_code != 200:
            print(f"  {key}: item not found ({resp.status_code}), using zeros")
            stacks.append(np.zeros((12, H, W), dtype=np.float32))
            continue

        item = resp.json()
        cc = item["properties"].get("eo:cloud_cover", 100)
        assets = item["assets"]
        print(f"  {key} {date_str}: cloud={cc:.1f}%")

        data = np.zeros((12, H, W), dtype=np.float32)
        for bi, asset_name in enumerate(S2_BAND_ASSETS):
            if asset_name not in assets:
                print(f"    {asset_name} MISSING")
                continue
            asset_url = assets[asset_name]["href"].replace(S3_E84, HTTPS_E84)
            try:
                with rasterio.open(asset_url) as src:
                    data[bi] = src.read(1, out_shape=(H, W),
                                        resampling=Resampling.bilinear).astype(np.float32)
            except Exception as e:
                print(f"    {asset_name} failed: {e}")
        np.save(str(cache), data)
        pct = (data.max(axis=0) > 0).mean() * 100
        print(f"    {pct:.1f}% valid pixels")
        stacks.append(data)

    full = np.stack(stacks, axis=0)  # (4, 12, H, W)
    print(f"  Saving {full.shape} -> {s2_path.name} ...", end=" ", flush=True)
    save_zarr(full, s2_path)
    print(f"done ({s2_path.stat().st_size/1e6:.0f} MB)")
    return s2_path


def download_s1_4t():
    print("\n=== S1 4-timestep ===")
    s1_dir = DATA_DIR / "S1_4t"
    s1_dir.mkdir(parents=True, exist_ok=True)
    s1_path = s1_dir / "sample_001_S1_4t.zarr.zip"

    stacks = []
    for key in ["T0", "T1", "T2", "T3"]:
        date_str, platform = S1_DATES[key]
        cache = s1_dir / f"{key}_rtc.npy"
        if cache.exists():
            stored = np.load(str(cache))
            pct = (stored.max(axis=0) > 0).mean() * 100
            print(f"  {key} {date_str}: cached ({pct:.1f}% valid)")
            stacks.append(stored)
            continue

        print(f"  {key} {date_str} ({platform}):")
        t_start = time_mod.time()

        print(f"    STAC search...", end=" ", flush=True)
        payload = {
            "collections": ["sentinel-1-rtc"],
            "bbox": [114, 27, 118, 31],
            "datetime": f"{date_str}T00:00:00Z/{date_str}T23:59:59Z",
            "limit": 10,
        }
        try:
            r = requests.post(PC_SEARCH, json=payload, timeout=30)
            items = r.json().get("features", [])
        except Exception as e:
            print(f"FAILED: {e}")
            stacks.append(np.zeros((2, H, W), dtype=np.float32))
            continue
        print(f"found {len(items)} granules")

        vv = vh = None
        for gi, granule in enumerate(items):
            signed = pc.sign(granule)
            try:
                with rasterio.open(signed["assets"]["vv"]["href"]) as src:
                    b = src.bounds
                    if not (b.left <= left and b.right >= right and
                            b.bottom <= bottom and b.top >= top):
                        continue
                    tx = src.transform
                    col_off = int(round((left - tx.c) / tx.a))
                    row_off = int(round((top - tx.f) / tx.e))
                    ncols = int(round((right - left) / tx.a))
                    nrows = int(round((top - bottom) / abs(tx.e)))
                    window = rasterio.windows.Window(col_off, row_off, ncols, nrows)

                print(f"    Granule {gi} covers tile, window={ncols}x{nrows}")

                print(f"    Reading VV  (resampling to {H}x{W})...", end=" ", flush=True)
                t_read = time_mod.time()
                try:
                    with rasterio.open(signed["assets"]["vv"]["href"]) as src:
                        vv = src.read(1, window=window, out_shape=(H, W),
                                      resampling=Resampling.average).astype(np.float32)
                    dt_vv = time_mod.time() - t_read
                    vv_pct = 100 * (vv > 0).mean()
                    print(f"done ({dt_vv:.1f}s, {vv_pct:.1f}% valid)")
                except Exception as e:
                    print(f"FAILED: {e}")
                    vv = None

                print(f"    Reading VH  (resampling to {H}x{W})...", end=" ", flush=True)
                t_read = time_mod.time()
                try:
                    with rasterio.open(signed["assets"]["vh"]["href"]) as src:
                        vh = src.read(1, window=window, out_shape=(H, W),
                                      resampling=Resampling.average).astype(np.float32)
                    dt_vh = time_mod.time() - t_read
                    vh_pct = 100 * (vh > 0).mean()
                    print(f"done ({dt_vh:.1f}s, {vh_pct:.1f}% valid)")
                except Exception as e:
                    print(f"FAILED: {e}")
                    vh = None

                if vv is not None or vh is not None:
                    break
            except Exception as e:
                print(f"    Granule {gi} check failed: {e}")
                continue

        if vv is None and vh is None:
            print(f"    NO covering granule found")
            stacks.append(np.zeros((2, H, W), dtype=np.float32))
            continue

        if vv is None:
            vv = np.zeros((H, W), dtype=np.float32)
        if vh is None:
            vh = np.zeros((H, W), dtype=np.float32)

        data = np.stack([vv, vh], axis=0)  # (2, H, W)
        print(f"    Saving cache...", end=" ", flush=True)
        np.save(str(cache), data)
        print(f"done")
        dt = time_mod.time() - t_start
        valid = (data.max(axis=0) > 0).mean() * 100
        print(f"    Total: {dt:.1f}s, {valid:.1f}% valid pixels")
        stacks.append(data)

    full = np.stack(stacks, axis=0)  # (4, 2, H, W)
    print(f"  Saving {full.shape} -> {s1_path.name} ...", end=" ", flush=True)
    save_zarr(full, s1_path)
    print(f"done ({s1_path.stat().st_size/1e6:.1f} MB)")
    return s1_path


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    parser = argparse.ArgumentParser(description="Download S2 + S1 4-timestep data")
    parser.add_argument("--s2-only", action="store_true", help="Download S2 only")
    parser.add_argument("--s1-only", action="store_true", help="Download S1 only")
    parser.add_argument("--data-dir", type=str, default=None,
                        help="Custom output directory (default: data/Poyang_SingleTile)")
    args = parser.parse_args()

    global DATA_DIR
    if args.data_dir:
        DATA_DIR = Path(args.data_dir)

    s1_only = args.s1_only
    s2_only = args.s2_only

    if not s1_only:
        download_s2_4t()
    if not s2_only:
        download_s1_4t()

    print("\n=== Complete ===")


if __name__ == "__main__":
    main()
