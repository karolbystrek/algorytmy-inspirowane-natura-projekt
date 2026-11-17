export type Method = "abc" | "ga" | "ga_restart" | "random" | "greedy";
export type Scenario = "aggregate" | "morning" | "day" | "evening";
export type Pool = "all" | "existing";
export type Parameters = {
    p: number;
    budget: number;
    seed: number;
    scenario: Scenario;
    include_exact: boolean;
    threshold_m: number;
    candidate_pool: Pool;
};
export type Point = {
    id: string;
    lat: number;
    lon: number;
    name?: string;
    category?: string;
    source?: string;
    status?: string;
    floor_area_m2?: number;
    levels_source?: string;
};
export type Dataset = {
    id: string;
    sha256: string;
    pools: Partial<
        Record<Pool, { count: number; greedy_min_budget: number[] }>
    >;
    candidates: Point[];
    demand: Point[];
    quality: {
        retained_graph_nodes: number;
        retained_graph_edges: number;
        buildings: number;
    };
};
export type Step = {
    evaluation: number;
    candidate_ids: string[];
    mean_distance_m: number;
    coverage: number;
    p90_distance_m: number;
    max_distance_m: number;
};
export type Solution = Omit<Step, "evaluation"> & {
    evaluations: number;
    elapsed_s: number;
    steps: Step[];
};
export type Run = {
    parameters: Parameters;
    abc: { foods: number; limit: number };
    ga: {
        population: number;
        mutation: number;
        crossover: string;
        restart_after: number;
    };
    dataset_id: string;
    problem_sha256: string;
    methods: Record<Method, Solution>;
    exact: {
        mean_distance_m: number;
        elapsed_s: number;
    } | null;
    threshold_m: number;
    demand_weights: number[];
};

export type GroupRow = {
    group: string;
    buildings: number;
    demand_share: number;
    mean_m: number;
    p90_m: number;
    max_m: number;
    coverage: number;
};
export type BuildingRow = {
    id: string;
    name?: string;
    category: string;
    distance_m: number;
    station: string;
    demand_share: number;
};
export type StationRow = {
    id: string;
    buildings: number;
    demand_share: number;
    mean_m: number | null;
    max_m: number | null;
};
export type ScenarioRow = {
    scenario: Exclude<Scenario, "aggregate">;
    mean_m: number;
    optimum_m: number;
    regret_percent: number;
    coverage: number;
    common_stations: number;
};
export type Analysis = {
    groups: GroupRow[];
    buildings: BuildingRow[];
    stations: StationRow[];
    scenarios: ScenarioRow[];
    gates: {
        demand_without_route: number;
        buildings_without_route: number;
        mean_open_m: number | null;
        mean_closed_m: number | null;
        increase_percent: number | null;
    } | null;
};
export type CurveRow = {
    p: number;
    mean_distance_m: number;
    coverage: number;
    p90_distance_m: number;
    max_distance_m: number;
    gain_m: number | null;
};
export type SeriesResult = {
    optimum_m: number;
    parameters: { seeds: number };
    methods: Record<
        Method,
        {
            values: number[];
            mean_m: number;
            best_m: number;
            worst_m: number;
            mean_gap_percent: number;
            optimum_hits: number;
        }
    >;
};
export type RobustResult = {
    candidate_ids: string[];
    worst_regret_percent: number;
    mean_m: number;
    cost_on_aggregate_percent: number;
    proved: boolean;
    elapsed_s: number;
};
export type Focus = {
    kind: "building" | "station";
    id: string;
    pan?: boolean;
};

export const methodNames: Record<Method, string> = {
    abc: "ABC · rój pszczół",
    ga: "GA · algorytm genetyczny",
    ga_restart: "GA z restartem populacji",
    random: "Losowanie",
    greedy: "Greedy + zamiany",
};
export const methodLabels: Record<Method, string> = {
    abc: "ABC",
    ga: "GA",
    ga_restart: "GA + restart",
    random: "Losowanie",
    greedy: "Greedy",
};
export const methodColors: Record<Method, string> = {
    abc: "#0e7a5a",
    ga: "#8a4fbf",
    ga_restart: "#c43c5e",
    random: "#b67a1e",
    greedy: "#4a7cc9",
};
export const categoryNames: Record<string, string> = {
    all: "Cały kampus",
    dorm: "Akademiki",
    teaching: "Budynki uczelni",
    other: "Pozostałe",
    unknown: "Bez kategorii",
};
export const buildingName = (name: string | undefined) =>
    !name || /^(way|relation)\//.test(name) ? "Budynek bez nazwy w OSM" : name;
export const stationLabel = (id: string) => id.replace("candidate-", "");
export const scenarioNames: Record<Scenario, string> = {
    aggregate: "Cały dzień",
    morning: "Poranek",
    day: "Dzień",
    evening: "Wieczór",
};
export const number = (value: number, digits = 1) =>
    value.toLocaleString("pl-PL", {
        maximumFractionDigits: digits,
        minimumFractionDigits: digits,
    });

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(`/api/${path}`, init);
    if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(
            typeof body?.detail === "string"
                ? body.detail
                : `Żądanie nie powiodło się (${response.status}). Sprawdź parametry i połączenie z serwerem.`,
        );
    }
    return response.json();
}
