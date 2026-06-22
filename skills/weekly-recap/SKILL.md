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

## Step 0 — Load config

Read `pe-config.json` from the connected workspace folder. This file contains the PE's key, GitHub token, and org-specific channel IDs.

If the file does not exist, stop and tell the PE: "I couldn't find your config file. Please say 'set up my weekly recap' first — it only takes a minute."

Once loaded, validate the config before proceeding:
- If `pe_key` is missing or empty → stop: "Your config is missing a pe_key. Please re-run setup."
- If `github_token` is missing, empty, or still the placeholder `ghp_xxxxxxxxxxxxxxxxxxxx` → stop: "Your GitHub token doesn't look right. Please re-run setup and paste a real token."
- If `org_channels` is missing or not a list → stop: "Your org channels aren't configured. Please re-run setup."

Config shape:
```json
{
  "pe_key": "teresa",
  "github_token": "ghp_xxxxxxxxxxxxxxxxxxxx",
  "org_channels": [
    { "id": "CXXXXXXXX", "name": "#cx-invite-all" }
  ]
}
```

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

## Step 2 — Read the IOPE Newsletter

Read the two most recent entries from the IOPE Newsletter Google Doc via Glean:
`https://docs.google.com/document/d/1cv_04zDPx7PtSCZtXnDnpSDdHqaNdG5jJZiy0I12fC4/edit`

Use the `read_document` tool (Glean). If inaccessible, note it and continue.

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

- `query="Jaime Tavarez"` → returns Jaime's profile with all 13 direct reports
- `query="Teresa Waggoner"` → returns Teresa's profile with all 10 direct reports
- `query="Kebone Moloko"` → returns Kebone's profile with all 5 direct reports
- `query="Michelle Cordray"` → returns Michelle's profile with all 5 direct reports
- `query="Lisa Pham"` → returns Lisa's profile with all 4 direct reports

From each result, extract:
1. The manager themselves (name + startDate from the top-level person)
2. All people in their `directReports` array (name + startDate)

Deduplicate the combined list by email, then run:

```python
import datetime

# team_members = list of (name, start_date_str) from all three Glean queries, deduplicated by email
# Example: [("Ashleigh Huffman", "2019-08-05"), ("Jeremy Murdy", "2022-04-04"), ...]

today = datetime.date.today()
upcoming_anniversaries = []

for name, start_date_str in team_members:
    start = datetime.date.fromisoformat(start_date_str)
    
    # Skip anyone who started this year — no anniversary yet
    if start.year >= today.year:
        continue
    
    years_this = today.year - start.year
    
    # Try anniversary this calendar year
    try:
        anniversary_this = start.replace(year=today.year)
    except ValueError:
        anniversary_this = start.replace(year=today.year, day=28)  # Feb 29 edge case
    
    if anniversary_this >= today:
        anniversary = anniversary_this
        years = years_this
    else:
        # Already passed — check next year
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

**PE-specific (updates)** — sourced from the PE's org channels only. Anything that belongs only to their org and is not already covered in shared. Examples: org-specific hiring wins, exec meetings, team announcements, pipeline alerts.

For each item:
- Limit to the past 7 days
- Flag items that are ongoing (not new this week) explicitly
- Always cite the source channel and date
- Assign priority: `red` = action required or high urgency, `yellow` = important/FYI, `green` = informational

**Departed employee filter:** The following people are no longer at Gusto — skip any message authored by them entirely, do not include in any section:
- Roberto Segovia (roberto.segovia@gusto.com)
- Todd Hazen (todd.hazen@gusto.com)

**Source integrity — critical:** Every item you include must be directly traceable to a specific message you actually read. Do NOT:
- Synthesize or infer summaries that weren't explicitly stated in a channel (e.g. do not construct a "Notable Closes" list from names mentioned across different threads)
- Combine fragments from multiple messages into a new item that didn't exist as a single post
- Include any item you cannot cite with a specific channel, author, and date

If you cannot point to an exact message as the source, leave it out entirely.

**Thread age filter — strict:** Slack returns threads that had *any* activity in the past 7 days, including old threads with new replies. Always check the timestamp of the **original/parent message**:
- If the original message is older than 7 days → **exclude entirely, regardless of what the replies say**
- Only include items where the original message itself was posted within the past 7 days

## Step 4 — Push JSON to GitHub

**Repo:** `jaimetavarez1/invite-weekly-recap`

Before writing any code, extract the values you loaded in Step 0:
- `TOKEN` = the exact string value of `github_token` from the config (e.g. `ghp_abc123...`)
- `PE_KEY` = the exact string value of `pe_key` from the config (e.g. `kebone`)

Determine the week string (Monday–Sunday of the current week, e.g. "June 9 – June 15, 2026").

Push `data/shared.json`:
```json
{
  "week": "<week string>",
  "refreshedAt": "<use: datetime.datetime.utcnow().isoformat() + 'Z'>",  // ALWAYS compute at runtime — never hardcode
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

Push `data/<PE_KEY>.json` (e.g. `data/kebone.json`):
```json
{
  "pe": "<PE_KEY>",
  "week": "<week string>",
  "refreshedAt": "<use: datetime.datetime.utcnow().isoformat() + 'Z'>",  // ALWAYS compute at runtime — never hardcode
  "updates": [
    { "heading": "", "bullets": [] }
  ]
}
```

Use this Python pattern to push. **Substitute the real TOKEN and PE_KEY values inline before running** — do not leave any placeholder strings:
```python
import json, base64, urllib.request

TOKEN = "PASTE_REAL_TOKEN_HERE"   # replace with actual github_token from config
OWNER = "jaimetavarez1"
REPO  = "invite-weekly-recap"

def gh_push(path, data_dict, message):
    url = f"https://api.github.com/repos/{OWNER}/{REPO}/contents/{path}"
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
**Page title format:** `Week of [end], [year]`

Always use `notion-create-pages` to create a new page. Do NOT search for or update an existing page — each run creates a fresh page to preserve history.

**Page content — shared sections only (no PE-specific org updates):**

First block:
> 🔴 **[→ Open Live Interactive Recap](https://invite-weekly-recap.netlify.app/)** — tabs, filters, and one-click Slack summary

Then:

```
## 📋 Org & Policy Updates
(orgPolicy items — ## section, ### per item, - bullets, *italic* source citations)

---

## 📅 Key Events & Decisions
(keyEvents items — ### per theme, - bullets, *italic* source citations)
```

Do NOT include PE-specific org updates in the Notion page. That data lives in the GitHub JSON and the live artifact only.

Use `---` dividers between items. Bold key terms. Italicize source citations.

## Step 6 — Confirm

Tell the PE the recap is done. Share:
- The Notion page link
- The live artifact link: https://invite-weekly-recap.netlify.app/
- A 2–3 sentence plain-language summary of the most important things this week
