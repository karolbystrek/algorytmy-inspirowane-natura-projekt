import { useState } from "react";
import { LoaderCircle, Pin } from "lucide-react";
import {
    buildingName,
    categoryNames,
    methodColors,
    methodLabels,
    number,
    scenarioNames,
    stationLabel,
    type Analysis,
    type CurveRow,
    type Focus,
    type Method,
    type RobustResult,
    type SeriesResult,
} from "./types";

const METHODS: Method[] = ["abc", "ga", "random", "greedy"];
const LINE = "#0e7a5a";
const SURFACE = "#ffffff";

function Waiting({ children }: { children: string }) {
    return (
        <div className="insight-empty">
            <LoaderCircle size={15} className="spin" /> {children}
        </div>
    );
}

function CurvePlot({
    rows,
    title,
    read,
    top: ceiling,
    p,
    hover,
    onHover,
    onPick,
}: {
    rows: CurveRow[];
    title: string;
    read: (row: CurveRow) => number;
    top?: number;
    p: number;
    hover: number | null;
    onHover: (p: number | null) => void;
    onPick: (p: number) => void;
}) {
    const width = 340;
    const height = 158;
    const left = 42;
    const right = 8;
    const top = 8;
    const bottom = 132;
    const low = 0;
    const high = ceiling ?? Math.ceil(Math.max(...rows.map(read)) / 100) * 100;
    const last = rows[rows.length - 1].p;
    const x = (v: number) =>
        left + ((v - 1) / Math.max(1, last - 1)) * (width - left - right);
    const y = (v: number) => bottom - ((v - low) / (high - low)) * (bottom - top);
    const line = rows
        .map((r, i) => `${i ? "L" : "M"} ${x(r.p)} ${y(read(r))}`)
        .join(" ");
    const xTicks = [1, ...[10, 20, 30, 40, 60, 80].filter((t) => t < last), last];
    const chosen = rows.find((r) => r.p === p);
    const hovered = rows.find((r) => r.p === hover);
    const band = (width - left - right) / Math.max(1, last - 1);
    return (
        <figure className="curve-plot">
            <figcaption>{title}</figcaption>
            <svg
                viewBox={`0 0 ${width} ${height}`}
                role="img"
                aria-label={`${title}, od 1 do ${last} stacji`}
                onMouseLeave={() => onHover(null)}
            >
                {[0, 0.5, 1].map((t) => {
                    const value = low + (high - low) * t;
                    return (
                        <g key={t}>
                            <line
                                x1={left}
                                x2={width - right}
                                y1={y(value)}
                                y2={y(value)}
                                stroke="#e8ece9"
                            />
                            <text x={left - 7} y={y(value) + 4} textAnchor="end">
                                {number(value, 0)}
                            </text>
                        </g>
                    );
                })}
                {xTicks.map((t) => (
                    <text key={t} x={x(t)} y={height - 8} textAnchor="middle">
                        {t}
                    </text>
                ))}
                <path d={line} fill="none" stroke={LINE} strokeWidth="2" />
                {hovered ? (
                    <line
                        x1={x(hovered.p)}
                        x2={x(hovered.p)}
                        y1={top}
                        y2={bottom}
                        stroke="#9aa79f"
                    />
                ) : null}
                {chosen ? (
                    <circle
                        cx={x(chosen.p)}
                        cy={y(read(chosen))}
                        r="5"
                        fill={LINE}
                        stroke={SURFACE}
                        strokeWidth="2"
                    />
                ) : null}
                {rows.map((r) => (
                    <rect
                        key={r.p}
                        x={x(r.p) - band / 2}
                        y={top}
                        width={band}
                        height={bottom - top}
                        fill="transparent"
                        style={{ cursor: "pointer" }}
                        onMouseEnter={() => onHover(r.p)}
                        onClick={() => onPick(r.p)}
                    />
                ))}
            </svg>
        </figure>
    );
}

