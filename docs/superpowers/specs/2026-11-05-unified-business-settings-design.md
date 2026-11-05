# 业务配置统一数据库存储设计（已确认）

## 目标

数据库和 Redis 连接信息保留本地启动配置。其他现有服务端业务配置统一进入 PostgreSQL 的配置表，通过后端接口读取和修改，保留当前页面、字段校验和业务行为。

## 当前范围

- crawler：爬虫参数和抓取模式，来自 crawler.conf。
- storage：CloudDrive2 地址、API Token、等待时间和扩展名规则，来自 storage.conf。
- scraping：刮削、MetaTube 和 Jellyfin 参数，来自 scraping.conf。
- backup：自动备份计划和目录，来自 backup.conf。
- movie_filters：电影列表查询区域配置，来自 movie_filter_config.json，包括查询项显示/隐藏（visible）、排列顺序（order）和默认值（defaultValue），完整迁移现有 filters 结构。
- crawler_cookies：当前 Cookie 配置，来自 JavDB Cookie JSON 文件；列表以一个 JSON 值保存。

数据库和 Redis 本地连接配置、实际媒体/索引/日志/备份文件不进入配置表。Chrome 扩展连接后端所需的 URL 和本地 Token 仍由浏览器保存，因为扩展连接服务器之前就需要它们。Agent 身份和 Token 哈希沿用现有 agent 表，不复制进通用配置表。

## 方案比较

1. 按配置项一行，namespace + key 唯一，JSONB value：适合当前混合的标量、数组和 JSON 配置，可逐项更新，避免整组配置写入覆盖其他字段。推荐。
2. 每模块一行 JSONB：行数更少，但同一模块的不同设置并发保存时需要额外处理整组覆盖，不作为首选。

## 表与服务

新增 application_settings 表：id、namespace、key、value(JSONB)、is_secret、created_at、updated_at；建立 (namespace, key) 唯一约束。配置分组和可用字段由代码注册，沿用现有 Pydantic 类型、默认值与校验规则，不允许接口任意写入未注册字段。

统一 repository/service 负责读写、事务和默认值合并。前端通过接口读取；后端任务、调度器和爬虫运行参数通过公共服务读库，不在后端内部调用自己的 HTTP 接口。不引入跨进程永久缓存，避免任务读取旧配置。

现有模块配置接口暂时保留，内部切换公共服务，避免破坏页面和扩展协议。统一增加按 namespace 获取/更新的接口；新旧接口必须复用同一校验和序列化流程，不能出现两套行为。

## 密钥查看

普通查询返回脱敏值和 configured 标志；点击眼睛通过已登录接口按需读取已保存原值，响应 no-store。沿用刚实现的查看与编辑分离行为，避免查看操作改变保存内容。不新增复制按钮。无法恢复仅保存哈希的历史 Agent Token。

## 迁移与兼容

Alembic 只创建表，不在结构迁移时依赖部署机器上的配置路径。现有健康数据库启动不保证自动执行 Alembic，实施时必须补齐旧库升级入口，并把新模型加入首次初始化注册；确认新表存在后才执行导入。应用连接数据库并完成结构升级后、业务 worker/调度器启动前，在事务中导入现有文件里尚未迁移的配置；数据库记录优先，重复启动不覆盖已保存的数据库值。

导入失败必须明确失败原因，不允许静默丢弃原配置或长期双写。原文件保留作为迁移前备份；迁移后业务写入只更新数据库，运行时也读取数据库。数据库离线时返回明确错误，不回退到旧文件造成状态分叉。

备份当前是分组 ZIP，不是整库备份。新格式覆盖全部业务配置 namespace，旧格式 ZIP 也要能恢复到新表。include_sensitive=false 时排除所有密钥和 cookies，恢复省略的敏感项时保留现有值。数据库/Redis 启动配置不纳入业务配置备份。测试可注入存储实现，现有显式临时文件测试迁移为导入器和服务测试。

## 验证

覆盖旧文件导入、重复导入不覆盖、默认值/类型校验、局部更新保留其他字段、鉴权、脱敏及原值查看，以及爬虫/存储/刮削/Jellyfin/备份的运行读取路径。检查备份恢复和多进程读配置；执行相关后端测试、前端测试及构建。

## 实施顺序

先交付通用表、服务和导入器，再逐模块替换文件读写，最后验证后台任务、统一接口及备份恢复。每个功能组独立提交，不创建 worktree，不处理已有无关 artwork 修改。

运行入口核对：覆盖 crawler/agent/cookie_sync.py 的写入和 scraper/cookies/cookie_manager.py 的读取；移除 shared/runtime_config.py 对旧 storage.conf 的启动注入，防止数据库与旧环境值分叉。
