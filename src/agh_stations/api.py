"""Local presentation API and built React frontend; all computation stays offline."""

import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Literal

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from agh_stations.model import Problem, weighted_quantile
from agh_stations.routing import Router
from agh_stations.solvers import greedy_construction_cost, optimal, robust_optimal, solve
from agh_stations.study import closed_gate_effect, gap

ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "data/processed" / os.environ.get("AGH_DATASET", "agh-v2")
FRONTEND = ROOT / "frontend/dist"
ABC_FOODS = 8  # Chosen on the development instance, with abandonment limit foods * p.
CURVE_STATIONS = 40  # Past this point one more station shortens the walk by about a metre.
ScenarioName = Literal["aggregate", "morning", "day", "evening"]
PoolName = Literal["all", "existing"]
Threshold = Field(default=250, ge=50, le=1000, strict=True)


class Options(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RunRequest(Options):
    p: int = Field(default=4, ge=1, strict=True)
    budget: int = Field(default=1000, ge=500, le=20_000, strict=True)
    seed: int = Field(default=0, ge=0, le=2**32 - 1, strict=True)
    scenario: ScenarioName = "aggregate"
    include_exact: bool = True
    threshold_m: int = Threshold
    candidate_pool: PoolName = "all"


class RoutesRequest(Options):
    candidate_ids: list[str] = Field(min_length=1, max_length=2000)
    scenario: ScenarioName = "aggregate"


class AnalysisRequest(RoutesRequest):
    threshold_m: int = Threshold
    candidate_pool: PoolName = "all"


class CurveRequest(Options):
    scenario: ScenarioName = "aggregate"
    threshold_m: int = Threshold
    candidate_pool: PoolName = "all"
    p_max: int = Field(default=CURVE_STATIONS, ge=1, strict=True)


class SeriesRequest(Options):
    p: int = Field(default=4, ge=1, strict=True)
    budget: int = Field(default=1000, ge=500, le=20_000, strict=True)
    scenario: ScenarioName = "aggregate"
    candidate_pool: PoolName = "all"
    seeds: int = Field(default=10, ge=2, le=30, strict=True)


class RobustRequest(Options):
    p: int = Field(default=4, ge=1, strict=True)
    candidate_pool: PoolName = "all"


ASSUMED_HEIGHT_M = 9.0


@lru_cache(maxsize=1)
def dataset():
    manifest = json.loads((DATASET / "manifest.json").read_text(encoding="utf-8"))
    for name, expected in manifest["files_sha256"].items():
        if hashlib.sha256((DATASET / name).read_bytes()).hexdigest() != expected:
            raise RuntimeError(f"Snapshot checksum mismatch: {name}")
    raw = json.loads((DATASET / "problem.json").read_text(encoding="utf-8"))
    return raw, Problem.load(DATASET / "problem.json"), manifest


@lru_cache(maxsize=1)
def map_data():
    dataset()  # Verify the snapshot before serving its geometry.
    raw = json.loads((DATASET / "map.geojson").read_text(encoding="utf-8"))
    seen, features = set(), []
    for feature in raw["features"]:
        props = feature["properties"]
        if props["kind"] not in {"walk", "building"}:
            continue
        if props["kind"] == "walk":
            key = (*sorted((props["u"], props["v"])), props["length_m"])
            if key in seen:
                continue
            seen.add(key)
        properties = {"kind": props["kind"]}
        if props["kind"] == "building":
            properties["height_m"] = props.get("height_m", ASSUMED_HEIGHT_M)
            properties["height_source"] = props.get("height_source", "assumed")
        features.append(
            {"type": "Feature", "geometry": feature["geometry"], "properties": properties}
        )
    return {"type": "FeatureCollection", "features": features}


@lru_cache(maxsize=1)
def router():
    return Router(DATASET / "map.geojson", dataset()[0])


@lru_cache(maxsize=2)
def existing_parking():
    """Candidates where OSM already records bike or scooter parking."""
    raw = dataset()[0]
    return [
        j for j, c in enumerate(raw["candidates"]) if str(c.get("source", "")).startswith("osm_")
    ]


@lru_cache(maxsize=2)
def pool_problem(pool):
    problem = dataset()[1]
    if pool == "all":
        return problem
    if not existing_parking():
        raise HTTPException(422, "Ten zestaw danych nie ma listy istniejących parkingów.")
    return problem.restricted_to(existing_parking())


@lru_cache(maxsize=4096)
def proved_optimum(pool, p, scenario):
    return optimal(pool_problem(pool), p, scenario)


@lru_cache(maxsize=1)
def closed_matrix():
    raw = dataset()[0]
    if "distances_m_gates_closed" not in raw:
        return None
    rows = raw["distances_m_gates_closed"]
    return np.array([[np.nan if v is None else v for v in row] for row in rows], dtype=float)


def check_size(problem, p, budget=None):
    candidates = len(problem.candidate_ids)
    if p > candidates:
        raise HTTPException(422, f"Ten zestaw danych ma tylko {candidates} możliwych lokalizacji.")
    if budget is None:
        return
    needed = greedy_construction_cost(candidates, p)
    if p < candidates and budget < needed:
        raise HTTPException(
            422, f"Metoda greedy potrzebuje przy {p} stacjach co najmniej {needed} ocen."
        )


def group_summary(nearest, weights, threshold):
    share = weights / weights.sum()
    return {
        "mean_m": float(share @ nearest),
        "p90_m": weighted_quantile(nearest, weights),
        "max_m": float(nearest.max()),
        "coverage": float(share @ (nearest <= threshold)),
    }


app = FastAPI(title="AGH Station Lab", version="0.1.0")
app.add_middleware(GZipMiddleware, minimum_size=1000)
run_lock = Lock()


@app.get("/api/health")
def health():
    return {"status": "ok", "dataset": dataset()[2]["dataset_id"]}


@app.get("/api/dataset")
def get_dataset():
    raw, _, manifest = dataset()
    pools = {"all": len(raw["candidates"])}
    if existing_parking():
        pools["existing"] = len(existing_parking())
    return {
        "id": manifest["dataset_id"],
        "sha256": manifest["files_sha256"]["problem.json"],
        "pools": {
            name: {
                "count": count,
                # Index p - 1: the smallest budget in which greedy finishes its construction.
                "greedy_min_budget": [
                    greedy_construction_cost(count, p) if p < count else 1
                    for p in range(1, count + 1)
                ],
            }
            for name, count in pools.items()
        },
        "candidates": raw["candidates"],
        "demand": raw["demand"],
        "quality": manifest["quality"],
        "limitations": manifest["limitations"],
    }


@app.get("/api/map")
def get_map():
    return map_data()


@app.post("/api/routes")
def routes(request: RoutesRequest):
    """Walk from every demand point to its nearest selected station."""
    _, problem, _ = dataset()
    position = {identifier: j for j, identifier in enumerate(problem.candidate_ids)}
    unknown = sorted(set(request.candidate_ids) - set(position))
    if unknown:
        raise HTTPException(422, f"Nieznane lokalizacje: {', '.join(unknown)}")
    selected = sorted({position[identifier] for identifier in request.candidate_ids})
    weights = problem.weights(request.scenario)
    largest = float(weights.max())
    features = []
    for i, demand_id in enumerate(problem.demand_ids):
        nearest = selected[int(problem.distances[i, selected].argmin())]
        candidate_id = problem.candidate_ids[nearest]
        coordinates, length = router().route(i, candidate_id)
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": coordinates},
                "properties": {
                    "demand_id": demand_id,
                    "candidate_id": candidate_id,
                    "distance_m": length,
                    "scale": float(weights[i]) / largest if largest else 0.0,
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


@app.post("/api/analysis")
def analysis(request: AnalysisRequest):
    """Who is served how well by one layout, and how that layout fares at other times of day."""
    raw, _, _ = dataset()
    problem = pool_problem(request.candidate_pool)
    position = {identifier: j for j, identifier in enumerate(problem.candidate_ids)}
    unknown = sorted(set(request.candidate_ids) - set(position))
    if unknown:
        raise HTTPException(422, f"Nieznane lokalizacje: {', '.join(unknown)}")
    selected = sorted({position[identifier] for identifier in request.candidate_ids})
    weights = problem.weights(request.scenario)
    routes = problem.distances[:, selected]
    assignment, nearest = routes.argmin(axis=1), routes.min(axis=1)
    threshold = request.threshold_m
    categories = np.array([d.get("category", "unknown") for d in raw["demand"]])
    groups = [
        {
            "group": "all",
            "buildings": len(weights),
            "demand_share": 1.0,
            **group_summary(nearest, weights, threshold),
        }
    ]
    for category in sorted(set(categories)):
        mask = categories == category
        groups.append(
            {
                "group": str(category),
                "buildings": int(mask.sum()),
                "demand_share": float(weights[mask].sum()),
                **group_summary(nearest[mask], weights[mask], threshold),
            }
        )
    stations = []
    for k, j in enumerate(selected):
        mask = assignment == k
        served = float(weights[mask].sum())
        stations.append(
            {
                "id": problem.candidate_ids[j],
                "buildings": int(mask.sum()),
                "demand_share": served,
                "mean_m": float(weights[mask] @ nearest[mask] / served) if served else None,
                "max_m": float(nearest[mask].max()) if mask.any() else None,
            }
        )
    p = len(selected)
    scenarios = []
    for name in problem.scenarios:
        own = proved_optimum(request.candidate_pool, p, name)
        value = problem.objective(selected, name)
        scenarios.append(
            {
                "scenario": name,
                "mean_m": value,
                "optimum_m": own.objective,
                "regret_percent": gap(value, own.objective),
                "coverage": problem.metrics(selected, name, threshold)["coverage"],
                "common_stations": len(set(selected) & set(own.selection)),
            }
        )
    gates = None
    if closed_matrix() is not None:
        full = {identifier: j for j, identifier in enumerate(dataset()[1].candidate_ids)}
        indices = [full[problem.candidate_ids[j]] for j in selected]
        gates = closed_gate_effect(closed_matrix(), weights, nearest, indices)
    return {
        "groups": groups,
        "buildings": [
            {
                "id": raw["demand"][i]["id"],
                "name": raw["demand"][i].get("name"),
                "category": str(categories[i]),
                "distance_m": float(nearest[i]),
                "station": problem.candidate_ids[selected[int(assignment[i])]],
                "demand_share": float(weights[i]),
            }
            for i in range(len(weights))
        ],
        "stations": stations,
        "scenarios": scenarios,
        "gates": gates,
    }


@app.post("/api/curve")
def curve(request: CurveRequest):
    """Proved optima for every station count: what one more station is worth."""
    problem = pool_problem(request.candidate_pool)
    rows, previous = [], None
    for p in range(1, min(request.p_max, len(problem.candidate_ids)) + 1):
        result = proved_optimum(request.candidate_pool, p, request.scenario)
        metrics = problem.metrics(result.selection, request.scenario, request.threshold_m)
        rows.append(
            {
                "p": p,
                **metrics,
                "gain_m": None if previous is None else previous - metrics["mean_distance_m"],
            }
        )
        previous = metrics["mean_distance_m"]
    return {"rows": rows}


@app.post("/api/series")
def series(request: SeriesRequest):
    """Many seeds with the settings of one run: a single run says little about a heuristic."""
    problem = pool_problem(request.candidate_pool)
    check_size(problem, request.p, request.budget)
    if not run_lock.acquire(blocking=False):
        raise HTTPException(429, "Trwają już obliczenia. Spróbuj ponownie za chwilę.")
    try:
        optimum = proved_optimum(request.candidate_pool, request.p, request.scenario).objective
        methods = {}
        for method in ("abc", "random", "greedy"):
            seeds = range(request.seeds) if method != "greedy" else [0]
            values = [
                solve(
                    problem,
                    method,
                    request.p,
                    budget=request.budget,
                    seed=seed,
                    scenario=request.scenario,
                    foods=ABC_FOODS,
                    limit=ABC_FOODS * request.p,
                ).objective
                for seed in seeds
            ]
            methods[method] = {
                "values": values,
                "mean_m": float(np.mean(values)),
                "best_m": float(min(values)),
                "worst_m": float(max(values)),
                "mean_gap_percent": gap(float(np.mean(values)), optimum),
                "optimum_hits": sum(v <= optimum + 1e-6 for v in values),
            }
        return {"parameters": request.model_dump(), "optimum_m": optimum, "methods": methods}
    finally:
        run_lock.release()


@app.post("/api/robust")
def robust(request: RobustRequest):
    """One layout for the whole day that shares the loss evenly between times of day."""
    problem = pool_problem(request.candidate_pool)
    check_size(problem, request.p)
    if len(problem.scenarios) < 2:
        raise HTTPException(422, "Ten zestaw danych ma tylko jeden scenariusz popytu.")
    if not run_lock.acquire(blocking=False):
        raise HTTPException(429, "Trwają już obliczenia. Spróbuj ponownie za chwilę.")
    try:
        result = robust_optimal(problem, request.p, time_limit_s=20)
    finally:
        run_lock.release()
    aggregate = proved_optimum(request.candidate_pool, request.p, "aggregate").objective
    return {
        "candidate_ids": [problem.candidate_ids[j] for j in result["selection"]],
        "worst_regret_percent": result["worst_regret_percent"],
        "mean_m": problem.objective(result["selection"]),
        "cost_on_aggregate_percent": gap(problem.objective(result["selection"]), aggregate),
        "proved": result["proved"],
        "elapsed_s": result["elapsed_s"],
    }


@app.post("/api/run")
def run(request: RunRequest):
    _, _, manifest = dataset()
    problem = pool_problem(request.candidate_pool)
    check_size(problem, request.p, request.budget)
    if not run_lock.acquire(blocking=False):
        raise HTTPException(429, "Trwają już obliczenia. Spróbuj ponownie za chwilę.")
    try:
        methods = {}
        for method in ("abc", "random", "greedy"):
            steps = []

            def record(evaluation, objective, selection, steps=steps):
                steps.append(
                    {
                        "evaluation": evaluation,
                        "candidate_ids": [problem.candidate_ids[i] for i in selection],
                        **problem.metrics(selection, request.scenario, request.threshold_m),
                    }
                )

            result = solve(
                problem,
                method,
                request.p,
                budget=request.budget,
                seed=request.seed,
                scenario=request.scenario,
                foods=ABC_FOODS,
                limit=ABC_FOODS * request.p,
                on_improvement=record,
            )
            methods[method] = {
                "candidate_ids": [problem.candidate_ids[i] for i in result.selection],
                "evaluations": result.evaluations,
                "elapsed_s": result.elapsed_s,
                "steps": steps,
                **problem.metrics(result.selection, request.scenario, request.threshold_m),
            }
        reference = None
        if request.include_exact:
            result = proved_optimum(request.candidate_pool, request.p, request.scenario)
            reference = {
                "mean_distance_m": result.objective,
                "elapsed_s": result.elapsed_s,
            }
        return {
            "parameters": request.model_dump(),
            "abc": {"foods": ABC_FOODS, "limit": ABC_FOODS * request.p},
            "dataset_id": manifest["dataset_id"],
            "problem_sha256": manifest["files_sha256"]["problem.json"],
            "methods": methods,
            "exact": reference,
            "threshold_m": request.threshold_m,
            "demand_weights": problem.weights(request.scenario).tolist(),
        }
    finally:
        run_lock.release()


@app.get("/api/{path:path}", include_in_schema=False)
def unknown_api(path: str):
    raise HTTPException(404, "Nieznany endpoint API")


@app.get("/", include_in_schema=False)
def index():
    if not (FRONTEND / "index.html").exists():
        raise HTTPException(
            503, "Zbuduj interfejs: npm --prefix frontend ci && npm --prefix frontend run build"
        )
    return FileResponse(FRONTEND / "index.html")


if (FRONTEND / "assets").exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND / "assets"), name="assets")
