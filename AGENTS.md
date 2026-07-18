# AGENTS.md

## Scope

This file describes the homepage crawler project under `yanbridge-homepage-server`.
Use it when working on the crawler, homepage pipeline, academic graph builder, or the related `/schools` data surface in the parent YanBridge repo.

## Project Purpose

`yanbridge-homepage-server` collects faculty and lab/research-group homepages, stores raw crawled pages in PostgreSQL, and can transform those pages into:

- `posts`
- `academic_institutions`
- `academic_people`
- `academic_affiliations`
- `post_entity_links`
- `agent_runs`

The project is not a long-running service. It is run manually through scripts or Docker Compose, and can be scheduled by host `crontab`.

## Directory Map

```text
yanbridge-homepage-server/
  README.md
  AGENTS.md
  .env.example
  docker-compose.yml
  scripts/
    run_once.sh
    daily_run.sh
  crawler/
    homepage/
      homepage_crawler/
        main.py
        import_sources.py
        source_store.py
        raw_store.py
      config/*.jsonl
      README.md
    pipline/
      cli.py
      parser.py
      reader.py
      writer.py
      academic_agent.py
      academic_runner.py
      academic_resolver.py
      academic_schemas.py
      academic_tools.py
```

The spelling `pipline` is intentional in this repo. Do not rename it casually.

## Core Data Flow

```text
crawler/homepage/config/*.jsonl
  -> homepage_crawler.import_sources
  -> homepage_sources
  -> homepage_crawler.main
  -> homepage_raw_page
  -> crawler.pipline.cli run --source homepage
  -> posts / discarded_post

homepage_raw_page
  -> crawler.pipline.cli academic
  -> academic_institutions / academic_people / academic_affiliations
  -> post_entity_links / posts / agent_runs
```

`homepage_sources` stores only source URL metadata. It does not store page text.

`homepage_raw_page` stores the current raw snapshot per `source_id`. It is overwritten by `source_id`; it is not a historical version table.

`pipeline_pending` on `homepage_raw_page` means the raw page should still be processed by the normal homepage pipeline. The crawler sets it only for `update_status=new|changed`; `low_diff` and `unchanged` do not create new pipeline work.

## Environment

Copy `.env.example` to `.env` for local or Docker use.

In Docker Compose / shared network:

```text
DATABASE_URL=postgresql://yanbridge:yanbridge@db:5432/yanbridge?sslmode=disable
```

For direct local host execution, replace `db:5432` with the exposed local database port:

```bash
cd crawler/pipline
set -a; source ../../.env; set +a
export DATABASE_URL="${DATABASE_URL/@db:5432\//@127.0.0.1:6542/}"
```

DeepSeek calls require:

```text
DEEPSEEK_API_KEY=...
```

Do not print secrets from `.env`. If inspecting `.env`, redact keys.

## Common Commands

Build images:

```bash
docker compose --profile run-only build
```

Import JSONL source lists into `homepage_sources`:

```bash
scripts/run_once.sh --import-only
```

Run crawler and normal pipeline:

```bash
scripts/run_once.sh
```

Run crawler only:

```bash
scripts/run_once.sh --no-pipeline --crawl-limit 50
```

Run normal homepage post pipeline only:

```bash
docker compose run --rm pipeline \
  uv run python -m crawler.pipline.cli run --source homepage --limit 10
```

Run academic graph builder dry-run:

```bash
docker compose run --rm pipeline \
  uv run python -m crawler.pipline.cli academic --limit 20 --dry-run
```

Run academic graph builder locally:

```bash
cd crawler/pipline
set -a; source ../../.env; set +a
export DATABASE_URL="${DATABASE_URL/@db:5432\//@127.0.0.1:6542/}"
PYTHONPATH=../.. uv run python -m crawler.pipline.cli academic \
  --limit 100 \
  --model deepseek-v4-flash \
  --workers 20 \
  --jsonl-output /tmp/academic_limit100.jsonl
```

For full academic runs, use concurrency below 100 unless explicitly asked otherwise:

```bash
PYTHONPATH=../.. uv run python -m crawler.pipline.cli academic \
  --model deepseek-v4-flash \
  --workers 50 \
  --jsonl-output /tmp/academic_full.jsonl
```

`--workers` has a hard CLI cap of 2500, but practical DeepSeek/API runs should normally be 20-100.

## Academic Builder Design

The academic builder is intentionally simple:

- Uses Pydantic AI for a single structured extraction call.
- Does not use free-form agent tools.
- Does not search the web during extraction.
- Does not use CRW for the academic builder.
- Uses only `homepage_raw_page` content, raw hints, and URL.
- Writes through deterministic resolver code, not model-side database tools.
- Does not use confidence thresholds for accept/reject decisions. Confidence is logged only.

Important files:

- `academic_agent.py`: Pydantic AI extractor prompt and model call.
- `academic_schemas.py`: structured output schema and raw row normalization.
- `academic_resolver.py`: deterministic conversion from extraction to database rows.
- `academic_tools.py`: PostgreSQL schema, upserts, post links, token usage logging, duplicate institution merge.
- `academic_runner.py`: CLI runner, model concurrency, sequential write path, JSONL output.
- `cli.py`: top-level `academic` subcommand.

