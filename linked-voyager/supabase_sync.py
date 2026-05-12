"""
Sync LinkedIn messages to the Supabase `global_messaging` table.

Schema (existing):
  id, conversation_urn, participant_name, participant_url,
  sender_name, sender_is_me, message_text, message_date, created_at

Reads credentials from ~/.claude/config/supabase.json (key: service_key).
"""
import json
import os
from pathlib import Path
from datetime import datetime, timezone

try:
    import requests
except ImportError:
    import subprocess, sys
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q', 'requests'])
    import requests


def load_creds():
    p = Path.home() / '.claude' / 'config' / 'supabase.json'
    with open(p) as f:
        c = json.load(f)
    return c['url'], c.get('service_key') or c.get('key')


def existing_message_keys(conversation_urn: str) -> set:
    """Return set of (message_date, sender_name) tuples already in Supabase for a conv."""
    url_root, key = load_creds()
    hdr = {'apikey': key, 'Authorization': f'Bearer {key}'}
    # PostgREST exact-equality on conversation_urn
    r = requests.get(
        f'{url_root}/rest/v1/global_messaging'
        f'?conversation_urn=eq.{conversation_urn}'
        f'&select=message_date,sender_name,message_text',
        headers=hdr,
    )
    if r.status_code != 200:
        return set()
    keys = set()
    for row in r.json():
        # Use (date, sender, text-prefix) as natural key for dedup
        key_tuple = (
            row.get('message_date', '') or '',
            row.get('sender_name', '') or '',
            (row.get('message_text', '') or '')[:50],
        )
        keys.add(key_tuple)
    return keys


def upsert_messages(rows: list) -> dict:
    """
    POST rows into global_messaging. Skips duplicates client-side.

    Each row dict needs: conversation_urn, participant_name, participant_url,
                        sender_name, sender_is_me, message_text, message_date.

    Returns: {'inserted': N, 'skipped': N, 'errors': [...]}
    """
    if not rows:
        return {'inserted': 0, 'skipped': 0, 'errors': []}
    url_root, key = load_creds()
    hdr = {
        'apikey': key,
        'Authorization': f'Bearer {key}',
        'Content-Type': 'application/json',
        'Prefer': 'return=minimal',
    }
    # Group by conversation for efficient dedup lookup
    by_conv = {}
    for r in rows:
        by_conv.setdefault(r['conversation_urn'], []).append(r)

    inserted = skipped = 0
    errors = []
    for conv_urn, conv_rows in by_conv.items():
        existing = existing_message_keys(conv_urn)
        fresh = []
        for r in conv_rows:
            k = (r.get('message_date', '') or '', r.get('sender_name', '') or '',
                 (r.get('message_text', '') or '')[:50])
            if k in existing:
                skipped += 1
            else:
                fresh.append(r)
                existing.add(k)
        if not fresh:
            continue
        resp = requests.post(
            f'{url_root}/rest/v1/global_messaging',
            headers=hdr, json=fresh,
        )
        if resp.status_code in (200, 201, 204):
            inserted += len(fresh)
        else:
            errors.append(f'  HTTP {resp.status_code}: {resp.text[:200]}')
    return {'inserted': inserted, 'skipped': skipped, 'errors': errors}


def conversation_count() -> int:
    """How many distinct conversations are in global_messaging?"""
    url_root, key = load_creds()
    hdr = {'apikey': key, 'Authorization': f'Bearer {key}'}
    r = requests.get(
        f'{url_root}/rest/v1/global_messaging?select=conversation_urn',
        headers=hdr,
    )
    return len({row['conversation_urn'] for row in r.json()}) if r.status_code == 200 else 0


def message_count() -> int:
    """Total messages in global_messaging."""
    url_root, key = load_creds()
    hdr = {'apikey': key, 'Authorization': f'Bearer {key}'}
    r = requests.get(
        f'{url_root}/rest/v1/global_messaging?select=*',
        headers={**hdr, 'Prefer': 'count=exact', 'Range': '0-0'},
    )
    return int(r.headers.get('content-range', '0/0').split('/')[-1])
