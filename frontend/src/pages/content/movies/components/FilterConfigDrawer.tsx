import {useState, useCallback, useEffect} from "react";
import {App, Drawer, List, Switch, Button, Space, Typography, Input, InputNumber, Select} from "antd";
import type {FilterItemConfig} from "@/api/movie";
import {updateMovieFilterConfig} from "@/api/movie";
import {MOVIE_FILTER_CONFIG_ITEMS as filterConfigItems} from "../constants";

interface FilterConfigDrawerProps {
    open: boolean;
    onClose: () => void;
    config: Record<string, FilterItemConfig>;
    onSave: (config: Record<string, FilterItemConfig>) => void;
}

function DefaultValueInput({filterKey, value, onChange}: {filterKey: string; value: unknown; onChange: (val: unknown) => void}) {
    if (["actors", "tags", "director", "maker", "series"].includes(filterKey)) {
        return <Input size="small" style={{width: 120}} placeholder="默认值(逗号分隔)" value={(value as string) ?? ""} onChange={(e) => onChange(e.target.value || undefined)} />;
    }
    if (["ratingMin", "ratingMax", "actorsCountMin", "actorsCountMax"].includes(filterKey)) {
        const isRating = filterKey.startsWith("rating");
        return <InputNumber size="small" style={{width: 100}} placeholder="默认值" min={0} max={isRating ? 5 : undefined} step={isRating ? 0.1 : 1} value={value as number} onChange={(v) => onChange(v ?? undefined)} />;
    }
    if (filterKey === "storageStatus") {
        return <Select size="small" style={{width: 100}} placeholder="默认值" allowClear value={value as string} onChange={(v) => onChange(v)} options={[
            {value: "completed", label: "已完成"}, {value: "missing", label: "缺失"}, {value: "failed", label: "失败"}, {value: "pending", label: "等待"}, {value: "running", label: "运行"}, {value: "retryable", label: "可重试"},
        ]} />;
    }
    if (filterKey === "sortBy") {
        return <Select size="small" style={{width: 120}} placeholder="默认排序" allowClear value={value as string} onChange={(v) => onChange(v)} options={[
            {value: "code:1", label: "番号 ↑"}, {value: "code:-1", label: "番号 ↓"},
            {value: "release_date:-1", label: "发行日期 ↓"}, {value: "rating:-1", label: "评分 ↓"},
            {value: "created_at:-1", label: "抓取时间 ↓"}, {value: "created_at:1", label: "抓取时间 ↑"},
        ]} />;
    }
    return null;
}

export default function FilterConfigDrawer({open, onClose, config, onSave}: FilterConfigDrawerProps) {
    const {message} = App.useApp();
    const [editingConfig, setEditingConfig] = useState<Record<string, FilterItemConfig>>({});

    useEffect(() => {
        if (open) {
            setEditingConfig({...config});
        }
    }, [open, config]);

    const updateEditingConfig = useCallback((key: string, partial: Partial<FilterItemConfig>) => {
        setEditingConfig((prev) => ({
            ...prev,
            [key]: {...(prev[key] ?? {visible: true, order: 0}), ...partial},
        }));
    }, []);

    const moveFilterItem = useCallback((key: string, direction: -1 | 1) => {
        setEditingConfig((prev) => {
            const currentOrder = prev[key]?.order ?? filterConfigItems.find((i) => i.key === key)?.defaultOrder ?? 0;
            const newOrder = currentOrder + direction;
            const updated = {...prev};
            updated[key] = {...(updated[key] ?? {visible: true, order: currentOrder}), order: newOrder};
            for (const [k, v] of Object.entries(updated)) {
                if (k !== key && (v.order === newOrder || (v.order === undefined && filterConfigItems.find((i) => i.key === k)?.defaultOrder === newOrder))) {
                    updated[k] = {...v, order: currentOrder};
                    break;
                }
            }
            return updated;
        });
    }, []);

    const handleSave = useCallback(() => {
        onSave(editingConfig);
        updateMovieFilterConfig(editingConfig).catch(() => message.error("保存失败"));
        onClose();
    }, [editingConfig, onSave, onClose]);

    return (
        <Drawer
            title="筛选条件配置"
            open={open}
            onClose={onClose}
            width={400}
            footer={
                <Button type="primary" block onClick={handleSave}>
                    保存配置
                </Button>
            }
        >
            <List
                dataSource={filterConfigItems.map((item) => ({
                    ...item,
                    config: editingConfig[item.key] ?? {visible: true, order: item.defaultOrder},
                }))}
                renderItem={({key, label, config: itemConfig}) => (
                    <List.Item>
                        <div style={{display: "flex", alignItems: "center", gap: 8, width: "100%"}}>
                            <Space size={0}>
                                <Button size="small" type="text" onClick={() => moveFilterItem(key, -1)}>↑</Button>
                                <Button size="small" type="text" onClick={() => moveFilterItem(key, 1)}>↓</Button>
                            </Space>
                            <Typography.Text style={{minWidth: 80}}>{label}</Typography.Text>
                            <Switch
                                size="small"
                                checked={itemConfig.visible}
                                onChange={(checked) => updateEditingConfig(key, {visible: checked})}
                            />
                            <DefaultValueInput
                                filterKey={key}
                                value={itemConfig.defaultValue}
                                onChange={(val) => updateEditingConfig(key, {defaultValue: val})}
                            />
                        </div>
                    </List.Item>
                )}
            />
        </Drawer>
    );
}
