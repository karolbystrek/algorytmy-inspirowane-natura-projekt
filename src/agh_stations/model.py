"""Validated p-median input and scenario-normalized objectives (distances in metres)."""

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class Problem:
    candidate_ids: list[str]
    demand_ids: list[str]
    distances: np.ndarray
    scenarios: dict[str, np.ndarray]
    mixture: dict[str, float]

    def __post_init__(self):
        self.distances = np.asarray(self.distances, dtype=float)
        n, m = len(self.demand_ids), len(self.candidate_ids)
        if not n or not m or self.distances.shape != (n, m):
            raise ValueError("Distances must have shape demand_count × candidate_count, both > 0")
        if len(set(self.candidate_ids)) != m or len(set(self.demand_ids)) != n:
            raise ValueError("IDs must be unique within each set")
        if not np.isfinite(self.distances).all() or (self.distances < 0).any():
            raise ValueError("Distances must be finite and non-negative; audit disconnected points")
        if not self.scenarios or set(self.scenarios) != set(self.mixture):
            raise ValueError("Scenarios and mixture must have the same non-empty keys")
        for name, weights in self.scenarios.items():
            weights = np.asarray(weights, dtype=float)
            if (
                weights.shape != (n,)
                or not np.isfinite(weights).all()
                or (weights < 0).any()
                or weights.sum() <= 0
            ):
                raise ValueError(f"Invalid weights for scenario {name}")
            self.scenarios[name] = weights / weights.sum()
        mixture = np.asarray(list(self.mixture.values()), dtype=float)
        if not np.isfinite(mixture).all() or (mixture < 0).any() or mixture.sum() <= 0:
            raise ValueError("Mixture must contain non-negative finite weights with positive sum")
        self.mixture = {name: float(value / mixture.sum()) for name, value in self.mixture.items()}

    @classmethod
    def load(cls, path: str | Path):
        data = json.loads(Path(path).read_text())
        if data.get("schema_version") != 1:
            raise ValueError("Expected schema_version 1")
        return cls(
            [p["id"] for p in data["candidates"]],
            [p["id"] for p in data["demand"]],
            data["distances_m"],
            data["scenarios"],
            data["scenario_mixture"],
        )

    def weights(self, scenario="aggregate"):
        if scenario != "aggregate":
            return self.scenarios[scenario]
        return sum(self.mixture[name] * w for name, w in self.scenarios.items())

    def nearest(self, selection):
        selection = tuple(selection)
        if (
            not selection
            or len(set(selection)) != len(selection)
            or any(not isinstance(i, (int, np.integer)) for i in selection)
            or min(selection) < 0
            or max(selection) >= len(self.candidate_ids)
        ):
            raise ValueError("Select distinct valid candidate indices")
        return self.distances[:, selection].min(axis=1)

    def objective(self, selection, scenario="aggregate"):
        return float(self.weights(scenario) @ self.nearest(selection))

    def metrics(self, selection, scenario="aggregate", threshold=250):
        nearest = self.nearest(selection)
        return {
            "mean_distance_m": float(self.weights(scenario) @ nearest),
            "coverage": float(self.weights(scenario) @ (nearest <= threshold)),
            "max_distance_m": float(nearest.max()),
        }
