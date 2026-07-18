# Homepage Server

## 当前去重逻辑

当前最小迁移版是“一个 URL 来源一个帖子”，不是“一个老师/课题组天然合并一个帖子”。

- `homepage_sources.source_id` 是 crawler、raw、pipeline 的稳定来源 ID。
- `homepage_raw_page` 按 `source_id` 覆盖保存当前 raw 快照。
- pipeline 写 `posts` 时使用 `posts.dedupe_key=website:{source_id}`。
- 如果同一个导师/课题组有多个 URL，也就是多条不同 `source_id`，当前会分别爬取、分别进入 raw，并且可能分别生成帖子。
- `homepage_sources.is_primary` 目前只作为数据字段保留，暂时没有参与 crawler/pipeline 的 URL 选择。

后续如果要改成“一个老师/课题组只保留一个帖子”，需要把帖子去重键从 `source_id` 改为 `entity_key`，并增加多 URL 选择规则，例如优先 `is_primary=true`，其次按 `url_type` 优先级选择，主 URL 失败时再 fallback 到同一 `entity_key` 下其他 active URL。

`homepage_server` 是研途星桥导师/课题组主页爬虫的独立运行目录，部署方式参考小红书 `xhsserver`：

- 不常驻服务。
- 通过 `docker compose run --rm ...` 手动触发。
- 通过宿主机 `crontab` 定时触发。
- 连接主站 PostgreSQL，将抓取成功的当前 raw 快照写入 `homepage_raw_page`，再由 pipeline 写入 `posts`。

## 目录结构

```text
homepage_server/
  docker-compose.yml
  .env.example
  scripts/
    run_once.sh
    daily_run.sh
  crawler/
    homepage/
      homepage_crawler/
      config/
      Dockerfile
    pipline/
      Dockerfile
```

## 新表结构：homepage_sources

`homepage_sources` 是干净的爬虫数据源表。它只维护“哪些导师/课题组主页 URL 要爬”，不保存网页正文。

网页正文、Markdown、diff、hash 等当前原始抓取结果全部保存在 PostgreSQL `homepage_raw_page`。正式运行不再使用本地 SQLite/DB 文件。

```sql
CREATE TABLE IF NOT EXISTS homepage_sources (
    id bigserial PRIMARY KEY,

    -- 稳定来源
    source_id varchar(160) NOT NULL UNIQUE,
    batch varchar(64) NOT NULL,

    -- 学校
    university_code varchar(32) NOT NULL,
    university_name varchar(128) NOT NULL,

    -- 被爬取对象：导师 or 课题组
    entity_type varchar(32) NOT NULL,
    -- faculty | research_group

    entity_name varchar(160) NOT NULL,
    -- 导师姓名 / 课题组名 / 实验室名

    entity_key varchar(255) NOT NULL,
    -- 例：
    -- thu:faculty:李国良
    -- thu:research_group:数据库课题组

    -- URL
    url text NOT NULL,
    url_type varchar(32) NOT NULL DEFAULT 'unknown',
    -- official_profile | personal_homepage | lab_homepage | unknown

    is_primary boolean NOT NULL DEFAULT false,

    -- 爬虫状态
    status varchar(32) NOT NULL DEFAULT 'active',
    -- active | paused | failed | removed

    http_status integer NULL,
    content_hash varchar(128) NULL,
    last_crawled_at timestamptz NULL,
    last_success_at timestamptz NULL,
    failure_count integer NOT NULL DEFAULT 0,

    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,

    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_homepage_sources_university
ON homepage_sources (university_code, university_name);

CREATE INDEX IF NOT EXISTS ix_homepage_sources_entity
ON homepage_sources (university_code, entity_type, entity_key);

CREATE INDEX IF NOT EXISTS ix_homepage_sources_status
ON homepage_sources (status);

CREATE UNIQUE INDEX IF NOT EXISTS ux_homepage_sources_entity_url
ON homepage_sources (entity_key, url);
```

## 数据流

```text
config/*.jsonl
  -> import_sources
  -> homepage_sources
  -> homepage crawler
  -> homepage_raw_page
  -> pipeline
  -> posts
```

说明：

- JSONL 只作为导入/初始化来源，用来把 URL 写进 `homepage_sources`。
- 正式爬取直接从 PostgreSQL `homepage_sources` 读取 `active` / `failed` URL。
- `paused` / `removed` 不会被爬取。
- `homepage_sources` 不保存 `text` / `markdown`。
- `homepage_raw_page` 保存 raw text / markdown / content_hash，用于 diff 和 pipeline。
- crawler 会按 `source_id` 覆盖写入当前 raw 快照，`homepage_raw_page` 不保存历史多版本。
- `update_status=new|changed|low_diff|unchanged|failed` 记录本次 diff 判断。
- `pipeline_pending` 单独表示当前 raw 是否待 pipeline 处理。crawler 只有在 `update_status=new|changed` 时置为 `true`；`low_diff` / `unchanged` 不会新建 pipeline 任务，但也不会覆盖掉之前尚未处理的 pending 状态。
- pipeline 只处理 `status=success` 且 `pipeline_pending=true` 的当前 raw 快照，并用 `website:{source_id}:{content_hash}` 做内容级去重。
- pipeline 写入 `posts` 或 `discarded_post` 后，会把对应 raw 的 `pipeline_pending` 置回 `false`。
- pipeline 写 `posts` 时仍保持一个主页源一个展示帖子：`posts.dedupe_key=website:{source_id}`，页面内容变化后会 upsert 更新这条帖子。
- pipeline 的 resume/去重按当前内容键 `website:{source_id}:{content_hash}` 判断，避免页面内容变化后被旧帖子跳过。
- pipeline 仍然按当前 LLM 逻辑：`action=keep` 写入 `posts`，`irrelevant` 写入 `discarded_post`。

