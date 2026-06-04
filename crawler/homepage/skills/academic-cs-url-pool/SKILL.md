---
name: academic-cs-url-pool
description: Use when building a clean URL pool for a university's broad CS faculty homepages, personal websites, research groups, labs, teams, centers, advisor pages, 招生信息 source pools, 导师个人页, 教师主页, 课题组首页, or 实验室首页.
---

# Academic CS URL Pool

## Goal

Build clean Markdown URL pools for a target university's broad CS ecosystem:

- `<university_full_name>_faculty_urls.md`: faculty/advisor name + official profile or personal homepage URL.
- `<university_full_name>_lab_urls.md`: research group/lab/team/center name + homepage URL.
- `<university_full_name>_root_urls.md`: broad root/entry URL inventory, search coverage, expansion status, and pending review notes.

Use the university's English full name for `<university_full_name>`, normalized to lowercase words joined by underscores. Do not use abbreviations such as `zju`, `nju`, or `sjtu`. Examples: `zhejiang_university`, `nanjing_university`, `shanghai_jiao_tong_university`.

The first two files should stay clean: name plus URL only. Keep process notes, search coverage, failures, and root expansion status in the root file or a separate review ledger.

## Tool Priority

Use heuristic web search and page reading as the default method.

1. Use agent-native `web open` / `web fetch` first for every page read. Use `web search` only to discover candidate URLs.
2. If native `web open` / `web fetch` returns only an empty page, placeholder shell, JS app shell, generic template text, or otherwise inadequate content, do not classify it as low-value yet.
3. For inadequate native reads, try a rendered-page fallback or Crawl4AI. Use `curl` only after those fail.

Record fallback use and failure reasons. Do not use scripts or crawlers as the main discovery path. Scripts may help deduplicate, count, or normalize candidates, but final inclusion must come from page content read by the agent or subagent.

Subagent tool restriction: subagents must use only agent-native web tools such as `web open`/`web fetch` for detail-page reading. Subagents must not use Crawl4AI, `curl`, shell commands, custom scripts, or browser automation. If native web tools cannot read a URL adequately, the subagent reports the URL as failed or pending review; the main agent decides whether to retry with Crawl4AI, `curl`, or browser automation strictly for abnormal-page diagnosis.

Fallback rule: subagents may only use native `web open`/`web fetch` for page reading. If native web tools fail or expose only a shell, only the main agent may try rendered-page fallback, Crawl4AI, `curl`, or browser automation. The main agent may judge from fallback-read content, but must record the tool used, why fallback was needed, and the evidence.

## Core Principle

Search heuristically, read pages, and expand outward until the URL graph stops yielding new useful faculty or lab homepage candidates.

Broad CS must include related departments, programs, institutes, and cross-disciplinary directions. Do not limit discovery to "computer science" or the main CS school.

No hard domain blacklist: official university pages, personal domains, GitHub Pages, Google Sites, Netlify, lab-owned domains, and project/team sites can all be valid.

Mandatory detail-page closure: every URL that enters the final faculty or lab pool, plus every official faculty detail page, lab detail page, team detail page, member page, reverse-search hit, and redirect shell used as evidence, must be fully read with `web open`/`web fetch` before merge. The subagent must analyze the complete page content and decide whether it contains any new useful links, such as a real personal homepage, better canonical homepage, lab/group/team site, member page, or redirect target. Do not reduce this task to script-based link extraction or checking only links labeled "homepage." Any newly discovered useful or possibly useful link must be opened/fetched, fully read, analyzed, and fed back into the same loop. The task is not complete until this full-page analysis loop yields no new useful links, or all remaining failures are explicitly listed as pending review.

Reverse-search closure is mandatory: reverse search may only produce candidates. A reverse-search candidate cannot enter `faculty_urls.md` or `lab_urls.md` until its detail page has been opened/fetched, fully read, classified by target-page identity, and checked for further useful links.

Rendered-page caution: native `web open`/`web fetch` may show only an initial shell such as "Your Name", "hello world", blank `#app`, or generic template text while the browser-rendered page is valid. Treat these as `pending_render_check`, not `low_value`, until the main agent uses a rendered fallback or records a failed fallback.

