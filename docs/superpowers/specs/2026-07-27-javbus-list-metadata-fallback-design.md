# JavBus 列表元数据提取与详情兜底设计

## 背景

当前 JavBus 列表解析只从 `div.item a.movie-box` 返回详情 URL、标题和番号。真实列表页还提供缩略图和发布日期，但列表任务会先持久化为 `CrawlRunDetailTask`，再从数据库恢复并执行详情抓取，因此仅在内存任务字典中增加字段会在详情阶段丢失。

本次改动扩展既有 JavBus 爬虫，不改变 JavDB 行为、详情抓取流程、磁力解析或最终影片数据模型。

## 目标

- 从 JavBus 列表影片元素提取详情 URL、番号、标题、缩略图 URL 和发布日期。
- 将标题、缩略图 URL 和发布日期作为独立列表元数据持久化。
- 详情页成功解析后，仅用列表元数据填补详情结果的空字段。
- 保持详情页非空数据为权威数据源。

## 非目标

- 不提取列表 `.item-tag` 中的“高清”“字幕”或时效标签。
- 不使用列表元数据将失败的详情任务伪装为成功。
- 不修改磁力请求、磁力解析、影片数据库模型或前端 API。
- 不改变 JavBus 当前按番号去重和分页的行为。

## 真实列表 DOM

影片节点使用以下结构：

```html
<div class="item masonry-brick">
  <a class="movie-box" href="https://www.javbus.com/TIKB-224">
    <div class="photo-frame">
      <img
        src="/pics/thumb/cedm.jpg"
        title="巨乳変態言いなりメイドがドMご奉仕でお漏らしイキ！ 羽月乃蒼"
      >
    </div>
    <div class="photo-info">
      <span>
        巨乳変態言いなりメイドがドMご奉仕でお漏らしイキ！ 羽月乃蒼
        <div class="item-tag">...</div>
        <date>TIKB-224</date> / <date>2026-07-18</date>
      </span>
    </div>
  </a>
</div>
```

页面中还存在演员头像 `div.item`，但它不包含 `a.movie-box`，因此现有影片节点选择器会自然排除该节点。

部分详情链接带日期后缀，例如：

```text
https://www.javbus.com/IENF-451_2026-07-08
```

此时第一个 `<date>` 的 `IENF-451` 是列表展示的准确番号，URL 解析只作为缺失时的兜底。

## 列表解析

`scraper/spiders/javbus/javbus_parser.py` 中的 `parse_list_page()` 对每个 `div.item a.movie-box` 返回：

| 字段 | 来源 | 规则 |
| --- | --- | --- |
| `url` | `a.movie-box[href]` | 使用当前列表页 URL 转为绝对地址 |
| `code` | 第一个 `<date>` | 清理文本后使用；缺失时才从详情 URL 提取 |
| `title` | `img[title]` | 清理文本，缺失时为空字符串 |
| `cover_url` | `img[src]` | 清理文本并使用当前列表页 URL 转为绝对地址 |
| `release_date` | 第二个 `<date>` | 仅清理文本，不猜测或转换格式 |

解析器不读取 `.item-tag`。任一可选字段缺失时仍保留该列表项。

## 列表任务数据结构

`JavbusSpider.collect_detail_tasks_for_url()` 继续使用现有顶层任务字段：

```python
{
    "url": "https://www.javbus.com/TIKB-224",
    "name": "影片标题",
    "code": "TIKB-224",
}
```

新增私有列表元数据：

```python
{
    "_list_item_data": {
        "title": "影片标题",
        "cover_url": "https://www.javbus.com/pics/thumb/cedm.jpg",
        "release_date": "2026-07-18",
    },
}
```

`_list_item_data` 只包含已确认的三个可选字段，不复制番号或详情 URL，也不包含列表标签。

## 持久化边界

`CrawlRunDetailTask` 新增可空的 `list_item_data` JSON 字段，并通过 Alembic 迁移加入数据库。

两条列表任务持久化路径必须保持一致：

- 线程式运行通过 `backend/app/modules/crawler/runtime/detail_queue.py` 写入 `list_item_data`。
- 回调式运行通过 `backend/app/modules/crawler/runtime/callbacks.py` 写入或更新 `list_item_data`。

`backend/app/modules/crawler/runtime/details.py` 的 `detail_row_to_task_info()` 将数据库值恢复为 `_list_item_data`，供详情爬虫使用。

现有 `item_data` 继续只表示详情抓取并经过 pipeline 清理后的最终结果，不承载列表阶段元数据。

## 详情兜底

JavBus 详情页和 Ajax 磁力均成功解析后，`JavbusSpider.run_single_detail_task()` 对详情结果应用列表兜底：

| 详情字段 | 列表兜底字段 | 兜底条件 |
| --- | --- | --- |
| `title` | `title` | 详情值为空 |
| `source_name` | `title` | 详情值为空 |
| `cover_url` | `cover_url` | 详情值为空 |
| `release_date` | `release_date` | 详情值为空 |

详情页的非空值始终优先。兜底不覆盖番号，番号继续由现有详情解析和 URL 回退逻辑负责。

如果详情请求、详情解析、Ajax 参数提取、Ajax 请求或磁力解析失败，任务保持现有失败状态；列表元数据不能将失败任务转为成功。

## 数据流

```text
JavBus 列表 DOM
  -> parse_list_page()
  -> JavbusSpider 列表任务 + _list_item_data
  -> CrawlRunDetailTask.list_item_data
  -> detail_row_to_task_info()
  -> JavbusSpider 详情抓取
  -> 仅为空字段应用列表兜底
  -> MoviePipeline
  -> 现有影片与磁力持久化
```

## 测试策略

### 列表解析

使用附件裁剪出的真实 `movie-box` fixture，验证：

- 第一个 `<date>` 解析为番号。
- 第二个 `<date>` 解析为发布日期。
- 相对缩略图 URL 转为绝对 URL。
- 图片 `title` 解析为标题。
- `.item-tag` 文本未进入返回结果。
- 演员头像 `div.item` 未被识别为影片。
- 带日期后缀的详情 URL 仍使用第一个 `<date>` 作为番号。
- 缺少标题、图片或发布日期时仍返回列表项。

### Spider 数据传递

验证 JavBus 列表任务包含 `_list_item_data`，且不包含列表标签。

### 持久化往返

分别验证线程式和回调式任务创建路径：

- `_list_item_data` 写入 `CrawlRunDetailTask.list_item_data`。
- 从数据库恢复的详情任务包含相同 `_list_item_data`。
- 更新或重试任务时列表元数据不丢失。
- 最终 `item_data` 的语义和生命周期保持不变。

### 详情优先级

验证：

- 详情标题、封面或发布日期为空时使用列表值。
- 详情字段非空时不被列表值覆盖。
- 列表标题可分别填补 `title` 和 `source_name`。
- 详情流程失败时仍返回失败，不应用成功兜底。

### 回归验证

运行 JavBus parser/spider、crawler runtime、detail queue、callback 和 Alembic 相关测试，并确认 JavDB 列表解析和详情持久化行为未改变。

## 验收标准

- 真实 JavBus 列表项能够提取标题、绝对缩略图 URL、番号和发布日期。
- 列表标签不会被提取或持久化。
- 列表元数据经过数据库任务队列后仍可用于详情处理。
- 详情非空字段不会被列表数据覆盖。
- 详情空字段能够使用列表数据补齐并进入现有 pipeline。
- 详情失败状态不会因列表元数据而改变。
- 两种运行路径行为一致，JavDB 行为无回归。
