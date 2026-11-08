import { memo, useEffect, useRef, useState } from "react";
import L from "leaflet";
import type { FeatureCollection } from "geojson";
import { LocateFixed, Minus, Plus } from "lucide-react";
import { request, type Dataset } from "./types";

const EMPTY: string[] = [];

function CampusMap({
    dataset,
    selected = EMPTY,
}: {
    dataset: Dataset | null;
    selected?: string[];
}) {
    const element = useRef<HTMLDivElement>(null);
    const map = useRef<L.Map | null>(null);
    const stations = useRef<L.LayerGroup | null>(null);
    const [status, setStatus] = useState("Wczytywanie geometrii kampusu…");
    const [retry, setRetry] = useState(0);
    const [failed, setFailed] = useState(false);

    useEffect(() => {
        if (!element.current) return;
        const controller = new AbortController();
        const instance = L.map(element.current, {
            center: [50.0678, 19.9128],
            zoom: 16,
            zoomSnap: 0.25,
            minZoom: 14,
            maxZoom: 20,
            zoomControl: false,
            preferCanvas: true,
            attributionControl: false,
        });
        instance.createPane("base").style.zIndex = "250";
        map.current = instance;
        stations.current = L.layerGroup().addTo(instance);
        L.control
            .attribution({ prefix: false })
            .addAttribution(
                '<a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">© OpenStreetMap contributors</a> · ODbL',
            )
            .addTo(instance);
        L.control
            .scale({ imperial: false, position: "bottomleft", maxWidth: 100 })
            .addTo(instance);
        const resize = new ResizeObserver(() => instance.invalidateSize());
        resize.observe(element.current);
        request<FeatureCollection>("map", { signal: controller.signal })
            .then((data) => {
                L.geoJSON(data, {
                    pane: "base",
                    style: (feature) =>
                        feature?.properties?.kind === "building"
                            ? {
                                  color: "#cbd1ce",
                                  fillColor: "#e1e5e2",
                                  fillOpacity: 0.85,
                                  weight: 0.7,
                              }
                            : { color: "#c2cac4", weight: 1.1, opacity: 0.8 },
                    interactive: false,
                }).addTo(instance);
                setStatus("");
            })
            .catch((error) => {
                if (!controller.signal.aborted) {
                    setStatus(error.message);
                    setFailed(true);
                }
            });
        return () => {
            controller.abort();
            resize.disconnect();
            instance.remove();
            map.current = null;
            stations.current = null;
        };
    }, [retry]);

    useEffect(() => {
        if (!map.current || !dataset) return;
        const points = L.layerGroup().addTo(map.current);
        const renderer = L.canvas({ padding: 0.5 });
        for (const point of dataset.candidates) {
            L.circleMarker([point.lat, point.lon], {
                renderer,
                radius: 4,
                color: "#808f87",
                weight: 1.5,
                fillColor: "#ffffff",
                fillOpacity: 1,
            })
                .bindTooltip(`${point.id} · kandydat do weryfikacji`)
                .addTo(points);
        }
        for (const point of dataset.demand) {
            const node = document.createElement("span");
            node.textContent = `${point.name?.startsWith("way/") ? "Punkt popytu" : point.name || "Punkt popytu"} · wagi scenariuszowe`;
            L.circleMarker([point.lat, point.lon], {
                renderer,
                radius: 5.5,
                color: "#fff",
                weight: 2,
                fillColor: "#bd833b",
                fillOpacity: 1,
            })
                .bindTooltip(node)
                .addTo(points);
        }
        const instance = map.current;
        instance.fitBounds(
            L.latLngBounds(
                [...dataset.candidates, ...dataset.demand].map(
                    (p) => [p.lat, p.lon] as [number, number],
                ),
            ),
            { padding: [24, 24], animate: false },
        );
        return () => {
            instance.removeLayer(points);
        };
    }, [dataset, retry]);

    useEffect(() => {
        const group = stations.current;
        if (!group || !dataset) return;
        group.clearLayers();
        for (const point of dataset.candidates.filter((p) =>
            selected.includes(p.id),
        )) {
            L.marker([point.lat, point.lon], {
                icon: L.divIcon({
                    className: "station-pin",
                    html: `<span>${point.id.replace("candidate-", "")}</span>`,
                    iconSize: [32, 32],
                    iconAnchor: [16, 16],
                }),
                zIndexOffset: 1000,
            })
                .bindTooltip(`${point.id} · wybrana stacja`)
                .addTo(group);
        }
    }, [dataset, selected, retry]);

    function resetView() {
        if (dataset)
            map.current?.fitBounds(
                L.latLngBounds(
                    [...dataset.candidates, ...dataset.demand].map(
                        (p) => [p.lat, p.lon] as [number, number],
                    ),
                ),
                { padding: [24, 24], animate: false },
            );
    }

    return (
        <section
            className="map-panel"
            aria-label="Interaktywna mapa kampusu AGH"
        >
            <div ref={element} className="campus-map" />
            <div className="map-controls">
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
                    <i className="legend-station" /> Wybrane stacje
                </span>
                <span>
                    <i className="legend-demand" /> Punkty popytu
                </span>
                <span>
                    <i className="legend-candidate" /> Kandydaci
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

export default memo(CampusMap);