Member-page expansion is mandatory and not a one-pass check. When a faculty page, lab page, reverse-search result, or subagent report leads to a people/member/team/staff page, the main agent must re-open and re-expand that member page as its own root-like page, then inspect every faculty/staff/PI/advisor-looking member detail page and every linked homepage/lab homepage it exposes. Classify each discovered page before final inclusion: actual personal/faculty/advisor homepages may enter the faculty pool, actual lab/group/team homepages may enter the lab pool, while ordinary student/alumni/member-only pages, admissions posts, project pages, or vague directory pages stay in the root ledger or pending review. If a subagent reports a member page during reverse search, the subagent should classify it as a lead unless it clearly functions as a final homepage; the main agent owns the second-pass expansion and final judgment.

## Main Agent Responsibilities

The main agent owns coverage, coordination, and final files.

- Confirm the target university, output directory, and default file names.
- Build the broad CS keyword and direction list.
- Run high-frequency web searches to discover root URLs.
- Open/fetch root candidates to confirm they are real roots or useful entries.
- Write and maintain the root URL inventory.
- Expand roots into the first wave of concrete candidate faculty/lab URLs.
- Split final candidate URLs into subagent batches of 50-80 URLs.
- Merge subagent feedback, deduplicate, verify ambiguous or abnormal cases, and update Markdown files.
- Run name-based reverse search for every output faculty name and lab/group name; split this work across subagents when there are many names.
- Send every reverse-search discovery through detail-page reading before merging.
- Re-dispatch newly discovered URLs until no new useful URL appears.
- Produce the final counts and unresolved limitations.

The main agent does not outsource judgment entirely. It must review high-risk items such as failed pages, pages with vague identity, cross-institution pages, redirect shells, and duplicates.

## Subagent Responsibilities

Subagents read concrete final-candidate URLs and report discoveries. They should not edit the Markdown files.

Detail-page lookup and verification should proactively use subagents. Once the workflow reaches concrete faculty/lab detail URLs, the main agent should split them into batches and dispatch subagents by default; it does not need the user to separately ask for "parallel agents" or "subagents."

Subagents must use only agent-native web tools such as `web open` and `web fetch` for detail pages. Either native tool is acceptable if it exposes enough page content for full-page analysis. Subagents must not use Crawl4AI, `curl`, shell commands, custom scripts, or browser automation. If native web tools are inadequate for a URL, report the URL as failed or pending review and let the main agent handle fallback.

Each subagent receives 50-80 specific URLs and must:

- Use agent-native `web open`/`web fetch` tools first for every detail URL.
- Fully read enough visible page content to analyze the page; switch native tools if the first reading is incomplete.
- Decide whether the page is a useful faculty/advisor page, personal homepage, lab/group/team/center homepage, low-value page, or failed page.
- Analyze the full page content for newly discoverable useful links; do not rely on scripts or link text alone.
- Open/fetch and fully read every newly discovered link that could be a real personal homepage, better canonical homepage, lab site, group site, team page, redirect target, member page, or other useful detail page.
- Feed newly found useful links back into the same verification loop until no new useful links remain for the batch.
- Report access success, failure, abnormal content, redirects, and native web tool reading limits.
- Return newly discovered faculty or lab URLs with one-sentence evidence.

Subagents return structured findings only. The main agent merges them.

## Workflow

### 1. Build the Broad CS Keyword List

Use frequent web searches to discover all likely broad CS directions at the target university. The keyword list must be broad before root URL search begins.

Include Chinese and English names, abbreviations, old names, and likely school/department/program/lab terms. Cover at least these directions unless evidence shows the target school clearly lacks them:

