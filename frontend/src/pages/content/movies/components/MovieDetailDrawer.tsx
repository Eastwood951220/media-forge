import {Descriptions, Drawer, Image, Space, Tag, Typography} from "antd";
import type {MovieMagnet} from "@/api/movie/types";

export interface MovieDetailDrawerProps {
    open: boolean;
    detail: Record<string, unknown> | null;
    onClose: () => void;
    onFilterClick?: (field: string, value: string) => void;
}

function getDetailMagnets(value: unknown): MovieMagnet[] {
    if (!Array.isArray(value)) return [];
    return value.filter((item): item is MovieMagnet => typeof item === "object" && item !== null);
}

export function getMagnetSizeText(magnet: MovieMagnet): string {
    if (magnet.size_text) return magnet.size_text;
    if (typeof magnet.size === "string" && magnet.size.trim()) return magnet.size;
    const sizeMb = typeof magnet.size_mb === "number" ? magnet.size_mb : magnet.size;
    return typeof sizeMb === "number" ? `${(sizeMb / 1024).toFixed(1)} GB` : "";
}

function getDetailSizeText(size: unknown, magnets: MovieMagnet[]): string {
    if (typeof size === "number") return `${(size / 1024).toFixed(1)} GB`;
    if (typeof size === "string" && size.trim()) return size;
    const firstMagnetSize = magnets.length > 0 ? getMagnetSizeText(magnets[0]) : "";
    return firstMagnetSize || "-";
}

function getMagnetDisplayText(magnet: MovieMagnet): string {
    const metadata = [magnet.name || magnet.title, getMagnetSizeText(magnet), magnet.file_text]
        .filter(Boolean)
        .join(" · ");
    return metadata ? `${metadata}\n${magnet.magnet}` : (magnet.magnet ?? "");
}

function FilterValue({value, field, onClick}: {value: string; field: string; onClick?: (field: string, value: string) => void}) {
    if (!value || value === "-") return <>{value || "-"}</>;
    if (onClick) {
        return <Typography.Link onClick={() => onClick(field, value)}>{value}</Typography.Link>;
    }
    return <>{value}</>;
}

