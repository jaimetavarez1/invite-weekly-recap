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

## Step 2 — Read the IOPE Newsletter

Read the two most recent entries from the IOPE Newsletter Google Doc via Glean:
`https://docs.google.com/document/d/1cv_04zDPx7PtSCZtXnDnpSDdHqaNdG5jJZiy0I12fC4/edit`

Use the `read_document` tool (Glean). If inaccessible, note it and continue.

## Step 3 — Synthesize content

Classify everything you read into two buckets:

**Shared (orgPolicy + keyEvents)** — sourced from #invite-team, #invite-pes, #invite_pes_and_people_insights, and the IOPE Newsletter only. These are updates that affect all Invite recruiters regardless of org.
- `orgPolicy` = process/tooling/SOP changes (new fields in GH, scorecard rules, offer calculator updates, VMA changes)
- `keyEvents` = decisions, departures, launches, roadmap updates, upcoming dates

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
  "refreshedAt": "<ISO timestamp>",
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
  "refreshedAt": "<ISO timestamp>",
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

## Step 5 — Create Notion page

**Parent page ID:** `376ad673-c6c2-8196-8e2e-e09dbc954986`
**Page title format:** `📋 Week of [start] – [end], [year]`

Always use `notion-create-pages` to create a new page. Do NOT search for or update an existing page — each run creates a fresh page to preserve history.

**Page content — shared sections only (no PE-specific org updates):**

First block:
> 🔴 **[→ Open Live Interactive Recap](https://jaimetavarez1.github.io/invite-weekly-recap/)** — tabs, filters, and one-click Slack summary

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
- The live artifact link: https://jaimetavarez1.github.io/invite-weekly-recap/
- A 2–3 sentence plain-language summary of the most important things this week