## 环境变量

复制 `.env.example`：

```bash
cp .env.example .env
```

如果和主站 compose 共用 `yanbridge_default` 网络，`DATABASE_URL` 可使用：

```text
DATABASE_URL=postgresql://yanbridge:yanbridge@db:5432/yanbridge?sslmode=disable
```

pipeline 需要：

```text
DEEPSEEK_API_KEY=...
```

## 构建镜像

```bash
docker compose --profile run-only build
```

## 第一次导入 JSONL 到 PostgreSQL

```bash
scripts/run_once.sh --import-only
```

这一步会读取 `crawler/homepage/config/*.jsonl`，写入 `homepage_sources`。
导入时会按 `(entity_key, url)` 去重；如果 JSONL 里同一个导师/课题组同一个 URL 出现多次，只保留一条来源记录，优先保留 `is_primary=true` 的记录。

之后日常运行默认不会再导入 JSONL。如果 URL 清单有更新，需要手动重新同步：

```bash
scripts/run_once.sh --import
```

## 手动触发

默认流程：直接从 PostgreSQL `homepage_sources` 爬取 active/failed URL、运行 pipeline。

```bash
scripts/run_once.sh
```

限制爬取数量：

```bash
scripts/run_once.sh --crawl-limit 50
```

限制 pipeline 数量：

```bash
scripts/run_once.sh --pipeline-limit 20
```

只爬取，不跑 pipeline：

```bash
scripts/run_once.sh --no-pipeline --crawl-limit 50
```

导入 JSONL 后继续爬取：

```bash
scripts/run_once.sh --import --crawl-limit 50
```

调整 diff 阈值：

```bash
scripts/run_once.sh --update-diff-chars 10
```

## 定时触发

宿主机 crontab：

```cron
0 0 * * * cd /home/yanbridge/homepage_server && scripts/daily_run.sh
```

`daily_run.sh` 默认执行：

```bash
scripts/run_once.sh
```

也就是说，定时任务不会重复导入 JSONL，只会直接从 PostgreSQL `homepage_sources` 读取 `active` / `failed` URL。

## 常用调试命令

查看导入后的 URL 数量：

```bash
docker compose run --rm homepage-crawler \
  uv run python - <<'PY'
from homepage_crawler.source_store import load_active_url_items_from_pg
print(len(load_active_url_items_from_pg()))
PY
```

只预热数据源表：

```bash
docker compose run --rm homepage-crawler \
  uv run python -m homepage_crawler.import_sources
```

直接跑 crawler：

```bash
docker compose run --rm homepage-crawler \
  uv run python -m homepage_crawler.main \
    --limit 10 \
    --update-diff-chars 10
```

直接跑 pipeline：

```bash
docker compose run --rm pipeline \
  uv run python -m crawler.pipline.cli run --source homepage --limit 10
```

直接跑学术关系构建器：

```bash
docker compose run --rm pipeline \
  uv run python -m crawler.pipline.cli academic --limit 20 --dry-run
```

这个命令从 `homepage_raw_page` 读取成功抓取的 raw 页面，用 Pydantic AI 做单页结构化抽取，再用确定性规则写入 `academic_institutions`、`academic_people`、`academic_affiliations`、`post_entity_links` 和 `posts`。当前实现不让 Agent 自由搜索或调用工具，也不使用 confidence 阈值做取舍；confidence 只作为观测字段保存。写库前建议先用 `--dry-run --jsonl-output /tmp/academic.jsonl` 看每条 raw 的解析结果。

模型抽取可以并发，写库仍由主进程逐条执行：

```bash
PYTHONPATH=../.. uv run python -m crawler.pipline.cli academic \
  --limit 100 \
  --model deepseek-v4-flash \
  --workers 20 \
  --jsonl-output /tmp/academic_limit100.jsonl
```

`--workers` 上限为 2500；实际跑 deepseek 时建议先用 20-100。机构写入前会按同一大学/父机构下的确定性 identity 做去重：会统一 `lab` / `research_group` 中明显由名称表达的类型，并用中文名、英文名、括号缩写、去括号名做精确匹配，避免 `软件工程组(SEG)` 和 `软件工程组 / Software Engineering Group (SEG)` 被拆成两条。

本机直接跑时，如果 `.env` 里的 `DATABASE_URL` 使用 compose 网络主机名 `db:5432`，需要临时替换成宿主机暴露端口：

```bash
cd crawler/pipline
set -a; source ../../.env; set +a
export DATABASE_URL="${DATABASE_URL/@db:5432\//@127.0.0.1:6542/}"
PYTHONPATH=../.. uv run python -m crawler.pipline.cli academic \
  --include-processed \
  --dry-run \
  --jsonl-output /tmp/academic.jsonl
```

确认结果后去掉 `--dry-run` 即可写入目标表：

```bash
PYTHONPATH=../.. uv run python -m crawler.pipline.cli academic --limit 20
```
