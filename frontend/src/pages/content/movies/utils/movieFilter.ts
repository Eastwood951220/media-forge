import type {Dayjs} from "dayjs";
import type { MovieFilterConfig } from "@/api/movie/types";

export interface MovieFilterState {
    selectedTask?: string;
    search: string;
    ratingMin?: number;
    ratingMax?: number;
    actorsCountMin?: number;
    actorsCountMax?: number;
    selectedActors: string[];
    selectedActorsNot: string[];
    selectedTags: string[];
    selectedTagsNot: string[];
    selectedDirectors: string[];
    selectedDirectorsNot: string[];
    selectedMakers: string[];
    selectedMakersNot: string[];
    selectedSeries: string[];
    selectedSeriesNot: string[];
    storageStatus?: string;
    releaseDateFrom: Dayjs | null;
    releaseDateTo: Dayjs | null;
    createdAtFrom: Dayjs | null;
    createdAtTo: Dayjs | null;
}

export interface MovieFilterParams {
    source_task_id?: string;
    search?: string;
    rating_min?: number;
    rating_max?: number;
    actors?: string;
    actors_not?: string;
    actors_count_min?: number;
    actors_count_max?: number;
    tags?: string;
    tags_not?: string;
    director?: string;
    director_not?: string;
    maker?: string;
    maker_not?: string;
    series?: string;
    series_not?: string;
    release_date_from?: string;
    release_date_to?: string;
    created_at_from?: string;
    created_at_to?: string;
    storage_status?: string;
}

function joinValues(values: string[]): string | undefined {
    return values.length > 0 ? values.join(",") : undefined;
}

export function buildMovieFilterParams(state: MovieFilterState): MovieFilterParams {
    return {
        source_task_id: state.selectedTask,
        search: state.search.trim() || undefined,
        rating_min: state.ratingMin,
        rating_max: state.ratingMax,
        actors: joinValues(state.selectedActors),
        actors_not: joinValues(state.selectedActorsNot),
        actors_count_min: state.actorsCountMin,
        actors_count_max: state.actorsCountMax,
        tags: joinValues(state.selectedTags),
        tags_not: joinValues(state.selectedTagsNot),
        director: joinValues(state.selectedDirectors),
        director_not: joinValues(state.selectedDirectorsNot),
        maker: joinValues(state.selectedMakers),
        maker_not: joinValues(state.selectedMakersNot),
        series: joinValues(state.selectedSeries),
        series_not: joinValues(state.selectedSeriesNot),
        release_date_from: state.releaseDateFrom?.format("YYYY-MM-DD"),
        release_date_to: state.releaseDateTo?.format("YYYY-MM-DD"),
        created_at_from: state.createdAtFrom?.format("YYYY-MM-DD"),
        created_at_to: state.createdAtTo?.format("YYYY-MM-DD"),
        storage_status: state.storageStatus,
    };
}

function splitDefaultValues(value: unknown): string[] {
    if (Array.isArray(value)) {
        return value.map((item) => String(item).trim()).filter(Boolean);
    }
    if (typeof value !== "string") return [];
    return value.split(",").map((item) => item.trim()).filter(Boolean);
}

export function buildMovieFilterDefaultState(config: MovieFilterConfig | undefined): Partial<MovieFilterState> {
    const defaults: Partial<MovieFilterState> = {};
    if (!config) return defaults;

    for (const [key, value] of Object.entries(config)) {
        if (key === "sortBy" || value?.defaultValue === undefined) continue;
        const defaultValue = value.defaultValue;
        switch (key) {
            case "actors":
                defaults.selectedActors = splitDefaultValues(defaultValue);
                break;
            case "actorsNot":
                defaults.selectedActorsNot = splitDefaultValues(defaultValue);
                break;
            case "tags":
                defaults.selectedTags = splitDefaultValues(defaultValue);
                break;
            case "tagsNot":
                defaults.selectedTagsNot = splitDefaultValues(defaultValue);
                break;
            case "director":
                defaults.selectedDirectors = splitDefaultValues(defaultValue);
                break;
            case "directorNot":
                defaults.selectedDirectorsNot = splitDefaultValues(defaultValue);
                break;
            case "maker":
                defaults.selectedMakers = splitDefaultValues(defaultValue);
                break;
            case "makerNot":
                defaults.selectedMakersNot = splitDefaultValues(defaultValue);
                break;
            case "series":
                defaults.selectedSeries = splitDefaultValues(defaultValue);
                break;
            case "seriesNot":
                defaults.selectedSeriesNot = splitDefaultValues(defaultValue);
                break;
            case "storageStatus":
                defaults.storageStatus = typeof defaultValue === "string" ? defaultValue : undefined;
                break;
            case "ratingMin":
                defaults.ratingMin = typeof defaultValue === "number" ? defaultValue : undefined;
                break;
            case "ratingMax":
                defaults.ratingMax = typeof defaultValue === "number" ? defaultValue : undefined;
                break;
            case "actorsCountMin":
                defaults.actorsCountMin = typeof defaultValue === "number" ? defaultValue : undefined;
                break;
            case "actorsCountMax":
                defaults.actorsCountMax = typeof defaultValue === "number" ? defaultValue : undefined;
                break;
            case "releaseDateFrom":
            case "releaseDateTo":
            case "createdAtFrom":
            case "createdAtTo":
                break;
        }
    }

    return defaults;
}
