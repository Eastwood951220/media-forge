import type {Dayjs} from "dayjs";

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
