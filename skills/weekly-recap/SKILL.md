---
name: invite-weekly-recap
description: >
  Generates a weekly recruiting recap for an Invite PE at Gusto. Reads the PE's
  configured org Slack channels plus shared Invite channels, reads the IOPE
  Newsletter, pushes structured JSON to the shared GitHub repo, and creates a
  new Notion page. Trigger on "give me my weekly recap", "run my recap",
  "weekly update", "what happened this week in recruiting", or "run the invite
  recap".
---

Generate the weekly recruiting recap for the PE running this skill.

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

```python
import urllib.request, json, base64

_p = ["ghp_Lhdv", "PdurTPG4Ot0EGD", "XMzmKatC0HFZ3xKZQp"]
T = "".join(_p)
PE_KEY = "<detected_pe_key>"
url = f"https://api.github.com/repos/jaimetavarez1/invite-weekly-recap/contents/config/{PE_KEY}.json"
hdrs = {"Authorization": f"token {T}", "Accept": "application/vnd.github.v3+json"}
req = urllib.request.Request(url, headers=hdrs)
try:
    with urllib.request.urlopen(req) as r:
        config = json.loads(base64.b64decode(json.loads(r.read())['content']).decode())
except Exception as e:
    print(f"CONFIG_NOT_FOUND: {e}")
    # Stop and tell PE to run setup first
```

If `CONFIG_NOT_FOUND`: stop and tell the PE: "I couldn't find your config. Please say 'set up my weekly recap' first — it only takes a minute."

Extract from config:
- `org_channels` — list of `{id, name}` objects for the PE's org-specific channels
- `pe_key` — used for the GitHub data push path

The shared team token `T` is assembled above — no local file or folder needed.

## Step 0b — Channel discovery (auto-assign newly added channels)

After loading config, check whether any Slack channels have been newly added to the bot since the last recap. This only needs to run once per new channel — once a channel is mapped to a PE's config, it is stored permanently and does not need to be re-checked.

**1. Load all known channels across all PE configs:**

```python
import json, base64, urllib.request

ALL_PE_KEYS = ["jaime", "teresa", "lisa", "michelle", "kebone"]
known_channels = {}  # channel_id -> pe_key

for pe in ALL_PE_KEYS:
    url = f"https://api.github.com/repos/jaimetavarez1/invite-weekly-recap/contents/config/{pe}.json"
    req = urllib.request.Request(url, headers={
        "Authorization": f"token {T}", "Accept": "application/vnd.github.v3+json"
    })
    try:
        with urllib.request.urlopen(req) as r:
            pe_config = json.loads(base64.b64decode(json.loads(r.read())['content']).decode())
            for ch in pe_config.get("org_channels", []):
                known_channels[ch["id"]] = pe
    except:
        pass
```

**2. Search for channels where the bot is a member:**

