"""Chạy mọi solver trên mọi màn trong levels/ và xuất bảng, CSV, biểu đồ cho báo cáo.

Ví dụ::

    python benchmark.py                          # 55 màn x 7 cấu hình, mặc định lặp 3 lần
    python benchmark.py --set classic            # chỉ 33 màn gốc;  --set custom: chỉ các màn nhóm thiết kế
    python benchmark.py --repeat 5 --timeout 120 # trung vị 5 lần, giới hạn 120 giây mỗi lần
    python benchmark.py --set custom --levels 1-8,20 --solvers "UCS,A*"
    python benchmark.py --plots                  # thêm biểu đồ (cần: pip install matplotlib)

Mỗi dòng kết quả là một cặp (màn, cấu hình solver). Các cấu hình:

    BFS / DFS / UCS          solver gốc với hàm chi phí mặc định của ``Problem.action_cost``
    UCS (risk)               UCS với chi phí "rủi ro": mỗi ô fragile bị chạm cộng +10 (như Test 2B)
    A* manhattan / modified_manhattan / relaxed / relaxed (after)

Solver nào chưa có file (ví dụ BFS) sẽ được bỏ qua và báo rõ. Thời gian chạy lấy
trung vị của ``--repeat`` lần; mỗi lần chạy nằm trong một tiến trình con để có thể
dừng khi quá ``--timeout``.
"""

from __future__ import annotations

import argparse
import csv
import multiprocessing as mp
import statistics
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Dict, List, Optional, Sequence

if hasattr(sys.stdout, "reconfigure"):  # in tiếng Việt đúng trên console Windows
    sys.stdout.reconfigure(encoding="utf-8")

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:  # chạy trực tiếp `python tools/benchmark.py` từ thư mục gốc
    sys.path.insert(0, str(_ROOT))

from App.Game.experiment import (  # noqa: F401  (một số tên được test và script khác import từ đây)
    Config,
    all_configs,
    apply_cost,
    replay_ok,
)
from App.Components.level_loader import load_level
from App.Game.solver_bridge import available_solvers, make_solver

ROOT = Path(__file__).resolve().parent
LEVELS_DIR = ROOT / "levels"
CLASSIC_DIR = LEVELS_DIR / "classic"
SETS = {"classic": CLASSIC_DIR, "custom": LEVELS_DIR}
GROUP_ORDER = ("simple", "fragile", "switch", "split", "combined", "classic", "all")
REPORT_FIELDS = [
    "set", "level_no", "level", "group", "rows", "cols", "solver", "status",
    "length", "moves", "cost", "expanded", "time_ms", "memory_kb", "valid",
    "successes", "attempts", "heuristic_first_ms", "heuristic_cached_mean_us",
    "heuristic_cache_calls", "heuristic_speedup", "repeat_metrics_consistent",
]


class _TimedHeuristic:
    """Measure the cold build and warm cached calls without retaining samples."""

    def __init__(self, inner):
        self.inner = inner
        self.calls = 0
        self.first_ns = None
        self.cached_ns = 0
        self.cached_calls = 0

    def __call__(self, state, problem):
        start = time.perf_counter_ns()
        value = self.inner(state, problem)
        elapsed = time.perf_counter_ns() - start
        if self.calls == 0:
            self.first_ns = elapsed
        else:
            self.cached_ns += elapsed
            self.cached_calls += 1
        self.calls += 1
        return value

    def metrics(self) -> Dict:
        cached_mean = self.cached_ns / self.cached_calls if self.cached_calls else None
        first_ms = self.first_ns / 1_000_000 if self.first_ns is not None else None
        speedup = self.first_ns / cached_mean if cached_mean else None
        return {
            "heuristic_first_ms": round(first_ms, 6) if first_ms is not None else None,
            "heuristic_cached_mean_us": round(cached_mean / 1_000, 4) if cached_mean is not None else None,
            "heuristic_cache_calls": self.cached_calls,
            "heuristic_speedup": round(speedup, 1) if speedup is not None else None,
        }


