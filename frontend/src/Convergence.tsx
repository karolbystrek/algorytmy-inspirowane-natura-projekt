import type { Method, Run } from "./types";
import { methodColors, number } from "./types";

export default function Convergence({
    run,
    method,
    evaluation,
}: {
    run: Run | null;
    method: Method;
    evaluation: number;
}) {
    if (!run)
        return (
            <div className="chart-empty">
                Uruchom eksperyment, aby zobaczyć przebieg optymalizacji.
            </div>
        );
    const methods: Method[] = ["abc", "random", "greedy"];
    const values = methods.flatMap((m) =>
        run.methods[m].steps.map((s) => s.mean_distance_m),
    );
    if (run.exact) values.push(run.exact.mean_distance_m);
    const low = Math.min(...values) * 0.95;
    const high = Math.max(...values) * 1.03;
    const x = (e: number) => 53 + (e / run.parameters.budget) * 627;
    const y = (v: number) => 150 - ((v - low) / (high - low || 1)) * 132;
    const active = run.methods[method].steps
        .filter((s) => s.evaluation <= evaluation)
        .at(-1);
    return (
        <svg
            className="chart"
            viewBox="0 0 700 184"
            role="img"
            aria-label="Wykres najlepszego średniego dojścia w metrach względem liczby ocen funkcji celu"
        >
            {[0, 0.5, 1].map((t) => {
                const value = low + (high - low) * t;
                return (
                    <g key={t}>
                        <line
                            x1="53"
                            x2="680"
                            y1={y(value)}
                            y2={y(value)}
                            stroke="#e5e9e6"
                            strokeDasharray="3 5"
                        />
                        <text x="42" y={y(value) + 4} textAnchor="end">
                            {number(value, 0)}
                        </text>
                    </g>
                );
            })}
            {[0, 0.25, 0.5, 0.75, 1].map((t) => (
                <text
                    key={t}
                    x={x(t * run.parameters.budget)}
                    y="174"
                    textAnchor="middle"
                >
                    {number(t * run.parameters.budget, 0)}
                </text>
            ))}
            {run.exact ? (
                <line
                    x1="53"
                    x2="680"
                    y1={y(run.exact.mean_distance_m)}
                    y2={y(run.exact.mean_distance_m)}
                    stroke="#788277"
                    strokeDasharray="5 4"
                />
            ) : null}
            {methods.map((m) => {
                const steps = run.methods[m].steps;
                const path =
                    steps
                        .map(
                            (s, i) =>
                                `${i === 0 ? "M" : "H"} ${x(s.evaluation)} ${i === 0 ? y(s.mean_distance_m) : `V ${y(s.mean_distance_m)}`}`,
                        )
                        .join(" ") + ` H ${x(run.parameters.budget)}`;
                return (
                    <path
                        key={m}
                        d={path}
                        fill="none"
                        stroke={methodColors[m]}
                        strokeWidth={m === method ? 3 : 2}
                        opacity={m === method ? 1 : 0.75}
                    />
                );
            })}
            {active ? (
                <g>
                    <line
                        x1={x(evaluation)}
                        x2={x(evaluation)}
                        y1="18"
                        y2="150"
                        stroke={methodColors[method]}
                        opacity="0.25"
                    />
                    <circle
                        cx={x(evaluation)}
                        cy={y(active.mean_distance_m)}
                        r="4.5"
                        fill={methodColors[method]}
                        stroke="white"
                        strokeWidth="2"
                    />
                </g>
            ) : null}
        </svg>
    );
}
