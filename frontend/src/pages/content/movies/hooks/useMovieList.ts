import {useCallback, useEffect, useState} from "react";
import type React from "react";
import {App} from "antd";
import {fetchMovies, syncMovieStorageStatus} from "@/api/movie";
import {DEFAULT_MOVIE_PAGE, DEFAULT_MOVIE_PAGE_SIZE, INITIAL_MOVIE_LIST_RESPONSE, DEFAULT_MOVIE_SORT_FIELD, DEFAULT_MOVIE_SORT_ORDER} from "../constants";
import type {Movie, MovieListResponse} from "@/api/movie/types";
import type {MovieFilterParams} from "../utils/movieFilter";

function getErrorMessage(error: unknown): string {
    return error instanceof Error ? error.message : "请求失败";
}

export function useMovieList(
    filterParams: MovieFilterParams | undefined,
    initialSort?: { sortBy: string; sortOrder: number },
) {
    const {message} = App.useApp();
    const [data, setData] = useState<MovieListResponse>(INITIAL_MOVIE_LIST_RESPONSE);
    const [page, setPage] = useState(DEFAULT_MOVIE_PAGE);
    const [pageSize, setPageSize] = useState(DEFAULT_MOVIE_PAGE_SIZE);
    const [sortBy, setSortBy] = useState(initialSort?.sortBy ?? DEFAULT_MOVIE_SORT_FIELD);
    const [sortOrder, setSortOrder] = useState<number>(initialSort?.sortOrder ?? DEFAULT_MOVIE_SORT_ORDER);
    const [loading, setLoading] = useState(false);
    const [syncingStorage, setSyncingStorage] = useState(false);
    const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);

    const loadMovies = useCallback(async () => {
        if (!filterParams) return;
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

    const syncStorageStatus = useCallback(async () => {
        if (!filterParams) return;
        setSyncingStorage(true);
        try {
            const selectedIds = selectedRowKeys.map((key) => String(key));
            const payload = selectedIds.length > 0
                ? {movie_ids: selectedIds}
                : {filters: filterParams};
            const result = await syncMovieStorageStatus(payload);
            message.success(`同步完成：已存储 ${result.stored_count} 条，未存储 ${result.not_stored_count} 条`);
            setSelectedRowKeys([]);
            await loadMovies();
        } catch (e: unknown) {
            message.error(getErrorMessage(e));
        } finally {
            setSyncingStorage(false);
        }
    }, [filterParams, loadMovies, message, selectedRowKeys]);

    return {
        data, page, pageSize, sortBy, sortOrder, loading, syncingStorage, selectedRowKeys,
        setPage, setPageSize, setSelectedRowKeys,
        search, reload, syncStorageStatus, handlePageChange, handleShowSizeChange, handleSortChange, resetSort, updateMovie,
    };
}

export type MovieList = ReturnType<typeof useMovieList>;
