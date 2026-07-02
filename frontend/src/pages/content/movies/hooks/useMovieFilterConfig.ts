import {useCallback, useEffect, useState} from "react";
import {App} from "antd";
import {fetchMovieFilterConfig, updateMovieFilterConfig} from "@/api/movie";
import type {MovieFilterConfig, MovieFilterField} from "@/api/movie/types";

export function useMovieFilterConfig() {
    const {message} = App.useApp();
    const [config, setConfig] = useState<MovieFilterConfig>({});
    const [drawerOpen, setDrawerOpen] = useState(false);

    useEffect(() => {
        fetchMovieFilterConfig()
            .then((result) => setConfig(result.filters))
            .catch(() => message.error("加载筛选配置失败"));
    }, []);

    const toggle = useCallback(async (key: MovieFilterField, visible: boolean) => {
        const previous = config;
        const updated: MovieFilterConfig = {
            ...config,
            [key]: {...(config[key] ?? {}), visible},
        };
        setConfig(updated);
        try {
            await updateMovieFilterConfig(updated);
        } catch {
            setConfig(previous);
            message.error("保存筛选配置失败");
        }
    }, [config]);

    return {config, drawerOpen, setDrawerOpen, toggle, setConfig};
}

export type MovieFilterConfigState = ReturnType<typeof useMovieFilterConfig>;
