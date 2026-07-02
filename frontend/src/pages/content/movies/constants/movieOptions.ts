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
    {value: "completed", label: "已完成"},
    {value: "missing", label: "文件缺失"},
    {value: "failed", label: "失败"},
    {value: "pending", label: "等待中"},
    {value: "running", label: "运行中"},
    {value: "waiting_download", label: "等待下载"},
    {value: "waiting_retry", label: "等待重试"},
    {value: "retryable", label: "可重试"},
];
