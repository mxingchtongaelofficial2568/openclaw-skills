"""Publication-quality comparison figures for Poyang Lake 2020 flood detection.
Generates Fig 1-4: truecolour, TerraMind, LightGBM, and agreement comparison.
"""
import numpy as np, zarr, rasterio
from pathlib import Path
from zarr.storage import ZipStore
import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.patheffects as patheffects

mpl.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
    "axes.spines.right": False, "axes.spines.top": False,
    "axes.linewidth": 0.6,
    "svg.fonttype": "none", "pdf.fonttype": 42,
    "font.size": 8, "axes.titlesize": 9, "axes.labelsize": 8,
    "xtick.labelsize": 7, "ytick.labelsize": 7,
    "legend.frameon": True, "legend.fontsize": 7,
    "legend.edgecolor": "#CCCCCC", "legend.framealpha": 0.95,
})

ROOT = Path(r"C:\Users\24964\Downloads\terramind impactmesh")
OUT = ROOT / "data" / "Poyang_SingleTile" / "output"
OUT.mkdir(parents=True, exist_ok=True)
S2_ZIP = ROOT / "data" / "Poyang_SingleTile" / "S2_4t" / "sample_001_S2_4t.zarr.zip"
H, W = 3660, 3660
KM = 109.8
PX_KM = W / KM


def save_pub(fig, name, dpi=600):
    for ext, kw in [(".svg", {}), (".pdf", {}),
                    (".tiff", {"dpi": dpi, "pil_kwargs": {"compression": "tiff_lzw"}}),
                    (".png", {"dpi": 300})]:
        fig.savefig(str(OUT / f"{name}{ext}"), bbox_inches="tight",
                    pad_inches=0.06, facecolor="white", edgecolor="none", **kw)


def load_tc(t=0):
    with ZipStore(str(S2_ZIP), mode='r') as store:
        arr = np.array(zarr.open(store, mode='r')["bands"])
    return np.stack([arr[t, 3] / 10000, arr[t, 2] / 10000, arr[t, 1] / 10000],
                    axis=-1).astype(np.float32)


def stretch(rgb):
    valid = np.where(rgb.max(axis=-1) > 0)
    out = np.zeros_like(rgb)
    for i in range(3):
        b = rgb[..., i]; bv = b[valid]
        lo, hi = np.percentile(bv, [2, 98])
        out[..., i] = np.clip((b - lo) / (hi - lo + 1e-8), 0, 1)
    out[~np.any(rgb > 0, axis=-1)] = 0.06
    return out.astype(np.float32)


def load_mask(name):
    with rasterio.open(str(OUT / name)) as f:
        return f.read(1).astype(bool)


def add_panel_label(ax, s):
    ax.text(0.025, 0.97, s, transform=ax.transAxes,
            fontsize=10, fontweight="bold", color="black", va="top",
            bbox=dict(facecolor="white", alpha=0.92, pad=1.5,
                      boxstyle="round,pad=0.15", ec="none"))


def add_scalebar(ax, bar_km=20):
    bar_w = int(bar_km * PX_KM)
    x0 = int(0.06 * W)
    y0 = int(0.06 * H)
    ax.plot([x0, x0 + bar_w], [y0, y0], "w-", lw=3.5, solid_capstyle="butt",
            path_effects=[patheffects.withStroke(linewidth=5, foreground="black")])
    ax.text(x0 + bar_w / 2, y0 - 90, f"{bar_km} km", ha="center",
            fontsize=7, color="white", fontweight="bold",
            path_effects=[patheffects.withStroke(linewidth=2.5, foreground="black")])


# -- Load data --
print("Loading...")
bg = stretch(load_tc(0))
tm = load_mask("terramind_flood_4t.tif")
lg = load_mask("lgbm_enhanced_flood.tif")
n_tm, n_lg = int(tm.sum()), int(lg.sum())
pct_tm = 100 * n_tm / (H * W)
pct_lg = 100 * n_lg / (H * W)
a_tm = n_tm * 900 / 1e6
a_lg = n_lg * 900 / 1e6
both    = tm & lg
tm_only = tm & ~lg
lg_only = lg & ~tm
iou_val = both.sum() / max((tm | lg).sum(), 1)
print(f"TerraMind: {n_tm:,} px ({pct_tm:.1f}%)  {a_tm:.1f} km2")
print(f"LightGBM:  {n_lg:,} px ({pct_lg:.1f}%)  {a_lg:.1f} km2")
print(f"IoU: {iou_val:.4f}")

red = np.array([0.85, 0.15, 0.18], dtype=np.float32)


def ov(bg_img, mask, alpha=0.50):
    out = bg_img.copy()
    m = mask.astype(bool)
    for c in range(3):
        out[m, c] = (1 - alpha) * out[m, c] + alpha * red[c]
    return out


# ==============================================================
# Fig 1 -- Pre-flood Truecolor (S2 T0, 2020-04-26)
# ==============================================================
print("Fig 1...")
fig1, ax1 = plt.subplots(figsize=(7.2, 7.2))
ax1.imshow(bg)
ax1.axis("off")
add_scalebar(ax1)
add_panel_label(ax1, "a")
ax1.set_title("Sentinel-2 L2A Truecolour  |  T0 (2020-04-26)  |  28.8% cloud",
              fontsize=9, fontweight="bold", pad=10, color="#4D4D4D")
fig1.tight_layout(pad=0.3); save_pub(fig1, "fig1_truecolor"); plt.close(fig1)


