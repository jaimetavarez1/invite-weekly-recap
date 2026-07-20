---
name: invite-weekly-recap
description: >
  Generates a weekly recruiting recap for an Invite PE at Gusto. Reads the PE's
  configured org Slack channels plus shared Invite channels, reads the IOPE
  Newsletter, pushes structured JSON to the shared GitHub repo, and creates a
  new Notion page. Trigger on "give me my weekly recap", "run my recap",
  "weekly update", "what happened this week in recruiting", or "run the invite
  recap". Also handles mid-week live artifact refreshes — trigger on "refresh my
  recap", "refresh the live artifact", "add new updates", or "update my recap".
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

## Step 0b — Detect run mode

Determine whether this is a **full run** or a **refresh** based on what the PE said:

| Trigger phrases | Mode |
|---|---|
| "give me my weekly recap", "run my recap", "weekly update", "what happened this week" | `FULL` |
| "refresh my recap", "refresh the live artifact", "add new updates", "update my recap", "refresh" | `REFRESH` |

Set `MODE = "FULL"` or `MODE = "REFRESH"` and carry it through every subsequent step.

**Full mode** — runs on Mondays (or whenever the PE explicitly wants a fresh weekly recap). Overwrites all JSON data, creates a new Notion page. This is the clean-slate weekly reset.

**Refresh mode** — runs mid-week to add new updates to the live artifact without removing anything that's already there. Only looks for content since the last `refreshedAt` timestamp. Does NOT create a Notion page. Does NOT clear or overwrite existing data.

If `MODE = "REFRESH"`, load the current `data/shared.json` and `data/<PE_KEY>.json` from GitHub now — these are the baseline you will merge into:

```python
import urllib.request, json, base64

def gh_read(path):
    url = f"https://api.github.com/repos/jaimetavarez1/invite-weekly-recap/contents/{path}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"token {T}", "Accept": "application/vnd.github.v3+json"
    })
    try:
        with urllib.request.urlopen(req) as r:
            raw = json.loads(r.read())
            return json.loads(base64.b64decode(raw['content']).decode()), raw['sha']
    except:
        return None, None

existing_shared, shared_sha = gh_read("data/shared.json")
existing_pe, pe_sha = gh_read(f"data/{PE_KEY}.json")
```

Also extract the `refreshedAt` timestamp from `existing_shared` to use as the `oldest` cutoff in Step 1:

```python
import datetime

if existing_shared and existing_shared.get("refreshedAt"):
    last_refresh = datetime.datetime.fromisoformat(existing_shared["refreshedAt"].replace("Z", "+00:00"))
    oldest = str(last_refresh.timestamp())
else:
    # Fall back to 7 days ago if no prior refresh found
    oldest = str((datetime.datetime.utcnow() - datetime.timedelta(days=7)).timestamp())
```

## Step 0c — Channel discovery (auto-assign newly added channels)

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

If no new channels are found, skip the rest of Step 0c entirely.

**3. For each new channel not yet in any PE config:**

a. Read the channel's history using `slack_read_channel` with `limit: 50` to find the `bot_join` or `channel_join` event that corresponds to when the bot was added.

b. Identify the Slack user ID who performed the join action from that event's `user` field.

c. Look up that user's profile using `slack_read_user_profile` to get their email.

d. Map their email to a PE key using the table in Step 0. If no match is found, skip this channel and log a warning.

e. Add the new channel to the matched PE's `org_channels` list in their GitHub config file. Push the updated config:

```python
pe_url = f"https://api.github.com/repos/jaimetavarez1/invite-weekly-recap/contents/config/{matched_pe}.json"
req = urllib.request.Request(pe_url, headers={"Authorization": f"token {T}", "Accept": "application/vnd.github.v3+json"})
with urllib.request.urlopen(req) as r:
    raw = json.loads(r.read())
    existing_sha = raw['sha']
    pe_config = json.loads(base64.b64decode(raw['content']).decode())

pe_config["org_channels"].append({"id": new_channel_id, "name": new_channel_name})

updated_content = base64.b64encode(json.dumps(pe_config, indent=2).encode()).decode()
body = {"message": f"Add channel #{new_channel_name} to {matched_pe} config", "content": updated_content, "sha": existing_sha}
req2 = urllib.request.Request(pe_url, data=json.dumps(body).encode(), method="PUT",
    headers={"Authorization": f"token {T}", "Content-Type": "application/json"})
with urllib.request.urlopen(req2) as r:
    json.loads(r.read())
```

