# Build Pool Workflow

Use this when building or expanding the broad faculty/lab URL pool before crawler-cleaning.

## Outputs

- `<university_full_name>_faculty_urls.md`: broad audited faculty/advisor URL pool.
- `<university_full_name>_lab_urls.md`: broad audited lab/group/team URL pool.
- `<university_full_name>_root_urls.md`: search coverage, expansion status, failures, and pending review.

## 1. Confirm Scope

Confirm or infer target university, output directory, canonical English filename stem, likely university domains, and whether existing pool files already exist.

## 2. Build Search Coverage

Create broad Chinese/English keyword coverage before root discovery. Include university names, abbreviations, old names, school names, broad CS directions, and terms such as 学院, 系, 研究院, 师资, 教师, 导师, 博导, 硕导, 课题组, 实验室, 团队, 招生, 个人主页.

Useful query shapes:

- `<university> <direction> faculty homepage`
- `<university> <direction> research group lab`
- `<university> <school/department> people faculty`
- `<university> <学院/系/研究院> 师资 教师 导师`
- `<university> <方向> 课题组 实验室 团队`
- `site:<domain> <direction> faculty`
- `site:<domain> <方向> 个人主页`
- `site:<domain> <方向> 实验室 课题组`

Record keyword families, representative queries, and results in the root file.

## 3. Confirm Root URLs

A root is any page that can lead to faculty, labs, member pages, or final detail pages. Open/fetch each promising result before adding it to root inventory; snippets are not evidence.

Root statuses:

- `pending_expand`
- `expanded`
- `low_value`
- `pending_review`
- `pending_render_check`

## 4. Expand Roots

Read each confirmed root and collect first-wave candidates: faculty/advisor details, personal homepages, lab/group/team/center homepages, people/member/staff pages, and related directories.

Member pages are root-like leads. Re-open and expand them, then inspect faculty/staff/PI/advisor-looking detail pages and linked homepages.

## Page Reading Principle

The same reading discipline applies throughout the workflow. In discovery/detail review use native `web open` / `web fetch`; in crawler-clean use Crawl4AI. The tool changes, but the standard does not.

- Read the full available page result as content, not as a URL list.
- Inspect title, main text/markdown, visible navigation, link context, and extracted links.
- Classify the page from content evidence.
- Decide from page content which new links are useful or plausible enough to read next.
- Fully read newly discovered links with the phase-appropriate tool before adding them to any pool or clean file.
- Use scripts only for mechanical support that does not influence judgment.

Never let a script, regex, link extractor, URL path, anchor text, keyword hit, generated summary, or precomputed classification replace full-page reading and judgment.

## 5. Detail-Read Candidate URLs

Every final URL and every official/detail/member/redirect page used as evidence must be opened/fetched and read deeply enough to classify it and inspect useful links.

For each page, decide:

- page type: `faculty_profile`, `personal_homepage`, `lab_group_homepage`, `directory`, `member_page`, `admissions_lead`, `project_page`, `unrelated`, `unclear`;
- status: `success`, `failed`, `abnormal`, `low_value`, `pending_render_check`;
- normalized name if identifiable;
- useful/maybe useful links discovered from page content;
- whether all discovered useful links were opened/fetched and recursively analyzed.

Personal-homepage team/member pages are not lab/group homepages by default. Keep `<person>/team.html`, `<person>/group.html`, "People", "Students", "Members", or personal homepage team tabs with faculty/profile evidence unless the page clearly self-identifies as an independent lab/research group/课题组/实验室 with group name, research identity, and lab-owned homepage.

## 6. Merge and Iterate

Merge valid faculty/lab URLs, deduplicate, prefer working HTTPS over HTTP duplicates, review high-risk cases, record unresolved items, and re-dispatch newly found concrete URLs until no new useful URLs appear.

## 7. Reverse-Search Every Final Name

Every final faculty/advisor name and lab/group/team/center name needs a reverse-search status.

Faculty query shapes:

- `<name> <university> personal homepage`
- `<name> <university> homepage`
- `<name> <school/department> website`
- `<name> <university> 招生`
- `<name> <university> 个人主页`
- `<name> <university> 课题组`

Lab/group query shapes:

- `<lab/group name> <university> homepage`
- `<lab/group name> <university> lab`
- `<lab/group name> <university> group`
- `<lab/group name> <university> 招生`
- `<lab/group name> <university> 首页`
- `<lab/group name> <university> 实验室`

Use `reverse_added` only after a candidate is opened/fetched, fully read, classified, and confirmed useful. Reverse discoveries enter the same detail-read loop before completion.
