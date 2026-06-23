---
name: setup-invite-recap
description: >
  First-time setup for the Invite Weekly Recap plugin. Walks the PE through
  configuring their PE key, org-specific Slack channels, and GitHub token, then
  saves a pe-config.json file to their connected workspace folder. Trigger on
  "set up my weekly recap", "configure my recap", "invite recap setup",
  "first time setup", or "my channels aren't configured yet".
---

Walk the PE through first-time configuration for the Invite Weekly Recap.
The goal is to write a `pe-config.json` file to their connected workspace folder.

## What this collects

1. **PE key** — a short lowercase identifier used as their filename in the shared GitHub repo (e.g. `teresa`, `michelle`, `kebone`, `lisa`, `jaime`).
2. **GitHub token** — a personal access token with `repo` scope so the skill can push their weekly JSON to the shared repo. The token is stored locally in their config and never shared.
3. **Org-specific Slack channel IDs** — the 2–5 channels specific to their org. Do NOT include the shared channels — those are already hardcoded in the weekly recap skill for everyone.

## Conversation flow

Greet the PE and explain what you're collecting and why. Keep it casual and short.

Then ask each piece of information conversationally — one at a time if needed. Don't dump all three asks at once.

**For PE key:** ask what name they go by on the Invite PE team (lowercase, no spaces — e.g. `teresa`).

**For GitHub token:** explain that this lets the skill push their weekly recap data to the shared repo. Direct them to:
- Go to github.com → Settings → Developer settings → Personal access tokens → Tokens (classic)
- Generate a new token with `repo` scope
- Paste it here — it will be stored only in their local config file

**For org channels:** explain that these are their org-specific Slack channels (the ones their pod uses that other PE orgs aren't in). Shared channels like #invite-team and #invite-pes are already covered for everyone.

To find a channel ID: right-click the channel in Slack → "View channel details" — the ID appears in the URL and starts with `C`. Walk them through this if needed.

Collect as many org channels as they have (typically 2–5). For each channel, get both the ID and the channel name.

Common org channel patterns to prompt for:
- `#[org]-invite-all` — the all-hands channel for their org's recruiting team
- `#[org]-invite-leadership` — the leadership/PE channel for their org
- Any admin or strategy channels specific to their org

## Save the config

Once you have all three pieces, write `pe-config.json` to the root of their connected workspace folder:

```json
{
  "pe_key": "teresa",
  "github_token": "ghp_xxxxxxxxxxxxxxxxxxxx",
  "org_channels": [
    { "id": "CXXXXXXXX", "name": "#cx-invite-all" },
    { "id": "CXXXXXXXX", "name": "#cx-invite-leadership" }
  ]
}
```

Confirm the file was saved. Tell the PE they're all set and can now say "give me my weekly recap" anytime.

## If no workspace folder is connected

If there is no connected workspace folder (no mounted folder visible), tell the PE:
"To save your config, I need access to a folder on your computer. Click the folder icon in Cowork to connect one, then run setup again."

## Updating config later

If the PE wants to update their channels or token, they can re-run setup (it will overwrite the existing config) or edit `pe-config.json` directly in their workspace folder.

<!-- updated -->