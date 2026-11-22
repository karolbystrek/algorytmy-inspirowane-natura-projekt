import type { LngLatBoundsLike } from "maplibre-gl";
import type { FeatureCollection } from "geojson";
import type { Dataset } from "./types";

export const NO_FEATURES: FeatureCollection = {
    type: "FeatureCollection",
    features: [],
};

export const OSM_ATTRIBUTION =
    '<a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">© OpenStreetMap contributors</a> · ODbL';

export function boundsOf(dataset: Dataset): LngLatBoundsLike {
    const points = [...dataset.candidates, ...dataset.demand];
    return [
        [
            Math.min(...points.map((p) => p.lon)),
            Math.min(...points.map((p) => p.lat)),
        ],
        [
            Math.max(...points.map((p) => p.lon)),
            Math.max(...points.map((p) => p.lat)),
        ],
    ];
}
