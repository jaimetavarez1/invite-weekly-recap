---
name: setup-invite-recap
description: >
  First-time setup for the Invite Weekly Recap plugin. Introduces the recap,
  confirms the PE's key, collects the org-specific Slack channels to include, and
  saves the PE's config to GitHub. The recap runs through Cowork using the PE's own
  Slack connection — no bot to invite. Trigger on "set up my weekly recap",
  "configure my recap", "invite recap setup", "first time setup", or "my channels
  aren't configured yet".
---

Walk the PE through first-time setup for the Weekly Recruiting Recap. Everything runs
through Cowork (Claude) using the PE's own connected Slack, Notion, and GitHub — there is
no bot to invite to channels.

## Step 1 — Welcome and introduce the recap

Greet the PE warmly and give them a clear picture of what they're setting up:

---

👋 **Welcome to your Invite Weekly Recruiting Recap.**

Each week, the recap does three things for you:

- **Recap** — reads your key Slack channels and synthesizes everything into a
  structured briefing: org & policy updates, key events, PE org updates, and talking
  points ready to cascade to your recruiting team
- **Events** — surfaces upcoming Gusto holidays, work anniversaries, and key deadlines
- **News** — pulls from the IOPE Newsletter, People Central Updates, and your Notion
  Leadership Hub so you're always current

It runs whenever you say **"give me my weekly recap"** in Cowork, using **your own Slack
connection** — so it reads every channel you're a member of, public and private, with no
bot to invite. It delivers a Notion page and updates the live dashboard, usually in under
2 minutes.

---

## Step 2 — Confirm connectors

Make sure the PE has these connectors authorized in Cowork:

- **Slack** — this is what the recap reads from (uses the PE's own access)
- **Notion** — so the recap can publish the weekly page
- **GitHub** — so the PE's config and dashboard data are saved

If any are missing, point the PE to Cowork's connector settings before continuing.

## Step 3 — Identify the PE

Check the system context for `userEmail` and map to a PE key:

| Email | PE key | Org coverage |
|---|---|---|
| jaime.tavarez@gusto.com | jaime | Engineering, Data |
| teresa.waggoner@gusto.com | teresa | Foundation, I&O, Finance |
| michelle.cordray@gusto.com | michelle | CX |
| kebone.moloko@gusto.com | kebone | PM/PD |
| lisa.pham@gusto.com | lisa | GTM, Sales, Marketing |

Confirm: "I see you're [Name], covering [Org]. I'll set you up as `[pe_key]` — does that look right?"

If the email isn't in the roster or isn't available, ask: "What PE key do you go by on the team? (lowercase, no spaces — e.g. `teresa`)"

## Step 4 — Collect the PE's org channels

The recap reads whatever channels the PE lists here, using the PE's own Slack access. The
three shared Invite channels are already included for everyone — no need to list them.

Tell the PE:

---

**Which Slack channels should your recap include?**

Aim for 2–4 channels where your recruiting team discusses:
- Pipeline updates and hiring decisions
- Org-wide announcements or leadership updates
- Role-specific strategy or sourcing
- Anything you'd want surfaced in a weekly briefing

Common patterns by org:
- `#[org]-invite-all` — your full recruiting pod
- `#[org]-invite-leadership` — PE and leadership discussions
- `#fy[year]-[org]-admin-invite` — headcount and admin

You don't need to invite anything to these channels — because the recap runs with your own
Slack access, it can already read every channel you're a member of, including private ones.

The three shared channels already included for everyone (no setup needed):
- #invite-team
- #invite-pes
- #invite_pes_and_people_insights

---

Ask the PE: "Which channels do you want included? Share the names — I'll save them to your
config." To find a channel ID if needed: right-click the channel in Slack → View channel
details → the ID is in the URL and starts with `C`.

Collect the name and ID for each channel.

## Step 5 — Save config to GitHub

Save the PE's channel list to the shared GitHub config using the **connected GitHub
connector** (do not use an embedded token). Write to `config/<pe_key>.json` in the
`jaimetavarez1/invite-weekly-recap` repo on the `main` branch. If the file already exists,
fetch its SHA first and include it in the update.

Config shape:

```json
{
  "pe_key": "<pe_key>",
  "org_channels": [
    { "id": "CXXXXXXXX", "name": "#channel-name" }
  ]
}
```

Use `create_or_update_file` (or `push_files`) on the GitHub connector with a commit message
like `setup: save config for <pe_key>`.

## Step 6 — Confirm and set expectations

Tell the PE:

---

✅ **You're all set!** Here's your quick-reference guide:

**To run your weekly recap:**
Say `give me my weekly recap` (or `run my recap`) in Cowork. It reads your channels,
synthesizes everything, and delivers a Notion page + live dashboard — usually in under
2 minutes.

**To add or change channels later:**
Run `set up my weekly recap` again and update your channel list.

**What every recap reads:**

| Source | What it covers |
|---|---|
| Your org channels | The channels you listed |
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

If the GitHub config save failed: "The config save didn't go through — try once more, or
ping Jaime to add your channels manually. Setup takes under a minute once it connects."
