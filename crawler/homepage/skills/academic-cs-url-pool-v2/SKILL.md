---
name: academic-cs-url-pool-v2
description: Use this whenever building, auditing, expanding, repairing, or crawler-cleaning a broad computer-science URL pool for a university, especially when the final pool will feed a crawler to extract 招生信息/admissions information. Covers CS/AI/software/data/systems/security/HCI/robotics/NLP/theory faculty homepages, advisor pages, personal sites, research groups, labs, teams, centers, member directories, 招生信息 sources, 导师个人页, 教师主页, 课题组首页, and 实验室首页. Prefer this skill even when the user asks briefly, such as "collect CS faculty URLs for X university", "make a lab homepage pool", or "clean URLs for admissions crawling".
---

# Academic CS URL Pool V2

Build auditable broad-CS URL pools, then produce crawler-ready clean URL lists for downstream 招生信息/admissions extraction.

## Read Only What This Task Needs

Do not load every bundled reference by default. Pick the route first, then read only the listed files.

- Build a new pool, expand a pool, or repair missing roots/details -> read `workflows/build-pool.md`, then `checklists/detail-review.md` before claiming detail-review closure.
- Clean existing pool for admissions crawler -> read `workflows/crawl4ai-clean.md`, `checklists/crawl4ai-clean.md`, and `templates/crawl-state.md`.
- Audit an existing pool or clean output -> read `workflows/audit-existing.md`, then the relevant checklist: `checklists/detail-review.md`, `checklists/crawl4ai-clean.md`, or `checklists/final-report.md`.
- Final response after any route -> read `checklists/final-report.md`.
- Dispatch subagents -> read only the needed section of `references/subagent-prompts.md`.
- Unclear mixed task -> read `workflows/audit-existing.md` first, write the todo, then load the smallest workflow that matches the discovered gap.

Compatibility note: `references/workflow.md` and `references/checklist.md` are short indexes. Use them only if an older prompt explicitly asks for those paths.

## First Action: Write Todo

Before searching, opening pages, or creating output files, write a visible todo list for the run. Use the native plan/todo tool when available; otherwise write a short Markdown todo in the root ledger or in your response. Keep it updated as phases finish.

Check: can the user see the current phase, next phase, and remaining closure gates before any collection work starts? If not, write or update the todo first.

## Common Tasks

- Build new university pool -> read `workflows/build-pool.md`; after pool closure, read `workflows/crawl4ai-clean.md` if the user needs clean files in the same run.
- Expand or repair an existing pool -> read `workflows/audit-existing.md`, then `workflows/build-pool.md` starting at the earliest incomplete phase.
- Clean existing pool for admissions crawler -> read `workflows/crawl4ai-clean.md`; run serial Crawl4AI clean phases for labs and faculty.
- Audit completion quality -> read `workflows/audit-existing.md`; verify detail-read closure, reverse search, crawler-clean outputs, and pending ledger with targeted checklists.
- Dispatch subagents -> read `references/subagent-prompts.md`; use the exact batch templates.
- Other / unclear task -> write todo; read `workflows/audit-existing.md`; proceed with the closest matching route.

## Core Principles

### Closure Over Collection

Treat URL pooling as a graph-closure task, not a search-results dump. Search finds candidates; opened/read page content decides inclusion.

Check: did every final URL come from a page that was opened/fetched, classified, and checked for further useful links?

### Pool Files, Clean Crawler Files, Messy Ledger

Keep pool files and crawler-clean files as names plus URLs only. Put search coverage, failures, fallbacks, Crawl4AI decisions, removed empty pages, and reasoning in `root_urls.md` or a review ledger.

Check: could a downstream script parse the clean files without seeing notes, statuses, or prose?

Pool and clean files must use this plain block format:

```md
张三
https://example.edu/zhangsan
https://lab.example.edu/zhangsan

李四
https://cs.example.edu/faculty/lisi
```

Rules: name on its own line; one or more raw HTTP/HTTPS URLs below it; blank line between entries; no bullets, numbering, tables, Markdown links, inline notes, statuses, or evidence.

### Native Read First

Use agent-native web search for discovery and native `web open` / `web fetch` first for candidate verification. Use Crawl4AI serially in the crawler-clean phase because the downstream target is crawler extraction. Shell, curl, browser, and rendered fallbacks remain main-agent diagnostics only.

Check: is every fallback use recorded with tool, reason, and evidence?

### Subagents Verify, Main Agent Judges

Use subagents for large concrete URL batches and reverse-search batches. Subagents use only native web search/open/fetch and return structured findings; they do not edit files or make final merge decisions.

Check: did the main agent review failures, abnormal pages, ambiguous identities, redirects, and cross-institution cases before merging?

### Broad CS Means Broad

Cover CS plus related AI, software, data, systems, security, graphics, HCI, robotics, NLP, theory, information science, EE/control intersections, and university-specific institutes or centers.

Check: does the root file show both Chinese and English keyword coverage instead of only the main CS school?

## Red Flags -- STOP

- You are about to search or edit files before writing the todo.
- You are adding a search result to a clean pool without opening/reading it.
- You are calling a JS shell, blank page, or placeholder `low_value` without a render check or pending note.
- You are treating reverse search as optional sampling.
- You are producing crawler-clean files without serial Crawl4AI reads.
- You are parallelizing Crawl4AI fetching or asking subagents to crawl pages instead of only reading already-crawled full results.
- You are using a script to produce candidate links, keyword-hit reports, page summaries, classifications, keep/remove decisions, or a draft clean list for the Crawl4AI clean phase. Scripts may save complete raw packets and do post-decision formatting only.
- You are giving subagents filtered snippets or candidate-only Crawl4AI results instead of complete raw packet text or packet file paths.
- You are keeping a faculty URL whose crawled content has no usable personal introduction/profile signal.
- You are formatting faculty/lab/clean files with bullets, nested lists, tables, Markdown links, notes, or statuses.
- You are about to say "complete" without reading the route-specific checklist plus `checklists/final-report.md`.

## Output Names

Create:

- `<university_full_name>_faculty_urls.md`
- `<university_full_name>_lab_urls.md`
- `<university_full_name>_clean_faculty_urls.md`
- `<university_full_name>_clean_lab_urls.md`
- `<university_full_name>_root_urls.md`

Use the university's English full name, lowercase with underscores. Do not use abbreviations like `zju`, `nju`, or `sjtu`.
