import {useCallback, useState} from "react";
import {App} from "antd";
import {fetchMovie} from "@/api/movie";

function getErrorMessage(error: unknown): string {
    return error instanceof Error ? error.message : "请求失败";
}

export function useMovieDetail() {
    const {message} = App.useApp();
    const [open, setOpen] = useState(false);
    const [detail, setDetail] = useState<Record<string, unknown> | null>(null);

    const showDetail = useCallback(async (id: string) => {
        try {
            const movie = await fetchMovie(id);
            setDetail(movie as unknown as Record<string, unknown>);
            setOpen(true);
        } catch (e: unknown) {
            message.error(getErrorMessage(e));
        }
    }, []);

    const closeDetail = useCallback(() => {
        setOpen(false);
    }, []);

    return {open, detail, setDetail, showDetail, closeDetail};
}

export type MovieDetail = ReturnType<typeof useMovieDetail>;
