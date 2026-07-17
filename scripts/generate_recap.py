#!/usr/bin/env python3
"""
generate_recap.py — runs entirely inside GitHub Actions (no Cowork session
needed). Replaces the old "fetch SKILL.md from GitHub and execute it"
bootstrap pattern.

What it does, in order:
  1. Auth as the Slack bot (SLACK_BOT_TOKEN) and find every channel it has
     been invited into (users.conversations) — no manual channel-ID list.
  2. For any channel not already in data/channel-map.json, figure out which
     PE owns it:
       a. PRIMARY: read the channel's join history for the message where the
          bot itself was added (subtype channel_join / bot_add) and pull the
          `inviter` field. If the inviter is one of the 5 PEs, that's the owner.
       b. FALLBACK: match the channel name against ORG_SLUG_TO_PE.
       c. Otherwise: mark it "unclassified" and leave it out of every PE's
          recap (surfaced in data/_unclassified_channels.json so the daily
          healthcheck can flag it instead of silently guessing wrong).
     Resolved mappings are cached in data/channel-map.json so history isn't
     re-scanned every week — only genuinely new channels get resolved.
  3. Pull the last 7 days of messages from each PE's channels (their assigned
     channels + the 3 shared Invite channels every PE gets automatically).
  4. jaime only: flags messages matching R&D-wide keywords (deep work week,
     R&D hiring/recruiting) from channels already fetched, in place of the
     old live Slack search (search.messages needs a user token; bots can't
     call it).
  5. Adds deterministic holiday lookahead (next 14 days) — no dependency.
  6. Merges in data/glean-cache.json for anniversaries — this ONE piece stays
     Cowork-only, since it comes from Glean's org-directory search, which has
     no service-account/API path reachable from a GitHub Actions runner.
  7. If CLAUDE_CODE_OAUTH_TOKEN is set, shells out to the Claude Code CLI
     (billed against Jaime's Claude Pro/Max subscription, not a metered API
     key) to turn each PE's raw messages into the same heading/bullets
     write-up format the recap has always used. If it's not set, falls back
     to a plain grouped-by-channel dump and says so in the data, rather than
     silently shipping a worse recap unlabeled.
  8. Writes data/shared.json + data/{pe}.json back via the GitHub Contents
     API using RECAP_GH_TOKEN.

Note: the IOPE Newsletter + Leadership Hub reads and the weekly Notion page
creation do NOT happen here — that's a separate Runlayer-hosted agent
("Invite Weekly Recap — Notion", scheduled Mondays 7:45am MT, ~15 min before
this script runs) that creates the Notion page directly via the Notion
connector, with no NOTION_TOKEN needed. That agent hands its orgPolicy/
keyEvents findings to this script by DMing this bot (Slack user ID
U0BGUH5QX7H) a marked JSON message (see fetch_notion_relay) — deliberately a
DM, not a shared channel, so no new channel membership is needed. If the
relay DM is missing, stale (>4h old), or unparseable, this script logs that
plainly and just proceeds without it rather than failing the whole run.

Secrets expected in the environment (set as GitHub Actions repo secrets):
  SLACK_BOT_TOKEN        — bot token (xoxb-...), scopes: channels:history,
                           groups:history, channels:read, groups:read,
                           im:read, im:history (the last two for the Notion
                           relay DM)
  RECAP_GH_TOKEN         — GitHub PAT with push access to this repo
  CLAUDE_CODE_OAUTH_TOKEN — optional; from running `claude setup-token`
                           locally (requires a Claude Pro/Max subscription).
                           Enables the write-up synthesis step via the
                           Claude Code CLI, which the workflow installs.
"""
import base64
import datetime
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

REPO = "jaimetavarez1/invite-weekly-recap"
API = "https://api.github.com"
SLACK_API = "https://slack.com/api"

# Known Invite PEs and their Slack user IDs (used to resolve "who invited the
# bot" -> which PE owns this channel).
PE_SLACK_IDS = {
    "jaime": "U02E8CN9Z7V",
    "teresa": "USCBB5XNX",
    "kebone": "U020DTP32V7",
    "lisa": "U0A9YJJ5USU",
    "michelle": "U0A6K3AKBJT",
}
SLACK_ID_TO_PE = {v: k for k, v in PE_SLACK_IDS.items()}

