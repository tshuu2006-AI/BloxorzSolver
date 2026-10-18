"""Chạy mọi solver trên mọi màn trong levels/ và xuất bảng, CSV, biểu đồ cho báo cáo.

Ví dụ::

    python benchmark.py                          # tất cả màn (Classic + Custom), tất cả solver
    python benchmark.py --set classic            # chỉ 33 màn gốc;  --set custom: chỉ các màn nhóm thiết kế
    python benchmark.py --repeat 5 --timeout 120 # lấy trung vị 5 lần, giới hạn 120 giây/lần chạy
    python benchmark.py --set custom --levels 1-8,20 --solvers "UCS,A*"
    python benchmark.py --plots                  # thêm biểu đồ (cần: pip install matplotlib)

Mỗi dòng kết quả là một cặp (màn, cấu hình solver). Các cấu hình:

    BFS / DFS / UCS          solver gốc với hàm chi phí mặc định của ``Problem.action_cost``
    UCS (risk)               UCS với chi phí "rủi ro": mỗi ô fragile bị chạm cộng +10 (như Test 2B)
    A* manhattan / orientation / relaxed    A* với từng heuristic

Solver nào chưa có file (ví dụ BFS) sẽ được bỏ qua và báo rõ. Thời gian chạy lấy
trung vị của ``--repeat`` lần; mỗi lần chạy nằm trong một tiến trình con để có thể
dừng khi quá ``--timeout``.
"""

from __future__ import annotations

import argparse
import multiprocessing as mp
import statistics
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from App.Game.experiment import (  # noqa: F401  (một số tên được test và script khác import từ đây)
    FIELDS,
    FRAGILE_PENALTY,
    Config,
    all_configs,
    apply_cost,
    replay_ok,
    run_config,
    run_isolated,
    write_csv,
)
from App.Components.level_loader import load_level
from App.Game.solver_bridge import available_solvers

ROOT = Path(__file__).resolve().parent
LEVELS_DIR = ROOT / "levels"
CLASSIC_DIR = LEVELS_DIR / "classic"
SETS = {"classic": CLASSIC_DIR, "custom": LEVELS_DIR}

# ----------------------------------------------------------------------------
def parse_levels(spec: Optional[str], count: int) -> List[int]:
    """'1-8,20' -> [0..7, 19] (chỉ số 0-based). None = tất cả."""
    if not spec:
        return list(range(count))
    picked: List[int] = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            lo, hi = part.split("-")
            picked += list(range(int(lo) - 1, int(hi)))
        elif part:
            picked.append(int(part) - 1)
    return [i for i in dict.fromkeys(picked) if 0 <= i < count]


def format_table(rows: Sequence[Dict]) -> str:
    cols = [("Set", "set", 7), ("#", "level_no", 3), ("Stage", "level", 18), ("Solver", "solver", 15), ("Status", "status", 11),
            ("Len", "length", 5), ("Moves", "moves", 5), ("Cost", "cost", 5),
            ("Expanded", "expanded", 9), ("Time ms", "time_ms", 10), ("Mem KB", "memory_kb", 9)]
    lines = ["  ".join(f"{h:<{w}}" for h, _, w in cols)]
    lines.append("  ".join("-" * w for _, _, w in cols))
    for r in rows:
        lines.append("  ".join(f"{str(r.get(k, ''))[:w]:<{w}}" for _, k, w in cols))
    return "\n".join(lines)


def plot_results(rows: Sequence[Dict], out_dir: Path) -> List[Path]:
    """Mỗi nhóm màn (classic / custom) một bộ biểu đồ riêng, thêm hậu tố tên nhóm vào tên file."""
    written: List[Path] = []
    for section in dict.fromkeys(r.get("set", "") for r in rows):
        subset = [r for r in rows if r.get("set", "") == section]
        written += _plot_set(subset, out_dir, f"_{section}" if section else "")
    return written