def _measurement_child(path: str, number: int, section: str, config: Config, out) -> None:
    """Run one measured attempt and return solver, validation, and cache metrics."""
    try:
        level = load_level(path, section)
        problem = level.problem
        apply_cost(problem, config.cost)
        solver = make_solver(config.solver, config.heuristic)
        timed_heuristic = None
        if config.solver == "A*" and config.heuristic == "relaxed":
            timed_heuristic = _TimedHeuristic(solver._heuristic)
            solver._heuristic = timed_heuristic

        # "A* relaxed (after)" primes the relaxed distance cache before
        # measuring the search. Its time therefore excludes the one-time graph
        # construction and reflects repeated O(1) heuristic lookups.
        warm_relaxed = config.label == "A* relaxed (after)"
        if warm_relaxed:
            # Track the retained distance table as memory, but keep its graph
            # construction outside the solver's timed search interval.
            tracemalloc.start()
            solver._heuristic(problem.initial_state, problem)

        actions = solver.solve(problem)
        metrics = solver.get_metrics()
        result = {
            "status": "ok" if actions is not None else "no_solution",
            "length": metrics["solution_length"] if actions is not None else None,
            "moves": sum(a != "SWITCH" for a in actions) if actions is not None else None,
            "cost": metrics["solution_cost"] if actions is not None else None,
            "expanded": metrics["expanded_nodes"],
            "time_ms": round(metrics["search_time_sec"] * 1000, 3),
            "memory_kb": round(metrics["peak_memory_kb"], 1),
            "valid": replay_ok(problem, actions) if actions is not None else None,
        }
        if timed_heuristic is not None:
            result.update(timed_heuristic.metrics())
        out.put(result)
    except Exception as exc:
        out.put({"status": f"error: {type(exc).__name__}: {exc}"})


def _run_attempt(path: Path, number: int, section: str, config: Config, timeout: float) -> Dict:
    """Run one repetition in its own process and enforce its individual timeout."""
    ctx = mp.get_context("spawn")
    out = ctx.Queue()
    proc = ctx.Process(
        target=_measurement_child,
        args=(str(path), number, section, config, out),
        daemon=True,
    )
    proc.start()
    proc.join(timeout)
    if proc.is_alive():
        proc.terminate()
        proc.join()
        return {"status": "timeout"}
    try:
        return out.get(timeout=5)
    except Exception:
        return {"status": "error: worker returned no result"}


def _median(values: Sequence) -> Optional[float]:
    vals = [v for v in values if isinstance(v, (int, float))]
    return statistics.median(vals) if vals else None


def _aggregate_attempts(meta: Dict, attempts: Sequence[Dict]) -> Dict:
    """Collapse repeated attempts to median search metrics and preserve counts."""
    successful = [r for r in attempts if r.get("status") == "ok"]
    row = dict(meta)
    row["attempts"] = len(attempts)
    row["successes"] = len(successful)
    statuses = [r.get("status") for r in attempts]
    row["status"] = "ok" if successful and all(s == "ok" for s in statuses) else (
        "no_solution" if statuses and all(s == "no_solution" for s in statuses) else "partial"
    )
    for field in ("expanded", "time_ms", "memory_kb", "heuristic_first_ms",
                  "heuristic_cached_mean_us", "heuristic_cache_calls", "heuristic_speedup"):
        row[field] = _median([r.get(field) for r in attempts])
    for field in ("length", "moves", "cost"):
        row[field] = _median([r.get(field) for r in successful])
    row["repeat_metrics_consistent"] = (
        all(
            len({r.get(field) for r in successful if r.get(field) is not None}) <= 1
            for field in ("expanded", "length", "cost")
        ) if successful else None
    )
    row["valid"] = bool(successful) and all(r.get("valid") is True for r in successful)
    errors = [r["status"] for r in attempts if r.get("status") not in ("ok", "no_solution")]
    if errors and not successful:
        row["status"] = errors[0]
    return row

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
    cols = [("Set", "set", 7), ("#", "level_no", 3), ("Stage", "level", 18), ("Solver", "solver", 24), ("Status", "status", 11),
            ("Len", "length", 5), ("Moves", "moves", 5), ("Cost", "cost", 5),
            ("Expanded", "expanded", 9), ("Time ms", "time_ms", 10), ("Mem KB", "memory_kb", 9)]
    lines = ["  ".join(f"{h:<{w}}" for h, _, w in cols)]
    lines.append("  ".join("-" * w for _, _, w in cols))
    for r in rows:
        lines.append("  ".join(f"{str(r.get(k, ''))[:w]:<{w}}" for _, k, w in cols))
    return "\n".join(lines)


def _report_groups(rows: Sequence[Dict]) -> Dict[str, List[Dict]]:
    groups = {name: [] for name in GROUP_ORDER}
    for row in rows:
        if row.get("status") not in ("ok", "partial", "no_solution"):
            continue
        category = "classic" if row.get("set") == "classic" else str(row.get("group", "")).lower()
        if category in groups and category != "all":
            groups[category].append(row)
        groups["all"].append(row)
    return groups