# Read for every PE automatically — never assigned to just one PE.
SHARED_CHANNEL_IDS = {
    "C0517BVP04V",  # #invite-team
    "C0AFC07JJKA",  # #invite-pes
    "C0B0PPHSCUA",  # #invite_pes_and_people_insights
}

# FALLBACK ONLY — used when the inviter isn't a recognized PE. Match is a
# substring check against the channel name. Add to this as orgs are confirmed;
# it is deliberately conservative (no match = unclassified, not a guess).
ORG_SLUG_TO_PE = {
    "r-and-d": "jaime",
    "cx": "michelle",
    "gtm": "lisa",
    "data": "kebone",
    "design": "kebone",
    "foundation": "teresa",
}

LOOKBACK_DAYS = 7

# Deterministic — no external dependency, so this can run unattended.
GUSTO_HOLIDAYS_FY27 = [
    ("Juneteenth", datetime.date(2026, 6, 19)),
    ("Independence Day", datetime.date(2026, 7, 3)),
    ("Labor Day", datetime.date(2026, 9, 7)),
    ("Veterans Day", datetime.date(2026, 11, 11)),
    ("Thanksgiving Day", datetime.date(2026, 11, 26)),
    ("Christmas Day", datetime.date(2026, 12, 25)),
]

# jaime (R&D)-only supplemental keyword filter, replacing the old Step 1b
# Slack search — search.messages requires a user token, which a bot doesn't
# have, so this filters messages already pulled from #r-and-d-invite-all /
# #invite-team instead of calling Slack search directly.
RND_KEYWORDS = ["deep work week", "r&d", "r-and-d"]


def detect_upcoming_holidays(today):
    """Mirrors the SKILL.md Step 3 holiday block — returns keyEvents items."""
    items = []
    for name, date in GUSTO_HOLIDAYS_FY27:
        days_away = (date - today).days
        if 0 <= days_away <= 14:
            items.append({
                "heading": f"{name} — {date.strftime('%A %B %-d')}",
                "bullets": [
                    f"{name} is {date.strftime('%A %B %-d, %Y')} — company holiday",
                    "Plan interview scheduling, offers, and candidate comms around this date",
                ],
                "source": "Gusto FY27 Holiday Calendar",
                "sourceUrl": None,
                "tp": {"priority": "red" if days_away <= 7 else "yellow"},
            })
    if not items:
        return []
    return [{"theme": "Upcoming Holiday", "tags": ["all"], "items": items}]


def rnd_keyword_matches(messages):
    """jaime-only: pull out messages matching the R&D keyword patterns from
    channels already fetched, instead of a live Slack search call."""
    matches = []
    for m in messages:
        text = (m.get("text") or "").lower()
        if any(kw in text for kw in RND_KEYWORDS):
            matches.append(m)
    return matches


# ── Slack helpers ────────────────────────────────────────────────────────
def slack_call(method, params, token):
    url = f"{SLACK_API}/{method}"
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    with urllib.request.urlopen(req) as r:
        resp = json.loads(r.read())
    if not resp.get("ok"):
        raise RuntimeError(f"Slack {method} failed: {resp.get('error')}")
    return resp


def slack_bot_user_id(token):
    return slack_call("auth.test", {}, token)["user_id"]


def list_bot_channels(token):
    """Every public + private channel the bot is currently a member of."""
    channels, cursor = [], None
    while True:
        params = {"types": "public_channel,private_channel", "limit": 200, "exclude_archived": "true"}
        if cursor:
            params["cursor"] = cursor
        resp = slack_call("users.conversations", params, token)
        channels.extend(resp.get("channels", []))
        cursor = resp.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break
    return channels


def find_inviter(channel_id, bot_user_id, token, max_pages=10):
    """Page back through history looking for the bot's own join message."""
    cursor = None
    for _ in range(max_pages):
        params = {"channel": channel_id, "limit": 200}
        if cursor:
            params["cursor"] = cursor
        try:
            resp = slack_call("conversations.history", params, token)
        except RuntimeError:
            return None
        for msg in resp.get("messages", []):
            if msg.get("subtype") in ("channel_join", "group_join", "bot_add") and (
                msg.get("user") == bot_user_id or msg.get("inviter")
            ):
                if msg.get("user") == bot_user_id and msg.get("inviter"):
                    return msg["inviter"]
        if not resp.get("has_more"):
            break
        cursor = resp.get("response_metadata", {}).get("next_cursor")
    return None