# ==============================================================
# Fig 2 -- TerraMind Flood
# ==============================================================
print("Fig 2...")
fig2, ax2 = plt.subplots(figsize=(7.2, 7.2))
ax2.imshow(ov(bg, tm))
ax2.axis("off")
add_scalebar(ax2)
add_panel_label(ax2, "b")
ax2.set_title(f"TerraMind V1-Base  |  {n_tm:,} px ({pct_tm:.1f}%)  |  {a_tm:.0f} km2  |  60-ch ViT end-to-end",
              fontsize=9, fontweight="bold", pad=10, color="#0F4D92")
fig2.tight_layout(pad=0.3); save_pub(fig2, "fig2_terramind_flood"); plt.close(fig2)


# ==============================================================
# Fig 3 -- LightGBM Flood
# ==============================================================
print("Fig 3...")
fig3, ax3 = plt.subplots(figsize=(7.2, 7.2))
ax3.imshow(ov(bg, lg))
ax3.axis("off")
add_scalebar(ax3)
add_panel_label(ax3, "c")
ax3.set_title(f"LightGBM (GBDT)  |  {n_lg:,} px ({pct_lg:.1f}%)  |  {a_lg:.0f} km2  |  38 features  |  thr=0.71",
              fontsize=9, fontweight="bold", pad=10, color="#42949E")
fig3.tight_layout(pad=0.3); save_pub(fig3, "fig3_lgbm_flood"); plt.close(fig3)


# ==============================================================
# Fig 4 -- Comparison: agreement map + horizontal legend below + bar chart right
# ==============================================================
print("Fig 4...")

# Agreement overlay map
cmp = bg.copy()
alpha = 0.55
cmp[both]    = (1 - alpha) * cmp[both]    + alpha * np.array([0.22, 0.44, 0.74])
cmp[tm_only] = (1 - alpha) * cmp[tm_only] + alpha * np.array([0.85, 0.15, 0.18])
cmp[lg_only] = (1 - alpha) * cmp[lg_only] + alpha * np.array([0.20, 0.68, 0.55])

# Layout: 2 rows x 2 cols
# Row 0 col 0: agreement map
# Row 0 col 1: bar chart
# Row 1 col 0: horizontal legend (below map)
fig4 = plt.figure(figsize=(12, 6.5), facecolor="white")
gs = fig4.add_gridspec(2, 2, height_ratios=[4.0, 0.55], width_ratios=[1.0, 0.65],
                       hspace=0.10, wspace=0.10)

# Panel d -- agreement map (top-left)
ax_d = fig4.add_subplot(gs[0, 0])
ax_d.imshow(cmp)
ax_d.axis("off")
add_scalebar(ax_d)
add_panel_label(ax_d, "d")
ax_d.set_title("Spatial Agreement  --  TM vs LGBM", fontweight="bold",
               fontsize=9, pad=10, color="#4D4D4D")

# Panel e -- horizontal legend below map (bottom-left)
ax_leg = fig4.add_subplot(gs[1, 0])
ax_leg.set_facecolor("white")
ax_leg.axis("off")
ax_leg.set_xlim(0, 10); ax_leg.set_ylim(0, 3)

legend_items = [
    (np.array([0.22, 0.44, 0.74]), "Agreement", f"{both.sum():,} px"),
    (np.array([0.85, 0.15, 0.18]), "TerraMind only", f"{tm_only.sum():,} px"),
    (np.array([0.20, 0.68, 0.55]), "LightGBM only", f"{lg_only.sum():,} px"),
]
x0 = 0.5
for color, label, count in legend_items:
    ax_leg.add_patch(plt.Rectangle((x0, 1.0), 0.6, 0.6,
                                   facecolor=color, edgecolor="none"))
    ax_leg.text(x0 + 0.8, 1.3, label, fontsize=7.5,
                va="center", color="#333333", fontweight="bold")
    ax_leg.text(x0 + 0.8, 0.7, count, fontsize=7,
                va="center", color="#767676")
    x0 += 2.8

ax_leg.text(x0 + 0.3, 1.3, f"IoU = {iou_val:.3f}",
            fontsize=9, fontweight="bold", color="#333333")

# Panel f -- bar chart (top-right)
ax_f = fig4.add_subplot(gs[0, 1])
ax_f.set_facecolor("white")
bar_colors = ["#0F4D92", "#42949E"]
area_vals = [a_tm, a_lg]
pct_vals = [pct_tm, pct_lg]

bars = ax_f.bar(range(2), area_vals, color=bar_colors, width=0.40,
                edgecolor="none", zorder=3)
for bar, val, pct in zip(bars, area_vals, pct_vals):
    ax_f.text(bar.get_x() + bar.get_width() / 2,
              bar.get_height() + max(area_vals) * 0.02,
              f"{val:.0f} km2", ha="center", fontsize=9,
              fontweight="bold", color="#333333")
    ax_f.text(bar.get_x() + bar.get_width() / 2, bar.get_height() / 2,
              f"{pct:.1f}%", ha="center", fontsize=9,
              fontweight="bold", color="white")

ax_f.set_xticks(range(2))
ax_f.set_xticklabels(["TerraMind", "LightGBM"], fontsize=8)
ax_f.set_xlim(-0.55, 1.55)
ax_f.set_ylabel("Flood area (km2)", fontsize=8, color="#4D4D4D", labelpad=6)
ax_f.tick_params(axis="both", labelsize=7.5, colors="#767676")
ax_f.spines[["right", "top"]].set_visible(False)
ax_f.spines[["left", "bottom"]].set_color("#767676")
ax_f.set_ylim(0, max(area_vals) * 1.15)
add_panel_label(ax_f, "e")
ax_f.set_title("Detected Flood Extent", fontweight="bold", fontsize=9,
               pad=12, color="#4D4D4D")

save_pub(fig4, "fig4_comparison")
plt.close(fig4)

print("Done -- 4 figures exported to output/")
