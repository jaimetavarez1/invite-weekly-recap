# How to find a Slack channel ID

1. Open Slack and navigate to the channel
2. Right-click the channel name in the left sidebar
3. Select "View channel details"
4. The channel ID appears in the browser URL — it starts with `C` and is 9–11 characters long (e.g. `C05V6DJ5QPQ`)

Alternatively: open the channel, click the channel name at the top → the ID is shown at the bottom of the "About" panel.

# Shared channels (already hardcoded — do not add to config)

These are read for every PE automatically:

| Channel | ID |
|---|---|
| #invite-team | C0517BVP04V |
| #invite-pes | C0AFC07JJKA |
| #invite_pes_and_people_insights | C0B0PPHSCUA |

# Common org channel patterns

Add your org's equivalents to your config:

| Pattern | Example |
|---|---|
| `#[org]-invite-all` | #r-and-d-invite-all, #cx-invite-all |
| `#[org]-invite-leadership` | #r-and-d-invite-leadership |
| `#fy26-[org]-admin-invite` | #fy26-r-and-d-admin-invite |
| Any other org-specific recruiting channels | — |
