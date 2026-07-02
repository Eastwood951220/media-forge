import {useCallback, useEffect, useState} from "react";
import type React from "react";
import {App} from "antd";
import {fetchMovies} from "@/api/movie";
import {DEFAULT_MOVIE_PAGE, DEFAULT_MOVIE_PAGE_SIZE, INITIAL_MOVIE_LIST_RESPONSE, DEFAULT_MOVIE_SORT_FIELD, DEFAULT_MOVIE_SORT_ORDER} from "../constants";
import type {Movie, MovieListResponse} from "@/api/movie/types";
import type {MovieFilterParams} from "../utils/movieFilter";

function getErrorMessage(error: unknown): string {
    return error instanceof Error ? error.message : "请求失败";
}

export function useMovieList(
    filterParams: MovieFilterParams,
    initialSort?: { sortBy: string; sortOrder: number },
) {
    const {message} = App.useApp();
    const [data, setData] = useState<MovieListResponse>(INITIAL_MOVIE_LIST_RESPONSE);
    const [page, setPage] = useState(DEFAULT_MOVIE_PAGE);
    const [pageSize, setPageSize] = useState(DEFAULT_MOVIE_PAGE_SIZE);
    const [sortBy, setSortBy] = useState(initialSort?.sortBy ?? DEFAULT_MOVIE_SORT_FIELD);
    const [sortOrder, setSortOrder] = useState<number>(initialSort?.sortOrder ?? DEFAULT_MOVIE_SORT_ORDER);
    const [loading, setLoading] = useState(false);
    const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);

    const loadMovies = useCallback(async () => {
        setLoading(true);
        try {
            const result = await fetchMovies({
                ...filterParams,
                page,
                limit: pageSize,
                sort_by: sortBy,
                sort_order: sortOrder,
            });
            setData(result);
        } catch (e: unknown) {
            message.error(getErrorMessage(e));
        } finally {
            setLoading(false);
        }
    }, [filterParams, page, pageSize, sortBy, sortOrder]);

    useEffect(() => {
        void loadMovies();
    }, [loadMovies]);

    const search = useCallback(() => {
        setSelectedRowKeys([]);
        if (page === DEFAULT_MOVIE_PAGE) {
            void loadMovies();
        } else {
            setPage(DEFAULT_MOVIE_PAGE);
        }
    }, [page, loadMovies]);

    const reload = useCallback(() => {
        setSelectedRowKeys([]);
        void loadMovies();
    }, [loadMovies]);

    const handleShowSizeChange = useCallback((_current: number, size: number) => {
        setSelectedRowKeys([]);
        setPageSize(size);
        setPage(DEFAULT_MOVIE_PAGE);
    }, []);

    const handlePageChange = useCallback((nextPage: number, nextPageSize: number) => {
        setSelectedRowKeys([]);
        setPage(nextPage);
        setPageSize(nextPageSize);
    }, []);

    const handleSortChange = useCallback((field: string, order: number) => {
        setSortBy(field);
        setSortOrder(order);
        setPage(DEFAULT_MOVIE_PAGE);
    }, []);

    const resetSort = useCallback((override?: { sortBy: string; sortOrder: number }) => {
        setSortBy(override?.sortBy ?? DEFAULT_MOVIE_SORT_FIELD);
        setSortOrder(override?.sortOrder ?? DEFAULT_MOVIE_SORT_ORDER);
    }, []);

    const updateMovie = useCallback((id: string, updater: (movie: Movie) => Movie) => {
        setData((prev) => ({
            ...prev,
            items: prev.items.map((item) => item._id === id ? updater(item) : item),
        }));
    }, []);

    return {
        data, page, pageSize, sortBy, sortOrder, loading, selectedRowKeys,
        setPage, setPageSize, setSelectedRowKeys,
        search, reload, handlePageChange, handleShowSizeChange, handleSortChange, resetSort, updateMovie,
    };
}

export type MovieList = ReturnType<typeof useMovieList>;