f. If the new channel belongs to the running PE, re-read the running PE's config so the new channel is included in Step 1.

**Do not re-check channel ownership on subsequent runs** — once a channel is stored in a PE's config it stays there. Only newly discovered channels (not yet in any config) go through this process.

## Step 1 — Read Slack channels

**Full mode:** Use 7 days ago as `oldest`:
```python
import datetime
oldest = str((datetime.datetime.utcnow() - datetime.timedelta(days=7)).timestamp())
```

**Refresh mode:** Use the `oldest` timestamp computed from `refreshedAt` in Step 0b — this limits reads to only content that appeared since the last run.

Read the following channels with `oldest` set to that timestamp and `limit: 100`:

**Shared channels (same for every PE):**
- `C0517BVP04V` — #invite-team
- `C0AFC07JJKA` — #invite-pes
- `C0B0PPHSCUA` — #invite_pes_and_people_insights

**PE's org channels (from config `org_channels`):**
- Read each channel ID listed in the config

If a channel returns an error or no messages, note it and continue.

## Step 1b — Search Slack for R&D org-wide updates (R&D PEs only)

If the PE's `pe_key` is `jaime` (R&D org), run the following Slack searches using `slack_search_public_and_private` with `after` set to the appropriate timestamp (7 days ago for full, `refreshedAt` for refresh). These catch org-wide R&D announcements that don't appear in invite-specific channels:

Search queries to run (one at a time):
- `"deep work week" in:#r-and-d-invite-all`
- `"R&D" "week" in:#invite-team`
- `"r-and-d" hiring OR recruiting`

For each result:
- Apply the same source integrity and thread age filters from Step 3
- Only include items where the original message is within the search window
- Add valid results to the PE-specific updates bucket for synthesis in Step 3

If the PE's `pe_key` is not `jaime`, skip this step entirely.

## Step 1c — Read Leadership Hub (Notion)

Pull active pass-downs and open action items from the Invite PE Leadership Hub.

**Cascade to Your Teams:**

Use `notion-query-data-sources` with:
- `data_source_id`: `collection://7c90c5eb-ca2f-42c1-a29a-66e2d7bbbbd9`
- SQL:
```sql
SELECT "Action", "Status", "Due Date", "Notes"
FROM "collection://7c90c5eb-ca2f-42c1-a29a-66e2d7bbbbd9"
WHERE "Status" NOT IN ('Cascaded ✓', 'Archived')
ORDER BY createdTime DESC
```

**PE Action Items:**

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

**Important — 7-day relevance filter:** Leadership Hub items will only be included in the final recap if they were explicitly mentioned or referenced in Slack messages or the IOPE Newsletter within the current search window.

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

Use the `read_document` tool (Glean). If inaccessible, try a Glean search for `"people central updates" site:sites.google.com`.

Pull any entries published in the past **14 days**. For each update found:
- Classify into `orgPolicy` if it describes a policy, process, or tooling change affecting recruiting
- Classify into `keyEvents` if it's an announcement, decision, or upcoming date
- Tag with `["all"]`
- Set `source` = "People Central Updates"

If no new content within 14 days, skip silently.

## Step 3 — Synthesize content

Classify everything you read into two buckets:

**Shared (orgPolicy + keyEvents)** — sourced from #invite-team, #invite-pes, #invite_pes_and_people_insights, and the IOPE Newsletter only.
- `orgPolicy` = process/tooling/SOP changes
- `keyEvents` = decisions, departures, launches, roadmap updates, upcoming dates, holidays, org-wide events

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

