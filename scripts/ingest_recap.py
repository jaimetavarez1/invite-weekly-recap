#!/usr/bin/env python3
"""
ingest_recap.py — runs inside GitHub Actions, triggered when a PE's Cowork
skill opens a "[RECAP-INGEST]" issue. Parses a JSON payload from the issue
body and writes it into the repo. The workflow then commits + pushes with the
built-in GITHUB_TOKEN (which rebuilds GitHub Pages), so PEs never need repo
write access or an embedded token — they only open an issue.

Issue body must contain a JSON object (optionally inside a ```json fence):

{
  "mode": "full" | "refresh",   # applies to shared/pe data; ignored for config
  "pe_key": "jaime",
  "config": { ... },            # optional — writes config/<pe_key>.json (always overwrite)
  "shared": { ... },            # optional — writes data/shared.json
  "pe":     { ... }             # optional — writes data/<pe_key>.json
}

- full    — overwrites data/shared.json and data/<pe_key>.json
- refresh — merges additively into existing data files (dedup, never removes)
- config  — always overwrites config/<pe_key>.json
"""
import datetime
import json
import os
import pathlib
import re
import sys

ROOT = pathlib.Path(".")


def extract_json(body):
    if not body or not body.strip():
        raise ValueError("empty issue body")
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", body, re.DOTALL)
    raw = m.group(1) if m else body
    start, end = raw.find("{"), raw.rfind("}") + 1
    if start == -1 or end <= start:
        raise ValueError("no JSON object found in issue body")
    return json.loads(raw[start:end])


def load_file(relpath, default):
    p = ROOT / relpath
    return json.loads(p.read_text()) if p.exists() else default


def write_file(relpath, data):
    p = ROOT / relpath
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def merge_shared(existing, incoming, now_iso):
    merged = dict(existing) if existing else {"orgPolicy": [], "keyEvents": []}
    merged["refreshedAt"] = now_iso
    if incoming.get("week"):
        merged["week"] = incoming["week"]
    if incoming.get("refreshedBy"):
        merged["refreshedBy"] = incoming["refreshedBy"]

    # orgPolicy — dedup by title
    titles = {p.get("title", "") for p in merged.get("orgPolicy", [])}
    for item in incoming.get("orgPolicy", []):
        if item.get("title", "") not in titles:
            merged.setdefault("orgPolicy", []).append(item)
            titles.add(item.get("title", ""))

    # keyEvents — dedup by theme, then by heading within theme
    themes = {t["theme"]: t for t in merged.get("keyEvents", []) if t.get("theme")}
    for nt in incoming.get("keyEvents", []):
        name = nt.get("theme")
        if name in themes:
            heads = {i.get("heading", "") for i in themes[name].get("items", [])}
            for it in nt.get("items", []):
                if it.get("heading", "") not in heads:
                    themes[name].setdefault("items", []).append(it)
                    heads.add(it.get("heading", ""))
        else:
            merged.setdefault("keyEvents", []).append(nt)
            themes[name] = nt
    return merged


def merge_pe(existing, incoming, now_iso):
    merged = dict(existing) if existing else {"updates": []}
    merged["refreshedAt"] = now_iso
    if incoming.get("pe"):
        merged["pe"] = incoming["pe"]
    if incoming.get("week"):
        merged["week"] = incoming["week"]
    heads = {u.get("heading", "") for u in merged.get("updates", []) if isinstance(u, dict)}
    for u in incoming.get("updates", []):
        if isinstance(u, dict) and u.get("heading", "") not in heads:
            merged.setdefault("updates", []).append(u)
            heads.add(u.get("heading", ""))
    return merged


def main():
    payload = extract_json(os.environ.get("ISSUE_BODY", ""))
    pe_key = payload.get("pe_key")
    if not pe_key:
        raise ValueError("payload missing 'pe_key'")
    mode = (payload.get("mode") or "full").lower()
    now_iso = datetime.datetime.utcnow().isoformat() + "Z"

    wrote = []

    # Config — always overwrite (setup flow)
    if payload.get("config") is not None:
        write_file(f"config/{pe_key}.json", payload["config"])
        wrote.append(f"config/{pe_key}.json")

    # Shared data
    if payload.get("shared") is not None:
        if mode == "refresh":
            out = merge_shared(load_file("data/shared.json", None), payload["shared"], now_iso)
        else:
            out = payload["shared"]
        write_file("data/shared.json", out)
        wrote.append("data/shared.json")

    # PE data
    if payload.get("pe") is not None:
        if mode == "refresh":
            out = merge_pe(load_file(f"data/{pe_key}.json", None), payload["pe"], now_iso)
        else:
            out = payload["pe"]
        write_file(f"data/{pe_key}.json", out)
        wrote.append(f"data/{pe_key}.json")

    if not wrote:
        raise ValueError("payload had no config/shared/pe to write")

    print(f"ingest ok: mode={mode} pe={pe_key} wrote={wrote}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"FAILED: {e}", file=sys.stderr)
        sys.exit(1)