def grouped_metric_table(rows: Sequence[Dict], metric: str, title: str, precision: int = 1) -> str:
    """Format per-configuration medians across the report's level groups."""
    groups = _report_groups(rows)
    solvers = list(dict.fromkeys(row["solver"] for row in rows))
    labels = ["Simple", "Fragile", "Switch", "Split", "Combined", "Classic", "All"]
    widths = [max(24, len("Algorithm"))] + [max(9, len(label)) for label in labels]
    header = ["Algorithm"] + labels
    lines = [title, "  ".join(f"{cell:<{widths[i]}}" for i, cell in enumerate(header))]
    lines.append("  ".join("-" * width for width in widths))
    for solver in solvers:
        cells = [solver]
        for group in GROUP_ORDER:
            vals = [row.get(metric) for row in groups[group] if row["solver"] == solver]
            value = _median(vals)
            cells.append("—" if value is None else f"{value:.{precision}f}")
        lines.append("  ".join(f"{cell:<{widths[i]}}" for i, cell in enumerate(cells)))
    return "\n".join(lines)


def heuristic_ratio_table(rows: Sequence[Dict], metric: str, title: str) -> str:
    """Summarize per-level A*/UCS ratios by level group, as in the report."""
    ratios = heuristic_ratio_values(rows, metric)
    group_labels = ["Simple", "Fragile", "Switch", "Split", "Combined", "Classic", "All"]
    widths = [24] + [max(9, len(label)) for label in group_labels]
    lines = [title, "  ".join(f"{label:<{widths[i]}}" for i, label in enumerate(["Heuristic"] + group_labels))]
    lines.append("  ".join("-" * width for width in widths))
    for solver, ratios_by_group in ratios.items():
        cells = [solver.removeprefix("A* ")]
        cells += ["—" if not ratios_by_group[g] else f"{statistics.median(ratios_by_group[g]):.2f}"
                  for g in GROUP_ORDER]
        lines.append("  ".join(f"{cell:<{widths[i]}}" for i, cell in enumerate(cells)))
    return "\n".join(lines)


def write_report_csv(rows: Sequence[Dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=REPORT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in REPORT_FIELDS} for row in rows)


def write_grouped_summary(rows: Sequence[Dict], path: Path) -> None:
    groups = _report_groups(rows)
    fields = ("expanded", "time_ms", "memory_kb", "length", "cost",
              "heuristic_first_ms", "heuristic_cached_mean_us", "heuristic_speedup")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=("metric", "solver", "group", "median"))
        writer.writeheader()
        for metric in fields:
            for solver in dict.fromkeys(row["solver"] for row in rows):
                for group in GROUP_ORDER:
                    values = [r.get(metric) for r in groups[group] if r["solver"] == solver]
                    median = _median(values)
                    if median is not None:
                        writer.writerow({"metric": metric, "solver": solver, "group": group, "median": median})
        # Per-level A*/UCS ratios isolate heuristic effects from board difficulty.
        for metric in ("expanded", "time_ms", "memory_kb"):
            ratios = heuristic_ratio_values(rows, metric)
            for solver, by_group in ratios.items():
                for group, values in by_group.items():
                    if values:
                        writer.writerow({"metric": f"{solver}/{metric}/UCS", "solver": solver,
                                         "group": group, "median": statistics.median(values)})


