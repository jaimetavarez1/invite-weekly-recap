---
name: invite-weekly-recap
description: >
  Generates a weekly recruiting recap for an Invite PE at Gusto. Reads the PE's
  configured org Slack channels plus shared Invite channels using the PE's own
  Slack connector, reads the IOPE Newsletter and Leadership Hub, pushes structured
  JSON to the shared GitHub repo using the PE's own GitHub connector, and creates a
  new Notion page. Trigger on "give me my weekly recap", "run my recap", "weekly
  update", "what happened this week in recruiting", or "run the invite recap". Also
  handles mid-week live artifact refreshes — trigger on "refresh my recap", "refresh
  the live artifact", "add new updates", or "update my recap".
---

Generate the weekly recruiting recap for the PE running this skill.

**How this runs:** Everything happens in the PE's own Cowork session using **their own
connectors** — Slack, Notion, and GitHub. There is no shared bot and no embedded token:

- **Slack** is read through the PE's Slack connector, so it can see every channel the PE
  is a member of, public and private — no bot invite needed.
- **GitHub** reads and writes go through the PE's GitHub connector. The PE must have write
  access to `jaimetavarez1/invite-weekly-recap` (they're added as a collaborator).
- **Notion** page creation goes through the PE's Notion connector.

Throughout this skill, use the connector tools available in the session (e.g.
`slack_read_channel`, `slack_search_public_and_private`, `notion-query-data-sources`,
`notion-fetch`, `notion-create-pages`, and the GitHub connector's file read/write tools).
Do **not** use raw `urllib` calls with a hardcoded token — there is no shared token anymore.

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

**Load config from GitHub (via the GitHub connector):**

Read `config/<pe_key>.json` from `jaimetavarez1/invite-weekly-recap` (branch `main`) using
the GitHub connector's file-read tool (e.g. `get_file_contents`). Parse it as JSON.

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

**Refresh mode** — mid-week top-up. Adds new updates to the live artifact without removing
anything already there. Does NOT create a Notion page.

If `MODE = REFRESH`, read the current `data/shared.json` and `data/<pe_key>.json` from GitHub
(via the connector) now — these are the baseline you'll merge into. Extract the `refreshedAt`
timestamp from `shared.json` to use as the `oldest` cutoff for Slack reads in Step 1. If no
prior `refreshedAt` exists, fall back to 7 days ago.

## Step 1 — Read Slack channels (via the PE's Slack connector)

**Full mode:** set `oldest` to 7 days ago.
**Refresh mode:** set `oldest` to the `refreshedAt` timestamp from Step 0b.

Using the PE's Slack connector (`slack_read_channel`), read messages from each of these with
`oldest` set accordingly and `limit: 100`:

- The three shared channels (IDs above)
- Every channel ID in the PE's `org_channels`

Because this uses the PE's own Slack access, private channels the PE belongs to are readable
directly — no invite step. If a channel returns an error or no messages, note it and continue.

## Step 1b — Search Slack for R&D org-wide updates (jaime only)

If `pe_key` is `jaime`, run these searches with the PE's Slack connector
(`slack_search_public_and_private`), with `after` set to the search-window start (7 days ago
for full, `refreshedAt` for refresh):

- `"deep work week" in:#r-and-d-invite-all`
- `"R&D" "week" in:#invite-team`
- `"r-and-d" hiring OR recruiting`

Apply the same source-integrity and thread-age filters from Step 3. Only include items whose
original message falls within the window. Add valid results to jaime's updates bucket.

If `pe_key` is not `jaime`, skip this step.

## Step 1c — Read Leadership Hub (Notion)

Pull active pass-downs and open action items from the Invite PE Leadership Hub via
`notion-query-data-sources`.

**Cascade to Your Teams:**
- `data_source_id`: `collection://7c90c5eb-ca2f-42c1-a29a-66e2d7bbbbd9`
```sql
SELECT "Action", "Status", "Due Date", "Notes"
FROM "collection://7c90c5eb-ca2f-42c1-a29a-66e2d7bbbbd9"
WHERE "Status" NOT IN ('Cascaded ✓', 'Archived')
ORDER BY createdTime DESC
```

**PE Action Items:**
- `data_source_id`: `collection://07af0c0a-3fe8-4531-af0a-fe315fda0aed`
```sql
SELECT "Action", "Status", "Priority", "Due Date", "Notes"
FROM "collection://07af0c0a-3fe8-4531-af0a-fe315fda0aed"
WHERE "Status" NOT IN ('Done ✓', 'Archived')
ORDER BY createdTime DESC
```

Store results for filtering in Step 3. If a query fails or returns nothing, note it and
continue.

**7-day relevance filter:** Leadership Hub items are only included if they were explicitly
mentioned or referenced in Slack or the IOPE Newsletter within the current window.

## Step 2 — Read the IOPE Newsletter

The IOPE Newsletter is a Notion gallery database. Read the two most recent entries via
`notion-query-data-sources`:
- `data_source_id`: `collection://37dad673-c6c2-802c-b922-000bd954d35c`
```sql
SELECT *
FROM "collection://37dad673-c6c2-802c-b922-000bd954d35c"
ORDER BY createdTime DESC
LIMIT 2
```
Fetch each result's full content with `notion-fetch`. If inaccessible, note it and continue.

## Step 2b — Read People Central Updates (bi-weekly)

Read the People Central Updates Google Site via Glean (`read_document`):
`https://sites.google.com/gusto.com/people-central-updates/home`
If inaccessible, try a Glean search for `"people central updates" site:sites.google.com`.

Pull entries from the past **14 days**. For each: classify into `orgPolicy` (policy/process/
tooling change) or `keyEvents` (announcement/decision/date), tag `["all"]`, set `source` =
"People Central Updates". If nothing new, skip silently.

## Step 3 — Synthesize content

Classify everything into two buckets:

**Shared (orgPolicy + keyEvents)** — sourced from #invite-team, #invite-pes,
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
For each holiday printed, add a keyEvent item — `theme`: "Upcoming Holiday", `heading`:
"{Holiday} — {Day Month Date}", `bullets`: ["Company holiday — plan interview scheduling and
candidate comms accordingly"], `source`: "Gusto FY27 Holiday Calendar", `tp.priority`:
"yellow" if >7 days away, "red" if ≤7 days away.

**Work anniversary auto-detection:** Query Glean via `employee_search` for each PE manager,
extract direct reports, dedup by email, and find anyone whose work anniversary falls within
the next 14 days. Add as keyEvent items with `theme`: "Work Anniversary".

**PE-specific (updates)** — sourced from the PE's org channels and Step 1b results.

**Filters (required):**
- **Org-wide only:** exclude updates about specific individuals' personal actions/accomplishments.
- **Leadership Hub 7-day relevance:** include only if referenced in Slack or IOPE this week.
- **Date filter:** skip Leadership Hub items whose "Due Date" is before today.
- **Departed employees:** skip all messages from Roberto Segovia and Todd Hazen.
- **Source integrity:** every item must trace to a specific message — do not infer.
- **Thread age:** include only items whose original parent message is within the window.

## Step 4 — Push JSON to GitHub (via the PE's GitHub connector)

**Repo:** `jaimetavarez1/invite-weekly-recap`, branch `main`.

Build the week label:
```python
import datetime
today = datetime.date.today()
start = today - datetime.timedelta(days=7)
week_str = f"{start.strftime('%B %-d')} – {today.strftime('%B %-d, %Y')}"
now_iso = datetime.datetime.utcnow().isoformat() + "Z"
```

Write files using the GitHub connector's file-write tool (e.g. `create_or_update_file`, or
`push_files` for both at once). When updating an existing file, first read it to get its
`sha` and pass that in. Never use a hardcoded token.

---

### Full mode — overwrite

`data/shared.json`:
```json
{
  "week": "<week_str>",
  "refreshedAt": "<now_iso>",
  "refreshedBy": "<pe_key>",
  "orgPolicy": [ ... ],
  "keyEvents": [ ... ]
}
```

`data/<pe_key>.json`:
```json
{
  "pe": "<pe_key>",
  "week": "<week_str>",
  "refreshedAt": "<now_iso>",
  "updates": [ ... ]
}
```

---

### Refresh mode — merge, never remove

Start from the `existing_shared` and `existing_pe` you loaded in Step 0b. Merge new items in;
never delete or overwrite existing ones.

- `orgPolicy`: skip any new item whose `title` already exists.
- `keyEvents`: for each new theme, match by `theme` name — if it exists, append only items
  whose `heading` isn't already present; otherwise append the whole theme block.
- PE `updates`: skip any new item whose `heading` already exists.

Update `refreshedAt` (and `refreshedBy` on shared) to now, then write both files back with
their current `sha`.

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

Before creating the page, read each PE's `data/<pe>.json` from GitHub (via the connector) so
the PE Org Updates section reflects everyone's latest data. For each PE section: if the file
is missing → "No data available yet." Otherwise render each update as `**heading**` + `-`
bullets.

## Step 6 — Confirm

**Full mode:** tell the PE it's done and share the Notion page link, the live artifact link
(https://jaimetavarez1.github.io/invite-weekly-recap/), and a 2–3 sentence plain-language
summary of the most important things this week.

**Refresh mode:** tell the PE what was added (counts of new orgPolicy / keyEvents / PE
updates), share the live artifact link, and note that existing updates were preserved and
nothing was removed. Example: "Added 2 new org policy items and 1 PE update to the live
artifact. Everything from earlier this week is still there."

**If a GitHub write fails:** it almost always means the PE's GitHub connector isn't authorized
or lacks write access to the repo. Tell them: "The push to GitHub didn't go through — make
sure your GitHub connector is connected in Cowork and that you've been added as a collaborator
on jaimetavarez1/invite-weekly-recap. Then try again, or ping Jaime."
