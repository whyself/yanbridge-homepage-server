# Crawl4AI Clean Workflow

Use this when pool files already exist and the task is to produce crawler-ready clean URL files.

## Outputs

- `<university_full_name>_clean_faculty_urls.md`
- `<university_full_name>_clean_lab_urls.md`
- `<university_full_name>_root_urls.md` or a clean ledger with Crawl4AI decisions

## Hard Script Boundary

Crawl4AI clean is a reading-and-judgment phase, not a scripted filtering phase.

Allowed:

- run Crawl4AI serially and save one complete raw packet per crawled URL;
- preserve full markdown/text and full extracted-link context;
- after agent/subagent decisions, normalize URLs, deduplicate, count, and format final Markdown.

Forbidden before judgment:

- extracting only matching links;
- filtering links by keywords;
- scoring/ranking candidates;
- summarizing pages;
- classifying pages;
- labeling admissions/profile/remove;
- generating keep/remove decisions;
- generating candidate-only packets;
- drafting clean URL lists.

Forbidden evidence: "the script found 招生/recruit/join" or "the regex matched PhD/master". Evidence must come from an agent reading the full crawled page or a subagent reading a complete raw packet.

## Serial Crawl Rule

Crawler fetching must remain serial to reduce anti-crawling risk. Do not run parallel Crawl4AI sessions or ask subagents to crawl.

When results are too large, split already-crawled full raw packets into reading batches. Subagents read saved Crawl4AI outputs only; they do not fetch pages, run Crawl4AI, or decide from filtered link lists, summaries, or keyword-hit reports.

If a subagent finds a new link needing a page read, it returns `needs_main_agent_crawl`. The main agent then serially crawls it, saves the full result, and judges it directly or sends it to another reading batch.

## Lab Clean

For lab clean, admissions-relevant means useful for a prospective master/PhD student who wants to contact or join the lab/group/PI.

Strong signals:

- 欢迎有意向的硕士生/博士生/本科生联系;
- 招收硕士/博士/研究生, 招募学生, 课题组招生;
- 加入我们, Join Us, prospective students, openings for students, PhD/master positions;
- PI/lab contact instructions for interested students;
- lab-specific requirements, research directions for applicants, or student application email.

Reject by default:

- generic school/department admissions columns;
- generic student-training pages such as 硕士生, 博士生, 培养方案, 课程, 毕业要求;
- thesis defense, awards, seminars, publications, activities, or enrolled-student news;
- staff/postdoc-only recruitment unless it also explicitly invites prospective master/PhD students;
- PDFs, ZIP files, manuals, datasets, tools, platform resources, downloads;
- personal-homepage team/member tabs unless independently identified as a lab/research group;
- joint-lab, industry-collaboration, platform, or cooperation-direction pages under a parent lab unless they have independent lab identity and independent prospective master/PhD joining/contact instructions.

When several joint/cooperation pages share the same parent lab and same student-facing joining page, keep the parent lab's accepted joining URL once and record joint pages in the ledger/root notes.

Process each lab entry:

1. Crawl source URL serially and save the full raw packet.
2. Read the complete packet; do not use a script to pre-filter, summarize, classify, or present matches.
3. Decide candidate links from full content.
4. Serially crawl every plausible target page before inclusion.
5. Keep a target only if the target page itself has lab/PI-specific prospective-student contact/joining signal.
6. If no accepted joining page exists but homepage has non-empty lab identity, keep the homepage.
7. Record checked candidates, accepted pages, rejected generic/training/news/resource links, and clean URLs.

## Faculty Clean

Process every faculty/advisor entry and every URL under that entry.

1. Crawl each URL serially and save the full raw packet.
2. Read the complete packet; do not use scripts to summarize, pre-label, or classify from keyword hits.
3. Classify independently:
   - `admissions_relevant`: teacher-specific student admissions/recruitment signal.
   - `profile_without_admissions`: usable personal/profile/advisor content without admissions.
   - `remove`: no usable personal/profile/advisor signal.
4. If any `admissions_relevant` URL exists for a teacher, keep only admissions-relevant URLs.
5. If no admissions-relevant URL exists, keep all usable profile-without-admissions URLs.
6. For discovered links, decide from full context whether another Crawl4AI read is warranted; crawl before inclusion.
7. Omit teachers with no surviving useful URL.

## State Tracking

Use `templates/crawl-state.md` or equivalent ledger rows. Check existing state before crawling to avoid duplicate fetches.