def heuristic_ratio_values(rows: Sequence[Dict], metric: str) -> Dict[str, Dict[str, List[float]]]:
    baseline = {(r["set"], r["level_no"]): r.get(metric) for r in rows if r.get("solver") == "UCS"}
    result: Dict[str, Dict[str, List[float]]] = {}
    for row in rows:
        solver = row.get("solver", "")
        value = row.get(metric)
        ucs = baseline.get((row.get("set"), row.get("level_no")))
        if not solver.startswith("A*") or not isinstance(value, (int, float)) or not isinstance(ucs, (int, float)) or ucs <= 0:
            continue
        group = "classic" if row.get("set") == "classic" else str(row.get("group", "")).lower()
        result.setdefault(solver, {g: [] for g in GROUP_ORDER})
        result[solver][group].append(value / ucs)
        result[solver]["all"].append(value / ucs)
    return result


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
    measured = [r for r in rows if r.get("expanded") is not None]
    solvers = list(dict.fromkeys(r["solver"] for r in measured))
    levels = sorted({(r["level_no"], r["level"]) for r in measured})
    groups = list(dict.fromkeys(r["group"] for r in measured))
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
                match = [r.get(key) for r in measured if r["level_no"] == no and r["solver"] == solver]
                ys.append(float(match[0]) if match and match[0] is not None else float("nan"))
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

    # Group plot uses medians, matching the summary tables.
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8))
    for ax, (key, title, _) in zip(axes, (metrics[0], metrics[2], metrics[3])):
        for si, solver in enumerate(solvers):
            ys = []
            for g in groups:
                vals = [float(r[key]) for r in measured if r.get(key) is not None
                        and r["group"] == g and r["solver"] == solver]
                ys.append(statistics.median(vals) if vals else float("nan"))
            ax.bar([i + si * width for i in range(len(groups))], ys, width, label=solver)
        ax.set_xticks([i + 0.4 - width / 2 for i in range(len(groups))])
        ax.set_xticklabels(groups)
        ax.set_title(f"Median {title.lower()} by group")
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
    ap.add_argument("--repeat", type=int, default=3, help="số lần chạy mỗi cấu hình, mỗi lần trong tiến trình riêng (lấy trung vị)")
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

    # Compare the requested seven configurations. UCS risk remains available
    # in experiment.py but is intentionally omitted from this report run set.
    available_configs = [cfg for cfg in all_configs() if cfg.cost == "default"]
    relaxed_config = next(
        (cfg for cfg in available_configs if cfg.solver == "A*" and cfg.heuristic == "relaxed"),
        None,
    )
    if relaxed_config is not None:
        available_configs.append(Config("A* relaxed (after)", "A*", heuristic="relaxed"))

    configs = []
    for cfg in available_configs:
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
    total_attempts = total * max(1, args.repeat)
    attempt_number = 0
    for section, number, path in work:
        level = load_level(path, section)
        for cfg in configs:
            meta = {"set": section, "level_no": number, "level": level.name, "group": level.group,
                    "rows": level.rows, "cols": level.cols, "solver": cfg.label}
            attempts = []
            for repetition in range(max(1, args.repeat)):
                attempt_number += 1
                result = _run_attempt(path, number, section, cfg, args.timeout)
                attempts.append(result)
                print(
                    f"[{attempt_number}/{total_attempts}] {section}#{number} {level.name:<18} "
                    f"{cfg.label:<24} run {repetition + 1}/{max(1, args.repeat)} {result.get('status')}",
                    flush=True,
                )
            result = _aggregate_attempts(meta, attempts)
            rows.append(result)

    out = Path(args.out)
    write_report_csv(rows, out / "benchmark.csv")
    print()
    print(format_table(rows))
    print(f"\nĐã ghi {out / 'benchmark.csv'}")
    solved_attempts = sum(int(r.get("successes") or 0) for r in rows)
    attempts_total = sum(int(r.get("attempts") or 0) for r in rows)
    valid_groups = sum(bool(r.get("successes")) and r.get("valid") is True for r in rows)
    consistent = sum(r.get("repeat_metrics_consistent") is True for r in rows)
    print(f"Solved attempts: {solved_attempts}/{attempts_total}; valid solution rows: {valid_groups}/{len(rows)}")
    print(f"Expanded nodes, solution length, and cost were consistent across repeats in {consistent}/{len(rows)} configurations.")
    print()
    for metric, title, precision in (
        ("expanded", "Expanded nodes (median by level group)", 0),
        ("time_ms", "Search time, ms (median by level group)", 1),
        ("memory_kb", "Peak memory, KiB (median by level group)", 0),
    ):
        print(grouped_metric_table(rows, metric, title, precision))
        print()
    print(grouped_metric_table(rows, "length", "Solution length, actions (median)", 0))
    print(grouped_metric_table(rows, "cost", "Solution cost (median)", 0))
    print()
    print(heuristic_ratio_table(rows, "expanded", "A* / UCS expanded-node ratio (median per level)"))
    print(heuristic_ratio_table(rows, "time_ms", "A* / UCS runtime ratio (median per level)"))
    print(heuristic_ratio_table(rows, "memory_kb", "A* / UCS peak-memory ratio (median per level)"))
    relaxed = [r for r in rows if r.get("solver", "").startswith("A* relaxed")
               and r.get("heuristic_first_ms") is not None]
    if relaxed:
        print()
        print(grouped_metric_table(relaxed, "heuristic_first_ms", "Relaxed heuristic: first evaluation, ms", 3))
        print(grouped_metric_table(relaxed, "heuristic_cached_mean_us", "Relaxed heuristic: subsequent cached calls, mean µs", 3))
        print(grouped_metric_table(relaxed, "heuristic_speedup", "Relaxed heuristic: first/cached call speedup", 1))
        print("Cached-call timing is averaged across evaluations within each run; the graph is built on the first call and reused thereafter.")

    summary_path = out / "benchmark_summary.csv"
    write_grouped_summary(rows, summary_path)
    print(f"Summary CSV: {summary_path}")
    bad = [r for r in rows if r.get("successes", 0) and r.get("valid") is False]
    if bad:
        print(f"CẢNH BÁO: {len(bad)} lời giải không đi tới đích khi phát lại!", file=sys.stderr)
    if args.plots:
        for path in plot_results(rows, out):
            print(f"Đã ghi {path}")
    return 1 if bad else 0


if __name__ == "__main__":
    mp.freeze_support()
    sys.exit(main())