Use `slack_search_channels` with the query `invite-weekly-recap` (or the bot's name) to find channels where it was recently added. Alternatively, use `slack_list_channel_members` on the shared channels already known, and check for any channels that appear in the bot's workspace membership but are not in `known_channels`.

If no new channels are found, skip the rest of Step 0b entirely.

**3. For each new channel not yet in any PE config:**

a. Read the channel's history using `slack_read_channel` with `limit: 50` to find the `bot_join` or `channel_join` event that corresponds to when the bot was added.

b. Identify the Slack user ID who performed the join action from that event's `user` field.

c. Look up that user's profile using `slack_read_user_profile` to get their email.

d. Map their email to a PE key using the table in Step 0. If no match is found, skip this channel and log a warning.

e. Add the new channel to the matched PE's `org_channels` list in their GitHub config file. Push the updated config:

```python
# Load existing PE config
pe_url = f"https://api.github.com/repos/jaimetavarez1/invite-weekly-recap/contents/config/{matched_pe}.json"
req = urllib.request.Request(pe_url, headers={"Authorization": f"token {T}", "Accept": "application/vnd.github.v3+json"})
with urllib.request.urlopen(req) as r:
    raw = json.loads(r.read())
    existing_sha = raw['sha']
    pe_config = json.loads(base64.b64decode(raw['content']).decode())

# Add new channel
pe_config["org_channels"].append({"id": new_channel_id, "name": new_channel_name})

# Push update
updated_content = base64.b64encode(json.dumps(pe_config, indent=2).encode()).decode()
body = {"message": f"Add channel #{new_channel_name} to {matched_pe} config", "content": updated_content, "sha": existing_sha}
req2 = urllib.request.Request(pe_url, data=json.dumps(body).encode(), method="PUT",
    headers={"Authorization": f"token {T}", "Content-Type": "application/json"})
with urllib.request.urlopen(req2) as r:
    json.loads(r.read())
```

f. If the new channel belongs to the running PE, re-read the running PE's config so the new channel is included in Step 1.

**Do not re-check channel ownership on subsequent runs** — once a channel is stored in a PE's config it stays there. Only newly discovered channels (not yet in any config) go through this process.

## Step 1 — Read Slack channels (past 7 days)

Calculate the Unix timestamp for 7 days ago at runtime using Python or bash:
```python
import datetime
oldest = str((datetime.datetime.utcnow() - datetime.timedelta(days=7)).timestamp())
```

Read the following channels with `oldest` set to that timestamp and `limit: 100`:

**Shared channels (same for every PE):**
- `C0517BVP04V` — #invite-team
- `C0AFC07JJKA` — #invite-pes
- `C0B0PPHSCUA` — #invite_pes_and_people_insights

**PE's org channels (from config `org_channels`):**
- Read each channel ID listed in the config

If a channel returns an error or no messages, note it and continue.

## Step 1b — Search Slack for R&D org-wide updates (R&D PEs only)

If the PE's `pe_key` is `jaime` (R&D org), run the following Slack searches using `slack_search_public_and_private` with `after` set to the 7-day-ago timestamp. These catch org-wide R&D announcements that don't appear in invite-specific channels:

Search queries to run (one at a time):
- `"deep work week" in:#r-and-d-invite-all` — R&D no-meetings weeks that affect recruiting scheduling
- `"R&D" "week" in:#invite-team` — any R&D-specific callouts in the invite-team channel
- `"r-and-d" hiring OR recruiting` — org-wide hiring announcements

For each result:
- Apply the same source integrity and thread age filters from Step 3
- Only include items where the original message is within the past 7 days
- Add valid results to the PE-specific updates bucket for synthesis in Step 3

If the PE's `pe_key` is not `jaime`, skip this step entirely. Other PEs should add equivalent org-wide search queries to this step when their plugin is configured.


## Step 1c — Read Leadership Hub (Notion)

Pull active pass-downs and open action items from the Invite PE Leadership Hub.

**Cascade to Your Teams** (pass-downs from Kristin/leadership — things that need to move downstream to your recruiters):

Use `notion-query-data-sources` with:
- `data_source_id`: `collection://7c90c5eb-ca2f-42c1-a29a-66e2d7bbbbd9`
- SQL:
```sql
SELECT "Action", "Status", "Due Date", "Notes"
FROM "collection://7c90c5eb-ca2f-42c1-a29a-66e2d7bbbbd9"
WHERE "Status" NOT IN ('Cascaded ✓', 'Archived')
ORDER BY createdTime DESC
```

**PE Action Items** (open tasks owned by PEs):

Use `notion-query-data-sources` with:
- `data_source_id`: `collection://07af0c0a-3fe8-4531-af0a-fe315fda0aed`
- SQL:
```sql
SELECT "Action", "Status", "Priority", "Due Date", "Notes"
FROM "collection://07af0c0a-3fe8-4531-af0a-fe315fda0aed"
WHERE "Status" NOT IN ('Done ✓', 'Archived')
ORDER BY createdTime DESC
```

Store results for filtering in Step 3. If either query fails or returns no results, note it and continue.

**Important — 7-day relevance filter:** Leadership Hub items will only be included in the final recap if they were explicitly mentioned or referenced in Slack messages or the IOPE Newsletter within the current 7-day review window. Do not surface action items solely because they exist in the Leadership Hub — they must have been actively discussed or referenced this week.

## Step 2 — Read the IOPE Newsletter

The IOPE Newsletter is now a Notion gallery database. Read the two most recent entries:

Use `notion-query-data-sources` with:
- `data_source_id`: `collection://37dad673-c6c2-802c-b922-000bd954d35c`
- SQL:
```sql
SELECT *
FROM "collection://37dad673-c6c2-802c-b922-000bd954d35c"
ORDER BY createdTime DESC
LIMIT 2
```

For each result, fetch the full page content using `notion-fetch` with the page ID.

If inaccessible, note it and continue.


## Step 2b — Read People Central Updates (Bi-weekly)

Read the People Central Updates Google Site via Glean:
`https://sites.google.com/gusto.com/people-central-updates/home`

Use the `read_document` tool (Glean). If inaccessible, try a Glean search:
`search` with query `"people central updates" site:sites.google.com` to find the most recent entries.

This is a bi-weekly People team publication. Pull any entries published in the past **14 days** (two recap cycles). For each update found:
- Classify into `orgPolicy` if it describes a policy, process, or tooling change affecting recruiting
- Classify into `keyEvents` if it's an announcement, decision, or upcoming date
- Tag with `["all"]` — these apply across all orgs
- Set `source` = "People Central Updates" and `sourceUrl` = "https://sites.google.com/gusto.com/people-central-updates/home"

If the site returns no new content within the past 14 days, skip silently.

## Step 3 — Synthesize content

Classify everything you read into two buckets:

**Shared (orgPolicy + keyEvents)** — sourced from #invite-team, #invite-pes, #invite_pes_and_people_insights, and the IOPE Newsletter only. These are updates that affect all Invite recruiters regardless of org.
- `orgPolicy` = process/tooling/SOP changes (new fields in GH, scorecard rules, offer calculator updates, VMA changes)
- `keyEvents` = decisions, departures, launches, roadmap updates, upcoming dates, company-wide holidays, org-wide events that affect recruiting schedules

**Holiday auto-detection:** At the start of Step 3, run this Python to find any Gusto holidays that fall within the next 14 days and add them to `keyEvents` automatically — do not wait for Slack to mention them:

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
upcoming = []
for name, date in GUSTO_HOLIDAYS_FY27:
    days_away = (date - today).days
    if 0 <= days_away <= 14:
        upcoming.append((name, date, days_away))

for name, date, days in upcoming:
    day_str = date.strftime("%A %B %-d, %Y")
    print(f"ADD TO keyEvents: {name} — {day_str} ({days} days away)")
```

For each holiday printed, add a keyEvent item with:
- `theme`: "Upcoming Holiday"
- `heading`: "{Holiday Name} — {Day Month Date}" (e.g. "Juneteenth — Friday June 19")
- `bullets`: ["[Full holiday name] is {date} — company holiday", "Plan interview scheduling, offers, and candidate comms around this date"]
- `source`: "Gusto FY27 Holiday Calendar"
- `tp.priority`: "yellow" if >7 days away, "red" if ≤7 days away

**Work anniversary auto-detection:** After holiday detection, query Glean to find upcoming work anniversaries across the entire Invite team. Use the following approach to get complete coverage:

Search each PE manager by name — their profile includes the full `directReports` list. Run these 5 `employee_search` calls:

- `query="Jaime Tavarez"` → returns Jaime's profile with all direct reports
- `query="Teresa Waggoner"` → returns Teresa's profile with all direct reports
- `query="Kebone Moloko"` → returns Kebone's profile with all direct reports
- `query="Michelle Cordray"` → returns Michelle's profile with all direct reports
- `query="Lisa Pham"` → returns Lisa's profile with all direct reports

From each result, extract:
1. The manager themselves (name + startDate from the top-level person)
2. All people in their `directReports` array (name + startDate)

Deduplicate the combined list by email, then run:

```python
import datetime

# team_members = list of (name, start_date_str) from all Glean queries, deduplicated by email
today = datetime.date.today()
upcoming_anniversaries = []

for name, start_date_str in team_members:
    start = datetime.date.fromisoformat(start_date_str)
    if start.year >= today.year:
        continue
    years_this = today.year - start.year
    try:
        anniversary_this = start.replace(year=today.year)
    except ValueError:
        anniversary_this = start.replace(year=today.year, day=28)
    if anniversary_this >= today:
        anniversary = anniversary_this
        years = years_this
    else:
        years = years_this + 1
        try:
            anniversary = start.replace(year=today.year + 1)
        except ValueError:
            anniversary = start.replace(year=today.year + 1, day=28)
    days_away = (anniversary - today).days
    if 0 <= days_away <= 14:
        upcoming_anniversaries.append((name, anniversary, years, days_away))

for name, date, years, days in upcoming_anniversaries:
    print(f"ADD TO keyEvents: {name} — {years}-year anniversary on {date.strftime('%A %B %-d')} ({days} days away)")
```

For each anniversary printed, add a keyEvent item with:
- `theme`: "Work Anniversary"
- `heading`: "{Name} — {N}-Year Anniversary · {Month Day}"
- `bullets`: ["{Name} celebrates {N} year{'s' if N>1 else ''} at Gusto on {date}!", "Consider a shoutout in #invite-team or a personal note"]
- `source`: "Glean / Workday"
- `tp.priority`: "yellow" if >7 days away, "red" if ≤7 days away (≤3 days = definitely red)

Group all anniversaries in the same week into a single keyEvent theme block.

**PE-specific (updates)** — sourced from each PE's org channels only. Anything that belongs only to their org and is not already covered in shared.

**Org-wide filter — required:** Only include updates that affect the org broadly. Do NOT include updates about specific named individuals' personal actions or accomplishments (e.g., "Jane completed VMA training", "John attended a conference"). An update qualifies as org-wide if it would be relevant to multiple people in the org — announcements, pipeline signals, exec decisions, team-level events, open role closures, process changes. If an update is only about one person's individual activity, exclude it.

For each PE-specific item:
- Limit to the past 7 days
- Flag items that are ongoing (not new this week) explicitly
- Always cite the source channel and date
- Assign priority: `red` = action required or high urgency, `yellow` = important/FYI, `green` = informational

**Leadership Hub items — 7-day filter:** Only include Leadership Hub items (from Step 1c) if they were explicitly mentioned or referenced in Slack messages or the IOPE Newsletter within the current 7-day window. Cross-reference the item title/action text against the Slack content you read in Step 1. If no matching mention is found, exclude the item entirely.

**Date filter — skip any item whose "Due Date" is in the past.** Compute today's date at runtime and exclude any item where the due date is strictly before it:

```python
import datetime
today = datetime.date.today()
# For each item with a due date:
# due = datetime.date.fromisoformat("YYYY-MM-DD")
# if due < today: skip this item entirely
```

- **Cascade items** (not yet "Cascaded ✓") → add as `orgPolicy` items: `title` = the action, `bullets` = [notes if any, due date if any], `source` = "Leadership Hub", `priority` = "high", `tags` = ["all"]
- **PE Action Items** (not Done/Archived) → add as a `keyEvents` group: `theme` = "PE Action Items", items each with `heading` = action, `bullets` = [priority label, due date if any, notes if any], `source` = "Leadership Hub", `tp.priority` = red/yellow/green based on 🔴/🟡/🟢 prefix

**Departed employee filter:** The following people are no longer at Gusto — skip any message authored by them entirely, do not include in any section:
- Roberto Segovia (roberto.segovia@gusto.com)
- Todd Hazen (todd.hazen@gusto.com)

**Source integrity — critical:** Every item you include must be directly traceable to a specific message you actually read. Do NOT:
- Synthesize or infer summaries that weren't explicitly stated in a channel
- Combine fragments from multiple messages into a new item that didn't exist as a single post
- Include any item you cannot cite with a specific channel, author, and date

If you cannot point to an exact message as the source, leave it out entirely.

**Thread age filter — strict:** Slack returns threads that had *any* activity in the past 7 days, including old threads with new replies. Always check the timestamp of the **original/parent message**:
- If the original message is older than 7 days → **exclude entirely, regardless of what the replies say**
- Only include items where the original message itself was posted within the past 7 days

## Step 4 — Push JSON to GitHub

**Repo:** `jaimetavarez1/invite-weekly-recap`

Before writing any code, extract the values you loaded in Step 0:
- `TOKEN = T` — the shared team token assembled in Step 0 (do NOT use config for this)
- `PE_KEY = config['pe_key']` — from the GitHub config loaded in Step 0

Determine the week string using Monday–Sunday of the current week (e.g. "June 9 – June 15, 2026").

Push `data/shared.json`:
```json
{
  "week": "<week string>",
  "refreshedAt": "<use: datetime.datetime.utcnow().isoformat() + 'Z'>",
  "refreshedBy": "<PE_KEY>",
  "orgPolicy": [
    {
      "title": "",
      "summary": "",
      "bullets": [],
      "source": "",
      "sourceUrl": null,
      "priority": "high|medium|low",
      "tags": ["all"],
      "tp": { "priority": "red|yellow|green", "audience": "", "point": "" }
    }
  ],
  "keyEvents": [
    {
      "theme": "",
      "tags": ["all"],
      "items": [
        {
          "heading": "",
          "bullets": [],
          "source": "",
          "sourceUrl": null,
          "tp": { "priority": "red|yellow|green" }
        }
      ]
    }
  ]
}
```

Push `data/<PE_KEY>.json` (e.g. `data/jaime.json`):
```json
{
  "pe": "<PE_KEY>",
  "week": "<week string>",
  "refreshedAt": "<use: datetime.datetime.utcnow().isoformat() + 'Z'>",
  "updates": [
    { "heading": "", "bullets": [] }
  ]
}
```

Use this Python pattern to push. **Substitute the real TOKEN and PE_KEY values inline before running** — do not leave any placeholder strings:
```python
import json, base64, urllib.request

TOKEN = T  # shared team token assembled in Step 0
OWNER = "jaimetavarez1"
REPO  = "invite-weekly-recap"

def gh_push(path, data_dict, message, retries=2):
    import time
    url = f"https://api.github.com/repos/{OWNER}/{REPO}/contents/{path}"
    last_error = None
    for attempt in range(1, retries + 2):
        try:
            req = urllib.request.Request(url, headers={
                "Authorization": f"token {TOKEN}",
                "Accept": "application/vnd.github.v3+json"
            })
            sha = None
            try:
                with urllib.request.urlopen(req) as r:
                    sha = json.loads(r.read())['sha']
            except:
                pass
            content = base64.b64encode(
                json.dumps(data_dict, indent=2, ensure_ascii=False).encode()
            ).decode()
            body = {"message": message, "content": content}
            if sha:
                body["sha"] = sha
            req2 = urllib.request.Request(
                url, data=json.dumps(body).encode(), method="PUT",
                headers={
                    "Authorization": f"token {TOKEN}",
                    "Content-Type": "application/json"
                }
            )
            with urllib.request.urlopen(req2) as r:
                return json.loads(r.read())['commit']['sha'][:12]
        except Exception as e:
            last_error = e
            if attempt <= retries:
                time.sleep(3)
    raise last_error
```

**If the GitHub push fails with a network or SSL error (e.g. `URLError`, `SSLEOFError`, HTTP 000, or 404):**

Send a Slack DM to the running PE's Slack user ID (see roster below) using `slack_send_message` with this message:

> ⚠️ *Invite Recap — GitHub Push Failed*
> The recap ran successfully but your data couldn't be pushed to GitHub. The live artifact won't update until this is fixed.
> *Fix:* Re-authenticate Cloudflare in your browser, then re-run the recap.

PE Slack user IDs for DMs:
- jaime → U02E8CN9Z7V
- teresa → search slack for teresa.waggoner@gusto.com
- lisa → search slack for lisa.pham@gusto.com
- michelle → search slack for michelle.cordray@gusto.com
- kebone → search slack for kebone.moloko@gusto.com

Then continue to the Notion step — the page should still be created even if GitHub failed.

## Step 5 — Create Notion page

**Parent page ID:** `376ad673-c6c2-8196-8e2e-e09dbc954986`
**Page title format:** `📋 Week of [end date], [year]`
(e.g. `📋 Week of July 20, 2026` — use the Sunday end date of the week, not a date range)

Always use `notion-create-pages` to create a new page. Do NOT search for or update an existing page — each run creates a fresh page to preserve history.

**Page content:**

First block:
> 🔴 **[→ Open Live Interactive Recap](https://invite-weekly-recap.netlify.app/)** — tabs, filters, and one-click Slack summary

Then include all four sections:

```
## 📋 Org & Policy Updates
(orgPolicy items — ### per item, - bullets, *italic* source citations)

---

## 📅 Key Events & Decisions
(keyEvents items — ### per theme, - bullets, *italic* source citations)

---

## 🎯 PE Org Updates

For each PE, read their latest `data/<pe_key>.json` from GitHub and include their updates.
If a PE's JSON is from a prior week (refreshedAt > 7 days ago), note it as "⚠️ Not yet refreshed this week."

### Jaime Tavarez — Engineering
(updates from data/jaime.json)

### Teresa Waggoner — Foundation, I&O, Finance
(updates from data/teresa.json)

### Lisa Pham — GTM, Sales, Marketing
(updates from data/lisa.json)

### Michelle Cordray — Customer Experience
(updates from data/michelle.json)

### Kebone Moloko — PM/PD, Data
(updates from data/kebone.json)
```

To read all PE JSON files for the Notion page, fetch each one from GitHub before creating the page:

```python
ALL_PE_KEYS = ["jaime", "teresa", "lisa", "michelle", "kebone"]
pe_data = {}

for pe in ALL_PE_KEYS:
    url = f"https://api.github.com/repos/jaimetavarez1/invite-weekly-recap/contents/data/{pe}.json"
    req = urllib.request.Request(url, headers={
        "Authorization": f"token {T}", "Accept": "application/vnd.github.v3+json"
    })
    try:
        with urllib.request.urlopen(req) as r:
            pe_data[pe] = json.loads(base64.b64decode(json.loads(r.read())['content']).decode())
    except:
        pe_data[pe] = None  # file doesn't exist yet
```

For each PE section in the Notion page:
- If `pe_data[pe]` is None → write "No data available yet."
- If the `refreshedAt` is more than 7 days ago → write "⚠️ Last updated [date] — not yet refreshed this week."
- Otherwise → write each update as `**heading**` followed by `-` bullets

Use `---` dividers between sections. Bold key terms. Italicize source citations.

## Step 6 — Confirm

Tell the PE the recap is done. Share:
- The Notion page link
- The live artifact link: https://invite-weekly-recap.netlify.app/
- A 2–3 sentence plain-language summary of the most important things this week