export function StationCurve({
    rows,
    p,
    threshold,
    onPick,
}: {
    rows: CurveRow[] | null;
    p: number;
    threshold: number;
    onPick: (p: number) => void;
}) {
    const [hover, setHover] = useState<number | null>(null);
    const shown = rows?.find((r) => r.p === (hover ?? p));
    return (
        <section className="insight-panel insight-wide">
            <div className="insight-heading">
                <h2>Ile stacji warto postawić?</h2>
                <p>
                    Układy optymalne dla każdej liczby stacji. Kliknij wykres,
                    aby ustawić tę liczbę w eksperymencie.
                </p>
            </div>
            {rows ? (
                <>
                    <div className="curve-readout" aria-live="polite">
                        {shown ? (
                            <>
                                <strong>{shown.p} stacji</strong>
                                <span>
                                    {number(shown.mean_distance_m)} m średnio
                                </span>
                                <span>
                                    {number(shown.coverage * 100)}% w zasięgu{" "}
                                    {threshold} m
                                </span>
                                <span>
                                    {shown.gain_m === null
                                        ? "pierwsza stacja"
                                        : `ta stacja skraca dojście o ${number(shown.gain_m)} m`}
                                </span>
                            </>
                        ) : (
                            <span>Najedź na wykres, aby odczytać wartości.</span>
                        )}
                    </div>
                    <div className="curve-grid">
                        <CurvePlot
                            rows={rows}
                            title="Średnie ważone dojście [m]"
                            read={(r) => r.mean_distance_m}
                            p={p}
                            hover={hover}
                            onHover={setHover}
                            onPick={onPick}
                        />
                        <CurvePlot
                            rows={rows}
                            title={`Popyt w zasięgu ${threshold} m [%]`}
                            read={(r) => r.coverage * 100}
                            top={100}
                            p={p}
                            hover={hover}
                            onHover={setHover}
                            onPick={onPick}
                        />
                    </div>
                    <p className="insight-note">
                        Pokrycie może chwilowo spaść po dodaniu stacji, bo
                        optymalizowane jest średnie dojście, a nie pokrycie.
                    </p>
                </>
            ) : (
                <Waiting>Liczenie układów optymalnych…</Waiting>
            )}
        </section>
    );
}