def _plot_set(rows: Sequence[Dict], out_dir: Path, suffix: str) -> List[Path]:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("Bỏ qua biểu đồ: chưa cài matplotlib (pip install matplotlib)", file=sys.stderr)
        return []
    ok = [r for r in rows if r.get("status") == "ok"]
    solvers = list(dict.fromkeys(r["solver"] for r in ok))
    levels = sorted({(r["level_no"], r["level"]) for r in ok})
    groups = list(dict.fromkeys(r["group"] for r in ok))
    metrics = [("time_ms", "Search time (ms)", True), ("memory_kb", "Peak memory (KB)", True),
               ("expanded", "Expanded nodes", True), ("length", "Solution length (actions)", False),
               ("cost", "Solution cost", False)]
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    width = 0.8 / max(1, len(solvers))
    for key, title, logy in metrics:
        fig, ax = plt.subplots(figsize=(max(10, len(levels) * 0.9), 5.5))
        for si, solver in enumerate(solvers):
            ys = []
            for no, _ in levels:
                match = [r[key] for r in ok if r["level_no"] == no and r["solver"] == solver]
                ys.append(float(match[0]) if match else float("nan"))
            ax.bar([i + si * width for i in range(len(levels))], ys, width, label=solver)
        ax.set_xticks([i + 0.4 - width / 2 for i in range(len(levels))])
        ax.set_xticklabels([f"{no}" for no, _ in levels])
        ax.set_xlabel("Stage")
        ax.set_ylabel(title)
        if logy:
            ax.set_yscale("log")
        ax.set_title(f"{title} per stage")
        ax.legend(ncol=min(4, len(solvers)), fontsize=8)
        fig.tight_layout()
        path = out_dir / f"{key}{suffix}.png"
        fig.savefig(path, dpi=130)
        plt.close(fig)
        written.append(path)

    # trung bình theo nhóm màn (mức độ khó)
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8))
    for ax, (key, title, _) in zip(axes, (metrics[0], metrics[2], metrics[3])):
        for si, solver in enumerate(solvers):
            ys = []
            for g in groups:
                vals = [float(r[key]) for r in ok if r["group"] == g and r["solver"] == solver]
                ys.append(statistics.fmean(vals) if vals else float("nan"))
            ax.bar([i + si * width for i in range(len(groups))], ys, width, label=solver)
        ax.set_xticks([i + 0.4 - width / 2 for i in range(len(groups))])
        ax.set_xticklabels(groups)
        ax.set_title(f"Mean {title.lower()} by group")
        if key != "length":
            ax.set_yscale("log")
    axes[0].legend(fontsize=7)
    fig.tight_layout()
    path = out_dir / f"by_group{suffix}.png"
    fig.savefig(path, dpi=130)
    plt.close(fig)
    written.append(path)
    return written


# ----------------------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--set", choices=("all", "classic", "custom"), default="all",
                    help="nhóm màn: classic (33 màn gốc), custom (màn nhóm tự thiết kế) hoặc all")
    ap.add_argument("--levels", help="vd 1-8,20 (số thứ tự trong nhóm, áp cho từng nhóm đã chọn); mặc định: tất cả")
    ap.add_argument("--solvers", help="lọc theo nhãn, ngăn cách bằng dấu phẩy, vd 'UCS,A*'")
    ap.add_argument("--repeat", type=int, default=1, help="số lần chạy mỗi cấu hình (lấy trung vị thời gian/bộ nhớ)")
    ap.add_argument("--timeout", type=float, default=60.0, help="giây tối đa cho mỗi cấu hình trên mỗi màn")
    ap.add_argument("--out", default=str(ROOT / "results"), help="thư mục xuất kết quả")
    ap.add_argument("--plots", action="store_true", help="vẽ biểu đồ (cần matplotlib)")
    args = ap.parse_args(argv)

    chosen = [s for s in SETS if args.set in ("all", s) and SETS[s].exists()]
    work = []  # (nhóm, số thứ tự trong nhóm, đường dẫn)
    for section in chosen:
        paths = sorted(SETS[section].glob("*.json"))
        work += [(section, i + 1, paths[i]) for i in parse_levels(args.levels, len(paths))]
    avail = available_solvers()
    wanted = {s.strip().lower() for s in args.solvers.split(",")} if args.solvers else None

    configs = []
    for cfg in all_configs():
        if wanted and not any(w in cfg.label.lower() for w in wanted):
            continue
        if not avail.get(cfg.solver, False):
            print(f"[skip] {cfg.label}: chưa có solver {cfg.solver}")
            continue
        configs.append(cfg)
    if not configs or not work:
        print("Không có gì để chạy.")
        return 1

    rows: List[Dict] = []
    total = len(work) * len(configs)
    for section, number, path in work:
        level = load_level(path, section)
        for cfg in configs:
            result = run_isolated(path, number, section, cfg, args.repeat, args.timeout)
            if "level" not in result:
                result = {"set": section, "level_no": number, "level": level.name, "group": level.group,
                          "rows": level.rows, "cols": level.cols, "solver": cfg.label, **result}
            rows.append(result)
            print(f"[{len(rows)}/{total}] {section}#{number} {level.name:<18} {cfg.label:<15} {result.get('status')}", flush=True)

    out = Path(args.out)
    write_csv(rows, out / "benchmark.csv")
    print()
    print(format_table(rows))
    print(f"\nĐã ghi {out / 'benchmark.csv'}")
    bad = [r for r in rows if r.get("status") == "ok" and r.get("valid") is False]
    if bad:
        print(f"CẢNH BÁO: {len(bad)} lời giải không đi tới đích khi phát lại!", file=sys.stderr)
    if args.plots:
        for path in plot_results(rows, out):
            print(f"Đã ghi {path}")
    return 1 if bad else 0


if __name__ == "__main__":
    mp.freeze_support()
    sys.exit(main())