| Direction | Search keyword examples |
| --- | --- |
| Computer science/software | 计算机, 软件工程, computer science, software engineering |
| AI/machine learning | 人工智能, 机器学习, 深度学习, AI, machine learning |
| Data/database | 数据库, 数据科学, 数据挖掘, database, data science, data mining |
| Networks/systems | 网络, 分布式系统, 操作系统, 体系结构, systems, network, architecture |
| Security/privacy | 网络安全, 信息安全, 隐私, security, privacy |
| Graphics/vision/multimedia | 图形学, 计算机视觉, 可视化, 多媒体, graphics, vision, visualization |
| HCI/design | 人机交互, 交互设计, HCI, human-computer interaction |
| Robotics/perception/automation | 机器人, 感知, 自动化, robotics, perception, automation |
| NLP/speech/knowledge | 自然语言处理, 语音, 知识图谱, NLP, speech, knowledge graph |
| Theory/algorithms/quantum | 理论计算机, 算法, 量子信息, theory, algorithms, quantum information |
| Information/EE/control intersections | 信息科学, 电子信息, 控制, 智能工程, information science, EE, control |

Also search for university-specific units such as school, department, institute, center, laboratory, faculty, people, staff, advisors, PhD supervisors, research groups, labs, teams, and admissions.

Record the resulting keyword/direction coverage in the root file. This record is the audit trail for "searched broadly enough."

### 2. Find and Confirm Root URLs

For each keyword group, run multiple web searches to find root or entry URLs. Use both broad web search and site-restricted search when the university domain is known.

Useful query shapes:

- `<university> <direction> faculty homepage`
- `<university> <direction> research group lab`
- `<university> <school/department> people faculty`
- `<university> <学院/系/研究院> 师资 教师 导师`
- `<university> <方向> 课题组 实验室 团队`
- `site:<university-domain> <direction> faculty`
- `site:<university-domain> <方向> 个人主页`
- `site:<university-domain> <方向> 实验室 课题组`

Open/fetch each promising result to confirm the page content. A root URL is any useful entry that can lead to faculty or lab homepages, including:

- school, department, institute, or center homepages;
- faculty/staff/people/advisor directories;
- research group, lab, team, or center directories;
- topic/program pages with member or lab lists;
- lab pages that contain member directories;
- official faculty detail pages or independent lab pages found during search.

Do not count a URL as confirmed root from a search snippet alone. Use page content to decide.

Write root entries like:

```markdown
# <University> Broad CS Root URL List

## Search Coverage

- <direction/keyword group>
  - Queries: <short list>
  - Result: <confirmed roots or not found>

## Root URLs

- <entry name>
  - URL: <url>
  - Type: <school/department | faculty directory | lab directory | research center | member list | search lead>
  - Status: <pending_expand | expanded | low_value | pending_review>
  - Note: <short note if needed>
```

### 3. Expand Roots Into First-Wave Final Candidates

Starting from the root URL list, expand downward in a tree/network pattern.

- Read each root with `web fetch`/`web open`.
- Extract likely faculty detail pages, personal homepages, lab/group/team homepages, member pages, and related directories.
- Prefer completeness over premature classification in this phase.
- Add concrete candidate final URLs to the faculty or lab Markdown files in the same clean format used for final delivery.
- Do not deeply read every candidate detail page yet; the goal is to collect the first wave of likely final URLs.
- Mark root status as expanded, low value, or pending review.

Candidate inclusion is allowed at this stage if the URL is plausibly a faculty page or lab page, but it must later be detail-read by subagents before final completion is claimed.

### 4. Dispatch Subagents for Detail Reading

When detail-page lookup begins, proactively batch concrete candidate final URLs into groups of 50-80 and assign them to subagents. Do this as the default execution path for reading final candidate pages, discovering secondary external links, and checking success/failure status. Subagents must use only agent-native `web open`/`web fetch` tools and must not perform crawler or shell fallbacks.

This stage is a mandatory full-page analysis pass. For every personal homepage, official faculty detail page, lab/group homepage, lab detail page, member page, and redirect shell in the batch, the subagent must use native web tools to read enough page content and check whether the page contains new useful links. Subagents do not use Crawl4AI, `curl`, shell commands, custom scripts, or browser automation. If native web tools fail, report the URL as failed or pending review. Only the main agent may use fallback tools, and it must record the tool, reason, and evidence. Useful or possibly useful links must be opened/fetched and checked recursively. Do not stop after confirming the original URL works; the goal is to find real/canonical homepage links hidden inside detail pages.

Subagent prompt template:

