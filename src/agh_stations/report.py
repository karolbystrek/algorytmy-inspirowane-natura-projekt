"""Standalone scientific plots based only on local, frozen experiment artifacts."""

import csv
import hashlib
import json
from pathlib import Path

import numpy as np


def render(results_dir, dataset_dir):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection

    results_dir, dataset_dir = Path(results_dir), Path(dataset_dir)
    results = json.loads((results_dir / "results.json").read_text())
    problem_path = dataset_dir / "problem.json"
    if hashlib.sha256(problem_path.read_bytes()).hexdigest() != results["problem_sha256"]:
        raise ValueError("Results refer to a different problem snapshot")
    manifest = json.loads((dataset_dir / "manifest.json").read_text())
    expected_map = manifest["files_sha256"]["map.geojson"]
    if hashlib.sha256((dataset_dir / "map.geojson").read_bytes()).hexdigest() != expected_map:
        raise ValueError("Map does not match the dataset manifest")
    problem = json.loads(problem_path.read_text())
    features = json.loads((dataset_dir / "map.geojson").read_text())["features"]
    selected_ids = set(results["best_solutions"]["abc"]["candidate_ids"])
    fig, ax = plt.subplots(figsize=(11, 8))
    walk_segments = []
    for feature in features:
        geometry = feature["geometry"]
        kind = feature["properties"]["kind"]
        if kind == "walk":
            walk_segments.append(geometry["coordinates"])
        elif kind == "building":
            polygons = (
                [geometry["coordinates"]]
                if geometry["type"] == "Polygon"
                else geometry["coordinates"]
            )
            for polygon in polygons:
                xy = np.asarray(polygon[0])
                ax.fill(xy[:, 0], xy[:, 1], color="#e0e5ed", ec="#bdc5cf", lw=0.35)
    ax.add_collection(LineCollection(walk_segments, colors="#a7afb8", linewidths=0.45, zorder=1))
    for key, color, marker, size, label in (
        ("candidates", "#6b7280", ".", 35, "Kandydaci (wymagają weryfikacji)"),
        ("demand", "#e78a27", "^", 65, "Popyt: punkty zastępcze, wagi założone"),
    ):
        points = problem[key]
        ax.scatter(
            [p["lon"] for p in points],
            [p["lat"] for p in points],
            c=color,
            marker=marker,
            s=size,
            label=label,
            zorder=3,
        )
    points = [p for p in problem["candidates"] if p["id"] in selected_ids]
    ax.scatter(
        [p["lon"] for p in points],
        [p["lat"] for p in points],
        c="#1654b8",
        marker="o",
        s=120,
        label=f"Stacje ABC (najlepszy z {results['parameters']['runs']} przebiegów)",
        zorder=4,
    )
    for point in points:
        ax.annotate(
            point["id"].removeprefix("candidate-"),
            (point["lon"], point["lat"]),
            xytext=(6, 6),
            textcoords="offset points",
            color="#1654b8",
        )
    ax.set_aspect(1 / np.cos(np.radians(np.mean([p["lat"] for p in points]))))
    ax.set_title("AGH: pilotaż p-median / rzeczywisty graf OSM / model demonstracyjny")
    ax.set_xlabel("Długość geograficzna [°]")
    ax.set_ylabel("Szerokość geograficzna [°]")
    ax.legend(loc="upper right", fontsize=8)
    fig.text(
        0.5,
        0.01,
        "© OpenStreetMap contributors | ODbL | openstreetmap.org/copyright",
        ha="center",
        fontsize=8,
    )
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(results_dir / "map.png", dpi=160)
    fig.savefig(results_dir / "map.svg")
    plt.close(fig)

    with (results_dir / "history.csv").open() as handle:
        histories = list(csv.DictReader(handle))
    fig, ax = plt.subplots(figsize=(9, 5))
    colors = {"abc": "#1654b8", "random": "#e78a27", "greedy": "#37864f"}
    budget = results["parameters"]["budget"]
    grid = np.arange(1, budget + 1)
    for method, color in colors.items():
        curves = []
        seeds = sorted({r["seed"] for r in histories if r["method"] == method})
        for seed in seeds:
            rows = [r for r in histories if r["method"] == method and r["seed"] == seed]
            evaluations = np.array([int(r["evaluation"]) for r in rows])
            values = np.array([float(r["best_m"]) for r in rows])
            indices = np.searchsorted(evaluations, grid, side="right") - 1
            curve = values[np.maximum(indices, 0)].copy()
            curve[indices < 0] = np.nan  # No feasible incumbent yet during greedy construction.
            curves.append(curve)
        curves = np.asarray(curves)
        valid = np.isfinite(curves).all(axis=0)
        median = np.median(curves[:, valid], axis=0)
        ax.plot(grid[valid], median, label=method, color=color)
        if len(curves) > 1:
            q25, q75 = np.quantile(curves[:, valid], [0.25, 0.75], axis=0)
            ax.fill_between(grid[valid], q25, q75, color=color, alpha=0.15)
    if "exact" in results["summary"]:
        ax.axhline(
            results["summary"]["exact"]["best_m"],
            color="#222",
            ls="--",
            label="optimum: pełny przegląd (osobny budżet)",
        )
    ax.set(
        xlabel="Liczba ocen funkcji celu",
        ylabel="Najlepsze średnie dojście [m]",
        title="Mediana i kwartyle; greedy zatrzymuje się po braku poprawy",
    )
    ax.legend()
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(results_dir / "convergence.png", dpi=160)
    fig.savefig(results_dir / "convergence.svg")
    plt.close(fig)
