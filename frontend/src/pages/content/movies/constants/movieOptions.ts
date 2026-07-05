import type {SelectOption} from "@/api/movie/types";

export const MOVIE_FILTER_OPTION_TYPE = {
    ACTOR: "actor",
    TAG: "tag",
    DIRECTOR: "director",
    MAKER: "maker",
    SERIES: "series",
} as const;

export type MovieFilterOptionType = typeof MOVIE_FILTER_OPTION_TYPE[keyof typeof MOVIE_FILTER_OPTION_TYPE];

export const MOVIE_STORAGE_STATUS_OPTIONS: SelectOption[] = [
    {value: "not_stored", label: "未存储"},
    {value: "storing", label: "入库中"},
    {value: "stored", label: "已存储"},
];
