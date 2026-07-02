import type {SelectOption} from "@/api/movie/types";

export const MOVIE_SORT_FIELD = {
    CREATED_AT: "created_at",
    RELEASE_DATE: "release_date",
    RATING: "rating",
    CODE: "code",
} as const;

export type MovieSortField = typeof MOVIE_SORT_FIELD[keyof typeof MOVIE_SORT_FIELD];

export const MOVIE_SORT_FIELD_OPTIONS: SelectOption[] = [
    {value: "code:1", label: "番号 ↑"},
    {value: "code:-1", label: "番号 ↓"},
    {value: "release_date:-1", label: "发行日期 ↓"},
    {value: "release_date:1", label: "发行日期 ↑"},
    {value: "rating:-1", label: "评分 ↓"},
    {value: "rating:1", label: "评分 ↑"},
    {value: "created_at:-1", label: "抓取时间 ↓"},
    {value: "created_at:1", label: "抓取时间 ↑"},
];

export const MOVIE_SORT_ORDER = {
    ASC: 1,
    DESC: -1,
} as const;
