import React from "react";
import {Input, Select, InputNumber, DatePicker, Button, Space} from "antd";
import {SearchOutlined, ReloadOutlined, SettingOutlined} from "@ant-design/icons";
import type {MovieFilters} from "../hooks/useMovieFilters";
import type {MovieFilterConfig, MovieFilterField} from "@/api/movie/types";

// Module-level constant — defines all filter items with their default order
const FILTER_ITEMS: {key: MovieFilterField; label: string; defaultOrder: number}[] = [
    {key: "actors", label: "演员筛选", defaultOrder: 0},
    {key: "actorsNot", label: "排除演员", defaultOrder: 1},
    {key: "tags", label: "标签筛选", defaultOrder: 2},
    {key: "tagsNot", label: "排除标签", defaultOrder: 3},
    {key: "director", label: "导演筛选", defaultOrder: 4},
    {key: "directorNot", label: "排除导演", defaultOrder: 5},
    {key: "maker", label: "片商筛选", defaultOrder: 6},
    {key: "makerNot", label: "排除片商", defaultOrder: 7},
    {key: "series", label: "系列筛选", defaultOrder: 8},
    {key: "seriesNot", label: "排除系列", defaultOrder: 9},
    {key: "storageStatus", label: "存储状态", defaultOrder: 10},
    {key: "ratingMin", label: "最低评分", defaultOrder: 11},
    {key: "ratingMax", label: "最高评分", defaultOrder: 12},
    {key: "actorsCountMin", label: "最少演员", defaultOrder: 13},
    {key: "actorsCountMax", label: "最多演员", defaultOrder: 14},
    {key: "releaseDateFrom", label: "发行开始", defaultOrder: 15},
    {key: "releaseDateTo", label: "发行结束", defaultOrder: 16},
    {key: "createdAtFrom", label: "入库开始", defaultOrder: 17},
    {key: "createdAtTo", label: "入库结束", defaultOrder: 18},
    {key: "sortBy", label: "排序", defaultOrder: 19},
];

// Date picker keys that are rendered as paired groups
const DATE_PICKER_KEYS: MovieFilterField[] = ["releaseDateFrom", "releaseDateTo", "createdAtFrom", "createdAtTo"];

export interface MovieFilterBarProps {
    filters: Omit<MovieFilters, "requestParams">;
    sort: {
        sortBy: string;
        sortOrder: number;
        onChange: (field: string, order: number) => void;
    };
    filterConfig: MovieFilterConfig;
    onSearch: () => void;
    onReset: () => void;
    onConfigClick?: () => void;
}

