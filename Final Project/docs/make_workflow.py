"""
make_workflow.py
Draws the workflow diagram (docs/workflow.png and docs/workflow.pdf) used in the
README and in the report. Run from the repository folder:  python docs/make_workflow.py
Positions are in inches on a 6.5-inch-wide page.
"""
from pathlib import Path
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

plt.rcParams["font.family"] = "serif"
plt.rcParams["font.serif"] = ["Times New Roman", "Liberation Serif", "Times", "DejaVu Serif"]

INK = "#1F2A44"      # text and lines
STEP = "#EEF2F7"     # step containers
GREEN, GREEN_LINE = "#E7F0E7", "#3A5F3A"
INPUT = "#F2F2F2"
OUT_LINE = "#2E5C9A"

W, H = 6.5, 7.9
fig = plt.figure(figsize=(W, H))
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(-0.04, W + 0.04)
ax.set_ylim(H + 0.02, -0.04)          # y grows downward, like a page
ax.axis("off")


def box(x, y, w, h, title, lines=(), fill="white", edge=INK, title_size=8.5, body_size=7.3,
        dashed=False, center=True, lw=0.9):
    """A rectangle with a bold title and body lines."""
    ax.add_patch(Rectangle((x, y), w, h, facecolor=fill, edgecolor=edge, linewidth=lw,
                           linestyle=(0, (4, 2)) if dashed else "solid"))
    tx = x + w / 2 if center else x + 0.08
    ha = "center" if center else "left"
    ax.text(tx, y + 0.07, title, ha=ha, va="top", fontsize=title_size, fontweight="bold", color=INK)
    for i, line in enumerate(lines):
        ax.text(tx, y + 0.07 + title_size / 72 * 1.35 + i * body_size / 72 * 1.25, line,
                ha=ha, va="top", fontsize=body_size, color=INK)


def output(ystep, hstep, title, lines):
    h = 0.32 + 0.155 * len(lines)
    box(OX, ystep + (hstep - h) / 2, OW, h, title, lines, edge=OUT_LINE)
    arrow([(LW, ystep + hstep / 2), (OX, ystep + hstep / 2)])


def container(x, y, w, h, title, fill=STEP, edge=INK):
    ax.add_patch(Rectangle((x, y), w, h, facecolor=fill, edgecolor=edge, linewidth=1.1))
    ax.text(x + 0.1, y + 0.07, title, ha="left", va="top", fontsize=10, fontweight="bold", color=INK)


def arrow(points, dashed=False):
    """Arrow along a list of (x, y) points; the head is at the last point."""
    style = (0, (4, 2)) if dashed else "solid"
    xs, ys = zip(*points)
    if len(points) > 2:
        ax.plot(xs[:-1], ys[:-1], color=INK, linewidth=0.9, linestyle=style)
    ax.annotate("", xy=points[-1], xytext=points[-2],
                arrowprops=dict(arrowstyle="-|>", color=INK, lw=0.9, linestyle=style,
                                shrinkA=0, shrinkB=0, mutation_scale=8))


LW = 4.75             # width of the step column
OX, OW = 4.95, 1.55   # output column

# ---------------- inputs ----------------
iy, ih = 0.0, 0.62
iw = (LW - 0.3) / 3
inputs = [("ACS 2020–2024 5-year", ["Census Data API", "estimates + MOEs"]),
          ("TIGER/Line 2024", ["block group, tract,", "county polygons"]),
          ("config.toml", ["state, year, indicators,", "thresholds, paths"])]
for k, (t, l) in enumerate(inputs):
    box(0.0 + k * (iw + 0.15), iy, iw, ih, t, l, fill=INPUT)
ax.text(OX + OW / 2, iy + ih / 2, "Outputs", ha="center", va="center", fontsize=10,
        fontweight="bold", color=INK)

# ---------------- step 1 ----------------
y1, h1 = 0.9, 1.22
for k in range(3):
    cx = k * (iw + 0.15) + iw / 2
    arrow([(cx, iy + ih), (cx, y1)])
container(0, y1, LW, h1, "1. Prepare data (each scale)")
sw = (LW - 0.2 - 2 * 0.2) / 3
sy, sh = y1 + 0.32, 0.8
s1 = [("Download", ["download_acs", "download_boundaries", "saved once in data/raw", "+ metadata.csv; retry 3×"]),
      ("Indicators and MOEs", ["clean_acs", "compute_indicators", "25 indicators, MOEs by", "Census formulas"]),
      ("Screen and project", ["check_availability", "screen_units", "drop if > 20% missing", "EPSG:5070 (equal area)"])]
for k, (t, l) in enumerate(s1):
    x = 0.1 + k * (sw + 0.2)
    box(x, sy, sw, sh, t, l)
    if k < 2:
        arrow([(x + sw, sy + sh / 2), (x + sw + 0.2, sy + sh / 2)])
output(y1, h1, "O0  Data description",
       ["describe_indicators", "reliability_table (CV)", "plot_indicator_maps", "24 indicator maps,", "statistics tables"])

