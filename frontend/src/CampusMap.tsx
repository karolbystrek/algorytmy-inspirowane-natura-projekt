import { memo, useEffect, useRef, useState, type ReactNode } from "react";
import maplibregl, {
    type ExpressionSpecification,
    type GeoJSONSource,
    type LngLatBoundsLike,
    type Map as MapLibre,
    type Marker,
} from "maplibre-gl";
import type { Feature, FeatureCollection } from "geojson";
import {
    Box,
    LocateFixed,
    Maximize,
    Minimize,
    Minus,
    Plus,
    Square,
} from "lucide-react";
import { request, stationLabel, type Dataset, type Focus } from "./types";

const EMPTY: string[] = [];
const NO_FEATURES: FeatureCollection = {
    type: "FeatureCollection",
    features: [],
};
const COMPACT_PINS_ABOVE = 12; // Numbered pins start to cover each other past this count.
const NOTHING: ExpressionSpecification = ["==", ["get", "demand_id"], ""];

function boundsOf(dataset: Dataset): LngLatBoundsLike {
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

function pointFeatures(
    dataset: Dataset,
    weights: number[] | undefined,
    baseline: string[],
): FeatureCollection {
    const largest = Math.max(...(weights ?? [1]), 1e-9);
    const features: Feature[] = [
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
                label: `${point.id} · kandydat do weryfikacji w terenie`,
            },
        })),
        ...dataset.demand.map((point, index) => ({
            type: "Feature" as const,
            geometry: {
                type: "Point" as const,
                coordinates: [point.lon, point.lat],
            },
            properties: {
                kind: "demand",
                id: point.id,
                // Area, not radius, should follow demand: hence the square root.
                scale: Math.sqrt((weights?.[index] ?? largest) / largest),
                label: `${!point.name || /^(way|relation)\//.test(point.name) ? "Punkt popytu" : point.name} · waga założona`,
            },
        })),
    ];
    return { type: "FeatureCollection", features };
}

