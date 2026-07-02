import {useCallback, useEffect, useMemo, useReducer, useState} from "react";
import {App} from "antd";
import {fetchFilters, fetchTaskNames} from "@/api/movie";
import {MOVIE_FILTER_OPTION_TYPE} from "../constants";
import type {SelectOption} from "@/api/movie/types";
import {buildMovieFilterParams, type MovieFilterState} from "../utils/movieFilter";

function getErrorMessage(error: unknown): string {
    return error instanceof Error ? error.message : "请求失败";
}

type FilterAction =
    | {type: "patch"; payload: Partial<MovieFilterState>}
    | {type: "reset"};

const INITIAL_FILTER_STATE: MovieFilterState = {
    selectedTask: undefined,
    search: "",
    ratingMin: undefined,
    ratingMax: undefined,
    actorsCountMin: undefined,
    actorsCountMax: undefined,
    selectedActors: [],
    selectedActorsNot: [],
    selectedTags: [],
    selectedTagsNot: [],
    selectedDirectors: [],
    selectedDirectorsNot: [],
    selectedMakers: [],
    selectedMakersNot: [],
    selectedSeries: [],
    selectedSeriesNot: [],
    storageStatus: undefined,
    releaseDateFrom: null,
    releaseDateTo: null,
    createdAtFrom: null,
    createdAtTo: null,
};

function filterReducer(state: MovieFilterState, action: FilterAction): MovieFilterState {
    switch (action.type) {
        case "patch":
            return {...state, ...action.payload};
        case "reset":
            return {...INITIAL_FILTER_STATE};
        default:
            return state;
    }
}

function toOptions(values: string[]): SelectOption[] {
    return values.map((value) => ({value, label: value}));
}

export function useMovieFilters() {
    const {message} = App.useApp();
    const [form, dispatch] = useReducer(filterReducer, INITIAL_FILTER_STATE);
    const [taskOptions, setTaskOptions] = useState<SelectOption[]>([]);
    const [actorOptions, setActorOptions] = useState<SelectOption[]>([]);
    const [tagOptions, setTagOptions] = useState<SelectOption[]>([]);
    const [directorOptions, setDirectorOptions] = useState<SelectOption[]>([]);
    const [makerOptions, setMakerOptions] = useState<SelectOption[]>([]);
    const [seriesOptions, setSeriesOptions] = useState<SelectOption[]>([]);
    const [filtersLoading, setFiltersLoading] = useState(false);

    const patchForm = useCallback((payload: Partial<MovieFilterState>) => {
        dispatch({type: "patch", payload});
    }, []);

    const resetFilters = useCallback(() => {
        dispatch({type: "reset"});
    }, []);

    const loadOptions = useCallback(async () => {
        setFiltersLoading(true);
        try {
            const [tasks, actors, tags, directors, makers, series] = await Promise.all([
                fetchTaskNames(),
                fetchFilters(MOVIE_FILTER_OPTION_TYPE.ACTOR),
                fetchFilters(MOVIE_FILTER_OPTION_TYPE.TAG),
                fetchFilters(MOVIE_FILTER_OPTION_TYPE.DIRECTOR),
                fetchFilters(MOVIE_FILTER_OPTION_TYPE.MAKER),
                fetchFilters(MOVIE_FILTER_OPTION_TYPE.SERIES),
            ]);
            setTaskOptions(tasks.map((t) => ({value: t.name, label: t.name})));
            setActorOptions(toOptions(actors));
            setTagOptions(toOptions(tags));
            setDirectorOptions(toOptions(directors));
            setMakerOptions(toOptions(makers));
            setSeriesOptions(toOptions(series));
        } catch (e: unknown) {
            message.error(getErrorMessage(e));
        } finally {
            setFiltersLoading(false);
        }
    }, []);

    useEffect(() => {
        void loadOptions();
    }, [loadOptions]);

    const requestParams = useMemo(() => buildMovieFilterParams(form), [form]);

    return {
        form,
        patchForm,
        resetFilters,
        requestParams,
        taskOptions,
        actorOptions,
        tagOptions,
        directorOptions,
        makerOptions,
        seriesOptions,
        filtersLoading,
    };
}

export type MovieFilters = ReturnType<typeof useMovieFilters>;