export default function MovieDetailDrawer({open, detail, onClose, onFilterClick}: MovieDetailDrawerProps) {
    const detailMagnets = getDetailMagnets(detail?.magnets);
    const detailMagnetLinks = detailMagnets.filter((m) => typeof m.magnet === "string" && m.magnet.trim());
    const detailHasChineseSub = Boolean(detail?.has_chinese_sub) || detailMagnets.some((m) => Boolean(m.has_chinese_sub));
    const detailSizeText = getDetailSizeText(detail?.size, detailMagnets);

    return (
        <Drawer
            title="影片详情"
            open={open}
            onClose={onClose}
            width={600}
        >
            {detail && (
                <Descriptions column={1} bordered size="small">
                    <Descriptions.Item label="番号">{detail.code as string}</Descriptions.Item>
                    <Descriptions.Item
                        label="标题">{(detail.source_name as string) || "-"}</Descriptions.Item>
                    <Descriptions.Item label="发行日期">{detail.release_date as string}</Descriptions.Item>
                    <Descriptions.Item
                        label="时长">{detail.duration != null ? `${detail.duration}分` : "-"}</Descriptions.Item>
                    <Descriptions.Item
                        label="评分">{detail.rating != null ? (detail.rating as number).toFixed(2) : "-"}</Descriptions.Item>
                    <Descriptions.Item label="导演">
                        <FilterValue value={detail.director as string || ""} field="director" onClick={onFilterClick} />
                    </Descriptions.Item>
                    <Descriptions.Item label="制作商">
                        <FilterValue value={detail.maker as string || ""} field="maker" onClick={onFilterClick} />
                    </Descriptions.Item>
                    <Descriptions.Item label="系列">
                        <FilterValue value={detail.series as string || ""} field="series" onClick={onFilterClick} />
                    </Descriptions.Item>
                    <Descriptions.Item label="演员">
                        {Array.isArray(detail.actors) && detail.actors.length > 0
                            ? (detail.actors as string[]).map((a) => (
                                <Tag key={a} style={{cursor: onFilterClick ? "pointer" : undefined}} onClick={() => onFilterClick?.("actors", a)}>
                                    {a}
                                </Tag>
                            ))
                            : "-"}
                    </Descriptions.Item>
                    <Descriptions.Item label="标签">
                        {Array.isArray(detail.tags) && detail.tags.length > 0
                            ? (detail.tags as string[]).map((t) => (
                                <Tag key={t} style={{cursor: onFilterClick ? "pointer" : undefined}} onClick={() => onFilterClick?.("tags", t)}>
                                    {t}
                                </Tag>
                            ))
                            : "-"}
                    </Descriptions.Item>
                    <Descriptions.Item label="中文字幕">{detailHasChineseSub ? "是" : "否"}</Descriptions.Item>
                    <Descriptions.Item label="大小">{detailSizeText}</Descriptions.Item>
                    <Descriptions.Item label="封面">
                        {detail.cover as string ? (
                            <Image src={detail.cover as string} width={200} referrerPolicy="no-referrer"/>
                        ) : "-"}
                    </Descriptions.Item>
                    <Descriptions.Item label="最佳磁力">
                        {(() => {
                            const selectedKey = detail.selected_magnet_dedupe_key as string | undefined;
                            if (!selectedKey) return <Typography.Text type="secondary">未选择</Typography.Text>;
                            const selectedMagnet = detailMagnets.find((m) => m.dedupe_key === selectedKey);
                            if (!selectedMagnet) return <Typography.Text type="secondary">未找到</Typography.Text>;
                            const m = selectedMagnet;
                            const displayName = m.name || m.title || "-";
                            const displaySize = getMagnetSizeText(m);
                            const displaySub = m.has_chinese_sub ? "是" : "否";
                            const displayWeight = m.weight != null ? ` · 权重: ${m.weight}` : "";
                            return (
                                <Space direction="vertical" size={2}>
                                    <Typography.Text strong>{displayName}</Typography.Text>
                                    <Typography.Text type="secondary">
                                        {displaySize ? `大小: ${displaySize}` : ""}
                                        {m.file_text ? ` · ${m.file_text}` : ""}
                                        {` · 中字: ${displaySub}`}
                                        {displayWeight}
                                    </Typography.Text>
                                    {m.magnet && (
                                        <Typography.Paragraph
                                            copyable={{text: m.magnet}}
                                            style={{marginBottom: 0, fontSize: 12, wordBreak: "break-all"}}
                                        >
                                            {m.magnet}
                                        </Typography.Paragraph>
                                    )}
                                </Space>
                            );
                        })()}
                    </Descriptions.Item>
                    <Descriptions.Item label="磁力链接">
                        {detailMagnetLinks.length > 0 ? (
                            <Space direction="vertical" size={4} style={{width: "100%"}}>
                                {detailMagnetLinks.map((magnet, index) => (
                                    <Typography.Paragraph
                                        key={`${magnet.magnet}-${index}`}
                                        copyable={{text: magnet.magnet}}
                                        style={{marginBottom: 0, whiteSpace: "pre-wrap", wordBreak: "break-all"}}
                                    >
                                        {getMagnetDisplayText(magnet)}
                                    </Typography.Paragraph>
                                ))}
                            </Space>
                        ) : detail.magnet as string ? (
                            <Typography.Paragraph copyable style={{marginBottom: 0, wordBreak: "break-all"}}>
                                {detail.magnet as string}
                            </Typography.Paragraph>
                        ) : "-"}
                    </Descriptions.Item>
                    <Descriptions.Item label="来源URL">
                        <Typography.Link href={detail.source_url as string} target="_blank">
                            {detail.source_url as string}
                        </Typography.Link>
                    </Descriptions.Item>
                    {(() => {
                        const storageSummary = detail.storage_summary as Record<string, unknown> | undefined;
                        const locations = storageSummary?.locations as
                            | {path: string; target_folder: string; exists?: boolean}[]
                            | undefined;
                        if (!locations || locations.length === 0) return null;
                        return (
                            <Descriptions.Item label="存储位置">
                                <Space direction="vertical" size={4} style={{width: "100%"}}>
                                    {locations.map((loc, index) => (
                                        <div
                                            key={`${loc.path}-${index}`}
                                            style={{display: "flex", alignItems: "center", gap: 8}}
                                        >
                                            <Tag color={loc.exists ? "success" : "error"}>
                                                {loc.exists ? "存在" : "缺失"}
                                            </Tag>
                                            <Typography.Text
                                                copyable={{text: loc.path}}
                                                style={{fontSize: 12, wordBreak: "break-all"}}
                                            >
                                                {loc.path}
                                            </Typography.Text>
                                            <Typography.Text type="secondary" style={{fontSize: 12}}>
                                                ({loc.target_folder})
                                            </Typography.Text>
                                        </div>
                                    ))}
                                </Space>
                            </Descriptions.Item>
                        );
                    })()}
                    {(() => {
                        const storageSummary = detail.storage_summary as Record<string, unknown> | undefined;
                        const syncedAt = storageSummary?.synced_at as string | undefined;
                        if (!syncedAt) return null;
                        return <Descriptions.Item label="最后同步时间">{syncedAt}</Descriptions.Item>;
                    })()}
                </Descriptions>
            )}
        </Drawer>
    );
}