# ---------------- step 2 ----------------
y2, h2 = y1 + h1 + 0.28, 1.76
arrow([(LW / 2, y1 + h1), (LW / 2, y2)])
container(0, y2, LW, h2, "2. Build the index: build_index (loop over 3 scales)")
bw = (LW - 0.2 - 3 * 0.18) / 4
r1y, rh = y2 + 0.32, 0.5
row1 = [("2a  Standardize", ["z-scores"]), ("2b  PCA", ["correlation matrix"]),
        ("2c  Components", ["eigenvalue > 1"]), ("2d  Varimax", ["rotation"])]
for k, (t, l) in enumerate(row1):
    x = 0.1 + k * (bw + 0.18)
    box(x, r1y, bw, rh, t, l)
    if k < 3:
        arrow([(x + bw, r1y + rh / 2), (x + bw + 0.18, r1y + rh / 2)])
r2y = r1y + rh + 0.2
row2 = [("2e  Direction", ["|loading| ≥ 0.5 and", "indicator directions"]),
        ("2f  Sum", ["equal weights"]),
        ("2g  Rank", ["percentile 0–100"])]
for k, (t, l) in enumerate(row2):
    x = 0.1 + k * (bw + 0.18)
    box(x, r2y, bw, rh + 0.1, t, l)
    if k < 2:
        arrow([(x + bw, r2y + (rh + 0.1) / 2), (x + bw + 0.18, r2y + (rh + 0.1) / 2)])
# elbow from 2d down to 2e
x2d = 0.1 + 3 * (bw + 0.18) + bw / 2
x2e = 0.1 + bw / 2
mid = r1y + rh + 0.1
arrow([(x2d, r1y + rh), (x2d, mid), (x2e, mid), (x2e, r2y)])
xc = 0.1 + 3 * (bw + 0.18)
box(xc, r2y, bw, rh + 0.1, "Checks", ["additive_index", "fixed structure"], dashed=True)
arrow([(0.1 + 2 * (bw + 0.18) + bw, r2y + (rh + 0.1) / 2), (xc, r2y + (rh + 0.1) / 2)], dashed=True)
output(y2, h2, "O1  Index", ["index maps (PCA and", "additive), loadings,", "index_structure.csv"])

# ---------------- step 3 ----------------
y3, h3 = y2 + h2 + 0.28, 2.0
arrow([(LW / 2, y2 + h2), (LW / 2, y3)])
container(0, y3, LW, h3, "3. Map the differences (loop over 3 pairs of scales)", fill=GREEN, edge=GREEN_LINE)
hw = (LW - 0.2 - 0.3) / 2
ay, ah = y3 + 0.32, 0.72
box(0.1, ay, hw, ah, "a  MOE simulation",
    ["simulate_ranks: 500 draws,", "indicator ~ Normal(value, MOE / 1.645)", "same structure, fixed seed"], edge=GREEN_LINE)
box(0.1 + hw + 0.3, ay, hw, ah, "b  Overlay and subtract",
    ["difference_table: larger unit from GEOID", "diff = small rank − large rank", "+ land area and population"], edge=GREEN_LINE)
cy, ch = ay + ah + 0.22, 0.62
box(0.1, cy, hw, ch, "c  Reliability",
    ["add_reliability: reliable if the", "90% interval excludes 0"], edge=GREEN_LINE)
box(0.1 + hw + 0.3, cy, hw, ch, "d  Map and summarize",
    ["plot_difference_maps (gray mask)", "summarize_differences (area, population)"], edge=GREEN_LINE)
xa = 0.1 + hw / 2
xb = 0.1 + hw + 0.3 + hw / 2
arrow([(xa, ay + ah), (xa, cy)])
arrow([(xb, ay + ah), (xb, ay + ah + 0.11), (xa + 0.25, ay + ah + 0.11), (xa + 0.25, cy)])
arrow([(0.1 + hw, cy + ch / 2), (0.1 + hw + 0.3, cy + ch / 2)])
output(y3, h3, "O2  Differences", ["3 difference maps", "(all / reliable only)", "difference_summary.csv"])

# ---------------- step 4 ----------------
y4, h4 = y3 + h3 + 0.28, 1.12
arrow([(LW / 2, y3 + h3), (LW / 2, y4)])
container(0, y4, LW, h4, "4. Compare scales and test")
tw = (LW - 0.2 - 2 * 0.15) / 3
ty, th = y4 + 0.32, 0.7
tests = [("compare_scales", ["rank correlation", "top-20% agreement", "reliable share, checks"]),
         ("check_nesting", ["point in parent polygon", "(GEOID vs geometry)"]),
         ("Hand check", ["hand_check_table", "vs data.census.gov"])]
for k, (t, l) in enumerate(tests):
    box(0.1 + k * (tw + 0.15), ty, tw, th, t, l)
output(y4, h4, "O3  Comparison", ["scale_comparison.csv", "test_nesting.csv"])

out = Path(__file__).resolve().parent
fig.savefig(out / "workflow.png", dpi=300)
fig.savefig(out / "workflow.pdf")
print("Saved", out / "workflow.png")