## Academic Builder Output

The model can output:

- `matches_hint`
- `page_type`
- `institutions`
- `person`
- `affiliations`
- `recruitment`

`recruitment.post_markdown` is the user-facing Markdown post body. Do not generate recruitment posts from resolver templates. If a post is created, use the agent's `post_title` and `post_markdown`.

Posts are created only when:

- `recruitment.has_recruitment` is true
- `evidence_text` is present
- `post_title` is present
- `post_markdown` is present
- the subject person exists

Current implementation creates mentor recruitment posts for people, not standalone lab recruitment posts.

## Institution Identity And Deduplication

Do not use similarity thresholds for institution deduplication.

The current strategy is deterministic:

- Normalize institution type.
- Treat `lab` and `research_group` as one type family for duplicate detection.
- Use exact normalized identities derived from:
  - Chinese name
  - English name
  - aliases
  - parenthetical abbreviations
  - slash-separated aliases, such as `软件工程组/SEG`
  - stripped-parenthesis names
- Before inserting a child institution, search active same-university/same-parent candidates in the same type family.
- If identity sets intersect exactly, reuse the existing row.
- After a batch, call `merge_duplicate_institutions()` to merge exact same-university/same-type-family/same-normalized-name duplicates.

This specifically prevents cases like:

```text
lab: 软件工程组(SEG) / Software Engineering Group (SEG)
research_group: 软件工程组 / Software Engineering Group (SEG)
```

from surviving as two active entities.

If duplicates remain after exact identity rules, prefer improving deterministic canonicalization before introducing model review loops.

## Relationship Rules

For faculty pages:

- The page must match `hint_name`; otherwise `matches_hint=false` and resolver skips it.
- If the model only links the person to the university but extracted non-university institutions exist, resolver adds fallback child affiliations to those specific institutions.
- If no explicit affiliations exist, resolver falls back to the best non-university institution, then university.

For lab pages:

- The page must match `hint_name` as a lab/group/team/center page.
- Lab pages create institution rows but normally do not create people unless extracted from faculty pages.
- Lab recruitment detection may be present in extraction, but current resolver only creates posts for person subjects.

## Database Tables

Crawler/source tables:

- `homepage_sources`
- `homepage_raw_page`

Normal post pipeline tables:

- `posts`
- `discarded_post`

Academic graph tables:

- `academic_institutions`
- `academic_people`
- `academic_affiliations`
- `post_entity_links`
- `agent_runs`

`agent_runs.usage` stores token usage JSON. Always preserve this when replaying or rerunning academic extraction.

## Current Full Academic Run State

As of the latest completed run in this workspace:

- `homepage_raw_page` successful rows: 2897
- `agent_runs` for `academic_builder`: 2897
- succeeded: 2763
- skipped: 134
- failed: 0
- active academic institutions: 1117
- merged academic institutions: 7
- academic people: 1985
- academic affiliations: 5064
- generated homepage academic posts: 552
- token usage logged:
  - requests: 3180
  - input_tokens: 9515853
  - output_tokens: 3706559
  - cache_read_tokens: 4957056

The run used `deepseek-v4-flash`. Failed rows from the initial full pass were rerun by `--source-id --include-processed`; all failures were resolved.

Useful logs from that run:

```text
/tmp/academic_full_20260608.log
/tmp/academic_full_20260608.jsonl
/tmp/academic_failed_retry_20260608.log
/tmp/academic_failed_retry_20260608.jsonl
```

## `/schools` Integration

The parent YanBridge backend/frontend use the academic graph to render `/schools`.

Relevant files in the parent repo:

```text
../server/app/services/school_service.py
../server/app/schemas/school.py
../server/app/database.py
../web/src/lib/api.ts
../web/src/pages/SchoolIntelligence.tsx
```

The `/schools` service reads active academic institutions, people, affiliations, and post links. It no longer depends on `school_faculty_sources` for the new display.

## Validation Commands

From `yanbridge-homepage-server/crawler/pipline`:

```bash
PYTHONPATH=../.. uv run python -m compileall \
  academic_agent.py academic_runner.py academic_schemas.py \
  academic_tools.py academic_resolver.py cli.py
```

From parent `server/`:

```bash
uv run python -m pytest
```

From parent `web/`:

```bash
npm run build
```

Check conflict markers:

```bash
rg -n '^<<<<<<<|^=======$|^>>>>>>>' server web yanbridge-homepage-server
```

## Operational Notes

- Do not clear `academic_*`, `post_entity_links`, generated posts, or `agent_runs` unless the user explicitly asks.
- If clearing academic generated data, remove generated post links/posts and `agent_runs`, then truncate `academic_affiliations`, `academic_people`, and `academic_institutions`.
- Raw remote data has previously been synced from SSH target `yanbridge`; verify current external state before doing that again.
- The local database container is typically `yanbridge-db-1` with Postgres exposed on `127.0.0.1:6542`.
- The remote `yanbridge` host also has a `yanbridge-db-1` container exposed at `127.0.0.1:6542` on that host.
- The worktree may be dirty. Do not revert unrelated user changes.
- Use `rg`/`rg --files` for searches.
- Use `apply_patch` for manual edits.