def channel_messages_since(channel_id, oldest_ts, token):
    messages, cursor = [], None
    while True:
        params = {"channel": channel_id, "oldest": str(oldest_ts), "limit": 200}
        if cursor:
            params["cursor"] = cursor
        resp = slack_call("conversations.history", params, token)
        for m in resp.get("messages", []):
            if m.get("subtype") in ("channel_join", "group_join", "bot_add", "channel_leave"):
                continue
            messages.append(m)
        cursor = resp.get("response_metadata", {}).get("next_cursor")
        if not cursor or not resp.get("has_more"):
            break
    return messages


# ── Notion relay (via Slack DM) ──────────────────────────────────────────
# The "Invite Weekly Recap — Notion" Runlayer agent reads the IOPE Newsletter
# + Leadership Hub directly (no NOTION_TOKEN here — see module docstring),
# then DMs this bot (Slack user ID U0BGUH5QX7H) a marker + JSON code block,
# ~15 minutes before this script runs. Deliberately NOT a shared channel —
# a DM is only visible to the two participants, so no new channel membership
# is needed. Requires the bot's token to have im:read (list its own DMs) and
# im:history (read them) scopes in addition to the channel ones.
NOTION_RELAY_MARKER = "RECAP_NOTION_CACHE_V1"
NOTION_RELAY_MAX_AGE_HOURS = 4  # older than this = treat as stale, not missing


def fetch_notion_relay(token, now):
    """Scans the bot's own DM conversations for the latest RECAP_NOTION_CACHE_V1
    message. Returns (orgPolicy_items, keyEvents_items, status) where status is
    one of "ok", "missing" (no marker message found in any DM), "stale" (found
    but too old), or "error: ..." (the im:read/im:history scopes are probably
    missing)."""
    try:
        resp = slack_call("conversations.list", {"types": "im", "limit": 50}, token)
    except RuntimeError as e:
        return [], [], f"error: {e}"
    for dm in resp.get("channels", []):
        try:
            hist = slack_call("conversations.history", {"channel": dm["id"], "limit": 5}, token)
        except RuntimeError:
            continue
        for msg in hist.get("messages", []):
            text = msg.get("text", "")
            if NOTION_RELAY_MARKER not in text:
                continue
            ts = float(msg.get("ts", 0))
            age_hours = (now.timestamp() - ts) / 3600
            if age_hours > NOTION_RELAY_MAX_AGE_HOURS:
                return [], [], "stale"
            json_part = text.split(NOTION_RELAY_MARKER, 1)[1]
            start, end = json_part.find("{"), json_part.rfind("}") + 1
            try:
                payload = json.loads(json_part[start:end])
            except (ValueError, json.JSONDecodeError):
                return [], [], "unparseable"
            return payload.get("orgPolicy", []), payload.get("keyEvents", []), "ok"
    return [], [], "missing"


# ── GitHub helpers ───────────────────────────────────────────────────────
def gh_get(path, token):
    req = urllib.request.Request(
        f"{API}/repos/{REPO}/contents/{path}",
        headers={"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"},
    )
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def gh_get_json(path, token, default=None):
    f = gh_get(path, token)
    if f is None:
        return default
    return json.loads(base64.b64decode(f["content"]).decode())


