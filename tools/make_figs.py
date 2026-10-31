"""Vẽ 4 hình (nhãn tiếng Việt) cho mục 5.2 và 5.3 của báo cáo từ benchmark.csv.

Chạy từ thư mục gốc: python tools/make_figs.py [benchmark.csv] [thư mục ra]
Cần: pip install matplotlib
"""
import csv, sys, math
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

# usage: python make_figs.py [benchmark.csv] [output_dir]
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("results/final_run/benchmark.csv")
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("results/figures")
OUT.mkdir(parents=True, exist_ok=True)
rows = list(csv.DictReader(open(SRC, encoding="utf-8")))
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.titlesize": 12, "axes.labelsize": 10.5,
                     "axes.spines.top": False, "axes.spines.right": False, "hatch.linewidth": 0.6})

SOLVERS = ["BFS", "DFS", "UCS", "UCS (risk)", "A* manhattan", "A* modified_manhattan", "A* relaxed"]
LABEL = {"BFS": "BFS", "DFS": "DFS", "UCS": "UCS", "UCS (risk)": "UCS (risk)", "A* manhattan": "A* manhattan",
         "A* modified_manhattan": "A* modified_manhattan", "A* relaxed": "A* relaxed"}
COLOR = {"BFS": "#1f77b4", "DFS": "#ff7f0e", "UCS": "#2ca02c", "UCS (risk)": "#d62728",
         "A* manhattan": "#9467bd", "A* modified_manhattan": "#8c564b", "A* relaxed": "#e377c2"}
HATCH = {"BFS": "", "DFS": "//", "UCS": "", "UCS (risk)": "\\\\", "A* manhattan": "", "A* modified_manhattan": "xx", "A* relaxed": ".."}

def table(set_name):
    d = {}
    for r in rows:
        if r["set"] != set_name: continue
        d[(int(r["level_no"]), r["solver"])] = r
    return d
custom = table("custom")
stages = sorted({k[0] for k in custom})

def per_stage(metric, ylabel, title, fname, log, scale=1.0, label_dfs_above=None):
    fig, ax = plt.subplots(figsize=(10, 4.4), dpi=300)
    n = len(SOLVERS); w = 0.82 / n
    ymin_data = min(float(custom[(s, v)][metric]) / scale for s in stages for v in SOLVERS
                    if custom[(s, v)]["status"] == "ok" and float(custom[(s, v)][metric]) > 0)
    for j, sv in enumerate(SOLVERS):
        xs, ys = [], []
        for i, s in enumerate(stages):
            r = custom[(s, sv)]
            if r["status"] == "ok":
                xs.append(i + (j - (n - 1) / 2) * w); ys.append(float(r[metric]) / scale)
        ax.bar(xs, ys, w * 0.95, color=COLOR[sv], edgecolor="white" if not HATCH[sv] else "#333333",
               hatch=HATCH[sv], linewidth=0.4, label=LABEL[sv], zorder=3)
    if log:
        ax.set_yscale("log"); ax.set_ylim(ymin_data * 0.55, None)
    ax.set_xticks(range(len(stages))); ax.set_xticklabels([str(s) for s in stages])
    ax.set_xlabel("Màn (màn tự thiết kế)"); ax.set_ylabel(ylabel)  # tiêu đề do caption của LaTeX đảm nhiệm
    ax.grid(axis="y", alpha=0.3, zorder=0)
    # đánh dấu T/O cho các lượt hết giờ
    for i, s in enumerate(stages):
        for j, sv in enumerate(SOLVERS):
            if custom[(s, sv)]["status"] == "timeout":
                x = i + (j - (n - 1) / 2) * w
                y = ax.get_ylim()[0] * (1.6 if log else 1) if log else ax.get_ylim()[1] * 0.02
                ax.text(x, y, "T/O", rotation=90, ha="center", va="bottom", fontsize=7.5, color=COLOR[sv], fontweight="bold", zorder=4)
    if label_dfs_above is not None:
        for i, s in enumerate(stages):
            r = custom[(s, "DFS")]
            if r["status"] == "ok" and float(r[metric]) > label_dfs_above:
                j = SOLVERS.index("DFS"); x = i + (j - (n - 1) / 2) * w
                ax.text(x, float(r[metric]), f"{int(float(r[metric]))}", ha="center", va="bottom", fontsize=7.5, color="#b35806")
    handles = [Patch(facecolor=COLOR[v], edgecolor="#333333" if HATCH[v] else "white", hatch=HATCH[v], label=LABEL[v]) for v in SOLVERS]
    leg = fig.legend(handles=handles, loc="upper center", ncol=4, frameon=False, bbox_to_anchor=(0.5, 0.995), fontsize=9)
    fig.text(0.99, 0.01, "T/O: hết thời gian (60 giây)", ha="right", va="bottom", fontsize=8, color="#555555")
    fig.tight_layout(rect=(0, 0.02, 1, 0.9))
    fig.savefig(OUT / fname); plt.close(fig)

per_stage("expanded", "Số nút mở rộng (thang log)", "Số nút mở rộng trên từng màn tự thiết kế", "exp_nodes_custom.png", True)
per_stage("memory_kb", "Bộ nhớ đỉnh (KiB, thang log)", "Bộ nhớ đỉnh trên từng màn tự thiết kế", "exp_memory_custom.png", True)
per_stage("length", "Độ dài lời giải (số hành động)", "Độ dài lời giải trên từng màn tự thiết kế", "exp_length_custom.png", False, label_dfs_above=60)

# --- màn 21
lv21 = {sv: custom[(21, sv)] for sv in SOLVERS}
show = ["BFS", "UCS", "A* manhattan", "A* modified_manhattan", "A* relaxed"]
panels = [("expanded", "Số nút mở rộng", 1.0, "{:,.0f}"), ("time_ms", "Thời gian (giây)", 1000.0, "{:.1f}"),
          ("memory_kb", "Bộ nhớ đỉnh (MB)", 1024.0, "{:.1f}")]
fig, axes = plt.subplots(1, 3, figsize=(10, 3.9), dpi=300)
for ax, (metric, title, scale, fmt) in zip(axes, panels):
    vals = [float(lv21[s][metric]) / scale for s in show]
    bars = ax.bar(range(len(show)), vals, 0.75, color=[COLOR[s] for s in show], hatch=[HATCH[s] for s in show],
                  edgecolor=["#333333" if HATCH[s] else "white" for s in show], linewidth=0.4, zorder=3)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v, fmt.format(v).replace(",", "#").replace(".", ",").replace("#", "."), ha="center", va="bottom", fontsize=8.5)
    ax.set_xticks([]); ax.set_title(title, fontsize=11); ax.grid(axis="y", alpha=0.3, zorder=0)
    ax.set_ylim(0, max(vals) * 1.15)
handles = [Patch(facecolor=COLOR[v], edgecolor="#333333" if HATCH[v] else "white", hatch=HATCH[v], label=LABEL[v]) for v in show]
fig.legend(handles=handles, loc="upper center", ncol=5, frameon=False, bbox_to_anchor=(0.5, 0.995), fontsize=9)
fig.text(0.5, 0.005, "Màn 21 (Grand Teleport Archipelago). DFS không hoàn thành trong 60 giây (T/O) nên không có trong hình.",
         ha="center", va="bottom", fontsize=8.5, color="#555555")
fig.tight_layout(rect=(0, 0.04, 1, 0.9))
fig.savefig(OUT / "exp_level21.png"); plt.close(fig)
print("ok", sorted(p.name for p in OUT.iterdir()))