export default function MovieFilterBar({filters, sort, filterConfig, onSearch, onReset, onConfigClick}: MovieFilterBarProps) {
    const {
        form, patchForm,
        taskOptions, actorOptions, tagOptions, directorOptions, makerOptions, seriesOptions,
        filtersLoading,
    } = filters;

    const {search, selectedTask, selectedActors, selectedActorsNot, selectedTags, selectedTagsNot,
        selectedDirectors, selectedDirectorsNot, selectedMakers, selectedMakersNot,
        selectedSeries, selectedSeriesNot, storageStatus,
        ratingMin, ratingMax, actorsCountMin, actorsCountMax,
        releaseDateFrom, releaseDateTo, createdAtFrom, createdAtTo,
    } = form;

    const {sortBy, sortOrder, onChange: onSortChange} = sort;

    const tagSelectProps = {loading: filtersLoading, maxTagCount: "responsive" as const, allowClear: true, mode: "tags" as const, style: {width: 200}};

    // Build render map for all filter controls
    const filterRenderers: Record<string, React.ReactNode> = {
        actors: <Select {...tagSelectProps} placeholder="筛选演员" value={selectedActors} onChange={(v) => patchForm({selectedActors: v})} options={actorOptions} />,
        actorsNot: <Select {...tagSelectProps} placeholder="排除演员" value={selectedActorsNot} onChange={(v) => patchForm({selectedActorsNot: v})} options={actorOptions} />,
        tags: <Select {...tagSelectProps} placeholder="筛选标签" value={selectedTags} onChange={(v) => patchForm({selectedTags: v})} options={tagOptions} />,
        tagsNot: <Select {...tagSelectProps} placeholder="排除标签" value={selectedTagsNot} onChange={(v) => patchForm({selectedTagsNot: v})} options={tagOptions} />,
        director: <Select {...tagSelectProps} placeholder="筛选导演" value={selectedDirectors} onChange={(v) => patchForm({selectedDirectors: v})} options={directorOptions} />,
        directorNot: <Select {...tagSelectProps} placeholder="排除导演" value={selectedDirectorsNot} onChange={(v) => patchForm({selectedDirectorsNot: v})} options={directorOptions} />,
        maker: <Select {...tagSelectProps} placeholder="筛选片商" value={selectedMakers} onChange={(v) => patchForm({selectedMakers: v})} options={makerOptions} />,
        makerNot: <Select {...tagSelectProps} placeholder="排除片商" value={selectedMakersNot} onChange={(v) => patchForm({selectedMakersNot: v})} options={makerOptions} />,
        series: <Select {...tagSelectProps} placeholder="筛选系列" value={selectedSeries} onChange={(v) => patchForm({selectedSeries: v})} options={seriesOptions} />,
        seriesNot: <Select {...tagSelectProps} placeholder="排除系列" value={selectedSeriesNot} onChange={(v) => patchForm({selectedSeriesNot: v})} options={seriesOptions} />,
        storageStatus: <Select style={{width: 160}} value={storageStatus} onChange={(v) => patchForm({storageStatus: v})} placeholder="存储状态筛选" allowClear options={[
            {value: "not_stored", label: "未存储"},
            {value: "storing", label: "入库中"},
            {value: "stored", label: "已存储"},
        ]} />,
        ratingMin: <InputNumber style={{width: 120}} placeholder="最低评分" min={0} max={5} step={0.1} value={ratingMin} onChange={(v) => patchForm({ratingMin: v ?? undefined})} />,
        ratingMax: <InputNumber style={{width: 120}} placeholder="最高评分" min={0} max={5} step={0.1} value={ratingMax} onChange={(v) => patchForm({ratingMax: v ?? undefined})} />,
        actorsCountMin: <InputNumber style={{width: 120}} placeholder="最少演员" min={0} value={actorsCountMin} onChange={(v) => patchForm({actorsCountMin: v ?? undefined})} />,
        actorsCountMax: <InputNumber style={{width: 120}} placeholder="最多演员" min={0} value={actorsCountMax} onChange={(v) => patchForm({actorsCountMax: v ?? undefined})} />,
        releaseDateFrom: <DatePicker placeholder="发行开始" value={releaseDateFrom} onChange={(v) => patchForm({releaseDateFrom: v})} style={{width: 130}} />,
        releaseDateTo: <DatePicker placeholder="发行结束" value={releaseDateTo} onChange={(v) => patchForm({releaseDateTo: v})} style={{width: 130}} />,
        createdAtFrom: <DatePicker placeholder="入库开始" value={createdAtFrom} onChange={(v) => patchForm({createdAtFrom: v})} style={{width: 130}} />,
        createdAtTo: <DatePicker placeholder="入库结束" value={createdAtTo} onChange={(v) => patchForm({createdAtTo: v})} style={{width: 130}} />,
        sortBy: <Select style={{width: 140}} value={`${sortBy}:${sortOrder}`} onChange={(v) => { const [by, order] = v.split(":"); onSortChange(by, Number(order)); }} options={[
            {value: "code:1", label: "番号 ↑"}, {value: "code:-1", label: "番号 ↓"},
            {value: "release_date:-1", label: "发行日期 ↓"}, {value: "release_date:1", label: "发行日期 ↑"},
            {value: "rating:-1", label: "评分 ↓"}, {value: "rating:1", label: "评分 ↑"},
            {value: "created_at:-1", label: "抓取时间 ↓"}, {value: "created_at:1", label: "抓取时间 ↑"},
        ]} />,
    };

    // Sort by config order, filter by visibility
    const sortedItems = [...FILTER_ITEMS]
        .sort((a, b) => {
            const orderA = filterConfig?.[a.key]?.order ?? a.defaultOrder;
            const orderB = filterConfig?.[b.key]?.order ?? b.defaultOrder;
            return orderA - orderB;
        })
        .filter((item) => filterConfig?.[item.key]?.visible !== false);

    // Check date picker pair visibility for grouped rendering
    const releaseDateVisible = filterConfig?.["releaseDateFrom"]?.visible !== false || filterConfig?.["releaseDateTo"]?.visible !== false;
    const createdAtVisible = filterConfig?.["createdAtFrom"]?.visible !== false || filterConfig?.["createdAtTo"]?.visible !== false;

    return (
        <Space vertical style={{width: "100%"}} size={8}>
            <Space wrap>
                <Select
                    style={{width: 200}}
                    value={selectedTask}
                    onChange={(v) => patchForm({selectedTask: v})}
                    options={taskOptions}
                    placeholder="选择任务"
                    allowClear
                />
                <Input
                    style={{width: 240}}
                    placeholder="搜索番号、标题..."
                    prefix={<SearchOutlined/>}
                    value={search}
                    onChange={(e) => patchForm({search: e.target.value})}
                    onPressEnter={onSearch}
                    allowClear
                />
                {sortedItems
                    .filter((item) => !DATE_PICKER_KEYS.includes(item.key))
                    .map((item) => <React.Fragment key={item.key}>{filterRenderers[item.key]}</React.Fragment>)}
                {releaseDateVisible && <Space size={4}>
                    {filterConfig?.["releaseDateFrom"]?.visible !== false && filterRenderers["releaseDateFrom"]}
                    {filterConfig?.["releaseDateTo"]?.visible !== false && filterRenderers["releaseDateTo"]}
                </Space>}
                {createdAtVisible && <Space size={4}>
                    {filterConfig?.["createdAtFrom"]?.visible !== false && filterRenderers["createdAtFrom"]}
                    {filterConfig?.["createdAtTo"]?.visible !== false && filterRenderers["createdAtTo"]}
                </Space>}
                <Button type="primary" onClick={onSearch}>搜索</Button>
                <Button icon={<ReloadOutlined/>} onClick={onReset}>刷新</Button>
                {onConfigClick && <Button icon={<SettingOutlined/>} onClick={onConfigClick}>配置</Button>}
            </Space>
        </Space>
    );
}
