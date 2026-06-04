# Subagent Prompts

Use these templates exactly enough to preserve tool restrictions and return shape. Replace bracketed placeholders.

## Detail-Read Batch

```text
Task: Verify and expand a batch of broad CS faculty/lab candidate URLs for [university].

Use only agent-native web open/web fetch tools for every detail URL. Either is acceptable if it exposes enough page content for full-page analysis. Do not use Crawl4AI, curl, shell commands, custom scripts, or browser automation. If native web tools cannot read the page adequately, mark the URL as failed or pending review and explain why.

Read the full visible content for each URL in this batch:
[50-80 URLs, or fewer if the remaining batch is smaller]

For each URL, report:
- status: success | failed | abnormal | low_value | pending_render_check
- page type: faculty_profile | personal_homepage | lab_group_homepage | directory | member_page | admissions_lead | project_page | unrelated | unclear
- normalized name if identifiable
- whether the full page was read with native web tools, or why native web reading was inadequate
- whether the native read looked like a placeholder/JS shell needing main-agent rendered fallback
- useful or maybe useful links discovered by analyzing the full page content
- whether every useful or maybe useful discovered link was opened/fetched, fully read, and recursively analyzed for more useful links
- one-sentence evidence for useful faculty/lab URLs

Do not edit files. Return:
1. New faculty/advisor URLs: name -> URL(s) -> evidence.
2. New lab/group/team URLs: name -> URL(s) -> evidence.
3. URLs checked with status and page type.
4. Failures, redirects, abnormal pages, shell/placeholder reads, and native web tool reading limits.
5. Newly discovered useful/maybe useful links, including proof that each was opened/fetched and fully analyzed.
6. Items that need main-agent review.
```

## Reverse-Search Batch

```text
Task: Reverse-search final output names for [university] broad CS URL pool.

Use only agent-native web search and native web open/web fetch reading tools. Prefer web open / web fetch for every candidate page read. Do not use Crawl4AI, curl, shell commands, custom scripts, or browser automation.

Existing Markdown files:
- Faculty URL file: [path/to/faculty_urls.md]
- Lab URL file: [path/to/lab_urls.md]

Treat URLs already present in these files as existing pool entries. If a reverse-search result URL is already present, do not open/read it again; report it as already_present. Only open/read new URLs or same-name different URLs that may contain non-empty useful content.

Names in this batch:
[faculty/advisor names or lab/group/team/center names]

For each name:
- run at least one targeted reverse search using visible variants where available: Chinese name, English name, romanization, acronym, email id, slug, GitHub handle, known domain, or project/org name;
- open/fetch and fully read promising results with native web tools before recommending them;
- skip search-result URLs already present in the provided Markdown files;
- verify page type before recommending a new URL: faculty_profile | personal_homepage | lab_group_homepage | admissions_lead | member_page | directory | low_value | unrelated | unclear;
- recommend faculty_profile and personal_homepage URLs for the faculty pool;
- recommend lab_group_homepage URLs for the lab pool;
- return admissions_lead, member_page, directory, and unclear pages as leads for main-agent review unless the page clearly functions as a final homepage;
- only keep pages that have non-empty relevant content;
- look for richer personal homepages, lab/group/team pages, member pages, and admissions information;
- report reverse_searched, reverse_added, reverse_pending, or already_present; use reverse_added only after full detail-page reading.

Return:
1. Name -> reverse-search status.
2. New faculty-pool URLs -> page type -> evidence that the page was opened/read and non-empty.
3. New lab-pool URLs -> page type -> evidence that the page was opened/read and non-empty.
4. Leads that should not be directly added yet -> page type -> reason.
5. Already-present URLs skipped.
6. Failed or pending searches/pages -> reason.
7. Items that need main-agent review.
```

## Crawl4AI Result Reading Batch

Use this only after the main agent has already run Crawl4AI serially and saved full results. This batch is for reading and judgment, not crawling.

Prefer giving saved raw-packet file paths instead of pasting large packet text when the subagent can read local files. Each path must contain one complete Crawl4AI result, including title, full markdown/text, visible navigation or rendered text when available, and extracted links with surrounding context. Do not pass script-created candidate-only files.

```text
Task: Read and judge already-crawled Crawl4AI outputs for [university] crawler-clean URL selection.

You must not fetch pages, run Crawl4AI, use web open/web fetch, use curl, use browser automation, or run scripts. The main agent has already crawled pages serially to reduce anti-crawling risk. Your job is to read the complete Crawl4AI raw packets provided below, either as full pasted text or as local file paths, and judge them from content.

Read every provided full Crawl4AI result. Do not decide from URL, title, anchor text, extracted-link list, script summary, pre-label, filtered candidate list, or keyword hits alone. Use the page title, main markdown/text, visible navigation, link context, and extracted links together.

If packet paths are provided, open/read each complete file before judging. Reject the batch and ask the main agent for complete raw packets if the input contains only summaries, candidate links, keyword-hit snippets, preclassified rows, filtered excerpts, or files that were produced by script filtering rather than complete Crawl4AI saves.

For lab pages, keep a URL only if the target page itself is useful for prospective master/PhD students who want to contact or join the lab/group/PI. Strong signals include 欢迎有意向的硕士生/博士生联系, 招收硕士/博士/研究生, 招募学生, 加入我们, Join Us, prospective students, openings for students, PhD/master positions, or lab-specific applicant contact instructions.

Reject generic school/department admissions columns, 招生就业, 人才培养, 研究生培养, 硕士生/博士生 training pages, thesis-defense news, awards, seminars, generic activities, PDFs, ZIP files, manuals, datasets, tools, and project downloads unless the target page itself explicitly invites prospective master/PhD students to contact or join the lab.

For faculty pages, classify each page as:
- admissions_relevant: teacher-specific admissions/recruitment signal.
- profile_without_admissions: usable personal introduction/profile/advisor content but no admissions signal.
- remove: no usable personal profile/advisor signal.

If you see a plausible new link that may need another full page read, do not fetch it. Return it as needs_main_agent_crawl with the surrounding evidence from the current page.

Provided Crawl4AI result batch:
[either paste complete saved Crawl4AI result texts here, or list complete raw-packet file paths here]

Return:
1. Source URL -> accepted clean URL(s) or rejected -> reason from page content.
2. For each accepted URL, evidence quote/summary from the crawled page content.
3. Rejected generic admissions/training/news/resource links -> reason.
4. New links that need main-agent serial Crawl4AI read: URL -> why it may matter -> source page evidence.
5. Ambiguous cases needing main-agent review.
```
