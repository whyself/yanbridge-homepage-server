# Homepage Crawler

定时爬取导师个人主页和课题组首页。本目录已迁移为 `homepage_server` 的 crawler 子模块，正式运行从 PostgreSQL `homepage_sources` 读取 URL，并把 raw text / markdown 写入 PostgreSQL `homepage_raw_page`。

请优先使用 `homepage_server/scripts/run_once.sh` 触发，不再使用本地 SQLite 作为正式 raw 存储。

目前爬虫部分未被风控过，并发数为 2，并发数提高，可以考虑打乱 url，降低风控概率。

## Scope

- 输入：PostgreSQL `homepage_sources` 中 `active` / `failed` 的导师/课题组 URL。
- 输出：PostgreSQL `homepage_raw_page`。
- 存储：按 `source_id` 覆盖保存当前 raw 快照，微小 diff 标记为 `low_diff`，不进入 pipeline。
- 内容：只保留 `page_title`、`markdown`、`text`、抓取状态和来源字段。

## URL List Notes

URL list 目前通过 agent skills 查找和清洗。

skill 目前已更新到 v2 剩余价值不多了。

URL list 目前包含：南京大学、浙江大学、上海交通大学、复旦大学、中国科学技术大学

现阶段已重构 skill，从 crawl4ai 优先过渡到强制 web open/web fetch 工具优先，通过分派子 agent 阅读主页详情页查找可能的主页链接，并添加最后的 clean 阶段，删去低质量页面，和寻找课题组的招生页面。

提示词：

使用 skill，目标大学：xx大学，允许使用 subagent，subagent 用完及时关，请遵循 skill 流程，记得全量展开详情页做最终决定，不要依赖脚本进行最终筛选，web fetch/web open 不了的降级用 crawl4ai，再抓取失败的用浏览器工具做最终确认，先写 todo，按 skill 格式输出 md 文件

请照 skill 流程核对有没有缺漏的，做完

- 学校官网可能有风控。（已解决，强制优先 web open/web fetch 工具 不被风控）
- 可能存在空白、失效、无关、重复个人主页。（已用 agent 串行 crawl4ai 作了质量筛选）
- codex 的 webopen 无法查看 https://mypage.zju.edu.cn/kaibu 这类的动态内容，因此在最后添加了 crawl4ai 对全体只有一个链接的导师进行 crawl4ai 的复抓，串行进行似乎就不会被封控
- 完整度仍需检验。
- 本地 agent 中转查找约需 30-60 分钟/学校，需要少量的人工推进介入。
- 目前使用的是 codex 接 gpt 中转，成本在 15r/学校 以内，目前在尝试迁移到 cc + ds
- 后续需要人工补漏机制。

原始 Markdown 清单和设计说明可在本模块 `docs/` 或同级 URL 清单文件中查看。

## Setup

Python 依赖包括 `crawl4ai` 和 `psycopg2-binary`。

```bash
cd crawler/homepage
uv sync
uv run crawl4ai-setup
```

如果 crawl4ai/Playwright 环境要求单独安装浏览器：

```bash
uv run playwright install chromium
```

## Run

推荐从 `homepage_server` 根目录运行：

```bash
scripts/run_once.sh --crawl-limit 20 --no-pipeline
```

如果只调 crawler 子模块，需要先确保 `homepage_sources` 已导入，并设置 `DATABASE_URL`：

```bash
uv run python -m homepage_crawler.main --limit 20
```

只跑前几条做 smoke test：

```bash
uv run python -m homepage_crawler.main --limit 1
```

常用参数：

```bash
uv run python -m homepage_crawler.main --concurrency 2 --timeout-ms 60000
```

## URL Import Format

URL 配置按学校拆分放在 `config/` 下。JSONL 只用于导入 `homepage_sources`，正式爬取不直接读取 JSONL。

```text
config/
  fdu.jsonl
  nju.jsonl
  sjtu.jsonl
  ustc.jsonl
  zju.jsonl
```

JSONL 一行一个 URL：

```json
{"id":"nju_faculty_bo_wenyang_001","batch":"nju_202605","university":"南京大学","source_type":"faculty","name":"柏文阳","url":"https://cs.nju.edu.cn/c9/4d/c2640a51533/page.htm","status":"active"}
```

字段说明：

- `id`: 稳定来源 ID，导入后作为 `homepage_sources.source_id`。
- `batch`: URL 批次。
- `university`: 学校名。
- `source_type`: `faculty` 或 `lab`。
- `name`: 导师、课题组或实验室名称。
- `url`: 待爬取主页。
- `status`: 导入后的初始状态，`active` / `failed` 会被爬取。

## Output

raw 输出在 PostgreSQL `homepage_raw_page`，失败 URL 日志仍写在 `output/logs/`。

如果本次运行有失败 URL，会额外写入：

```text
output/logs/failed_urls_<run_id>.jsonl
```

## Cron

```cron
0 0 * * * cd /path/to/homepage_server && scripts/daily_run.sh
```
