import { useEffect, useRef, useState, type CSSProperties } from "react";
import {
    ArrowDownRight,
    ArrowRight,
    Bike,
    Check,
    ChevronDown,
    CircleHelp,
    Download,
    Info,
    LoaderCircle,
    Pause,
    Pin,
    Play,
    RotateCcw,
    X,
} from "lucide-react";
import CampusMap from "./CampusMap";
import Convergence from "./Convergence";
import {
    GroupsPanel,
    ScenariosPanel,
    SeriesPanel,
    StationCurve,
    StationLoad,
    WorstBuildings,
} from "./Insights";
import {
    buildingName,
    categoryNames,
    methodColors,
    methodLabels as LABELS,
    methodNames,
    number,
    request,
    scenarioNames,
    stationLabel,
    type Analysis,
    type CurveRow,
    type Dataset,
    type Focus,
    type GroupRow,
    type Method,
    type Parameters,
    type Pool,
    type RobustResult,
    type Run,
    type Scenario,
    type SeriesResult,
} from "./types";

const DEFAULTS: Parameters = {
    p: 4,
    budget: 5000,
    seed: 0,
    scenario: "aggregate",
    include_exact: true,
    threshold_m: 250,
    candidate_pool: "all",
};
const METHODS: Method[] = ["abc", "ga", "random", "greedy"];
const BUDGETS = [500, 1000, 5000, 10000, 20000];
const CURVE_STATIONS = 40;
const JSON_POST = {
    method: "POST",
    headers: { "Content-Type": "application/json" },
};
type Baseline = { label: string; ids: string[] };