function CampusMap({
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
    const [fullscreen, setFullscreen] = useState(false);
    const [status, setStatus] = useState("Wczytywanie geometrii kampusu…");
    const [retry, setRetry] = useState(0);
    const [failed, setFailed] = useState(false);
    const [ready, setReady] = useState(false);
    const [threeD, setThreeD] = useState(false);

    useEffect(() => {
        if (!element.current) return;
        const controller = new AbortController();
        let instance: MapLibre;
        try {
            instance = new maplibregl.Map({
                container: element.current,
                // No tiles and no glyphs: the map must work without internet.
                style: {
                    version: 8,
                    sources: {},
                    layers: [
                        {
                            id: "background",
                            type: "background",
                            paint: { "background-color": "#f3f5f0" },
                        },
                    ],
                },
                center: [19.9128, 50.0678],
                zoom: 14.5,
                minZoom: 13,
                maxZoom: 20,
                maxPitch: 65,
                attributionControl: false,
                dragRotate: true,
            });
        } catch {
            setStatus(
                "Ta przeglądarka nie obsługuje WebGL, więc mapy nie można wyświetlić.",
            );
            setFailed(true);
            return;
        }
        map.current = instance;
        instance.addControl(
            new maplibregl.AttributionControl({
                compact: false,
                customAttribution:
                    '<a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">© OpenStreetMap contributors</a> · ODbL',
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
                    instance.addSource("routes", {
                        type: "geojson",
                        data: NO_FEATURES,
                    });
                    instance.addSource("points", {
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
                            "fill-extrusion-height": 0,
                            "fill-extrusion-opacity": 0.92,
                        },
                    });
                    instance.addLayer({
                        id: "routes",
                        type: "line",
                        source: "routes",
                        layout: { "line-cap": "round", "line-join": "round" },
                        paint: {
                            "line-color": "#24735c",
                            "line-opacity": 0.8,
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
                        filter: NOTHING,
                        layout: { "line-cap": "round", "line-join": "round" },
                        paint: { "line-color": "#14352b", "line-width": 4.5 },
                    });
                    instance.addLayer({
                        id: "baseline",
                        type: "circle",
                        source: "points",
                        filter: ["==", ["get", "kind"], "baseline"],
                        paint: {
                            "circle-radius": 11,
                            "circle-color": "#ffffff",
                            "circle-opacity": 0.65,
                            "circle-stroke-color": "#4a7cc9",
                            "circle-stroke-width": 2.5,
                        },
                    });
                    instance.addLayer({
                        id: "candidates",
                        type: "circle",
                        source: "points",
                        filter: ["==", ["get", "kind"], "candidate"],
                        paint: {
                            "circle-radius": 3.5,
                            "circle-color": "#ffffff",
                            "circle-stroke-color": "#808f87",
                            "circle-stroke-width": 1.4,
                        },
                    });
                    instance.addLayer({
                        id: "demand",
                        type: "circle",
                        source: "points",
                        filter: ["==", ["get", "kind"], "demand"],
                        paint: {
                            "circle-radius": [
                                "+",
                                3.5,
                                ["*", 8, ["get", "scale"]],
                            ],
                            "circle-color": "#bd833b",
                            "circle-opacity": 0.85,
                            "circle-stroke-color": "#ffffff",
                            "circle-stroke-width": 1.5,
                        },
                    });
                    instance.on("click", (event) => {
                        const hit = instance.queryRenderedFeatures(event.point, {
                            layers: ["demand"],
                        })[0];
                        const id = hit?.properties?.id;
                        focusHandler.current(
                            id ? { kind: "building", id } : null,
                        );
                    });
                    for (const layer of ["baseline", "candidates", "demand"]) {
                        instance.on("mousemove", layer, (event) => {
                            const label =
                                event.features?.[0]?.properties?.label;
                            if (!label) return;
                            instance.getCanvas().style.cursor = "default";
                            // setText: names come from OSM, so never as HTML.
                            tooltip
                                .setLngLat(event.lngLat)
                                .setText(label)
                                .addTo(instance);
                        });
                        instance.on("mouseleave", layer, () =>
                            tooltip.remove(),
                        );
                    }
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
            instance.remove();
            map.current = null;
            setReady(false);
        };
    }, [retry]);

    useEffect(() => {
        if (!ready || !map.current || !dataset) return;
        map.current.fitBounds(boundsOf(dataset), {
            padding: 36,
            animate: false,
        });
    }, [dataset, ready]);

    useEffect(() => {
        if (!ready || !map.current || !dataset) return;
        (map.current.getSource("points") as GeoJSONSource).setData(
            pointFeatures(dataset, weights, baseline),
        );
    }, [dataset, weights, baseline, ready]);

    useEffect(() => {
        const instance = map.current;
        if (!ready || !instance || !dataset) return;
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
                return new maplibregl.Marker({ element: pin })
                    .setLngLat([point.lon, point.lat])
                    .addTo(instance);
            });
    }, [dataset, selected, ready]);

    useEffect(() => {
        for (const marker of markers.current) {
            const pin = marker.getElement();
            pin.classList.toggle(
                "focused",
                focus?.kind === "station" && pin.dataset.station === focus.id,
            );
        }
        const instance = map.current;
        if (!ready || !instance) return;
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
                : NOTHING,
        );
        if (!focus?.pan || !dataset) return;
        const point = (
            focus.kind === "station" ? dataset.candidates : dataset.demand
        ).find((item) => item.id === focus.id);
        if (point)
            instance.easeTo({
                center: [point.lon, point.lat],
                zoom: Math.max(instance.getZoom(), 16),
                duration: 500,
            });
    }, [focus, selected, dataset, ready]);

    useEffect(() => {
        if (!ready || !map.current) return;
        map.current.setPaintProperty("routes", "line-color", [
            "case",
            ["<=", ["get", "distance_m"], threshold],
            "#24735c",
            "#c2571f",
        ]);
    }, [threshold, ready]);

    useEffect(() => {
        const update = () =>
            setFullscreen(document.fullscreenElement === panel.current);
        document.addEventListener("fullscreenchange", update);
        return () => document.removeEventListener("fullscreenchange", update);
    }, []);

    const selectedKey = selected.join(",");
    useEffect(() => {
        const instance = map.current;
        if (!ready || !instance) return;
        const source = instance.getSource("routes") as GeoJSONSource;
        if (!selectedKey) {
            source.setData(NO_FEATURES);
            return;
        }
        const controller = new AbortController();
        // Replay changes layouts quickly; ask only once a layout has settled.
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
                .then((routes) => source.setData(routes))
                .catch(() => {
                    if (!controller.signal.aborted) source.setData(NO_FEATURES);
                });
        }, 120);
        return () => {
            window.clearTimeout(timer);
            controller.abort();
        };
    }, [selectedKey, scenario, ready]);

    useEffect(() => {
        const instance = map.current;
        if (!ready || !instance) return;
        instance.setPaintProperty(
            "buildings",
            "fill-extrusion-height",
            threeD ? ["get", "height_m"] : 0,
        );
        instance.easeTo({
            pitch: threeD ? 58 : 0,
            bearing: threeD ? -24 : 0,
            duration: 500,
        });
    }, [threeD, ready]);

    function resetView() {
        if (dataset)
            map.current?.fitBounds(boundsOf(dataset), {
                padding: 36,
                pitch: threeD ? 58 : 0,
                bearing: threeD ? -24 : 0,
            });
    }

    return (
        <section
            ref={panel}
            className="map-panel"
            aria-label="Interaktywna mapa kampusu AGH"
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
                    onClick={() => setThreeD((v) => !v)}
                    aria-pressed={threeD}
                    aria-label={threeD ? "Widok płaski" : "Budynki 3D"}
                    title={threeD ? "Widok płaski" : "Budynki 3D"}
                >
                    {threeD ? <Square size={17} /> : <Box size={18} />}
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
            <div className="map-legend" aria-label="Legenda mapy">
                <span>
                    <i className="legend-station" /> Stacje
                </span>
                <span>
                    <i className="legend-route" /> Dojście do {threshold} m
                </span>
                <span>
                    <i className="legend-route far" /> Dłuższe
                </span>
                {baseline.length ? (
                    <span>
                        <i className="legend-baseline" /> Układ do porównania
                    </span>
                ) : null}
                <span>
                    <i className="legend-demand" /> Popyt (większy = więcej)
                </span>
                <span>
                    <i className="legend-candidate" /> Kandydaci
                </span>
                {threeD ? (
                    <span>
                        <i className="legend-assumed" /> Wysokość przybliżona
                    </span>
                ) : null}
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

export default memo(CampusMap);
