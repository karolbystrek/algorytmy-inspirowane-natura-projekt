import { memo, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import maplibregl, {
    type ExpressionSpecification,
    type GeoJSONSource,
    type Map as MapLibre,
    type Marker,
} from "maplibre-gl";
import type { Feature, FeatureCollection, Polygon } from "geojson";
import {
    LocateFixed,
    Maximize,
    Minimize,
    Minus,
    Plus,
    RotateCcw,
    RotateCw,
} from "lucide-react";
import {
    buildingName,
    number,
    request,
    stationLabel,
    type Dataset,
    type Focus,
} from "./types";
import { boundsOf, NO_FEATURES, OSM_ATTRIBUTION } from "./mapShared";

const EMPTY: string[] = [];
const COMPACT_PINS_ABOVE = 12;
const PITCH = 55;
const BEARING = -24;
const STATION_RADIUS_M = 6;
const STATION_HEIGHT_M = 60;
const COLUMN_RADIUS_M = 4;
const COLUMN_MIN_M = 4;
const COLUMN_MAX_M = 40;
const NEAR = "#7dbb9b";
const FAR = "#e3a274";
const WAITING = "#e2cfae";

type RouteProps = {
    demand_id: string;
    candidate_id: string;
    distance_m: number;
    scale: number;
};

/** Regular polygon approximating a circle of `radius` metres around a point. */
function disc(lon: number, lat: number, radius: number, sides = 20): Polygon {
    const dx = radius / (111_320 * Math.cos((lat * Math.PI) / 180));
    const dy = radius / 110_540;
    const ring = Array.from({ length: sides + 1 }, (_, i) => {
        const angle = (2 * Math.PI * (i % sides)) / sides;
        return [lon + dx * Math.cos(angle), lat + dy * Math.sin(angle)];
    });
    return { type: "Polygon", coordinates: [ring] };
}

/** Fit the campus as seen from above, then tilt: keeps the view close. */
function campusCamera(instance: MapLibre, dataset: Dataset) {
    const camera = instance.cameraForBounds(boundsOf(dataset), {
        padding: 36,
    });
    return camera ? { ...camera, pitch: PITCH, bearing: BEARING } : null;
}

function collection(features: Feature[]): FeatureCollection {
    return { type: "FeatureCollection", features };
}

function groundPoints(dataset: Dataset, baseline: string[]): FeatureCollection {
    return collection([
        ...dataset.candidates
            .filter((point) => baseline.includes(point.id))
            .map((point) => ({
                type: "Feature" as const,
                geometry: {
                    type: "Point" as const,
                    coordinates: [point.lon, point.lat],
                },
                properties: {
                    kind: "baseline",
                    label: `${point.id} · układ zapamiętany do porównania`,
                },
            })),
        ...dataset.candidates.map((point) => ({
            type: "Feature" as const,
            geometry: {
                type: "Point" as const,
                coordinates: [point.lon, point.lat],
            },
            properties: {
                kind: "candidate",
                label: `${point.id} · możliwa lokalizacja stacji`,
            },
        })),
    ]);
}

function demandColumns(
    dataset: Dataset,
    weights: number[] | undefined,
): FeatureCollection {
    const largest = Math.max(...(weights ?? [1]), 1e-9);
    return collection(
        dataset.demand.map((point, index) => {
            const share = (weights?.[index] ?? largest) / largest;
            return {
                type: "Feature" as const,
                geometry: disc(point.lon, point.lat, COLUMN_RADIUS_M, 12),
                properties: {
                    id: point.id,
                    height: COLUMN_MIN_M + (COLUMN_MAX_M - COLUMN_MIN_M) * share,
                    label: `${buildingName(point.name)} · waga założona ${number(share * 100, 0)}% największej`,
                },
            };
        }),
    );
}

function stationPillars(dataset: Dataset, selected: string[]): FeatureCollection {
    return collection(
        dataset.candidates
            .filter((point) => selected.includes(point.id))
            .map((point) => ({
                type: "Feature" as const,
                geometry: disc(point.lon, point.lat, STATION_RADIUS_M),
                properties: {
                    id: point.id,
                    label: `Stacja ${stationLabel(point.id)} · wybrana stacja`,
                },
            })),
    );
}

function demandBuildings(
    campus: FeatureCollection | null,
    dataset: Dataset,
    routes: FeatureCollection,
): FeatureCollection {
    if (!campus) return NO_FEATURES;
    const names = new Map(dataset.demand.map((d) => [d.id, d.name]));
    const access = new Map(
        routes.features.map((f) => {
            const props = f.properties as RouteProps;
            return [props.demand_id, props];
        }),
    );
    return collection(
        campus.features
            .filter(
                (f) =>
                    f.properties?.kind === "building" &&
                    names.has(f.properties.id),
            )
            .map((f) => {
                const id = f.properties!.id as string;
                const route = access.get(id);
                const name = buildingName(names.get(id));
                return {
                    type: "Feature" as const,
                    geometry: f.geometry,
                    properties: {
                        id,
                        height_m: f.properties!.height_m,
                        ...(route ? { distance_m: route.distance_m } : {}),
                        label: route
                            ? `${name} · ${number(route.distance_m, 0)} m do stacji ${stationLabel(route.candidate_id)}`
                            : name,
                    },
                };
            }),
    );
}

function CampusMap3D({
    dataset,
    selected = EMPTY,
    weights,
    scenario,
    baseline = EMPTY,
    threshold,
    focus,
    onFocus,
    children,
}: {
    dataset: Dataset | null;
    selected?: string[];
    weights?: number[];
    scenario: string;
    baseline?: string[];
    threshold: number;
    focus: Focus | null;
    onFocus: (focus: Focus | null) => void;
    children?: ReactNode;
}) {
    const panel = useRef<HTMLElement>(null);
    const element = useRef<HTMLDivElement>(null);
    const map = useRef<MapLibre | null>(null);
    const markers = useRef<Marker[]>([]);
    const focusHandler = useRef(onFocus);
    focusHandler.current = onFocus;
    const [campus, setCampus] = useState<FeatureCollection | null>(null);
    const [routes, setRoutes] = useState<FeatureCollection>(NO_FEATURES);
    const [fullscreen, setFullscreen] = useState(false);
    const [status, setStatus] = useState("Wczytywanie geometrii kampusu…");
    const [retry, setRetry] = useState(0);
    const [failed, setFailed] = useState(false);
    const [ready, setReady] = useState(false);

    useEffect(() => {
        if (!element.current) return;
        const controller = new AbortController();
        let instance: MapLibre;
        try {
            instance = new maplibregl.Map({
                container: element.current,
                style: {
                    version: 8,
                    sources: {},
                    light: {
                        anchor: "viewport",
                        color: "#ffffff",
                        intensity: 0.3,
                        position: [1.3, 210, 40],
                    },
                    sky: {
                        "sky-color": "#dbe7e1",
                        "horizon-color": "#f3f5f0",
                        "sky-horizon-blend": 0.7,
                        "fog-color": "#f3f5f0",
                        "fog-ground-blend": 0.6,
                        "horizon-fog-blend": 0.8,
                        "atmosphere-blend": 0,
                    },
                    layers: [
                        {
                            id: "background",
                            type: "background",
                            paint: { "background-color": "#f3f5f0" },
                        },
                    ],
                },
                center: [19.9128, 50.0678],
                zoom: 15,
                pitch: PITCH,
                bearing: BEARING,
                minZoom: 13,
                maxZoom: 20,
                maxPitch: 75,
                attributionControl: false,
            });
        } catch {
            setStatus(
                "Ta przeglądarka nie obsługuje WebGL, więc mapy 3D nie można wyświetlić.",
            );
            setFailed(true);
            return;
        }
        map.current = instance;
        instance.addControl(
            new maplibregl.AttributionControl({
                compact: false,
                customAttribution: OSM_ATTRIBUTION,
            }),
        );
        instance.addControl(
            new maplibregl.ScaleControl({ maxWidth: 100, unit: "metric" }),
            "bottom-left",
        );
        const resize = new ResizeObserver(() => instance.resize());
        resize.observe(element.current);
        const tooltip = new maplibregl.Popup({
            closeButton: false,
            closeOnClick: false,
            offset: 10,
        });
        instance.on("load", () => {
            request<FeatureCollection>("map", { signal: controller.signal })
                .then((data) => {
                    instance.addSource("campus", { type: "geojson", data });
                    for (const id of [
                        "routes",
                        "ground",
                        "demand-buildings",
                        "columns",
                        "stations",
                    ])
                        instance.addSource(id, {
                            type: "geojson",
                            data: NO_FEATURES,
                        });
                    instance.addLayer({
                        id: "walk",
                        type: "line",
                        source: "campus",
                        filter: ["==", ["get", "kind"], "walk"],
                        paint: {
                            "line-color": "#c2cac4",
                            "line-width": 1,
                            "line-opacity": 0.8,
                        },
                    });
                    instance.addLayer({
                        id: "routes",
                        type: "line",
                        source: "routes",
                        layout: { "line-cap": "round", "line-join": "round" },
                        paint: {
                            "line-color": "#24735c",
                            "line-opacity": 0.85,
                            "line-width": [
                                "+",
                                1.2,
                                ["*", 3, ["get", "scale"]],
                            ],
                        },
                    });
                    instance.addLayer({
                        id: "routes-focus",
                        type: "line",
                        source: "routes",
                        filter: ["==", ["get", "demand_id"], ""],
                        layout: { "line-cap": "round", "line-join": "round" },
                        paint: { "line-color": "#14352b", "line-width": 4.5 },
                    });
                    instance.addLayer({
                        id: "baseline",
                        type: "circle",
                        source: "ground",
                        filter: ["==", ["get", "kind"], "baseline"],
                        paint: {
                            "circle-radius": 11,
                            "circle-color": "#ffffff",
                            "circle-opacity": 0.65,
                            "circle-stroke-color": "#4a7cc9",
                            "circle-stroke-width": 2.5,
                            "circle-pitch-alignment": "map",
                        },
                    });
                    instance.addLayer({
                        id: "candidates",
                        type: "circle",
                        source: "ground",
                        filter: ["==", ["get", "kind"], "candidate"],
                        paint: {
                            "circle-radius": 3.5,
                            "circle-color": "#ffffff",
                            "circle-stroke-color": "#808f87",
                            "circle-stroke-width": 1.4,
                            "circle-pitch-alignment": "map",
                        },
                    });
                    instance.addLayer({
                        id: "buildings",
                        type: "fill-extrusion",
                        source: "campus",
                        filter: ["==", ["get", "kind"], "building"],
                        paint: {
                            "fill-extrusion-color": [
                                "match",
                                ["get", "height_source"],
                                "assumed",
                                "#eceee9",
                                "#d3dad5",
                            ],
                            "fill-extrusion-height": ["get", "height_m"],
                            "fill-extrusion-opacity": 0.9,
                        },
                    });
                    instance.addLayer({
                        id: "demand-buildings",
                        type: "fill-extrusion",
                        source: "demand-buildings",
                        paint: {
                            "fill-extrusion-color": WAITING,
                            "fill-extrusion-height": ["get", "height_m"],
                            "fill-extrusion-opacity": 0.95,
                        },
                    });
                    instance.addLayer({
                        id: "columns",
                        type: "fill-extrusion",
                        source: "columns",
                        paint: {
                            "fill-extrusion-color": "#bd833b",
                            "fill-extrusion-height": ["get", "height"],
                            "fill-extrusion-opacity": 0.95,
                        },
                    });
                    instance.addLayer({
                        id: "stations",
                        type: "fill-extrusion",
                        source: "stations",
                        paint: {
                            "fill-extrusion-color": "#21654f",
                            "fill-extrusion-height": STATION_HEIGHT_M,
                            "fill-extrusion-opacity": 0.95,
                        },
                    });
                    instance.on("click", (event) => {
                        const hit = instance.queryRenderedFeatures(event.point, {
                            layers: ["stations", "columns", "demand-buildings"],
                        })[0];
                        const id = hit?.properties?.id;
                        focusHandler.current(
                            id
                                ? {
                                      kind:
                                          hit.layer.id === "stations"
                                              ? "station"
                                              : "building",
                                      id,
                                  }
                                : null,
                        );
                    });
                    for (const layer of [
                        "baseline",
                        "candidates",
                        "demand-buildings",
                        "columns",
                        "stations",
                    ]) {
                        instance.on("mousemove", layer, (event) => {
                            const label =
                                event.features?.[0]?.properties?.label;
                            if (!label) return;
                            instance.getCanvas().style.cursor =
                                layer === "candidates" || layer === "baseline"
                                    ? "default"
                                    : "pointer";
                            tooltip
                                .setLngLat(event.lngLat)
                                .setText(label)
                                .addTo(instance);
                        });
                        instance.on("mouseleave", layer, () => {
                            instance.getCanvas().style.cursor = "";
                            tooltip.remove();
                        });
                    }
                    setCampus(data);
                    setStatus("");
                    setReady(true);
                })
                .catch((error) => {
                    if (!controller.signal.aborted) {
                        setStatus(error.message);
                        setFailed(true);
                    }
                });
        });
        return () => {
            controller.abort();
            resize.disconnect();
            tooltip.remove();
            for (const marker of markers.current) marker.remove();
            markers.current = [];
            instance.remove();
            map.current = null;
            setReady(false);
        };
    }, [retry]);

    useEffect(() => {
        if (!ready || !map.current || !dataset) return;
        const camera = campusCamera(map.current, dataset);
        if (camera) map.current.jumpTo(camera);
    }, [dataset, ready]);

    useEffect(() => {
        const instance = map.current;
        if (!ready || !instance || !dataset) return;
        instance.setFilter("buildings", [
            "all",
            ["==", ["get", "kind"], "building"],
            [
                "!",
                ["in", ["get", "id"], ["literal", dataset.demand.map((d) => d.id)]],
            ],
        ]);
        (instance.getSource("ground") as GeoJSONSource).setData(
            groundPoints(dataset, baseline),
        );
    }, [dataset, baseline, ready]);

    useEffect(() => {
        if (!ready || !map.current || !dataset) return;
        (map.current.getSource("columns") as GeoJSONSource).setData(
            demandColumns(dataset, weights),
        );
    }, [dataset, weights, ready]);

    const accessBuildings = useMemo(
        () => (dataset ? demandBuildings(campus, dataset, routes) : NO_FEATURES),
        [campus, dataset, routes],
    );
    useEffect(() => {
        if (!ready || !map.current) return;
        (map.current.getSource("demand-buildings") as GeoJSONSource).setData(
            accessBuildings,
        );
    }, [accessBuildings, ready]);

    useEffect(() => {
        const instance = map.current;
        if (!ready || !instance || !dataset) return;
        (instance.getSource("stations") as GeoJSONSource).setData(
            stationPillars(dataset, selected),
        );
        for (const marker of markers.current) marker.remove();
        const compact = selected.length > COMPACT_PINS_ABOVE;
        markers.current = dataset.candidates
            .filter((point) => selected.includes(point.id))
            .map((point) => {
                const pin = document.createElement("div");
                pin.className = compact
                    ? "station-pin compact"
                    : "station-pin";
                pin.dataset.station = point.id;
                pin.textContent = compact ? "" : stationLabel(point.id);
                pin.title = `${point.id} · wybrana stacja`;
                pin.addEventListener("click", (event) => {
                    event.stopPropagation();
                    focusHandler.current({ kind: "station", id: point.id });
                });
                return new maplibregl.Marker({
                    element: pin,
                    pitchAlignment: "viewport",
                })
                    .setLngLat([point.lon, point.lat])
                    .addTo(instance);
            });
    }, [dataset, selected, ready]);

    useEffect(() => {
        const instance = map.current;
        if (!ready || !instance) return;
        const building = focus?.kind === "building" ? focus.id : "";
        const station = focus?.kind === "station" ? focus.id : "";
        instance.setPaintProperty("demand-buildings", "fill-extrusion-color", [
            "case",
            ["==", ["get", "id"], building],
            "#2f5f4f",
            ["!", ["has", "distance_m"]],
            WAITING,
            ["<=", ["get", "distance_m"], threshold],
            NEAR,
            FAR,
        ] as ExpressionSpecification);
        instance.setPaintProperty("columns", "fill-extrusion-color", [
            "case",
            ["==", ["get", "id"], building],
            "#7a4f1c",
            "#bd833b",
        ] as ExpressionSpecification);
        instance.setPaintProperty("stations", "fill-extrusion-color", [
            "case",
            ["==", ["get", "id"], station],
            "#14352b",
            "#21654f",
        ] as ExpressionSpecification);
        instance.setPaintProperty("routes", "line-color", [
            "case",
            ["<=", ["get", "distance_m"], threshold],
            "#24735c",
            "#c2571f",
        ]);
        instance.setFilter(
            "routes-focus",
            focus
                ? [
                      "==",
                      [
                          "get",
                          focus.kind === "station"
                              ? "candidate_id"
                              : "demand_id",
                      ],
                      focus.id,
                  ]
                : ["==", ["get", "demand_id"], ""],
        );
    }, [focus, threshold, ready]);

    useEffect(() => {
        for (const marker of markers.current) {
            const pin = marker.getElement();
            pin.classList.toggle(
                "focused",
                focus?.kind === "station" && pin.dataset.station === focus.id,
            );
        }
        const instance = map.current;
        if (!ready || !instance || !focus?.pan || !dataset) return;
        const point = (
            focus.kind === "station" ? dataset.candidates : dataset.demand
        ).find((item) => item.id === focus.id);
        if (point)
            instance.easeTo({
                center: [point.lon, point.lat],
                zoom: Math.max(instance.getZoom(), 16.5),
                duration: 600,
            });
    }, [focus, selected, dataset, ready]);

    const selectedKey = selected.join(",");
    useEffect(() => {
        if (!ready) return;
        if (!selectedKey) {
            setRoutes(NO_FEATURES);
            return;
        }
        const controller = new AbortController();
        const timer = window.setTimeout(() => {
            request<FeatureCollection>("routes", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    candidate_ids: selectedKey.split(","),
                    scenario,
                }),
                signal: controller.signal,
            })
                .then(setRoutes)
                .catch(() => {
                    if (!controller.signal.aborted) setRoutes(NO_FEATURES);
                });
        }, 120);
        return () => {
            window.clearTimeout(timer);
            controller.abort();
        };
    }, [selectedKey, scenario, ready]);

    useEffect(() => {
        if (!ready || !map.current) return;
        (map.current.getSource("routes") as GeoJSONSource).setData(routes);
    }, [routes, ready]);

    useEffect(() => {
        const update = () =>
            setFullscreen(document.fullscreenElement === panel.current);
        document.addEventListener("fullscreenchange", update);
        return () => document.removeEventListener("fullscreenchange", update);
    }, []);

    function rotate(delta: number) {
        const instance = map.current;
        if (instance)
            instance.easeTo({
                bearing: instance.getBearing() + delta,
                duration: 400,
            });
    }

    function resetView() {
        const instance = map.current;
        if (!instance || !dataset) return;
        const camera = campusCamera(instance, dataset);
        if (camera) instance.easeTo({ ...camera, duration: 600 });
    }

    return (
        <section
            ref={panel}
            className="map-panel"
            aria-label="Trójwymiarowa mapa kampusu AGH"
        >
            <div ref={element} className="campus-map" />
            {children}
            <div className="map-controls">
                <button
                    onClick={() =>
                        fullscreen
                            ? document.exitFullscreen()
                            : panel.current?.requestFullscreen()
                    }
                    aria-pressed={fullscreen}
                    aria-label={fullscreen ? "Zamknij pełny ekran" : "Pełny ekran"}
                    title={fullscreen ? "Zamknij pełny ekran" : "Pełny ekran"}
                >
                    {fullscreen ? <Minimize size={17} /> : <Maximize size={17} />}
                </button>
                <button
                    onClick={() => rotate(-45)}
                    aria-label="Obróć w lewo"
                    title="Obróć w lewo (lub przeciągnij prawym przyciskiem)"
                >
                    <RotateCcw size={16} />
                </button>
                <button
                    onClick={() => rotate(45)}
                    aria-label="Obróć w prawo"
                    title="Obróć w prawo (lub przeciągnij prawym przyciskiem)"
                >
                    <RotateCw size={16} />
                </button>
                <button
                    onClick={() => map.current?.zoomIn()}
                    aria-label="Przybliż mapę"
                >
                    <Plus size={18} />
                </button>
                <button
                    onClick={() => map.current?.zoomOut()}
                    aria-label="Oddal mapę"
                >
                    <Minus size={18} />
                </button>
                <button onClick={resetView} aria-label="Pokaż cały kampus">
                    <LocateFixed size={18} />
                </button>
            </div>
            <div className="map-legend" aria-label="Legenda mapy 3D">
                <span>
                    <i className="legend-station" /> Stacje (słupy)
                </span>
                <span>
                    <i className="legend-block near" /> Budynek: dojście do{" "}
                    {threshold} m
                </span>
                <span>
                    <i className="legend-block far" /> Dłuższe
                </span>
                <span>
                    <i className="legend-column" /> Popyt (wyższy = więcej)
                </span>
                {baseline.length ? (
                    <span>
                        <i className="legend-baseline" /> Układ do porównania
                    </span>
                ) : null}
                <span>
                    <i className="legend-candidate" /> Kandydaci
                </span>
                <span>
                    <i className="legend-assumed" /> Wysokość przybliżona
                </span>
            </div>
            {status ? (
                <div
                    className={`map-status ${failed ? "failed" : ""}`}
                    role="status"
                >
                    {status}
                    {failed ? (
                        <button
                            onClick={() => {
                                setFailed(false);
                                setStatus("Wczytywanie geometrii kampusu…");
                                setRetry((v) => v + 1);
                            }}
                        >
                            Spróbuj ponownie
                        </button>
                    ) : null}
                </div>
            ) : null}
        </section>
    );
}

export default memo(CampusMap3D);