```text
Task: Verify and expand a batch of broad CS faculty/lab candidate URLs for <university>.

Use only agent-native web open/web fetch tools for every detail URL. Either is acceptable if it exposes enough page content for full-page analysis. Do not use Crawl4AI, curl, shell commands, custom scripts, or browser automation. If native web tools cannot read the page adequately, mark the URL as failed or pending review and explain why.

Read the full visible content for each URL in this batch:
<50-80 URLs>

For each URL, report:
- status: success | failed | abnormal | low_value
- page type: faculty_profile | personal_homepage | lab_group_homepage | directory | unrelated | unclear
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

Subagents must not rely on link text alone or script-extracted URL lists. They must read the page content as a page and reason over it. A page such as an official faculty profile may contain the real personal homepage in a field like "个人主页"; missing that link after a full-page read is a failed verification. Report `needs_main_agent_review` only for access or reading problems, such as failure, timeout, blank content, decoding trouble, JS shell, redirect anomaly, or suspected browser-rendered hidden fields.

### 5. Merge, Verify, Update, and Repeat

After each subagent wave:

1. Merge proposed new URLs into the faculty/lab Markdown files.
2. Normalize and deduplicate URLs.
3. Verify ambiguous, failed, abnormal, cross-institution, or redirect cases with native web tools first.
4. Record unresolved failures in the root file or a review ledger.
5. Dispatch newly added concrete URLs to another subagent wave.
6. Repeat until subagents report no new useful faculty or lab URLs.

Stop only when the loop converges or when remaining gaps are explicitly listed as pending review.

### 6. Reverse Search Every Final Name

Every faculty/advisor name and every lab/group/team/center name that appears in the final output must go through at least one name-based reverse search pass. This is mandatory, not optional sampling.

Use `web search` to find candidates. Use native `web open` / `web fetch` to read every promising candidate before judging it. A newly found page is useful only if it opens successfully and has non-empty relevant content; blank shells, empty redirects, dead pages, login pages, and unrelated search hits do not enter the final pools.

Reverse-search results must be classified by page type after detail-page reading. The important distinction is whether a page is actually a personal/faculty homepage or lab/group homepage, versus only a member page, directory, admissions page, project page, company page, or low-value mention.

Hard rule: `reverse_added` requires a completed detail-page read. If the candidate was found by search but not opened/fetched and read, its status is `reverse_pending`, not `reverse_added`.

Run reverse search after the first full detail-page pass, and run it again for any names newly added later. A name is not final until it has a reverse-search status.

For each faculty/advisor, search the name variants that are visible in the pages already read:

- Chinese name;
- English name or romanized name if shown;
- common homepage slug, email id, or GitHub/personal-site handle if shown.

For each lab/group/team/center, search the visible name variants:

- Chinese name;
- English name;
- acronym or short name;
- known domain/project/org name if shown.

This reverse-search step may and usually should be split across subagents when the final name list is large. Assign each subagent a concrete batch of faculty names or lab/group names. Subagents for reverse search follow the same tool restriction as detail-page subagents: use only agent-native `web search` plus `web open`/`web fetch`; do not use Crawl4AI, `curl`, shell commands, custom scripts, or browser automation. If native web tools cannot search or read a candidate page adequately, report `reverse_pending` and let the main agent decide fallback.

When dispatching reverse-search subagents, include the current faculty/lab Markdown file paths and tell subagents to treat them as the existing URL pool. If a search result URL is already present in those Markdown files, the subagent should not open/read it again for reverse-search purposes; mark it as `already_present` and focus on new candidate URLs. If a result has the same name but a different URL, inspect it only if it may add a non-empty personal homepage, lab page, team page, member page, or admissions source. Subagents must verify the page type before recommending it: faculty/personal homepage candidates go to the faculty pool, lab/group/team homepage candidates go to the lab pool, and admissions/member/directory pages are returned as leads unless they clearly function as a final homepage.

Faculty/advisor reverse-search query shapes:

- `<name> <university> personal homepage`
- `<name> <university> homepage`
- `<name> <school/department> website`
- `<name> <university> 招生`
- `<name> <university> 个人主页`
- `<name> <university> 课题组`

Lab/group reverse-search query shapes:

- `<lab/group name> <university> homepage`
- `<lab/group name> <university> lab`
- `<lab/group name> <university> group`
- `<lab/group name> <university> 招生`
- `<lab/group name> <university> 首页`
- `<lab/group name> <university> 实验室`

For each reverse-searched name, record the search status in the root file or review ledger:

- `reverse_searched`: searched and no new useful non-empty page found.
- `reverse_added`: searched, opened/fetched, fully read, classified, and new useful non-empty page(s) added.
- `reverse_pending`: search or page reading failed and needs review.

Use `reverse_added` only for a new URL with page type `faculty_profile`, `personal_homepage`, or `lab_group_homepage`. For `member_page`, `admissions_lead`, `directory`, `project_page`, `company_page`, or `unclear`, report the URL as a lead for main-agent review instead of adding it directly to clean pools.

Any newly discovered useful or maybe useful URL from reverse search must enter the same detail-page full-read and subagent verification loop. Do not add a reverse-search hit directly to the final file unless it has been opened/read, classified, checked for further useful links, and judged to have relevant non-empty content. The workflow is not complete until every final output name has a reverse-search status and every `reverse_added` URL has detail-read evidence.

Reverse search is a supplement, not a replacement for detail-page reading. It finds missing URLs by name; every URL it finds still has to be opened/read and classified.

Reverse-search subagent prompt template:

```text
Task: Reverse-search final output names for <university> broad CS URL pool.

