export type Method = "abc" | "random" | "greedy";
export type Scenario = "aggregate" | "morning" | "day" | "evening";
export type Parameters = {
    p: number;
    budget: number;
    seed: number;
    scenario: Scenario;
    include_exact: boolean;
};
export type Point = {
    id: string;
    lat: number;
    lon: number;
    name?: string;
    category?: string;
};
export type Dataset = {
    id: string;
    sha256: string;
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

export const methodNames: Record<Method, string> = {
    abc: "ABC · rój pszczół",
    random: "Losowanie",
    greedy: "Greedy + zamiany",
};
export const methodColors: Record<Method, string> = {
    abc: "#24735c",
    random: "#c38b41",
    greedy: "#6886b3",
};
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
