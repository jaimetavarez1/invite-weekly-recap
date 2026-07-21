---
name: invite-weekly-recap
description: >
  Generates a weekly recruiting recap for an Invite PE at Gusto. Reads the PE's
  configured org Slack channels plus shared Invite channels using the PE's own
  Slack connector, reads the IOPE Newsletter and Leadership Hub, then delivers the
  synthesized JSON by opening a [RECAP-INGEST] GitHub issue that a workflow ingests
  and pushes. Also creates a Notion page. Trigger on "give me my weekly recap",
  "run my recap", "weekly update", "what happened this week in recruiting", or "run
  the invite recap". Also handles mid-week live artifact refreshes — trigger on
  "refresh my recap", "refresh the live artifact", "add new updates", or "update my
  recap".
---

Generate the weekly recruiting recap for the PE running this skill.

**How this runs:** Everything happens in the PE's own Cowork session using **their own
connectors** — Slack, Notion, and GitHub. There is no shared bot and no embedded token:

- **Slack** is read through the PE's Slack connector, so it can see every channel the PE
  is a member of, public and private — no bot invite needed.
- **GitHub** — the skill does **not** push files directly and needs **no repo write access**.
  It reads public files (config, other PEs' data) via the connector, and delivers the
  synthesized recap by **opening a `[RECAP-INGEST]` issue**. A GitHub Action ingests that
  issue and pushes the data using the repo's own token. Opening an issue on a public repo is
  allowed for any GitHub account, so PEs never need to be collaborators.
- **Notion** page creation goes through the PE's Notion connector.

Throughout, use the connector tools available in the session (e.g. `slack_read_channel`,
`slack_search_public_and_private`, `notion-query-data-sources`, `notion-fetch`,
`notion-create-pages`, and the GitHub connector's issue-create and file-read tools). Do
**not** use raw `urllib` calls with a hardcoded token — there is no shared token anymore.

## Step 0 — Identify PE and load config

**Auto-detect from email:**
Check the Cowork system context for `userEmail`. Map it to a PE key:

| Email | PE key |
|---|---|
| jaime.tavarez@gusto.com | jaime |
| teresa.waggoner@gusto.com | teresa |
| michelle.cordray@gusto.com | michelle |
| kebone.moloko@gusto.com | kebone |
| lisa.pham@gusto.com | lisa |

If not found, ask: "What's your PE key? (e.g. `teresa`)"

**PE org assignments:**
- **Jaime Tavarez** — Engineering
- **Teresa Waggoner** — Foundation & Leadership, I&O, Finance
- **Lisa Pham** — Go-To-Market (GTM), Marketing, Sales, Revenue Operations
- **Michelle Cordray** — CX (Customer Experience)
- **Kebone Moloko** — PM/PD, Data

**Load config from GitHub:**

Read `config/<pe_key>.json` from `jaimetavarez1/invite-weekly-recap` (branch `main`) using
the GitHub connector's file-read tool (e.g. `get_file_contents`). This is a public read — no
write access needed. Parse it as JSON.

- If the file doesn't exist: stop and tell the PE — "I couldn't find your config. Please say
  'set up my weekly recap' first — it only takes a minute."
- Extract `org_channels` — a list of `{id, name}` objects for the PE's org-specific channels.

The three shared Invite channels are always included for every PE (no config needed):
- `C0517BVP04V` — #invite-team
- `C0AFC07JJKA` — #invite-pes
- `C0B0PPHSCUA` — #invite_pes_and_people_insights

## Step 0b — Detect run mode

Determine whether this is a **full run** or a **refresh** based on what the PE said:

| Trigger phrases | Mode |
|---|---|
| "give me my weekly recap", "run my recap", "weekly update", "what happened this week" | `FULL` |
| "refresh my recap", "refresh the live artifact", "add new updates", "update my recap", "refresh" | `REFRESH` |

**Full mode** — the clean-slate weekly reset. Overwrites all JSON data and creates a new
Notion page.

**Refresh mode** — mid-week top-up. Adds new updates without removing anything already there.
Does NOT create a Notion page.

For the Slack read window: **full** = 7 days ago; **refresh** = the `refreshedAt` timestamp
from the current `data/shared.json` (read it via the connector; fall back to 7 days ago if
absent). Carry `MODE` through to Step 4 — the ingest Action uses it to decide overwrite vs
merge.

## Step 1 — Read Slack channels (via the PE's Slack connector)

Set `oldest` per the window above. Using `slack_read_channel` (limit 100), read:
- The three shared channels (IDs above)
- Every channel ID in the PE's `org_channels`

Because this uses the PE's own Slack access, private channels the PE belongs to are readable
directly — no invite step. If a channel errors or is empty, note it and continue.

## Step 1b — Search Slack for R&D org-wide updates (jaime only)

If `pe_key` is `jaime`, run these with `slack_search_public_and_private` (`after` = window
start):
- `"deep work week" in:#r-and-d-invite-all`
- `"R&D" "week" in:#invite-team`
- `"r-and-d" hiring OR recruiting`

Apply the Step 3 filters. Add valid results to jaime's updates bucket. Otherwise skip.

## Step 1c — Read Leadership Hub (Notion)

Via `notion-query-data-sources`:

**Cascade to Your Teams** — `collection://7c90c5eb-ca2f-42c1-a29a-66e2d7bbbbd9`
```sql
SELECT "Action", "Status", "Due Date", "Notes"
FROM "collection://7c90c5eb-ca2f-42c1-a29a-66e2d7bbbbd9"
WHERE "Status" NOT IN ('Cascaded ✓', 'Archived')
ORDER BY createdTime DESC
```

**PE Action Items** — `collection://07af0c0a-3fe8-4531-af0a-fe315fda0aed`
```sql
SELECT "Action", "Status", "Priority", "Due Date", "Notes"
FROM "collection://07af0c0a-3fe8-4531-af0a-fe315fda0aed"
WHERE "Status" NOT IN ('Done ✓', 'Archived')
ORDER BY createdTime DESC
```

**7-day relevance filter:** include a Leadership Hub item only if it was explicitly mentioned
in Slack or the IOPE Newsletter this week. If a query fails, note it and continue.

## Step 2 — Read the IOPE Newsletter

Two most recent entries via `notion-query-data-sources` —
`collection://37dad673-c6c2-802c-b922-000bd954d35c`:
```sql
SELECT * FROM "collection://37dad673-c6c2-802c-b922-000bd954d35c"
ORDER BY createdTime DESC LIMIT 2
```
Fetch full content with `notion-fetch`. If inaccessible, note and continue.

## Step 2b — Read People Central Updates (bi-weekly)

Via Glean (`read_document`): `https://sites.google.com/gusto.com/people-central-updates/home`
(fallback: Glean search `"people central updates" site:sites.google.com`). Pull entries from
the past 14 days; classify into `orgPolicy` or `keyEvents`, tag `["all"]`, `source` =
"People Central Updates". If nothing new, skip silently.

## Step 3 — Synthesize content

**Shared (orgPolicy + keyEvents)** — from #invite-team, #invite-pes,
#invite_pes_and_people_insights, and the IOPE Newsletter only.
- `orgPolicy` = process/tooling/SOP changes
- `keyEvents` = decisions, departures, launches, roadmap updates, upcoming dates, holidays,
  org-wide events

**Holiday auto-detection:**
```python
import datetime
GUSTO_HOLIDAYS_FY27 = [
    ("Juneteenth", datetime.date(2026, 6, 19)),
    ("Independence Day", datetime.date(2026, 7, 3)),
    ("Labor Day", datetime.date(2026, 9, 7)),
    ("Veterans Day", datetime.date(2026, 11, 11)),
    ("Thanksgiving Day", datetime.date(2026, 11, 26)),
    ("Christmas Day", datetime.date(2026, 12, 25)),
]
today = datetime.date.today()
for name, date in GUSTO_HOLIDAYS_FY27:
    days_away = (date - today).days
    if 0 <= days_away <= 14:
        print(f"ADD TO keyEvents: {name} — {date.strftime('%A %B %-d, %Y')} ({days_away} days away)")
```
For each: `theme` "Upcoming Holiday", `heading` "{Holiday} — {Day Month Date}", `bullets`
["Company holiday — plan interview scheduling and candidate comms accordingly"], `source`
"Gusto FY27 Holiday Calendar", `tp.priority` "yellow" if >7 days, "red" if ≤7.

**Work anniversary auto-detection:** via Glean `employee_search` for each PE manager, extract
direct reports, dedup by email, find anniversaries within 14 days. Add as keyEvents with
`theme` "Work Anniversary".

**PE-specific (updates)** — from the PE's org channels and Step 1b results.

**Filters (required):** org-wide only (exclude individual personal actions); Leadership Hub
7-day relevance; skip Leadership Hub items whose Due Date is before today; skip messages from
Roberto Segovia and Todd Hazen; source integrity (every item traceable to a message — do not
infer); thread age (only items whose original parent message is within the window).

## Step 4 — Deliver by opening a [RECAP-INGEST] issue

Build the payload from the synthesized content, then open a GitHub **issue** using the PE's
GitHub connector (issue-create tool). No file push, no write access needed — the ingest
Action does the push.

```python
import datetime
today = datetime.date.today()
start = today - datetime.timedelta(days=7)
week_str = f"{start.strftime('%B %-d')} – {today.strftime('%B %-d, %Y')}"
now_iso = datetime.datetime.utcnow().isoformat() + "Z"
```

**Issue title:** `[RECAP-INGEST] <pe_key> <MODE> <week_str>`
(e.g. `[RECAP-INGEST] jaime FULL July 14 – July 21, 2026`)

**Issue body:** a single fenced ```json block containing exactly this object:

```json
{
  "mode": "full",
  "pe_key": "<pe_key>",
  "shared": {
    "week": "<week_str>",
    "refreshedAt": "<now_iso>",
    "refreshedBy": "<pe_key>",
    "orgPolicy": [ ... ],
    "keyEvents": [ ... ]
  },
  "pe": {
    "pe": "<pe_key>",
    "week": "<week_str>",
    "refreshedAt": "<now_iso>",
    "updates": [ ... ]
  }
}
```

- **Full mode:** set `"mode": "full"` — the Action overwrites `data/shared.json` and
  `data/<pe_key>.json`.
- **Refresh mode:** set `"mode": "refresh"` — the Action merges the new `shared`/`pe` items
  into the existing files (dedup by title / theme+heading / heading; never removes). You do
  not need to pre-merge; just send the newly synthesized items.

Create the issue in `jaimetavarez1/invite-weekly-recap`. The ingest workflow fires on issue
open, writes the files, pushes (rebuilding the dashboard), and auto-closes the issue. Confirm
the issue was created; the dashboard updates within ~1 minute.

## Step 5 — Create Notion page (full mode only)

**Skip entirely in refresh mode.**

**Parent page ID:** `376ad673-c6c2-8196-8e2e-e09dbc954986`
**Title:** `Week of [today's date], [year]` (e.g. `Week of July 20, 2026`), icon `📋`.

First content block:
> 🔴 **[→ Open Live Interactive Recap](https://jaimetavarez1.github.io/invite-weekly-recap/)** — tabs, filters, and one-click Slack summary

Then all four sections:
```
## 📋 Org & Policy Updates
(orgPolicy items — ### per item, - bullets, *italic* source citations)

---

## 📅 Key Events & Decisions
(keyEvents items — ### per theme, - bullets, *italic* source citations)

---

## 🎯 PE Org Updates

### Jaime Tavarez — Engineering
### Teresa Waggoner — Foundation, I&O, Finance
### Lisa Pham — GTM, Sales, Marketing
### Michelle Cordray — Customer Experience
### Kebone Moloko — PM/PD, Data
```

For the **running PE's own** section, use the updates you just synthesized in memory (the
issue push is asynchronous, so `data/<pe_key>.json` may not be updated yet). For the **other**
PEs, read their existing `data/<pe>.json` from GitHub via the connector (public read); if
missing → "No data available yet." Render each update as `**heading**` + `-` bullets.

## Step 6 — Confirm

**Full mode:** tell the PE it's done and share the Notion page link, the live artifact link
(https://jaimetavarez1.github.io/invite-weekly-recap/), and a 2–3 sentence plain-language
summary of the most important things this week. Note the dashboard updates within ~1 minute
once the ingest Action runs.

**Refresh mode:** tell the PE what was added (counts of new orgPolicy / keyEvents / PE
updates), share the live artifact link, and note existing updates were preserved and nothing
removed.

**If the issue couldn't be created:** it usually means the PE's GitHub connector isn't
authorized in Cowork. Tell them: "I couldn't open the GitHub issue that delivers your recap —
make sure your GitHub connector is connected in Cowork, then try again, or ping Jaime." (No
repo write access is required — only the ability to open an issue.)
