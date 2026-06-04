# Workflow Index

This compatibility file replaces the old all-in-one workflow. Do not use it as the main workflow body. Select the smallest task-specific workflow instead.

## Route

- Build, expand, or repair broad CS pool files: read `../workflows/build-pool.md`.
- Clean existing pool files for an admissions crawler: read `../workflows/crawl4ai-clean.md`.
- Audit existing pool or clean output and decide the next phase: read `../workflows/audit-existing.md`.

## Output Files

- `<university_full_name>_faculty_urls.md`
- `<university_full_name>_lab_urls.md`
- `<university_full_name>_clean_faculty_urls.md`
- `<university_full_name>_clean_lab_urls.md`
- `<university_full_name>_root_urls.md`

Use the university's English full name, lowercase with underscores. Keep pool and clean files in the same simple Markdown format: name line plus raw HTTP/HTTPS URL lines, blank line between entries. Do not use bullets, nested lists, tables, Markdown links, notes, statuses, or evidence in these files. Put notes, failures, Crawl4AI decisions, and pending items in the root/ledger file.

## Non-Negotiable Rules

- Write a visible todo before collection, crawling, or file edits.
- Decide from full page content, not search snippets, URL paths, anchor text, regex hits, script summaries, or generated classifications.
- In discovery/detail review, use native web open/fetch reading unless fallback is needed and recorded.
- In crawler-clean phases, use Crawl4AI serially and read complete raw packets.
- Do not use scripts to filter candidate links, summarize pages, classify pages, or draft clean URL lists before agent judgment.
- Subagents may read already-crawled complete packet text or packet file paths; they must not crawl or decide from snippets.
- For lab clean, keep lab/PI-specific prospective master/PhD joining/contact pages. Reject generic admissions/training/news/resource pages unless the target page itself invites prospective master/PhD students to contact or join the lab/PI.
- For faculty clean, crawl every URL for every teacher, remove pages with no usable personal/profile/advisor signal, keep admissions-relevant URLs when present, otherwise keep all usable profile URLs.
