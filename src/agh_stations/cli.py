"""Repeatable command-line experiments; no network is used by benchmark or report."""

import argparse
import csv
import hashlib
import json
import platform
from dataclasses import asdict
from pathlib import Path

import numpy as np

from agh_stations.model import Problem
from agh_stations.solvers import exact, solve


def benchmark(args):
    if args.runs < 1:
        raise ValueError("runs must be positive")
    problem = Problem.load(args.problem)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    rows, histories, solutions = [], [], {}
    for method in ("greedy", "random", "abc", *(("exact",) if args.exact else ())):
        repetitions = range(args.runs) if method in {"random", "abc"} else [0]
        for seed in repetitions:
            result = (
                exact(problem, args.p, args.scenario)
                if method == "exact"
                else solve(
                    problem,
                    method,
                    args.p,
                    args.budget,
                    seed,
                    args.scenario,
                    args.foods,
                    args.limit,
                )
            )
            row = {
                "method": method,
                "seed": seed if method in {"random", "abc"} else "",
                "p": args.p,
                "scenario": args.scenario,
                "evaluations": result.evaluations,
                "elapsed_s": result.elapsed_s,
                **problem.metrics(result.selection, args.scenario, args.threshold),
                "candidate_ids": ";".join(problem.candidate_ids[i] for i in result.selection),
            }
            rows.append(row)
            histories.extend(
                {"method": method, "seed": row["seed"], "evaluation": e, "best_m": value}
                for e, value in result.history
            )
            if method not in solutions or result.objective < solutions[method]["objective"]:
                solutions[method] = {
                    **asdict(result),
                    "seed": row["seed"],
                    "candidate_ids": [problem.candidate_ids[i] for i in result.selection],
                    "scenario_metrics": {
                        s: problem.metrics(result.selection, s, args.threshold)
                        for s in problem.scenarios
                    },
                }
                del solutions[method]["history"]
    for name, records in (("runs.csv", rows), ("history.csv", histories)):
        with (output / name).open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(records[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(records)
    summary = {}
    for method in solutions:
        subset = [r for r in rows if r["method"] == method]
        values = [r["mean_distance_m"] for r in subset]
        summary[method] = {
            "runs": len(subset),
            "best_m": min(values),
            "mean_m": float(np.mean(values)),
            "std_m": float(np.std(values, ddof=1)) if len(values) > 1 else 0,
            "median_m": float(np.median(values)),
            "q25_m": float(np.quantile(values, 0.25)),
            "q75_m": float(np.quantile(values, 0.75)),
            "mean_coverage": float(np.mean([r["coverage"] for r in subset])),
            "mean_elapsed_s": float(np.mean([r["elapsed_s"] for r in subset])),
            "min_evaluations": min(r["evaluations"] for r in subset),
            "max_evaluations": max(r["evaluations"] for r in subset),
        }
        if "exact" in solutions:
            optimum = solutions["exact"]["objective"]
            summary[method]["mean_gap_percent"] = (
                100 * (summary[method]["mean_m"] - optimum) / optimum if optimum else None
            )
    metadata = {
        "problem_sha256": hashlib.sha256(Path(args.problem).read_bytes()).hexdigest(),
        "parameters": {k: v for k, v in vars(args).items() if k != "func"},
        "versions": {"python": platform.python_version(), "numpy": np.__version__},
        "rng": "numpy.random.default_rng (PCG64), independent seeds 0..runs-1",
        "timing_scope": "Solver including objective evaluations; excludes loading, OSM and reports",
        "comparison_note": "Same cap; greedy may stop early; exact has its own budget.",
        "summary": summary,
        "best_solutions": solutions,
    }
    (output / "results.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    bench = sub.add_parser("benchmark", help="Compare methods on a frozen problem.json")
    bench.add_argument("--problem", default="data/processed/agh-pilot/problem.json")
    bench.add_argument("--output", default="outputs/demo")
    bench.add_argument("--p", type=int, default=4)
    bench.add_argument("--budget", type=int, default=1000)
    bench.add_argument("--runs", type=int, default=30)
    bench.add_argument("--scenario", default="aggregate")
    bench.add_argument("--threshold", type=float, default=250)
    bench.add_argument("--foods", type=int, default=12)
    bench.add_argument("--limit", type=int, default=30)
    bench.add_argument("--exact", action="store_true")
    bench.set_defaults(func=benchmark)
    prep = sub.add_parser("prepare-osm", help="Fetch a small OSM area; requires the geo extra")
    prep.add_argument("--config", default="configs/agh-pilot.json")
    prep.add_argument("--output", default="data/processed/agh-pilot")
    prep.add_argument("--raw-dir", default="data/raw")
    prep.add_argument("--refresh", action="store_true")

    def prepare_command(args):
        from agh_stations.prepare_osm import prepare

        prepare(args.config, args.output, args.raw_dir, args.refresh)

    prep.set_defaults(func=prepare_command)
    report = sub.add_parser("report", help="Render map and convergence; requires the report extra")
    report.add_argument("--results", default="outputs/demo")
    report.add_argument("--dataset", default="data/processed/agh-pilot")

    def report_command(args):
        from agh_stations.report import render

        render(args.results, args.dataset)

    report.set_defaults(func=report_command)
    args = parser.parse_args()
    try:
        args.func(args)
    except (ValueError, KeyError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