Use only agent-native web search and native web open/web fetch reading tools. Prefer `web open` / `web fetch` for every candidate page read. Do not use Crawl4AI, curl, shell commands, custom scripts, or browser automation.

Existing Markdown files:
- Faculty URL file: <path/to/<university_full_name>_faculty_urls.md>
- Lab URL file: <path/to/<university_full_name>_lab_urls.md>

Treat URLs already present in these files as existing pool entries. If a reverse-search result URL is already present, do not open/read it again; report it as `already_present`. Only open/read new URLs or same-name different URLs that may contain non-empty useful content.

Names in this batch:
<faculty/advisor names or lab/group/team/center names>

For each name:
- run at least one targeted reverse search using the query shapes from the skill;
- open/fetch and fully read promising results with native web tools before recommending them;
- skip search-result URLs already present in the provided Markdown files;
- verify page type before recommending a new URL: faculty_profile | personal_homepage | lab_group_homepage | admissions_lead | member_page | directory | low_value | unrelated | unclear;
- recommend `faculty_profile` and `personal_homepage` URLs for the faculty pool;
- recommend `lab_group_homepage` URLs for the lab pool;
- return `admissions_lead`, `member_page`, `directory`, and `unclear` pages as leads for main-agent review unless the page clearly functions as a final homepage;
- only keep pages that have non-empty relevant content;
- look for richer personal homepages, lab/group/team pages, member pages, and admissions information;
- report `reverse_searched`, `reverse_added`, or `reverse_pending`; use `reverse_added` only after full detail-page reading.

