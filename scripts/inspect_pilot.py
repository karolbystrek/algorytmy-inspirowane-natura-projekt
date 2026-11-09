"""Reproduce exploratory diagnostics of the frozen pilot, without downloading data."""

import hashlib
import json
from pathlib import Path

import numpy as np

from agh_stations.model import Problem
from agh_stations.solvers import exact


def main():
    root = Path(__file__).resolve().parents[1]
    problem_path = root / "data/processed/agh-pilot/problem.json"
    results_path = root / "reports/pilot/results.json"
    output_path = root / "reports/pilot/diagnostics.json"
    raw = json.loads(problem_path.read_text(encoding="utf-8"))
    results = json.loads(results_path.read_text(encoding="utf-8"))
    problem_hash = hashlib.sha256(problem_path.read_bytes()).hexdigest()
    if problem_hash != results["problem_sha256"]:
        raise ValueError("Pilot results and problem snapshot differ")
    problem = Problem.load(problem_path)
    selection = results["best_solutions"]["abc"]["selection"]
    distances = problem.nearest(selection)
    weights = problem.weights()
    order = np.argsort(distances)
    # Inverse weighted empirical CDF: first distance whose cumulative mass reaches 90%.
    cumulative = np.cumsum(weights[order])
    p90 = float(distances[order][np.searchsorted(cumulative, 0.9)])
    groups = {}
    for category in sorted({item["category"] for item in raw["demand"]}):
        mask = np.array([item["category"] == category for item in raw["demand"]])
        group_weights = weights[mask] / weights[mask].sum()
        groups[category] = {
            "mean_m": float(group_weights @ distances[mask]),
            "coverage_250": float(group_weights @ (distances[mask] <= 250)),
        }
    scenarios = {}
    for scenario in problem.scenarios:
        optimum = exact(problem, 4, scenario)
        value = problem.objective(selection, scenario)
        scenarios[scenario] = {
            "static_layout_m": value,
            "scenario_optimum_m": optimum.objective,
            "regret_m": value - optimum.objective,
            "regret_percent": (
                100 * (value - optimum.objective) / optimum.objective if optimum.objective else None
            ),
            "oracle_evaluations": optimum.evaluations,
        }
    station_counts = {}
    for count in (3, 4, 5):
        optimum = exact(problem, count)
        station_counts[str(count)] = {
            "mean_m": optimum.objective,
            "coverage_250": problem.metrics(optimum.selection)["coverage"],
            "candidate_ids": [problem.candidate_ids[i] for i in optimum.selection],
            "oracle_evaluations": optimum.evaluations,
        }
    diagnostics = {
        "problem_sha256": problem_hash,
        "source_results_sha256": hashlib.sha256(results_path.read_bytes()).hexdigest(),
        "reproduce": "uv run python scripts/inspect_pilot.py",
        "scope": "Exploratory analysis of the frozen pilot; demand and locations are assumptions.",
        "selection": results["best_solutions"]["abc"]["candidate_ids"],
        "aggregate": {
            "mean_m": problem.objective(selection),
            "weighted_p90_m": p90,
            "max_m": float(distances.max()),
        },
        "groups": groups,
        "scenarios": scenarios,
        "station_counts": station_counts,
    }
    output_path.write_text(
        json.dumps(diagnostics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(output_path)


if __name__ == "__main__":
    main()