export function SeriesPanel({
    series,
    busy,
    seeds,
    onSeeds,
    onRun,
    disabled,
}: {
    series: SeriesResult | null;
    busy: boolean;
    seeds: number;
    onSeeds: (seeds: number) => void;
    onRun: () => void;
    disabled: boolean;
}) {
    const [hover, setHover] = useState("");
    const width = 340;
    const left = 70;
    const right = 14;
    const rowHeight = 42;
    const gaps = (method: Method) =>
        series!.methods[method].values.map(
            (v) => (100 * (v - series!.optimum_m)) / series!.optimum_m,
        );
    const largest = series
        ? Math.max(1, ...METHODS.flatMap((m) => gaps(m)))
        : 1;
    // Random search is far worse than the rest; a root scale keeps both visible.
    const x = (gap: number) =>
        left +
        (Math.sqrt(Math.max(0, gap)) / Math.sqrt(largest)) *
            (width - left - right);
    const ticks = [0, 1, 5, 20, 50, 100].filter((t) => t <= largest);
    return (
        <section className="insight-panel insight-wide">
            <div className="insight-heading">
                <h2>Seria przebiegów</h2>
                <p>
                    Te same ustawienia, różne ziarna. Pojedynczy przebieg nie
                    wystarcza do oceny metody losowej.
                </p>
            </div>
            <div className="series-controls">
                <label htmlFor="seeds">Liczba ziaren</label>
                <select
                    id="seeds"
                    value={seeds}
                    disabled={busy}
                    onChange={(e) => onSeeds(+e.target.value)}
                >
                    {[10, 20, 30].map((v) => (
                        <option key={v} value={v}>
                            {v}
                        </option>
                    ))}
                </select>
                <button
                    className="button-secondary"
                    disabled={busy || disabled}
                    onClick={onRun}
                >
                    {busy ? (
                        <LoaderCircle size={14} className="spin" />
                    ) : null}
                    {busy ? "Trwa seria…" : "Uruchom serię"}
                </button>
            </div>
            {series ? (
                <div className="series-grid">
                    <div>
                    <svg
                        className="series-plot"
                        viewBox={`0 0 ${width} ${METHODS.length * rowHeight + 28}`}
                        role="img"
                        aria-label="Strata do optimum w kolejnych przebiegach każdej metody"
                        onMouseLeave={() => setHover("")}
                    >
                        {ticks.map((t) => (
                            <g key={t}>
                                <line
                                    x1={x(t)}
                                    x2={x(t)}
                                    y1="4"
                                    y2={METHODS.length * rowHeight + 6}
                                    stroke="#e8ece9"
                                />
                                <text
                                    x={x(t)}
                                    y={METHODS.length * rowHeight + 22}
                                    textAnchor="middle"
                                >
                                    {t}%
                                </text>
                            </g>
                        ))}
                        {METHODS.map((m, row) => {
                            const seen = new Map<number, number>();
                            const centre = row * rowHeight + rowHeight / 2 + 4;
                            return (
                                <g key={m}>
                                    <circle
                                        cx="6"
                                        cy={centre}
                                        r="4"
                                        fill={methodColors[m]}
                                    />
                                    <text x="15" y={centre + 4}>
                                        {methodLabels[m]}
                                    </text>
                                    {gaps(m).map((gap, i) => {
                                        const cell = Math.round(x(gap) / 7);
                                        const level = seen.get(cell) ?? 0;
                                        seen.set(cell, level + 1);
                                        const shift =
                                            ((level + 1) >> 1) *
                                            (level % 2 ? -7 : 7);
                                        return (
                                            <circle
                                                key={i}
                                                cx={x(gap)}
                                                cy={centre + shift}
                                                r="4"
                                                fill={methodColors[m]}
                                                stroke={SURFACE}
                                                strokeWidth="1.5"
                                                onMouseEnter={() =>
                                                    setHover(
                                                        `${methodLabels[m]}${m === "greedy" ? "" : `, ziarno ${i}`}: ${number(series.methods[m].values[i], 2)} m, strata ${number(gap, 3)}%`,
                                                    )
                                                }
                                            />
                                        );
                                    })}
                                </g>
                            );
                        })}
                    </svg>
                    <p className="series-readout" aria-live="polite">
                        {hover ||
                            "Strata do dowiedzionego optimum, skala pierwiastkowa."}
                    </p>
                    </div>
                    <table className="insight-table">
                        <thead>
                            <tr>
                                <th scope="col">Metoda</th>
                                <th scope="col">Średnio</th>
                                <th scope="col">Strata</th>
                                <th scope="col">Optimum</th>
                            </tr>
                        </thead>
                        <tbody>
                            {METHODS.map((m) => {
                                const result = series.methods[m];
                                return (
                                    <tr key={m}>
                                        <th scope="row">{methodLabels[m]}</th>
                                        <td>{number(result.mean_m, 2)} m</td>
                                        <td>
                                            {number(result.mean_gap_percent, 3)}%
                                        </td>
                                        <td>
                                            {result.optimum_hits}/
                                            {result.values.length}
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>
            ) : (
                <div className="insight-empty">
                    Uruchom serię, aby zobaczyć rozrzut wyników.
                </div>
            )}
        </section>
    );
}

export function GroupsPanel({
    analysis,
    threshold,
}: {
    analysis: Analysis | null;
    threshold: number;
}) {
    return (
        <section className="insight-panel">
            <div className="insight-heading">
                <h2>Kto ma blisko, a kto daleko?</h2>
                <p>Średnia może ukrywać źle obsłużoną grupę budynków.</p>
            </div>
            {analysis ? (
                <table className="insight-table">
                    <thead>
                        <tr>
                            <th scope="col">Grupa</th>
                            <th scope="col">Popyt</th>
                            <th scope="col">Średnio</th>
                            <th scope="col">P90</th>
                            <th scope="col">Maks.</th>
                            <th scope="col">Do {threshold} m</th>
                        </tr>
                    </thead>
                    <tbody>
                        {analysis.groups.map((g) => (
                            <tr key={g.group}>
                                <th scope="row">
                                    {categoryNames[g.group] ?? g.group}
                                    <small>{g.buildings} bud.</small>
                                </th>
                                <td>{number(g.demand_share * 100, 0)}%</td>
                                <td>{number(g.mean_m, 0)} m</td>
                                <td>{number(g.p90_m, 0)} m</td>
                                <td>{number(g.max_m, 0)} m</td>
                                <td>{number(g.coverage * 100, 0)}%</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            ) : (
                <Waiting>Analiza układu…</Waiting>
            )}
        </section>
    );
}

export function ScenariosPanel({
    analysis,
    robust,
    robustBusy,
    onRobust,
    onCompareRobust,
    disabled,
}: {
    analysis: Analysis | null;
    robust: RobustResult | null;
    robustBusy: boolean;
    onRobust: () => void;
    onCompareRobust: () => void;
    disabled: boolean;
}) {
    const gates = analysis?.gates;
    return (
        <section className="insight-panel">
            <div className="insight-heading">
                <h2>Jeden układ, różne pory dnia</h2>
                <p>
                    Strata tego układu wobec układu ułożonego osobno pod daną
                    porę.
                </p>
            </div>
            {analysis ? (
                <>
                    <table className="insight-table">
                        <thead>
                            <tr>
                                <th scope="col">Pora</th>
                                <th scope="col">Ten układ</th>
                                <th scope="col">Optimum</th>
                                <th scope="col">Strata</th>
                                <th scope="col">Wspólne</th>
                            </tr>
                        </thead>
                        <tbody>
                            {analysis.scenarios.map((s) => (
                                <tr key={s.scenario}>
                                    <th scope="row">
                                        {scenarioNames[s.scenario]}
                                    </th>
                                    <td>{number(s.mean_m, 0)} m</td>
                                    <td>{number(s.optimum_m, 0)} m</td>
                                    <td>{number(s.regret_percent)}%</td>
                                    <td>
                                        {s.common_stations}/
                                        {analysis.stations.length}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                    <div className="robust-row">
                        {robust ? (
                            <p>
                                <strong>Układ odporny:</strong> najgorsza strata{" "}
                                {number(robust.worst_regret_percent)}%, koszt na
                                całym dniu{" "}
                                {number(robust.cost_on_aggregate_percent)}%.
                                {robust.proved
                                    ? ""
                                    : " Limit czasu: bez dowodu optymalności."}
                            </p>
                        ) : (
                            <p>
                                Układ odporny wyrównuje stratę między porami
                                dnia.
                            </p>
                        )}
                        {robust ? (
                            <button
                                className="button-secondary"
                                onClick={onCompareRobust}
                            >
                                <Pin size={13} /> Porównaj na mapie
                            </button>
                        ) : (
                            <button
                                className="button-secondary"
                                disabled={robustBusy || disabled}
                                onClick={onRobust}
                            >
                                {robustBusy ? (
                                    <LoaderCircle size={14} className="spin" />
                                ) : null}
                                Policz układ odporny
                            </button>
                        )}
                    </div>
                    {gates ? (
                        <p className="insight-note">
                            Gdyby wszystkie bramy o nieznanym stanie były
                            zamknięte: {gates.buildings_without_route} bud. bez
                            trasy ({number(gates.demand_without_route * 100)}%
                            popytu)
                            {gates.increase_percent !== null
                                ? `, a dojście pozostałych dłuższe o ${number(gates.increase_percent)}%.`
                                : "."}
                        </p>
                    ) : null}
                </>
            ) : (
                <Waiting>Analiza układu…</Waiting>
            )}
        </section>
    );
}

export function WorstBuildings({
    analysis,
    threshold,
    onFocus,
}: {
    analysis: Analysis | null;
    threshold: number;
    onFocus: (focus: Focus) => void;
}) {
    const rows = analysis
        ? [...analysis.buildings]
              .sort((a, b) => b.distance_m - a.distance_m)
              .slice(0, 8)
        : [];
    const outside =
        analysis?.buildings.filter((b) => b.distance_m > threshold).length ?? 0;
    return (
        <section className="insight-panel">
            <div className="insight-heading">
                <h2>Najdłuższe dojścia</h2>
                <p>
                    {outside} z {analysis?.buildings.length ?? "—"} budynków
                    poza zasięgiem {threshold} m. Kliknij, aby pokazać trasę.
                </p>
            </div>
            {analysis ? (
                <table className="insight-table">
                    <thead>
                        <tr>
                            <th scope="col">Budynek</th>
                            <th scope="col">Popyt</th>
                            <th scope="col">Stacja</th>
                            <th scope="col">Dojście</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows.map((b) => (
                            <tr key={b.id}>
                                <th scope="row">
                                    <button
                                        className="table-link"
                                        onClick={() =>
                                            onFocus({
                                                kind: "building",
                                                id: b.id,
                                                pan: true,
                                            })
                                        }
                                    >
                                        {buildingName(b.name)}
                                    </button>
                                </th>
                                <td>{number(b.demand_share * 100)}%</td>
                                <td>{stationLabel(b.station)}</td>
                                <td>{number(b.distance_m, 0)} m</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            ) : (
                <Waiting>Analiza układu…</Waiting>
            )}
        </section>
    );
}

export function StationLoad({
    analysis,
    onFocus,
}: {
    analysis: Analysis | null;
    onFocus: (focus: Focus) => void;
}) {
    const rows = analysis
        ? [...analysis.stations]
              .sort((a, b) => b.demand_share - a.demand_share)
              .slice(0, 8)
        : [];
    const largest = rows[0]?.demand_share || 1;
    return (
        <section className="insight-panel">
            <div className="insight-heading">
                <h2>Obciążenie stacji</h2>
                <p>
                    Model nie ma limitu pojemności, więc tu widać, które stacje
                    przejęłyby najwięcej popytu.
                </p>
            </div>
            {analysis ? (
                <ul className="load-list">
                    {rows.map((s) => (
                        <li key={s.id}>
                            <button
                                className="table-link"
                                onClick={() =>
                                    onFocus({
                                        kind: "station",
                                        id: s.id,
                                        pan: true,
                                    })
                                }
                            >
                                {stationLabel(s.id)}
                            </button>
                            <span className="load-track">
                                <i
                                    style={{
                                        width: `${(s.demand_share / largest) * 100}%`,
                                    }}
                                />
                            </span>
                            <span className="load-value">
                                {number(s.demand_share * 100)}%
                                <small>{s.buildings} bud.</small>
                            </span>
                        </li>
                    ))}
                </ul>
            ) : (
                <Waiting>Analiza układu…</Waiting>
            )}
        </section>
    );
}