def gh_put_json(path, data_dict, token, message):
    existing = gh_get(path, token)
    body = {
        "message": message,
        "content": base64.b64encode(json.dumps(data_dict, indent=2, ensure_ascii=False).encode()).decode(),
    }
    if existing:
        body["sha"] = existing["sha"]
    req = urllib.request.Request(
        f"{API}/repos/{REPO}/contents/{path}",
        data=json.dumps(body).encode(),
        method="PUT",
        headers={"Authorization": f"token {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())["commit"]["sha"][:12]


# ── Channel -> PE resolution (cached) ────────────────────────────────────
def resolve_channel_map(channels, bot_user_id, slack_token, gh_token):
    cache = gh_get_json("data/channel-map.json", gh_token, default={})
    unclassified = []

    for ch in channels:
        cid = ch["id"]
        if cid in SHARED_CHANNEL_IDS or cid in cache:
            continue

        pe = None
        inviter = find_inviter(cid, bot_user_id, slack_token)
        if inviter and inviter in SLACK_ID_TO_PE:
            pe = SLACK_ID_TO_PE[inviter]
            method = "inviter"
        else:
            name = ch.get("name", "")
            for slug, mapped_pe in ORG_SLUG_TO_PE.items():
                if slug in name:
                    pe = mapped_pe
                    method = "name-pattern"
                    break

        if pe:
            cache[cid] = {"name": ch.get("name"), "pe": pe, "method": method}
        else:
            unclassified.append({"id": cid, "name": ch.get("name"), "inviter": inviter})

    return cache, unclassified


# ── Write-up synthesis ───────────────────────────────────────────────────
def synthesize_with_claude(pe, week_label, messages, oauth_token, highlight_note=None):
    """Ask Claude (via the Claude Code CLI, billed against Jaime's Pro/Max
    subscription rather than a metered API key) to turn raw Slack messages
    into heading/bullets blocks matching the existing recap format. Returns
    a list of {heading, bullets}.

    Requires the `claude` CLI on PATH (the workflow installs
    @anthropic-ai/claude-code) and CLAUDE_CODE_OAUTH_TOKEN in the
    environment — generated once by running `claude setup-token` locally.
    """
    if not messages:
        return []
    # Departed employees — never include anything they authored. Slack message
    # objects only carry a user ID, not an email, so this needs their Slack
    # user IDs filled in here (TODO) — until then this filter is a no-op and
    # the Claude prompt below is the only backstop.
    DEPARTED_SLACK_IDS = set()  # TODO: add Roberto Segovia's and Todd Hazen's user IDs
    messages = [m for m in messages if m.get("user") not in DEPARTED_SLACK_IDS]

    raw_text = "\n".join(
        f"[{m.get('ts')}] {m.get('user','?')}: {m.get('text','')}" for m in messages
    )[:20000]
    prompt = (
        f"You are drafting the '{pe}' section of the weekly Invite recruiting recap for "
        f"the week of {week_label}. Below are raw Slack messages from that PE's channels "
        f"this week. Group them into 2-5 themed blocks, each with a short heading and 2-4 "
        f"terse bullets (include who said what and the date where useful). Output ONLY a "
        f"JSON array like [{{\"heading\": \"...\", \"bullets\": [\"...\"]}}]. No commentary.\n\n"
        f"Rules:\n"
        f"- Source integrity: every bullet must be directly traceable to one of the messages "
        f"below. Do not infer, combine fragments across messages, or invent a summary that "
        f"wasn't explicitly stated in a single message.\n"
        f"- Thread age filter: these messages are already limited to the past {LOOKBACK_DAYS} "
        f"days, but if any message text clearly references an older thread reviving old news, "
        f"exclude it.\n"
        f"- If you cannot point to a specific message as the source for a bullet, leave it out.\n"
        + (f"- {highlight_note}\n" if highlight_note else "")
        + f"\nMESSAGES:\n{raw_text}"
    )
    env = {**os.environ, "CLAUDE_CODE_OAUTH_TOKEN": oauth_token}
    result = subprocess.run(
        ["claude", "-p", "--output-format", "text"],
        input=prompt, capture_output=True, text=True, env=env, timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"claude CLI failed (exit {result.returncode}): {result.stderr[:500]}")
    text = result.stdout.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("["), text.rfind("]") + 1
        return json.loads(text[start:end])


def fallback_dump(messages):
    """No CLAUDE_CODE_OAUTH_TOKEN: group raw messages by channel, no summarization."""
    by_channel = {}
    for m in messages:
        by_channel.setdefault(m.get("_channel_name", "unknown"), []).append(m)
    blocks = []
    for chan, msgs in by_channel.items():
        blocks.append({
            "heading": f"Raw activity in #{chan} (unsummarized — set CLAUDE_CODE_OAUTH_TOKEN to enable write-ups)",
            "bullets": [f"{m.get('user','?')}: {m.get('text','')[:200]}" for m in msgs[:10]],
        })
    return blocks


# ── Main ──────────────────────────────────────────────────────────────────
ARTIFACT_URL = "https://jaimetavarez1.github.io/invite-weekly-recap/"


def main():
    slack_token = os.environ["SLACK_BOT_TOKEN"]
    gh_token = os.environ["RECAP_GH_TOKEN"]
    claude_oauth_token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")

    now = datetime.datetime.utcnow()
    oldest_ts = time.time() - LOOKBACK_DAYS * 86400
    week_label = f"{(now - datetime.timedelta(days=LOOKBACK_DAYS)).strftime('%B %-d')} – {now.strftime('%B %-d, %Y')}"

    bot_user_id = slack_bot_user_id(slack_token)
    channels = list_bot_channels(slack_token)
    channel_map, unclassified = resolve_channel_map(channels, bot_user_id, slack_token, gh_token)

    if unclassified:
        gh_put_json(
            "data/_unclassified_channels.json", {"generatedAt": now.isoformat() + "Z", "channels": unclassified},
            gh_token, "recap: flag unclassified channels",
        )

    # Pull messages per channel once, then fan out to whichever PE(s) need them.
    channel_by_id = {c["id"]: c for c in channels}
    messages_by_channel = {}
    for cid in list(SHARED_CHANNEL_IDS) + list(channel_map.keys()):
        if cid not in channel_by_id:
            continue
        msgs = channel_messages_since(cid, oldest_ts, slack_token)
        for m in msgs:
            m["_channel_name"] = channel_by_id[cid].get("name")
        messages_by_channel[cid] = msgs

    glean_cache = gh_get_json("data/glean-cache.json", gh_token, default={
        "orgPolicy": [], "keyEvents": [], "anniversaries": [],
    })

    commit_shas = {}

    for pe in PE_SLACK_IDS:
        pe_channel_ids = [cid for cid, info in channel_map.items() if info["pe"] == pe]
        pe_channel_ids += list(SHARED_CHANNEL_IDS)
        pe_messages = [m for cid in pe_channel_ids for m in messages_by_channel.get(cid, [])]

        highlight_note = None
        if pe == "jaime":
            rnd_hits = rnd_keyword_matches(pe_messages)
            if rnd_hits:
                highlight_note = (
                    f"{len(rnd_hits)} message(s) matched R&D-wide keywords "
                    f"(deep work week / R&D hiring or recruiting) — call these out explicitly"
                )

        if claude_oauth_token:
            updates = synthesize_with_claude(pe, week_label, pe_messages, claude_oauth_token, highlight_note)
        else:
            updates = fallback_dump(pe_messages)

        pe_doc = {
            "pe": pe,
            "week": week_label,
            "refreshedAt": now.isoformat() + "Z",
            "refreshedBy": "github-actions",
            "updates": updates,
        }
        commit_shas[pe] = gh_put_json(f"data/{pe}.json", pe_doc, gh_token, f"recap: {pe} — {week_label}")

    org_policy = list(glean_cache.get("orgPolicy", []))
    key_events = list(glean_cache.get("keyEvents", []))

    holiday_events = detect_upcoming_holidays(now.date())
    key_events += holiday_events

    relay_policy, relay_events, relay_status = fetch_notion_relay(slack_token, now)
    org_policy += relay_policy
    key_events += relay_events

    shared_doc = {
        "week": week_label,
        "refreshedAt": now.isoformat() + "Z",
        "refreshedBy": "github-actions",
        "orgPolicy": org_policy,
        "keyEvents": key_events,
        "anniversaries": glean_cache.get("anniversaries", []),  # still Cowork/Glean-sourced — see README
    }
    commit_shas["shared"] = gh_put_json("data/shared.json", shared_doc, gh_token, f"recap: shared — {week_label}")
    commit_shas["channel-map"] = gh_put_json("data/channel-map.json", channel_map, gh_token, "recap: update channel map")

    print(f"Done. Week: {week_label}")
    print(f"Channels: {len(channels)} total, {len(channel_map)} mapped, {len(unclassified)} unclassified")
    print(f"Synthesis: {'Claude Code CLI' if claude_oauth_token else 'RAW DUMP — set CLAUDE_CODE_OAUTH_TOKEN for real write-ups'}")
    print(f"Notion relay: {relay_status} ({len(relay_policy)} orgPolicy, {len(relay_events)} keyEvents)")
    for k, sha in commit_shas.items():
        print(f"  {k}: {sha}")
    if unclassified:
        print(f"WARNING: {len(unclassified)} channel(s) could not be assigned to a PE — see data/_unclassified_channels.json")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"FAILED: {e}", file=sys.stderr)
        sys.exit(1)
