"""Local presentation API and built React frontend; all computation stays offline."""

import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from agh_stations.model import Problem
from agh_stations.routing import Router
from agh_stations.solvers import greedy_construction_cost, optimal, solve

ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "data/processed" / os.environ.get("AGH_DATASET", "agh-v2")
FRONTEND = ROOT / "frontend/dist"
ABC_FOODS = 8  # Chosen on the development instance, with abandonment limit foods * p.
ScenarioName = Literal["aggregate", "morning", "day", "evening"]


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    p: int = Field(default=4, ge=1, le=12, strict=True)
    budget: int = Field(default=1000, ge=500, le=20_000, strict=True)
    seed: int = Field(default=0, ge=0, le=2**32 - 1, strict=True)
    scenario: ScenarioName = "aggregate"
    include_exact: bool = True


class RoutesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_ids: list[str] = Field(min_length=1, max_length=50)
    scenario: ScenarioName = "aggregate"


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


app = FastAPI(title="AGH Station Lab", version="0.1.0")
app.add_middleware(GZipMiddleware, minimum_size=1000)
run_lock = Lock()


@app.get("/api/health")
def health():
    return {"status": "ok", "dataset": dataset()[2]["dataset_id"]}


@app.get("/api/dataset")
def get_dataset():
    raw, _, manifest = dataset()
    return {
        "id": manifest["dataset_id"],
        "sha256": manifest["files_sha256"]["problem.json"],
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


@app.post("/api/run")
def run(request: RunRequest):
    _, problem, manifest = dataset()
    needed = greedy_construction_cost(len(problem.candidate_ids), request.p)
    if request.budget < needed:
        raise HTTPException(
            422, f"Metoda greedy potrzebuje przy {request.p} stacjach co najmniej {needed} ocen."
        )
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
                        **problem.metrics(selection, request.scenario),
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
                **problem.metrics(result.selection, request.scenario),
            }
        reference = None
        if request.include_exact:
            result = optimal(problem, request.p, request.scenario)
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
            "threshold_m": 250,
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
