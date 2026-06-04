# Crawl4AI Clean Checklist

## Shared

- Crawl4AI fetching was serial; no parallel Crawl4AI sessions.
- Subagents did not run Crawl4AI or fetch pages.
- Each source page has a complete raw packet.
- Agent/subagents read complete raw packets, not filtered lists, summaries, keyword-hit reports, or preclassified rows.
- Scripts were used only for serial raw-packet saving, post-decision URL normalization/deduplication/counting, or final formatting.
- Scripts did not extract candidate links, summarize pages, classify pages, generate keep/remove decisions, or draft clean URL lists.
- Any subagent-discovered new link needing a page read was returned as `needs_main_agent_crawl` and then crawled serially before inclusion.
- State/ledger records source URL, packet path, reader, decision, follow-up links, and clean URLs.

## Lab Clean

- Every lab/group/team/center entry from `lab_urls.md` was processed.
- Kept admissions/join pages had lab/PI-specific joining/contact signals.
- Candidate target pages were Crawl4AI-read before inclusion.
- Generic admissions/training/news/resource links were rejected unless the target page itself explicitly invited prospective master/PhD students to contact or join the lab.
- Personal-homepage team/member tabs were rejected unless independently identified as lab/research group.
- Joint-lab/platform/collaboration pages under the same parent lab were merged into the parent clean entry unless independently eligible.
- If no accepted joining page was found, a non-empty lab homepage was kept.
- Rejected candidates and reasons are in the ledger.

## Faculty Clean

- Every faculty/advisor entry and every URL under it was processed.
- Each faculty URL was classified as `admissions_relevant`, `profile_without_admissions`, or `remove` from full packet content.
- If a teacher had admissions-relevant URLs, only those were kept.
- If no admissions-relevant URL existed, all usable profile-without-admissions URLs were kept.
- Teachers with no surviving useful URL were omitted.
- Removed URLs, omitted teachers, discovered URLs, per-URL classes, and kept clean URLs are recorded.
