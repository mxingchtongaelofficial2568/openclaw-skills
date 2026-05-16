"""Download Copernicus DEM 30m for tile 50RMT from AWS.
Works from any working directory — supports --data-dir flag like download_4t.py.
"""
import argparse, numpy as np, rasterio
from pathlib import Path
from rasterio.warp import reproject, transform_bounds
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.merge import merge

DATA_DIR = Path("data") / "Poyang_SingleTile"
TILE_UTM_BOUNDS = (399960.0, 3190200.0, 509760.0, 3300000.0)
TARGET_RES = 30.0


def download_dem(data_dir=None):
    dem_dir = (data_dir or DATA_DIR) / "DEM"
    dem_dir.mkdir(parents=True, exist_ok=True)

    left, bottom, right, top = TILE_UTM_BOUNDS
    wgs = transform_bounds("EPSG:32650", "EPSG:4326", left, bottom, right, top)
    buf = 0.03
    wgs_buf = (wgs[0] - buf, wgs[1] - buf, wgs[2] + buf, wgs[3] + buf)
    print(f"WGS84: {wgs}")
    print(f"WGS84+buf: {wgs_buf}")

    tiles = []
    for lat in [28, 29]:
        for lon in [115, 116, 117]:
            ns = "N" if lat >= 0 else "S"
            ew = "E" if lon >= 0 else "W"
            tid = f"{ns}{lat:02d}_00_{ew}{abs(lon):03d}_00"
            url = f"https://copernicus-dem-30m.s3.eu-central-1.amazonaws.com/Copernicus_DSM_COG_10_{tid}_DEM/Copernicus_DSM_COG_10_{tid}_DEM.tif"
            tiles.append((tid, url))

    read_tiles = []
    for tid, url in tiles:
        try:
            src = rasterio.open(url)
            t_left, t_bottom, t_right, t_top = src.bounds
            if (t_right > wgs_buf[0] and t_left < wgs_buf[2] and
                t_top > wgs_buf[1] and t_bottom < wgs_buf[3]):
                read_tiles.append(src)
                print(f"  {tid}: overlap OK, shape={src.shape}")
            else:
                src.close()
                print(f"  {tid}: no overlap, skip")
        except Exception as e:
            print(f"  {tid}: FAIL - {e}")

    print(f"Merging {len(read_tiles)} tiles...")
    mosaic, mosaic_transform = merge(read_tiles, bounds=wgs_buf,
                                     resampling=Resampling.bilinear,
                                     nodata=np.nan, method='first')
    for src in read_tiles:
        src.close()

    if mosaic.ndim == 3:
        mosaic = mosaic[0]

    h = int((TILE_UTM_BOUNDS[3] - TILE_UTM_BOUNDS[1]) / TARGET_RES)
    w = int((TILE_UTM_BOUNDS[2] - TILE_UTM_BOUNDS[0]) / TARGET_RES)
    dst_transform = from_origin(TILE_UTM_BOUNDS[0], TILE_UTM_BOUNDS[3],
                                TARGET_RES, TARGET_RES)

    dem_data = np.zeros((h, w), dtype=np.float32)
    reproject(source=mosaic.astype(np.float32), destination=dem_data,
              src_transform=mosaic_transform, src_crs="EPSG:4326",
              dst_transform=dst_transform, dst_crs="EPSG:32650",
              src_nodata=np.nan, dst_nodata=-9999,
              resampling=Resampling.bilinear)

    valid = (dem_data > -500) & (dem_data < 9000)
    dem_data[~valid] = 0

    print(f"DEM: {h}x{w}, range=[{dem_data[valid].min():.0f}, {dem_data[valid].max():.0f}] m")
    print(f"Valid: {valid.sum():,} px ({100*valid.mean():.1f}%)")

    dem_npy = dem_dir / "dem_50RMT.npy"
    np.save(str(dem_npy), dem_data.astype(np.float32))
    print(f"Saved {dem_npy} ({dem_npy.stat().st_size/1e6:.1f} MB)")

    dem_tif = dem_dir / "dem_50RMT.tif"
    meta = {"driver": "GTiff", "dtype": np.float32, "height": h, "width": w,
            "count": 1, "crs": "EPSG:32650", "compress": "lzw",
            "transform": dst_transform}
    with rasterio.open(str(dem_tif), "w", **meta) as f:
        f.write(dem_data, 1)
    print(f"Saved {dem_tif}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download Copernicus 30m DEM")
    parser.add_argument("--data-dir", type=str, default=None,
                        help="Custom output directory (default: data/Poyang_SingleTile)")
    args = parser.parse_args()
    data_dir = Path(args.data_dir) if args.data_dir else DATA_DIR
    download_dem(data_dir)
