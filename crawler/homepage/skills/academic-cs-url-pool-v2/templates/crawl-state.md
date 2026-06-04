# Crawl State Template

Use one row/block per source URL or follow-up URL. Keep this in the root file or a clean ledger.

```markdown
## Crawl State

- Entry: <name>
  - Source URL: <url>
  - Source type: <faculty | lab | followup>
  - Raw packet: <path/to/full-crawl4ai-packet.md>
  - Crawl status: <success | failed | pending>
  - Read by: <main | subagent-id>
  - Packet fully read: <yes | no>
  - Decision: <keep | remove | keep_homepage | accepted_join_page | pending>
  - Decision reason: <content-based reason>
  - Follow-up links needing crawl:
    - <url> -> <why it may matter>
  - Follow-up crawled: <yes | no | n/a>
  - Clean URL(s):
    - <url>
  - Rejected links:
    - <url> -> <reason>
```

Before crawling, check whether `Raw packet` already exists and whether `Packet fully read` is `yes`.