For each holiday printed, add a keyEvent item with:
- `theme`: "Upcoming Holiday"
- `heading`: "{Holiday Name} — {Day Month Date}"
- `bullets`: ["Company holiday — plan interview scheduling and candidate comms accordingly"]
- `source`: "Gusto FY27 Holiday Calendar"
- `tp.priority`: "yellow" if >7 days away, "red" if ≤7 days away

**Work anniversary auto-detection:** Query Glean via `employee_search` for each PE manager (Jaime Tavarez, Teresa Waggoner, Kebone Moloko, Michelle Cordray, Lisa Pham). Extract each manager and their `directReports`. Deduplicate by email, then find anyone whose work anniversary falls within the next 14 days. Add as keyEvent items with `theme`: "Work Anniversary".

**PE-specific (updates)** — sourced from each PE's org channels and Step 1b R&D searches.

**Org-wide filter — required:** Only include updates relevant to multiple people in the org. Exclude updates about specific individuals' personal actions or accomplishments.

**Leadership Hub — 7-day relevance filter:** Only include if explicitly mentioned in Slack or the IOPE Newsletter this week.

**Date filter:** Skip any Leadership Hub item whose "Due Date" is strictly before today.

**Departed employee filter:** Skip all messages from Roberto Segovia (roberto.segovia@gusto.com) and Todd Hazen (todd.hazen@gusto.com).

**Source integrity:** Every item must be traceable to a specific message. Do not synthesize or infer.

**Thread age filter:** Only include items where the **original** parent message was posted within the search window. Exclude threads whose parent is older, even if there were recent replies.

## Step 4 — Push JSON to GitHub

**Repo:** `jaimetavarez1/invite-weekly-recap`

```python
import datetime
today = datetime.date.today()
start = today - datetime.timedelta(days=7)
week_str = f"{start.strftime('%B %-d')} – {today.strftime('%B %-d, %Y')}"
now_iso = datetime.datetime.utcnow().isoformat() + "Z"
```

---

### Full mode — overwrite

Build `shared.json` and `data/<PE_KEY>.json` from scratch using the synthesized content and push with `gh_push`. This completely replaces any existing data.

`data/shared.json` shape:
```json
{
  "week": "<week_str>",
  "refreshedAt": "<now_iso>",
  "refreshedBy": "<PE_KEY>",
  "orgPolicy": [ ... ],
  "keyEvents": [ ... ]
}
```

`data/<PE_KEY>.json` shape:
```json
{
  "pe": "<PE_KEY>",
  "week": "<week_str>",
  "refreshedAt": "<now_iso>",
  "updates": [ ... ]
}
```

---

### Refresh mode — merge, never remove

Load `existing_shared` and `existing_pe` (already fetched in Step 0b). Merge newly synthesized items INTO the existing data. **Never delete or overwrite existing items.**

**Deduplication rules:**
- `orgPolicy`: skip any new item whose `title` already exists in `existing_shared["orgPolicy"]`
- `keyEvents`: for each new theme, find the matching theme by `theme` name in the existing list:
  - If the theme exists, append only items whose `heading` is not already present in that theme
  - If the theme doesn't exist yet, append the entire theme block
- PE `updates`: skip any new item whose `heading` already exists in `existing_pe["updates"]`

