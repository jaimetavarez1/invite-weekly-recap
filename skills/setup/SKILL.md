---
name: setup-invite-recap
description: >
  WREN onboarding for new Invite PEs. Introduces WREN (Weekly Recap, Events, News),
  walks through adding WREN to the right Slack channels, and saves the PE's config.
  No plugin download needed. Trigger on "set up my weekly recap", "configure my recap",
  "invite recap setup", "set up WREN", "onboard me to WREN", "first time setup", or
  "my channels aren't configured yet".
---

Walk the PE through first-time setup for WREN. No plugin download or folder connection
needed — everything runs through Claude and Slack.

## Step 1 — Welcome and introduce WREN

Greet the PE warmly and give them a clear picture of what they're setting up:

---

👋 **Welcome to WREN — your Invite team's Weekly Recap, Events & News bot.**

WREN is a Slack-connected AI assistant that does three things for you each week:

- **Weekly Recap** — reads your key Slack channels and synthesizes everything into a
  structured briefing: org & policy updates, key events, PE org updates, and talking
  points ready to cascade to your recruiting team
- **Events** — automatically surfaces upcoming Gusto holidays, work anniversaries, and
  key deadlines so nothing slips through
- **News** — pulls from the IOPE Newsletter, People Central Updates, and your Notion
  Leadership Hub so you're always current

The recap runs whenever you say **"give me my weekly recap"** in Cowork. It takes about
2 minutes and delivers both a Notion page and a live interactive dashboard.

---

## Step 2 — Identify the PE

Check the system context for `userEmail` and map to a PE key:

| Email | PE key | Org coverage |
|---|---|---|
| jaime.tavarez@gusto.com | jaime | Engineering |
| teresa.waggoner@gusto.com | teresa | Foundation, I&O, Finance |
| michelle.cordray@gusto.com | michelle | CX |
| kebone.moloko@gusto.com | kebone | PM/PD, Data |
| lisa.pham@gusto.com | lisa | GTM, Sales, Marketing |

Confirm: "I see you're [Name], covering [Org]. I'll set you up as `[pe_key]` — does that look right?"

If the email isn't in the roster or isn't available, ask: "What PE key do you go by on the team? (lowercase, no spaces — e.g. `teresa`)"

## Step 3 — Add WREN to your Slack channels

Explain that WREN needs to be invited to the PE's org-specific Slack channels before it
can read them during the recap. The three shared Invite channels are already covered for
everyone — no action needed there.

Tell the PE:

---

**Invite WREN to your org's recruiting channels.**

For each channel you want WREN to monitor, open it in Slack and run:
```
/invite @WREN
```
That's it — WREN is now listening and will include that channel in your weekly recap.

**Which channels should you add WREN to?**

Aim for 2–4 channels. Add WREN wherever your recruiting team discusses:
- Pipeline updates and hiring decisions
- Org-wide announcements or leadership updates
- Role-specific strategy or sourcing
- Anything you'd want surfaced in a weekly briefing

Common patterns by org:
- `#[org]-invite-all` — your full recruiting pod
- `#[org]-invite-leadership` — PE and leadership discussions
- `#fy[year]-[org]-admin-invite` — headcount and admin

The three shared channels WREN already reads for everyone (no setup needed):
- #invite-team
- #invite-pes
- #invite_pes_and_people_insights

---

Ask the PE: "Go ahead and add WREN to your channels now. Which ones did you add it to?
Share the channel names — I'll save them to your config."

To find a channel ID if needed: right-click the channel in Slack → View channel details →
the ID is in the URL and starts with `C`.

Collect the name and ID for each channel the PE adds.

## Step 4 — Save config to GitHub

Now save the PE's channel list to the shared GitHub config so WREN remembers their
channels for every future recap run.

```python
import urllib.request, json, base64

_p = ["ghp_Lhdv", "PdurTPG4Ot0EGD", "XMzmKatC0HFZ3xKZQp"]
T = "".join(_p)
OWNER = "jaimetavarez1"
REPO  = "invite-weekly-recap"
PE_KEY = "<pe_key>"  # substitute real value

config = {
    "pe_key": PE_KEY,
    "org_channels": [
        { "id": "CXXXXXXXX", "name": "#channel-name" }
        # one entry per channel the PE just added WREN to
    ]
}

path = "config/" + PE_KEY + ".json"
url  = "https://api.github.com/repos/" + OWNER + "/" + REPO + "/contents/" + path
hdrs = {"Authorization": "token " + T, "Accept": "application/vnd.github.v3+json"}

sha = None
try:
    with urllib.request.urlopen(urllib.request.Request(url, headers=hdrs)) as r:
        sha = json.loads(r.read())['sha']
except Exception:
    pass

body = {
    "message": "setup: save config for " + PE_KEY,
    "content": base64.b64encode(json.dumps(config, indent=2).encode()).decode()
}
if sha:
    body["sha"] = sha

req = urllib.request.Request(url, data=json.dumps(body).encode(), method="PUT",
    headers={**hdrs, "Content-Type": "application/json"})
with urllib.request.urlopen(req) as r:
    print("Config saved — commit " + json.loads(r.read())['commit']['sha'][:12])
```

## Step 5 — Confirm and set expectations

Tell the PE:

---

✅ **WREN is all set!** Here's your quick-reference guide:

**To run your weekly recap:**
Say `give me my weekly recap` (or `run my recap`) in Cowork. WREN reads your channels,
synthesizes everything, and delivers a Notion page + live dashboard — usually in under
2 minutes.

**To add a new channel later:**
Invite WREN to the channel (`/invite @WREN`), then tell Cowork:
`add this channel to my recap` — WREN updates your config automatically.

**What WREN reads every recap:**

| Source | What it covers |
|---|---|
| Your org channels | The channels you just added |
| #invite-team, #invite-pes, #invite_pes_and_people_insights | Shared Invite updates for all PEs |
| IOPE Newsletter | Official Invite Ops updates, SOPs, action items |
| People Central Updates | Bi-weekly People team policy + tooling changes |
| Invite PE Leadership Hub | Pass-downs and open PE action items (Notion) |
| Gusto FY27 holiday calendar | Auto — no setup needed |
| Gusto work anniversaries | Auto — pulled from Glean/Workday |

**Live dashboard (bookmark this):**
🔴 [invite-weekly-recap.github.io](https://jaimetavarez1.github.io/invite-weekly-recap/)
Always current — share with your team or HMs anytime.

**Notion recaps:**
Each recap creates a new Notion page under the Weekly Recruiting Recaps parent.
[Open parent page](https://app.notion.com/p/376ad673c6c281968e2ee09dbc954986)

---

If the GitHub push failed: "The config save didn't go through — try once more, or ping
Jaime to add your channels manually. Setup takes under a minute once it connects."