export default function App() {
    const [dataset, setDataset] = useState<Dataset | null>(null);
    const [params, setParams] = useState<Parameters>(DEFAULTS);
    const [run, setRun] = useState<Run | null>(null);
    const [method, setMethod] = useState<Method>("abc");
    const [busy, setBusy] = useState(true);
    const [error, setError] = useState("");
    const [playing, setPlaying] = useState(false);
    const [frame, setFrame] = useState(1);
    const [help, setHelp] = useState(false);
    const [analysis, setAnalysis] = useState<Analysis | null>(null);
    const [curve, setCurve] = useState<CurveRow[] | null>(null);
    const [series, setSeries] = useState<SeriesResult | null>(null);
    const [seeds, setSeeds] = useState(10);
    const [seriesBusy, setSeriesBusy] = useState(false);
    const [robust, setRobust] = useState<RobustResult | null>(null);
    const [robustBusy, setRobustBusy] = useState(false);
    const [focus, setFocus] = useState<Focus | null>(null);
    const [baseline, setBaseline] = useState<Baseline | null>(null);
    const [baselineSummary, setBaselineSummary] = useState<GroupRow | null>(
        null,
    );
    const helpDialog = useRef<HTMLDialogElement>(null);
    const activeRequest = useRef<AbortController | null>(null);

    useEffect(() => {
        const controller = new AbortController();
        activeRequest.current = controller;
        Promise.all([
            request<Dataset>("dataset", { signal: controller.signal }),
            request<Run>("run", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(DEFAULTS),
                signal: controller.signal,
            }),
        ])
            .then(([data, result]) => {
                setDataset(data);
                setRun(result);
            })
            .catch((e) => {
                if (!controller.signal.aborted) setError(e.message);
            })
            .finally(() => {
                if (!controller.signal.aborted) setBusy(false);
            });
        return () => activeRequest.current?.abort();
    }, []);

    useEffect(() => {
        if (!playing) return;
        const timer = window.setInterval(
            () => setFrame((previous) => Math.min(1, previous + 0.0125)),
            75,
        );
        return () => window.clearInterval(timer);
    }, [playing]);

    useEffect(() => {
        if (frame >= 1) setPlaying(false);
    }, [frame]);
    useEffect(() => {
        if (help) helpDialog.current?.showModal();
        else helpDialog.current?.close();
    }, [help]);

    const finalLayout = run?.methods[method].candidate_ids.join(",") ?? "";

    useEffect(() => {
        setFocus(null);
        setSeries(null);
        setRobust(null);
    }, [run]);

    // Only the final layout is analysed; replay frames change too quickly to be worth a request.
    useEffect(() => {
        if (!run || !finalLayout) return;
        const controller = new AbortController();
        setAnalysis(null);
        request<Analysis>("analysis", {
            ...JSON_POST,
            body: JSON.stringify({
                candidate_ids: finalLayout.split(","),
                scenario: run.parameters.scenario,
                threshold_m: run.parameters.threshold_m,
                candidate_pool: run.parameters.candidate_pool,
            }),
            signal: controller.signal,
        })
            .then(setAnalysis)
            .catch((e) => {
                if (!controller.signal.aborted) setError(e.message);
            });
        return () => controller.abort();
    }, [run, finalLayout]);

    const curveKey = run
        ? JSON.stringify({
              scenario: run.parameters.scenario,
              threshold_m: run.parameters.threshold_m,
              candidate_pool: run.parameters.candidate_pool,
              p_max: Math.max(CURVE_STATIONS, run.parameters.p),
          })
        : "";
    useEffect(() => {
        if (!curveKey) return;
        const controller = new AbortController();
        setCurve(null);
        request<{ rows: CurveRow[] }>("curve", {
            ...JSON_POST,
            body: curveKey,
            signal: controller.signal,
        })
            .then((result) => setCurve(result.rows))
            .catch((e) => {
                if (!controller.signal.aborted) setError(e.message);
            });
        return () => controller.abort();
    }, [curveKey]);

    // A remembered layout is always judged on the demand of the current run.
    useEffect(() => {
        if (!run || !baseline) {
            setBaselineSummary(null);
            return;
        }
        const controller = new AbortController();
        request<Analysis>("analysis", {
            ...JSON_POST,
            body: JSON.stringify({
                candidate_ids: baseline.ids,
                scenario: run.parameters.scenario,
                threshold_m: run.parameters.threshold_m,
            }),
            signal: controller.signal,
        })
            .then((result) => setBaselineSummary(result.groups[0]))
            .catch((e) => {
                if (!controller.signal.aborted) setError(e.message);
            });
        return () => controller.abort();
    }, [run, baseline]);

    async function runSeries() {
        if (!run) return;
        setSeriesBusy(true);
        setError("");
        try {
            setSeries(
                await request<SeriesResult>("series", {
                    ...JSON_POST,
                    body: JSON.stringify({
                        p: run.parameters.p,
                        budget: run.parameters.budget,
                        scenario: run.parameters.scenario,
                        candidate_pool: run.parameters.candidate_pool,
                        seeds,
                    }),
                }),
            );
        } catch (e) {
            setError(e instanceof Error ? e.message : "Seria nie powiodła się.");
        } finally {
            setSeriesBusy(false);
        }
    }

    async function runRobust() {
        if (!run) return;
        setRobustBusy(true);
        setError("");
        try {
            setRobust(
                await request<RobustResult>("robust", {
                    ...JSON_POST,
                    body: JSON.stringify({
                        p: run.parameters.p,
                        candidate_pool: run.parameters.candidate_pool,
                    }),
                }),
            );
        } catch (e) {
            setError(
                e instanceof Error
                    ? e.message
                    : "Nie udało się policzyć układu odpornego.",
            );
        } finally {
            setRobustBusy(false);
        }
    }

    async function calculate() {
        activeRequest.current?.abort();
        const controller = new AbortController();
        activeRequest.current = controller;
        setBusy(true);
        setError("");
        setPlaying(false);
        try {
            const [data, result] = await Promise.all([
                dataset
                    ? Promise.resolve(dataset)
                    : request<Dataset>("dataset", {
                          signal: controller.signal,
                      }),
                request<Run>("run", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(params),
                    signal: controller.signal,
                }),
            ]);
            setDataset(data);
            setRun(result);
            setMethod("abc");
            setFrame(0);
            setPlaying(true);
        } catch (e) {
            if (!controller.signal.aborted)
                setError(
                    e instanceof Error
                        ? e.message
                        : "Nie udało się uruchomić obliczeń.",
                );
        } finally {
            if (!controller.signal.aborted) setBusy(false);
        }
    }

    const pool = dataset?.pools[params.candidate_pool];
    const maxStations = pool?.count ?? DEFAULTS.p;
    const minBudget = pool?.greedy_min_budget[params.p - 1] ?? 0;

    // Keep the settings valid: too small a budget would only produce an error from the server.
    function changeSize(p: number, candidate_pool: Pool = params.candidate_pool) {
        const options = dataset?.pools[candidate_pool];
        const stations = Math.min(p, options?.count ?? p);
        const needed = options?.greedy_min_budget[stations - 1] ?? 0;
        setParams((v) => ({
            ...v,
            p: stations,
            candidate_pool,
            budget:
                v.budget >= needed
                    ? v.budget
                    : (BUDGETS.find((b) => b >= needed) ?? v.budget),
        }));
    }

    const solution = run?.methods[method];
    const evaluation = Math.round(frame * (run?.parameters.budget ?? 1000));
    const step = solution?.steps
        .filter((s) => s.evaluation <= evaluation)
        .at(-1);
    const selected = step?.candidate_ids;
    const changed =
        run && JSON.stringify(params) !== JSON.stringify(run.parameters);
    const improvement = solution
        ? ((solution.steps[0].mean_distance_m - solution.mean_distance_m) /
              solution.steps[0].mean_distance_m) *
          100
        : 0;
    const gap =
        run?.exact && solution
            ? ((solution.mean_distance_m - run.exact.mean_distance_m) /
                  run.exact.mean_distance_m) *
              100
            : null;

    function download() {
        if (!run) return;
        const url = URL.createObjectURL(
            new Blob(
                [
                    JSON.stringify(
                        {
                            ...run,
                            selected_method: method,
                            analysis,
                            station_curve: curve,
                            series,
                            robust,
                        },
                        null,
                        2,
                    ),
                ],
                { type: "application/json" },
            ),
        );
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = `agh-p${run.parameters.p}-${run.parameters.scenario}-seed${run.parameters.seed}.json`;
        anchor.click();
        window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    }

    function selectMethod(next: Method) {
        setMethod(next);
        setPlaying(false);
        setFrame(1);
        setFocus(null);
    }

    function rememberLayout() {
        if (!run || !solution) return;
        setBaseline({
            label: `${LABELS[method]} · ${scenarioNames[run.parameters.scenario]} · ${run.parameters.p} st.`,
            ids: solution.candidate_ids,
        });
    }

    const summary = analysis?.groups[0];
    const common =
        baseline && solution
            ? baseline.ids.filter((id) => solution.candidate_ids.includes(id))
                  .length
            : 0;
    const focusedBuilding =
        focus?.kind === "building"
            ? analysis?.buildings.find((b) => b.id === focus.id)
            : undefined;
    const focusedPoint =
        focus?.kind === "building"
            ? dataset?.demand.find((d) => d.id === focus.id)
            : undefined;
    const focusedStation =
        focus?.kind === "station"
            ? analysis?.stations.find((s) => s.id === focus.id)
            : undefined;
    const focusedCandidate =
        focus?.kind === "station"
            ? dataset?.candidates.find((c) => c.id === focus.id)
            : undefined;
    const threshold = run?.parameters.threshold_m ?? DEFAULTS.threshold_m;

    return (
        <div className="app-shell">
            <header className="topbar">
                <a
                    className="brand"
                    href="/"
                    aria-label="AGH Station Lab — strona główna"
                >
                    <span className="brand-symbol">
                        <Bike size={22} strokeWidth={1.7} />
                    </span>
                    <span>
                        AGH <strong>Station Lab</strong>
                    </span>
                </a>
                <div className="header-actions">
                    <span className="offline-badge">
                        <span className="live-dot" /> Działa offline
                    </span>
                    <span className="header-divider" />
                    <button
                        className="button-quiet"
                        onClick={() => setHelp(true)}
                    >
                        <CircleHelp size={17} /> Jak działają ABC i GA
                    </button>
                </div>
            </header>

            <main>
                <div className="page-heading">
                    <div>
                        <p className="eyebrow">
                            Miasteczko studenckie AGH <span> / </span> Wersja
                            robocza
                        </p>
                        <h1>Rozmieszczenie stacji</h1>
                        <p>
                            Wybierz liczbę stacji. Sprawdź, jak zmienia się
                            droga do najbliższej z nich.
                        </p>
                    </div>
                    <button
                        className="button-secondary export-button"
                        disabled={!run || busy}
                        onClick={download}
                    >
                        <Download size={16} /> Eksportuj wynik
                    </button>
                </div>

                {error ? (
                    <div className="error-banner" role="alert">
                        <Info size={18} />
                        <span>{error}</span>
                        <button onClick={calculate} disabled={busy}>
                            Spróbuj ponownie
                        </button>
                    </div>
                ) : null}

                <div className="workspace">
                    <aside className="settings-panel">
                        <div className="panel-heading">
                            <h2>Eksperyment</h2>
                        </div>
                        <div className="settings-body">
                            <div className="range-label">
                                <label htmlFor="station-count">
                                    Liczba stacji
                                </label>
                                <output htmlFor="station-count">
                                    {params.p}
                                </output>
                            </div>
                            <input
                                id="station-count"
                                type="range"
                                min="1"
                                max={maxStations}
                                value={params.p}
                                disabled={busy}
                                style={
                                    {
                                        "--range-progress": `${((params.p - 1) / Math.max(1, maxStations - 1)) * 100}%`,
                                    } as CSSProperties
                                }
                                onChange={(e) => changeSize(+e.target.value)}
                            />
                            <div className="range-extents">
                                <span>1</span>
                                <span>{maxStations} stacji</span>
                            </div>
                            <label className="field-label" htmlFor="scenario">
                                Scenariusz popytu
                            </label>
                            <select
                                id="scenario"
                                value={params.scenario}
                                disabled={busy}
                                onChange={(e) =>
                                    setParams((v) => ({
                                        ...v,
                                        scenario: e.target.value as Scenario,
                                    }))
                                }
                            >
                                {Object.entries(scenarioNames).map(
                                    ([key, label]) => (
                                        <option key={key} value={key}>
                                            {label}
                                        </option>
                                    ),
                                )}
                            </select>
                            <p className="field-hint">
                                {params.scenario === "aggregate"
                                    ? "Równa mieszanina trzech pór dnia."
                                    : "Założone wagi dla wybranej pory dnia."}
                            </p>
                            <label className="field-label" htmlFor="pool">
                                Możliwe lokalizacje
                            </label>
                            <select
                                id="pool"
                                value={params.candidate_pool}
                                disabled={busy}
                                onChange={(e) =>
                                    changeSize(params.p, e.target.value as Pool)
                                }
                            >
                                <option value="all">
                                    Wszystkie ({dataset?.pools.all?.count ?? "—"})
                                </option>
                                {dataset?.pools.existing ? (
                                    <option value="existing">
                                        Tylko istniejące parkingi (
                                        {dataset.pools.existing.count})
                                    </option>
                                ) : null}
                            </select>
                            <label className="field-label" htmlFor="threshold">
                                Akceptowalne dojście
                            </label>
                            <select
                                id="threshold"
                                value={params.threshold_m}
                                disabled={busy}
                                onChange={(e) =>
                                    setParams((v) => ({
                                        ...v,
                                        threshold_m: +e.target.value,
                                    }))
                                }
                            >
                                {[150, 250, 350, 500].map((v) => (
                                    <option key={v} value={v}>
                                        do {v} m
                                    </option>
                                ))}
                            </select>

                            <details className="advanced-settings">
                                <summary>
                                    Parametry zaawansowane{" "}
                                    <ChevronDown size={16} />
                                </summary>
                                <div className="advanced-body">
                                    <label
                                        className="field-label"
                                        htmlFor="budget"
                                    >
                                        Budżet ocen funkcji celu
                                    </label>
                                    <select
                                        id="budget"
                                        value={params.budget}
                                        disabled={busy}
                                        onChange={(e) =>
                                            setParams((v) => ({
                                                ...v,
                                                budget: +e.target.value,
                                            }))
                                        }
                                    >
                                        {BUDGETS.map((v) => (
                                            <option
                                                key={v}
                                                value={v}
                                                disabled={v < minBudget}
                                            >
                                                {number(v, 0)} ocen
                                            </option>
                                        ))}
                                    </select>
                                    <p className="field-hint">
                                        Greedy przy {params.p} st. potrzebuje co
                                        najmniej {number(minBudget, 0)} ocen.
                                    </p>
                                    <div className="seed-row">
                                        <label
                                            className="field-label"
                                            htmlFor="seed"
                                        >
                                            Ziarno losowe
                                        </label>
                                        <button
                                            className="button-quiet"
                                            disabled={busy}
                                            title="Wybierz nowe ziarno"
                                            onClick={() =>
                                                setParams((v) => ({
                                                    ...v,
                                                    seed: Math.floor(
                                                        Math.random() * 10000,
                                                    ),
                                                }))
                                            }
                                        >
                                            <RotateCcw size={13} /> Losuj
                                        </button>
                                    </div>
                                    <input
                                        id="seed"
                                        className="seed-input"
                                        type="number"
                                        min="0"
                                        max="4294967295"
                                        step="1"
                                        value={params.seed}
                                        disabled={busy}
                                        onChange={(e) =>
                                            setParams((v) => ({
                                                ...v,
                                                seed: Number(e.target.value),
                                            }))
                                        }
                                    />
                                    <p className="field-hint">
                                        To samo ziarno odtwarza ten sam wynik.
                                    </p>
                                    <label className="checkbox-label">
                                        <input
                                            type="checkbox"
                                            checked={params.include_exact}
                                            disabled={busy}
                                            onChange={(e) =>
                                                setParams((v) => ({
                                                    ...v,
                                                    include_exact:
                                                        e.target.checked,
                                                }))
                                            }
                                        />
                                        <span>
                                            Oblicz dokładne optimum
                                            <small>
                                                Programowanie całkowitoliczbowe
                                                · poza budżetem ocen
                                            </small>
                                        </span>
                                    </label>
                                    <p className="algorithm-parameters">
                                        ABC: {run?.abc.foods ?? "—"} źródeł ·
                                        limit porzucenia {run?.abc.limit ?? "—"}
                                        <br />
                                        GA: populacja {run?.ga.population ?? "—"}{" "}
                                        · mutacja {run?.ga.mutation ?? "—"} ·
                                        krzyżowanie{" "}
                                        {run?.ga.crossover === "greedy"
                                            ? "zachłanne"
                                            : "losowe z rodziców"}
                                        <br />
                                        Dobrane na osobnej instancji
                                        rozwojowej.
                                    </p>
                                </div>
                            </details>

                            <button
                                className="button-primary"
                                onClick={calculate}
                                disabled={
                                    busy ||
                                    !Number.isInteger(params.seed) ||
                                    params.seed < 0 ||
                                    params.seed > 4294967295
                                }
                            >
                                {busy ? (
                                    <LoaderCircle size={17} className="spin" />
                                ) : (
                                    <Play size={15} fill="currentColor" />
                                )}
                                {busy
                                    ? "Trwają obliczenia…"
                                    : "Uruchom eksperyment"}
                            </button>
                            {changed ? (
                                <p className="pending-note" role="status">
                                    Zmieniono parametry. Uruchom ponownie.
                                </p>
                            ) : (
                                <p className="run-note">
                                    <Check size={13} /> Porównanie czterech metod
                                </p>
                            )}
                        </div>
                        <div className="dataset-note">
                            <strong>Zestaw {dataset?.id ?? "…"}</strong>
                            <p>
                                {dataset?.candidates.length ?? "—"} możliwych
                                lokalizacji
                                <br />
                                {dataset?.demand.length ?? "—"} punktów popytu ·
                                graf pieszy OSM
                            </p>
                        </div>
                    </aside>

                    <div className="results-column">
                        <div className="metrics" aria-live="polite">
                            <div className="metric">
                                <span className="metric-label">
                                    Średnie ważone dojście
                                </span>
                                <strong>
                                    {step ? number(step.mean_distance_m) : "—"}
                                    <small>m</small>
                                </strong>
                                <span>po sieci pieszej</span>
                            </div>
                            <div className="metric">
                                <span className="metric-label">
                                    Pokrycie do {threshold} m
                                </span>
                                <strong>
                                    {step ? number(step.coverage * 100) : "—"}
                                    <small>%</small>
                                </strong>
                                <span>ważonego popytu</span>
                            </div>
                            <div className="metric">
                                <span className="metric-label">
                                    Dojście 90% popytu
                                </span>
                                <strong>
                                    {step
                                        ? number(step.p90_distance_m, 0)
                                        : "—"}
                                    <small>m</small>
                                </strong>
                                <span>percentyl ważony P90</span>
                            </div>
                            <div className="metric">
                                <span className="metric-label">
                                    Najdłuższe dojście
                                </span>
                                <strong>
                                    {step
                                        ? number(step.max_distance_m, 0)
                                        : "—"}
                                    <small>m</small>
                                </strong>
                                <span>najgorzej położony budynek</span>
                            </div>
                        </div>

                        <section
                            className="map-card"
                            aria-label="Wynik rozmieszczenia stacji"
                        >
                            <div className="map-header">
                                <h2>Mapa kampusu</h2>
                                <div
                                    className="method-tabs"
                                    role="group"
                                    aria-label="Metoda widoczna na mapie"
                                >
                                    {METHODS.map((m) => (
                                        <button
                                            key={m}
                                            aria-pressed={m === method}
                                            onClick={() => selectMethod(m)}
                                            title={methodNames[m]}
                                        >
                                            <i
                                                style={{
                                                    background: methodColors[m],
                                                }}
                                            />
                                            {LABELS[m]}
                                        </button>
                                    ))}
                                </div>
                            </div>
                            <CampusMap
                                dataset={dataset}
                                selected={selected}
                                weights={run?.demand_weights}
                                scenario={run?.parameters.scenario ?? "aggregate"}
                                baseline={baseline?.ids}
                                threshold={threshold}
                                focus={focus}
                                onFocus={setFocus}
                            >
                                {focusedBuilding ? (
                                    <aside className="map-detail">
                                        <h3>
                                            {buildingName(focusedBuilding.name)}
                                        </h3>
                                        <dl>
                                            <dt>Funkcja</dt>
                                            <dd>
                                                {categoryNames[
                                                    focusedBuilding.category
                                                ] ?? focusedBuilding.category}
                                            </dd>
                                            <dt>Pow. użytkowa</dt>
                                            <dd>
                                                {number(
                                                    focusedPoint?.floor_area_m2 ??
                                                        0,
                                                    0,
                                                )}{" "}
                                                m²
                                                {focusedPoint?.levels_source ===
                                                "osm"
                                                    ? ""
                                                    : " (szac.)"}
                                            </dd>
                                            <dt>Udział w popycie</dt>
                                            <dd>
                                                {number(
                                                    focusedBuilding.demand_share *
                                                        100,
                                                )}
                                                %
                                            </dd>
                                            <dt>Dojście</dt>
                                            <dd>
                                                {number(
                                                    focusedBuilding.distance_m,
                                                    0,
                                                )}{" "}
                                                m
                                            </dd>
                                            <dt>Najbliższa stacja</dt>
                                            <dd>
                                                {stationLabel(
                                                    focusedBuilding.station,
                                                )}
                                            </dd>
                                        </dl>
                                        <button
                                            aria-label="Zamknij szczegóły"
                                            onClick={() => setFocus(null)}
                                        >
                                            <X size={14} />
                                        </button>
                                    </aside>
                                ) : null}
                                {focusedStation ? (
                                    <aside className="map-detail">
                                        <h3>
                                            Stacja{" "}
                                            {stationLabel(focusedStation.id)}
                                        </h3>
                                        <dl>
                                            <dt>Obsługiwany popyt</dt>
                                            <dd>
                                                {number(
                                                    focusedStation.demand_share *
                                                        100,
                                                )}
                                                %
                                            </dd>
                                            <dt>Budynki</dt>
                                            <dd>{focusedStation.buildings}</dd>
                                            <dt>Średnie dojście</dt>
                                            <dd>
                                                {focusedStation.mean_m === null
                                                    ? "—"
                                                    : `${number(focusedStation.mean_m, 0)} m`}
                                            </dd>
                                            <dt>Najdłuższe dojście</dt>
                                            <dd>
                                                {focusedStation.max_m === null
                                                    ? "—"
                                                    : `${number(focusedStation.max_m, 0)} m`}
                                            </dd>
                                            <dt>Pochodzenie</dt>
                                            <dd>
                                                {focusedCandidate?.source?.startsWith(
                                                    "osm_",
                                                )
                                                    ? "parking w OSM"
                                                    : "węzeł przy budynkach"}
                                            </dd>
                                            <dt>Audyt</dt>
                                            <dd>
                                                {focusedCandidate?.status ===
                                                "reviewed"
                                                    ? "sprawdzona"
                                                    : "do sprawdzenia"}
                                            </dd>
                                        </dl>
                                        <button
                                            aria-label="Zamknij szczegóły"
                                            onClick={() => setFocus(null)}
                                        >
                                            <X size={14} />
                                        </button>
                                    </aside>
                                ) : null}
                            </CampusMap>
                            <div className="playback">
                                <button
                                    className="playback-play"
                                    disabled={!run || busy}
                                    onClick={() => {
                                        if (frame >= 1) setFrame(0);
                                        setPlaying((v) => !v);
                                    }}
                                    aria-label={
                                        playing
                                            ? "Wstrzymaj odtwarzanie"
                                            : "Odtwórz przebieg"
                                    }
                                >
                                    {playing ? (
                                        <Pause size={16} fill="currentColor" />
                                    ) : (
                                        <Play size={16} fill="currentColor" />
                                    )}
                                </button>
                                <div className="playback-label">
                                    <strong>
                                        {playing
                                            ? "Odtwarzanie popraw"
                                            : frame < 1
                                              ? "Zatrzymany przebieg"
                                              : "Odtwórz przebieg"}
                                    </strong>
                                    <span>Zapis popraw · {LABELS[method]}</span>
                                </div>
                                <input
                                    type="range"
                                    aria-label="Przebieg obliczeń"
                                    min="0"
                                    max="1000"
                                    value={Math.round(frame * 1000)}
                                    disabled={!run || busy}
                                    onChange={(e) => {
                                        setPlaying(false);
                                        setFrame(+e.target.value / 1000);
                                    }}
                                />
                                <span className="evaluation-count">
                                    {number(evaluation, 0)}
                                    <small>
                                        {" "}
                                        /{" "}
                                        {number(
                                            run?.parameters.budget ?? 1000,
                                            0,
                                        )}{" "}
                                        ocen
                                    </small>
                                </span>
                            </div>
                            <div className="selected-stations">
                                <span>Wybrane stacje</span>
                                <div className="station-chips">
                                    {selected?.length ? (
                                        selected.map((id) => (
                                            <span
                                                key={id}
                                                className="station-chip"
                                                title={`${id} · wymaga weryfikacji w terenie`}
                                            >
                                                {id.replace("candidate-", "")}
                                            </span>
                                        ))
                                    ) : (
                                        <span className="no-selection">
                                            Oczekiwanie na pierwszy układ
                                        </span>
                                    )}
                                </div>
                                <span className="result-context">
                                    {run
                                        ? `${scenarioNames[run.parameters.scenario]} · p = ${run.parameters.p} · seed ${run.parameters.seed}`
                                        : "Przygotowanie danych"}
                                </span>
                                <button
                                    className="pin-button"
                                    disabled={!run}
                                    onClick={rememberLayout}
                                    title="Pokaż ten układ na mapie obok kolejnych wyników"
                                >
                                    <Pin size={12} /> Zapamiętaj układ
                                </button>
                            </div>
                            {baseline ? (
                                <div className="compare-strip" role="status">
                                    <strong>
                                        Porównanie z: {baseline.label}
                                    </strong>
                                    {baselineSummary && summary ? (
                                        <>
                                            <span>
                                                dojście{" "}
                                                {number(baselineSummary.mean_m)}{" "}
                                                m (obecny układ{" "}
                                                {number(
                                                    summary.mean_m -
                                                        baselineSummary.mean_m,
                                                )}{" "}
                                                m)
                                            </span>
                                            <span>
                                                pokrycie{" "}
                                                {number(
                                                    baselineSummary.coverage *
                                                        100,
                                                )}
                                                %
                                            </span>
                                            <span>
                                                wspólne stacje: {common} z{" "}
                                                {solution?.candidate_ids.length}
                                            </span>
                                        </>
                                    ) : (
                                        <span>Liczenie…</span>
                                    )}
                                    <button onClick={() => setBaseline(null)}>
                                        <X size={12} /> Usuń
                                    </button>
                                </div>
                            ) : null}
                        </section>
                    </div>

                    <div className="analysis-grid">
                        <section className="convergence-panel">
                            <div className="chart-heading">
                                <div>
                                    <h2>Przebieg optymalizacji</h2>
                                    <p>
                                        Najlepsze średnie dojście [m]. Mniej
                                        znaczy lepiej.
                                    </p>
                                </div>
                                <span className="improvement">
                                    <ArrowDownRight size={18} />
                                    {number(improvement)}%
                                    <small>
                                        od pierwszego układu {LABELS[method]}
                                    </small>
                                </span>
                            </div>
                            <Convergence
                                run={run}
                                method={method}
                                evaluation={evaluation}
                            />
                            <div className="chart-footer">
                                <div className="chart-legend">
                                    {METHODS.map((m) => (
                                        <span key={m}>
                                            <i
                                                style={{
                                                    background: methodColors[m],
                                                }}
                                            />
                                            {LABELS[m]}
                                        </span>
                                    ))}
                                    {run?.exact ? (
                                        <span>
                                            <i className="legend-exact" />
                                            Optimum
                                        </span>
                                    ) : null}
                                </div>
                                <span>Liczba ocen funkcji celu</span>
                            </div>
                        </section>

                        <section className="comparison-panel">
                            <div className="comparison-heading">
                                <h2>Porównanie metod</h2>
                                <p>Wyniki końcowe · jeden przebieg</p>
                            </div>
                            <table>
                                <caption className="sr-only">
                                    Wyniki końcowe metod. Wybierz metodę, aby
                                    wyświetlić ją na mapie.
                                </caption>
                                <thead>
                                    <tr>
                                        <th scope="col">Metoda</th>
                                        <th scope="col">Dojście</th>
                                        <th scope="col">Oceny · czas</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {METHODS.map((m) => (
                                        <tr
                                            key={m}
                                            className={
                                                method === m ? "active" : ""
                                            }
                                        >
                                            <th scope="row">
                                                <button
                                                    aria-pressed={method === m}
                                                    onClick={() =>
                                                        selectMethod(m)
                                                    }
                                                    title={`Pokaż na mapie: ${methodNames[m]}`}
                                                >
                                                    <i
                                                        style={{
                                                            background:
                                                                methodColors[m],
                                                        }}
                                                    />
                                                    {m === "greedy"
                                                        ? "Greedy + swap"
                                                        : LABELS[m]}
                                                    {method === m ? (
                                                        <Check
                                                            size={13}
                                                            aria-label="Na mapie"
                                                        />
                                                    ) : null}
                                                </button>
                                            </th>
                                            <td>
                                                {run
                                                    ? number(
                                                          run.methods[m]
                                                              .mean_distance_m,
                                                      )
                                                    : "—"}
                                                <small> m</small>
                                            </td>
                                            <td>
                                                {run
                                                    ? number(
                                                          run.methods[m]
                                                              .evaluations,
                                                          0,
                                                      )
                                                    : "—"}
                                                <small>
                                                    {run
                                                        ? ` · ${number(run.methods[m].elapsed_s * 1000, 0)} ms`
                                                        : ""}
                                                </small>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                            <div className="reference-result">
                                <span>
                                    Dokładne optimum
                                    <small>
                                        {run?.exact
                                            ? `Solver MILP · ${number(run.exact.elapsed_s * 1000, 0)} ms`
                                            : "Dostępne w parametrach zaawansowanych"}
                                    </small>
                                </span>
                                <strong>
                                    {run?.exact
                                        ? `${number(run.exact.mean_distance_m)} m`
                                        : "—"}
                                </strong>
                            </div>
                            <div className="gap-note">
                                <span>Luka {LABELS[method]} do optimum</span>
                                <strong>
                                    {gap !== null ? `${number(gap, 2)}%` : "—"}
                                </strong>
                            </div>
                            <p className="single-run-note">
                                Ziarno {run?.parameters.seed ?? 0} · wspólny
                                limit ocen. Greedy może zakończyć wcześniej.
                                Ocena metod wymaga wielu przebiegów.
                            </p>
                        </section>
                    </div>

                    <div className="insight-grid">
                        <StationCurve
                            rows={curve}
                            p={run?.parameters.p ?? params.p}
                            threshold={threshold}
                            onPick={(p) => changeSize(p)}
                        />
                        <GroupsPanel
                            analysis={analysis}
                            threshold={threshold}
                        />
                        <ScenariosPanel
                            analysis={analysis}
                            robust={robust}
                            robustBusy={robustBusy}
                            onRobust={runRobust}
                            onCompareRobust={() =>
                                robust &&
                                run &&
                                setBaseline({
                                    label: `Układ odporny · ${run.parameters.p} st.`,
                                    ids: robust.candidate_ids,
                                })
                            }
                            disabled={!run || busy || seriesBusy}
                        />
                        <WorstBuildings
                            analysis={analysis}
                            threshold={threshold}
                            onFocus={setFocus}
                        />
                        <StationLoad analysis={analysis} onFocus={setFocus} />
                        <SeriesPanel
                            series={series}
                            busy={seriesBusy}
                            seeds={seeds}
                            onSeeds={setSeeds}
                            onRun={runSeries}
                            disabled={!run || busy || robustBusy}
                        />
                    </div>
                </div>

                <footer className="page-footer">
                    <Info size={16} />
                    <p>
                        <strong>Model demonstracyjny.</strong> Wagi są założone,
                        a lokalizacje wymagają weryfikacji w terenie, dopóki
                        audyt ich nie potwierdzi.
                    </p>
                </footer>
            </main>

            <dialog
                ref={helpDialog}
                onCancel={() => setHelp(false)}
                onClose={() => setHelp(false)}
                className="help-dialog"
                aria-labelledby="help-title"
            >
                <button
                    className="dialog-close"
                    aria-label="Zamknij opis algorytmu"
                    onClick={() => setHelp(false)}
                >
                    <X size={20} />
                </button>
                <p className="eyebrow">Artificial Bee Colony</p>
                <h2 id="help-title">Rój szuka lepszego układu.</h2>
                <p>
                    Jedno źródło pokarmu to zbiór dokładnie{" "}
                    <strong>p różnych stacji</strong>. Sąsiedni układ powstaje
                    przez zamianę jednego miejsca. Cel: zminimalizować średnie
                    ważone dojście od punktów popytu do najbliższej stacji po
                    grafie pieszym.
                </p>
                <ol>
                    <li>
                        <strong>Pszczoły pracujące</strong>
                        <span>
                            Każde źródło próbuje poprawić swój układ przez jedną
                            zamianę.
                        </span>
                    </li>
                    <li>
                        <strong>Obserwatorki</strong>
                        <span>
                            Częściej wybierają obiecujące źródła i szukają
                            kolejnych popraw.
                        </span>
                    </li>
                    <li>
                        <strong>Zwiadowczynie</strong>
                        <span>
                            Po stagnacji zastępują porzucone źródło nowym
                            losowym układem.
                        </span>
                    </li>
                </ol>
                <p>
                    <strong>Algorytm genetyczny</strong> utrzymuje populację
                    układów. Potomek dziedziczy stacje wspólne obu rodzicom, a
                    resztę bierze od któregoś z nich. Rzadka mutacja zamienia
                    jedną stację, a lepszy potomek zastępuje najgorszy układ.
                </p>
                <p>
                    Animacja odtwarza rzeczywiste poprawy po zakończeniu
                    obliczeń. Wykres porównuje pojedyncze przebiegi. Dokładne
                    optimum liczy osobny solver, poza budżetem ocen.
                </p>
                <div className="dialog-note">
                    <Info size={17} />
                    <span>
                        Linie to trasy po grafie pieszym OSM do najbliższej
                        stacji: zielone w zasięgu, pomarańczowe dłuższe.
                        Wielkość punktu popytu odpowiada założonej wadze w
                        wybranym scenariuszu.
                    </span>
                </div>
                <button
                    className="button-primary"
                    onClick={() => setHelp(false)}
                >
                    Wracam do eksperymentu <ArrowRight size={16} />
                </button>
            </dialog>
        </div>
    );
}