Return:
1. Name -> reverse-search status.
2. New faculty-pool URLs -> page type -> evidence that the page was opened/read and non-empty.
3. New lab-pool URLs -> page type -> evidence that the page was opened/read and non-empty.
4. Leads that should not be directly added yet -> page type -> reason.
5. Already-present URLs skipped.
6. Failed or pending searches/pages -> reason.
7. Items that need main-agent review.
```

### 7. Final Single-URL Faculty Audit

After detail-page review and reverse search, run one last audit for faculty/advisor entries that still have only one URL in `faculty_urls.md`. This catches missed personal homepage or lab links hidden in the sole detail page, especially but not only on official `person`/`mypage` profile platforms with JavaScript, redirects, tabs, or rendered-only sections.

- The main agent owns this audit. Only the main agent may run rendered fallback, Crawl4AI, curl, or browser automation, and only as a diagnostic step for suspected abnormal/dynamic pages.
- Subagents may help by reading main-agent-produced full-text diagnostic batches. They must read the full diagnostic text and report candidate links, but must not run Crawl4AI/curl/scripts/browser automation themselves.
- Diagnostic results are leads, not clean-pool evidence. Every candidate URL found this way must still be opened/fetched with native web tools, read as a non-empty page, classified, and checked for further useful links before it enters `faculty_urls.md` or `lab_urls.md`.
- If native web reading of the candidate fails, is blank, or shows only a placeholder/template, keep it in the root ledger as `pending_render_check`, `abnormal`, or `lead_only`; do not add it to clean pools unless the user explicitly approves a recorded exception.
- Record the audit in the root file: scope, fallback tool used, why fallback was needed, which batches/subagents read the diagnostic text, native-verified additions, already-present URLs, and rejected/pending leads.

## Classification Rules

Include in the faculty URL pool:

- official university faculty/advisor profile pages;
- personal homepages, personal websites, English homepages, or redirects clearly belonging to a faculty member;
- independent domains or hosted pages clearly used as a faculty homepage.

Include in the lab URL pool:

- research group, laboratory, team, center, or project-group homepages;
- group-owned domains, GitHub/GitHub Pages sites, Google Sites, or university-hosted group pages;
- a faculty page only when it clearly functions as the group homepage and no better group site is found.

Exclude from final pools:

- university/school homepages and generic navigation pages;
- news, notices, single admissions posts, course pages, login pages, maps, email links, and internal systems;
- PDFs, papers, DOI pages, publisher pages, Google Scholar, DBLP, ORCID, and publication databases;
- pages unrelated to the target university or target broad CS scope;
- failed, empty, login-only, or abnormal pages unless explicitly kept in a pending review ledger.

Do not exclude a page only because native reading shows a placeholder or JS shell. First run main-agent rendered fallback or record `pending_render_check`.

## Final Markdown Format

`<university_full_name>_faculty_urls.md`:

```markdown
# <University> Broad CS Faculty Homepage URL List

- <Faculty Name>
  - <url>
  - <url>
```

`<university_full_name>_lab_urls.md`:

```markdown
# <University> Broad CS Lab and Research Group Homepage URL List

- <Lab / Group / Team Name>
  - <url>
  - <url>
```

Keep URL lines as `http://` or `https://` only. Prefer working `https://` over `http://` for duplicate URLs.

## Completion Checklist

Before final response:

- The keyword/direction list covers broad CS and university-specific units.
- Root URLs were confirmed by opening/fetching page content, not only by search snippets.
- Root file records search coverage, confirmed roots, expansion status, and pending review items.
- First-wave candidate faculty/lab URLs were collected from root expansion.
- Every concrete final URL was assigned to a subagent or directly detail-read with the same standard.
- Every final faculty/lab URL and every official/detail page used as evidence was fully read with web open/web fetch.
- Subagents analyzed each full page for newly discoverable useful links, instead of relying on script-based link extraction.
- Every useful or maybe useful discovered link was opened/fetched, fully read, and recursively analyzed.
- Placeholder, empty-app, or JS-shell native reads were rendered by the main agent or recorded as `pending_render_check`.
- Every final faculty/advisor name and lab/group/team/center name completed name-based reverse search.
- Large reverse-search name lists were split across subagents where useful.
- Reverse-search hits were added only when opened/fetched, fully detail-read, classified, checked for further useful links, and confirmed to contain relevant non-empty content.
- Reverse-search discoveries were fed back into the same detail-page full-read and subagent verification loop.
- No `reverse_added` item lacks detail-read evidence.
- A final single-URL faculty audit was run for faculty/advisor entries that still had only one URL.
- Any Crawl4AI/rendered/curl/browser result from that final audit was treated as diagnostic only; clean additions from it were native-opened/fetched, non-empty, classified, and checked for more links before merge.
- Subagents reported full-page read status, newly discovered useful links, recursive checks, and success/failure/abnormal status.
- Newly discovered URLs were merged and re-dispatched until no new useful URLs appeared.
- Do not claim "full detail-page review completed" unless the full-page analysis loop above is complete for all final URLs.
- Ambiguous and failed items were reviewed by the main agent or listed as pending review.
- Final faculty/lab files are clean, deduplicated, and contain only names plus URLs.
- Final response reports faculty entries, faculty URL count, lab entries, lab URL count, failed/pending count, and whether full detail-page review was completed.