```python
import json, base64, urllib.request, datetime

now_iso = datetime.datetime.utcnow().isoformat() + "Z"

# --- Merge shared.json ---
merged_shared = existing_shared.copy() if existing_shared else {
    "week": week_str, "orgPolicy": [], "keyEvents": []
}
merged_shared["refreshedAt"] = now_iso
merged_shared["refreshedBy"] = PE_KEY

# Merge orgPolicy
existing_titles = {p["title"] for p in merged_shared.get("orgPolicy", [])}
for item in new_org_policy_items:
    if item["title"] not in existing_titles:
        merged_shared["orgPolicy"].append(item)
        existing_titles.add(item["title"])

# Merge keyEvents
existing_themes = {t["theme"]: t for t in merged_shared.get("keyEvents", [])}
for new_theme in new_key_event_themes:
    name = new_theme["theme"]
    if name in existing_themes:
        existing_headings = {i["heading"] for i in existing_themes[name].get("items", [])}
        for item in new_theme.get("items", []):
            if item["heading"] not in existing_headings:
                existing_themes[name]["items"].append(item)
                existing_headings.add(item["heading"])
    else:
        merged_shared["keyEvents"].append(new_theme)
        existing_themes[name] = new_theme

# --- Merge PE json ---
merged_pe = existing_pe.copy() if existing_pe else {
    "pe": PE_KEY, "week": week_str, "updates": []
}
merged_pe["refreshedAt"] = now_iso

existing_headings = {u["heading"] for u in merged_pe.get("updates", [])}
for item in new_pe_updates:
    if item["heading"] not in existing_headings:
        merged_pe["updates"].append(item)
        existing_headings.add(item["heading"])
```

Push `merged_shared` to `data/shared.json` and `merged_pe` to `data/<PE_KEY>.json` using the SHAs loaded in Step 0b.

---

**Push helper (both modes):**

```python
def gh_push(path, data_dict, message, sha=None, retries=2):
    import time
    url = f"https://api.github.com/repos/jaimetavarez1/invite-weekly-recap/contents/{path}"
    last_error = None
    for attempt in range(1, retries + 2):
        try:
            if sha is None:
                req = urllib.request.Request(url, headers={
                    "Authorization": f"token {T}",
                    "Accept": "application/vnd.github.v3+json"
                })
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
                headers={"Authorization": f"token {T}", "Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req2) as r:
                return json.loads(r.read())['commit']['sha'][:12]
        except Exception as e:
            last_error = e
            if attempt <= retries:
                time.sleep(3)
    raise last_error
```

**If push fails:** Send a Slack DM to the PE's user ID:

> ⚠️ *Invite Recap — GitHub Push Failed*
> Your data couldn't be pushed to GitHub. The live artifact won't update until this is fixed.
> *Fix:* Re-authenticate Cloudflare in your browser, then try again.

PE Slack user IDs:
- jaime → U02E8CN9Z7V
- teresa → search for teresa.waggoner@gusto.com
- lisa → search for lisa.pham@gusto.com
- michelle → search for michelle.cordray@gusto.com
- kebone → search for kebone.moloko@gusto.com

## Step 5 — Create Notion page (full mode only)

**Skip this step entirely in refresh mode.** Refreshes update the live artifact only — no new Notion page.

**Full mode only:**

**Parent page ID:** `376ad673-c6c2-8196-8e2e-e09dbc954986`

**Page title format:** `Week of [today's date], [year]` (e.g. `Week of July 20, 2026`)

Set page `icon` to `📋`.

```json
{
  "properties": { "title": "Week of [today's date], [year]" },
  "icon": "📋"
}
```

**Page content:**

First block:
> 🔴 **[→ Open Live Interactive Recap](https://jaimetavarez1.github.io/invite-weekly-recap/)** — tabs, filters, and one-click Slack summary

Then include all four sections:

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

Fetch each PE's data file from GitHub before creating the page:

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
        pe_data[pe] = None
```

For each PE section: if `None` → "No data available yet." Otherwise render each update as `**heading**` + `-` bullets.

## Step 6 — Confirm

**Full mode:**
Tell the PE the recap is done. Share:
- The Notion page link
- The live artifact link: https://jaimetavarez1.github.io/invite-weekly-recap/
- A 2–3 sentence plain-language summary of the most important things this week

**Refresh mode:**
Tell the PE what was added. Share:
- How many new items were added (orgPolicy, keyEvents, PE updates — by count)
- The live artifact link: https://jaimetavarez1.github.io/invite-weekly-recap/
- Note that existing updates were preserved and nothing was removed
- Example: "Added 2 new org policy items and 1 PE update to the live artifact. Everything from earlier this week is still there."
