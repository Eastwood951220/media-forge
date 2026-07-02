import type {MovieListResponse} from "@/api/movie/types";

export const DEFAULT_MOVIE_PAGE = 1;
export const DEFAULT_MOVIE_PAGE_SIZE = 20;
export const DEFAULT_MOVIE_SORT_FIELD = "created_at";
export const DEFAULT_MOVIE_SORT_ORDER = -1 as const;

export const INITIAL_MOVIE_LIST_RESPONSE: MovieListResponse = {
    items: [],
    total: 0,
    page: DEFAULT_MOVIE_PAGE,
    limit: DEFAULT_MOVIE_PAGE_SIZE,
    total_pages: 1,
};
