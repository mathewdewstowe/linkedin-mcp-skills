"""
LinkedIn Voyager Skill — Main Entry Point
Usage from Claude Chat: `/linked-voyager [command]`

Voyager HTTP commands (search-people, search-posts, post-likers, post-comments)
read JSESSIONID from ~/Job Apply/voyager-campaign.json — no browser needed.

Browser automation commands (connect, withdraw, run) use Brave profile.
"""

import sys
import os
import json
import re

SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SKILL_DIR)

from orchestrator import LinkedVoyagerOrchestrator
from store import LinkedVoyagerStore
from voyager_client import VoyagerClient

VOYAGER_CAMPAIGN_PATH = os.path.expanduser('~/Job Apply/voyager-campaign.json')


def load_client() -> VoyagerClient:
    """Load VoyagerClient using JSESSIONID from voyager-campaign.json."""
    with open(VOYAGER_CAMPAIGN_PATH) as f:
        cfg = json.load(f)
    jsessionid = cfg.get('sessionToken', '')
    if not jsessionid:
        raise RuntimeError(f'No sessionToken found in {VOYAGER_CAMPAIGN_PATH}')
    return VoyagerClient(jsessionid=jsessionid)


def urn_from_url(url_or_urn: str) -> str:
    """
    Extract a post URN from a LinkedIn URL or return as-is if already a URN.
    Handles:
      https://www.linkedin.com/feed/update/urn:li:activity:123/
      https://www.linkedin.com/posts/slug-activity-123-AbCd/
    """
    if url_or_urn.startswith('urn:li:'):
        return url_or_urn
    # /feed/update/urn:li:activity:123
    m = re.search(r'(urn:li:\w+:\d+)', url_or_urn)
    if m:
        return m.group(1)
    # /posts/...-activity-123-xxxx
    m = re.search(r'activity-(\d+)', url_or_urn)
    if m:
        return f'urn:li:activity:{m.group(1)}'
    raise ValueError(f'Cannot extract post URN from: {url_or_urn}')


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else 'help'

    if command in ['help', '-h', '--help']:
        print_help()
        return

    if command == 'config':
        show_config()

    elif command == 'status':
        LinkedVoyagerOrchestrator().check_status()

    elif command == 'search':
        query = sys.argv[2] if len(sys.argv) > 2 else None
        orchestrator = LinkedVoyagerOrchestrator()
        results = orchestrator.searcher.run(query_override=query)
        print(f'\nSearch complete: {results["queued_authors"]} new prospects queued')

    elif command == 'connect':
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else None
        orchestrator = LinkedVoyagerOrchestrator()
        results = orchestrator.connector.run(limit=limit)
        print(f'\nConnect complete: {results["sent_count"]} invites sent')
        if results['errors']:
            for e in results['errors']:
                print(f'  ⚠ {e}')

    elif command == 'withdraw':
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else None
        orchestrator = LinkedVoyagerOrchestrator()
        results = orchestrator.withdrawer.run(limit=limit)
        print(f'\nWithdraw complete: {results["withdrawn_count"]} invites withdrawn')

    elif command == 'run':
        skip_hours = '--skip-hours' in sys.argv
        orchestrator = LinkedVoyagerOrchestrator()
        results = orchestrator.run(skip_hours_check=skip_hours)
        if results:
            print('\n✅ Cycle complete')

    elif command == 'search-people':
        args = sys.argv[2:]
        first_degree = '--1st' in args
        title = None
        titles_any = None
        location = None
        industry = None
        industries_any = None
        no_location = '--no-location' in args
        positional = []
        i = 0
        while i < len(args):
            a = args[i]
            if a in ('--1st', '--no-location'):
                pass
            elif a.startswith('--title='):
                title = a.split('=', 1)[1]
            elif a == '--title' and i + 1 < len(args):
                title = args[i + 1]; i += 1
            elif a.startswith('--title-any='):
                titles_any = [t.strip() for t in a.split('=', 1)[1].split(',') if t.strip()]
            elif a == '--title-any' and i + 1 < len(args):
                titles_any = [t.strip() for t in args[i + 1].split(',') if t.strip()]; i += 1
            elif a.startswith('--location='):
                location = a.split('=', 1)[1]
            elif a == '--location' and i + 1 < len(args):
                location = args[i + 1]; i += 1
            elif a.startswith('--industry='):
                industry = a.split('=', 1)[1]
            elif a == '--industry' and i + 1 < len(args):
                industry = args[i + 1]; i += 1
            elif a.startswith('--industry-any='):
                industries_any = [t.strip() for t in a.split('=', 1)[1].split(',') if t.strip()]
            elif a == '--industry-any' and i + 1 < len(args):
                industries_any = [t.strip() for t in args[i + 1].split(',') if t.strip()]; i += 1
            else:
                positional.append(a)
            i += 1
        query = ' '.join(positional)
        if not query and not title and not titles_any:
            print('❌ Usage: search-people [<query>] [--1st] [--title "X"] [--title-any "X,Y,Z"] [--location "UK"] [--no-location] [--industry "Software Development"] [--industry-any "X,Y"]')
            return
        # Default location to UK unless explicitly disabled
        if not location and not no_location:
            location = 'United Kingdom'
        # When --title is passed without a free-text query, treat title as strict
        title_strict = bool(title) and not query
        from browser import LinkedInBrowser
        with LinkedInBrowser(headless=True) as br:
            people = br.voyager_search_people(
                query, title=title, first_degree_only=first_degree,
                location=location, title_strict=title_strict,
                titles_any=titles_any,
                industry=industry, industries_any=industries_any,
            )
        label_parts = []
        if query:       label_parts.append(f'"{query}"')
        if title:       label_parts.append(f'title="{title}"' + (' (strict)' if title_strict else ''))
        if titles_any:  label_parts.append(f'title-any={titles_any}')
        if industry:    label_parts.append(f'industry="{industry}"')
        if industries_any: label_parts.append(f'industry-any={industries_any}')
        if location:    label_parts.append(f'location="{location}"')
        if first_degree: label_parts.append('1st-degree')
        print(f'\nFound {len(people)} people for {" ".join(label_parts)}:\n')
        for p in people:
            print(f'  {p["name"]}')
            print(f'    {p["headline"]}')
            if p.get('location'):
                print(f'    📍 {p["location"]}')
            print(f'    {p["profile_url"]}')
            print()

    elif command == 'profile-posts':
        slug_or_url = sys.argv[2] if len(sys.argv) > 2 else None
        count = int(sys.argv[3]) if len(sys.argv) > 3 else 10
        if not slug_or_url:
            print('❌ Usage: profile-posts <slug_or_url> [count]')
            return
        from browser import LinkedInBrowser
        with LinkedInBrowser(headless=True) as br:
            posts = br.voyager_get_profile_posts(slug_or_url, count=count)
        print(f'\nFound {len(posts)} recent posts:\n')
        for i, p in enumerate(posts, 1):
            print(f'  [{i}] 👍 {p["reactions"]}  💬 {p["comments"]}')
            print(f'      {p["post_url"]}')
            if p['text']:
                print(f'      "{p["text"][:200]}..."')
            print()

    elif command == 'search-posts':
        query = ' '.join(sys.argv[2:]) if len(sys.argv) > 2 else None
        if not query:
            print('❌ Usage: search-posts <query>')
            return
        from browser import LinkedInBrowser
        with LinkedInBrowser(headless=True) as br:
            posts = br.voyager_search_posts(query)
        print(f'\nFound {len(posts)} posts for "{query}":\n')
        for p in posts:
            print(f'  Author: {p["author_name"]} ({p["author_slug"]})')
            print(f'  URN:    {p["post_urn"]}')
            print(f'  URL:    {p["post_url"]}')
            if p['text_snippet']:
                print(f'  Text:   {p["text_snippet"][:120]}...')
            print()

    elif command == 'post-likers':
        url_or_urn = sys.argv[2] if len(sys.argv) > 2 else None
        if not url_or_urn:
            print('❌ Usage: post-likers <post_url_or_urn>')
            return
        post_urn = urn_from_url(url_or_urn)
        from browser import LinkedInBrowser
        with LinkedInBrowser(headless=True) as br:
            likers = br.voyager_get_post_likers(post_urn)
        print(f'\n{len(likers)} people liked {post_urn}:\n')
        for p in likers:
            print(f'  {p["name"]}')
            if p['headline']:
                print(f'    {p["headline"]}')
            print(f'    {p["profile_url"]}')
            print()

    elif command == 'post-comments':
        url_or_urn = sys.argv[2] if len(sys.argv) > 2 else None
        if not url_or_urn:
            print('❌ Usage: post-comments <post_url_or_urn>')
            return
        post_urn = urn_from_url(url_or_urn)
        from browser import LinkedInBrowser
        with LinkedInBrowser(headless=True) as br:
            comments = br.voyager_get_post_comments(post_urn)
        print(f'\n{len(comments)} comments on {post_urn}:\n')
        for c in comments:
            print(f'  {c["author_name"]}')
            if c['author_headline']:
                print(f'    {c["author_headline"]}')
            print(f'    {c["profile_url"]}')
            print(f'    "{c["comment_text"][:200]}"')
            print()

    elif command == 'conversations':
        from browser import LinkedInBrowser
        count = int(sys.argv[2]) if len(sys.argv) > 2 else 20
        with LinkedInBrowser(headless=True) as br:
            convs = br.voyager_get_conversations(count=count)
        print(f'\n{len(convs)} conversations:\n')
        for c in convs:
            unread = f'  [{c["unread_count"]} unread]' if c['unread_count'] else ''
            print(f'  {c["participant_name"]}{unread}')
            print(f'    {c["participant_url"]}')
            if c['last_message_text']:
                print(f'    Last: "{c["last_message_text"][:100]}"')
            print()

    elif command == 'messages':
        conversation_urn = sys.argv[2] if len(sys.argv) > 2 else None
        if not conversation_urn:
            print('❌ Usage: messages <conversation_urn>')
            print('  Get conversation URNs with: python main.py conversations')
            return
        from browser import LinkedInBrowser
        with LinkedInBrowser(headless=True) as br:
            msgs = br.voyager_get_messages(conversation_urn)
        print(f'\n{len(msgs)} messages:\n')
        for m in msgs:
            print(f'  {m["sender_name"] or "me"}: {m["text"][:120]}')

    elif command == 'send-message':
        if len(sys.argv) < 4:
            print('❌ Usage: send-message <conversation_urn> "<message text>"')
            print('  Get conversation URNs with: python main.py conversations')
            return
        conversation_urn = sys.argv[2]
        message_text = ' '.join(sys.argv[3:])
        from browser import LinkedInBrowser
        with LinkedInBrowser(headless=True) as br:
            ok = br.voyager_send_message(conversation_urn, message_text)
        if ok:
            print(f'✅ Message sent to {conversation_urn}')
        else:
            print(f'❌ Failed to send message')

    elif command == 'profile-full':
        slug = sys.argv[2] if len(sys.argv) > 2 else None
        if not slug:
            print('❌ Usage: profile-full <slug_or_url>'); return
        from browser import LinkedInBrowser
        with LinkedInBrowser(headless=True) as br:
            p = br.voyager_get_profile_full(slug)
        if not p: print('❌ Profile not found or empty'); return
        print(f'\n{p["name"]} — {p["headline"]}')
        print(f'📍 {p.get("location","")}  |  {p.get("industry","")}')
        print(f'🔗 {p["profile_url"]}\n')
        if p.get('summary'):
            print(f'Summary:\n{p["summary"][:500]}\n')
        print('Experience:')
        for pos in p['positions'][:6]:
            print(f'  • {pos["title"]} at {pos["company"]} ({pos["start_year"]}–{pos["end_year"]})')
        if p['educations']:
            print('\nEducation:')
            for e in p['educations'][:4]:
                print(f'  • {e["school"]} — {e.get("degree","")} {e.get("field","")}')
        if p['skills']:
            print(f'\nSkills ({len(p["skills"])}): {", ".join(p["skills"][:15])}')

    elif command == 'profile-contact':
        slug = sys.argv[2] if len(sys.argv) > 2 else None
        if not slug: print('❌ Usage: profile-contact <slug_or_url>'); return
        from browser import LinkedInBrowser
        with LinkedInBrowser(headless=True) as br:
            c = br.voyager_get_profile_contact(slug)
        if not c: print('❌ No contact info available'); return
        print(f'\nContact info:')
        if c['email']:    print(f'  📧 {c["email"]}')
        for p in c['phones']:    print(f'  📞 {p}')
        for w in c['websites']:  print(f'  🌐 {w}')
        for t in c['twitter']:   print(f'  🐦 {t}')
        if c['address']: print(f'  🏠 {c["address"]}')

    elif command == 'profile-activity':
        slug = sys.argv[2] if len(sys.argv) > 2 else None
        count = int(sys.argv[3]) if len(sys.argv) > 3 else 20
        if not slug: print('❌ Usage: profile-activity <slug_or_url> [count]'); return
        from browser import LinkedInBrowser
        with LinkedInBrowser(headless=True) as br:
            acts = br.voyager_get_profile_activity(slug, count=count)
        print(f'\n{len(acts)} recent activities:\n')
        for a in acts:
            icon = {'post':'📝','like':'👍','comment':'💬','repost':'🔁'}.get(a['type'],'•')
            print(f'  {icon} [{a["type"]}] 👍 {a["reactions"]}  💬 {a["comments"]}')
            if a['header']: print(f'     {a["header"]}')
            print(f'     {a["post_url"]}')
            if a['text']: print(f'     "{a["text"][:150]}..."')
            print()

    elif command == 'company':
        slug = sys.argv[2] if len(sys.argv) > 2 else None
        if not slug: print('❌ Usage: company <slug>'); return
        from browser import LinkedInBrowser
        with LinkedInBrowser(headless=True) as br:
            c = br.voyager_get_company(slug)
        if not c: print(f'❌ Company "{slug}" not found'); return
        print(f'\n{c["name"]}')
        if c['tagline']: print(f'  "{c["tagline"]}"')
        print(f'  Industry:   {c["industry"]}')
        print(f'  Employees:  {c["employee_count"]}')
        print(f'  Followers:  {c["follower_count"]}')
        print(f'  HQ:         {c["hq"].get("city","")}, {c["hq"].get("country","")}')
        if c.get('website'): print(f'  Website:    {c["website"]}')
        print(f'  LinkedIn:   {c["public_url"]}')
        if c['description']: print(f'\n  {c["description"][:400]}...')

    elif command == 'profile-current-company':
        url = sys.argv[2] if len(sys.argv) > 2 else None
        if not url: print('❌ Usage: profile-current-company <linkedin_url>'); return
        from browser import LinkedInBrowser
        with LinkedInBrowser(headless=True) as br:
            r = br.voyager_get_profile_current_company(url)
        if not r or not r.get('company_name'):
            print('{}'); return
        print(json.dumps(r))

    elif command == 'company-size':
        slug = sys.argv[2] if len(sys.argv) > 2 else None
        if not slug: print('❌ Usage: company-size <slug>'); return
        from browser import LinkedInBrowser
        with LinkedInBrowser(headless=True) as br:
            r = br.voyager_get_company_size(slug)
        if not r: print('❌ Not found'); return
        print(f'\n{r}')

    elif command == 'company-jobs':
        slug_or_id = sys.argv[2] if len(sys.argv) > 2 else None
        keywords = sys.argv[3] if len(sys.argv) > 3 else ''
        count = int(sys.argv[4]) if len(sys.argv) > 4 else 50
        if not slug_or_id: print('❌ Usage: company-jobs <slug_or_id> [keywords] [count]'); return
        from browser import LinkedInBrowser
        with LinkedInBrowser(headless=True) as br:
            # Resolve slug → id if needed
            company_id = slug_or_id
            if not slug_or_id.isdigit():
                c = br.voyager_get_company(slug_or_id)
                if not c: print(f'❌ Company "{slug_or_id}" not found'); return
                company_id = c.get('company_id', slug_or_id)
            jobs = br.voyager_search_company_jobs(company_id, keywords=keywords, count=count)
        print(f'\n{len(jobs)} jobs:\n')
        for j in jobs:
            print(f'  {j.get("title","?")}')
            if j.get('location'): print(f'    📍 {j["location"]}')
            if j.get('url'):      print(f'    {j["url"]}')
            print()

    elif command == 'company-employees':
        args = sys.argv[2:]
        slug = None; title = None; location = None; first_degree = '--1st' in args
        positional = []
        i = 0
        while i < len(args):
            a = args[i]
            if a == '--1st': pass
            elif a.startswith('--title='):    title = a.split('=',1)[1]
            elif a == '--title' and i+1<len(args): title = args[i+1]; i+=1
            elif a.startswith('--location='): location = a.split('=',1)[1]
            elif a == '--location' and i+1<len(args): location = args[i+1]; i+=1
            else: positional.append(a)
            i += 1
        slug = positional[0] if positional else None
        if not slug: print('❌ Usage: company-employees <slug> [--title "X"] [--location "Y"] [--1st]'); return
        from browser import LinkedInBrowser
        with LinkedInBrowser(headless=True) as br:
            people = br.voyager_get_company_employees(slug, title=title, first_degree_only=first_degree, location=location)
        print(f'\nFound {len(people)} employees at {slug}:\n')
        for p in people:
            print(f'  {p["name"]}')
            print(f'    {p["headline"]}')
            if p.get('location'): print(f'    📍 {p["location"]}')
            print(f'    {p["profile_url"]}')
            print()

    elif command == 'my-feed':
        count = int(sys.argv[2]) if len(sys.argv) > 2 else 20
        from browser import LinkedInBrowser
        with LinkedInBrowser(headless=True) as br:
            posts = br.voyager_get_my_feed(count=count)
        print(f'\n{len(posts)} feed posts:\n')
        for p in posts:
            print(f'  {p["author"]} — 👍 {p["reactions"]}  💬 {p["comments"]}')
            print(f'    {p["post_url"]}')
            if p['text']: print(f'    "{p["text"][:150]}..."')
            print()

    elif command == 'sync-messages':
        # sync-messages [--full] [--limit N] [--since YYYY-MM-DD] [--existing-only]
        args = sys.argv[2:]
        full = '--full' in args
        existing_only = '--existing-only' in args
        limit = None
        since_date = None
        for i, a in enumerate(args):
            if a.startswith('--limit='):
                limit = int(a.split('=', 1)[1])
            elif a == '--limit' and i + 1 < len(args):
                limit = int(args[i + 1])
            elif a.startswith('--since='):
                since_date = a.split('=', 1)[1]
            elif a == '--since' and i + 1 < len(args):
                since_date = args[i + 1]
        # Convert --since YYYY-MM-DD to ms epoch
        since_ts = 0
        if since_date:
            from datetime import datetime as _dt
            since_ts = int(_dt.strptime(since_date, '%Y-%m-%d').timestamp() * 1000)
        import messages_store as MS
        from browser import LinkedInBrowser
        import sqlite3, os as _os
        existing_urns = set()
        if existing_only:
            _conn = sqlite3.connect(_os.path.expanduser('~/Job Apply/linked-voyager.db'))
            existing_urns = {r[0] for r in _conn.execute('SELECT conversation_urn FROM msg_conversations').fetchall()}
            _conn.close()
            print(f'  [existing-only] {len(existing_urns)} known conversations in DB')
        with LinkedInBrowser(headless=True) as br:
            # Paginate the inbox — get every conversation (not just first 20)
            print('  [fetch] paginating inbox...')
            convs = br.voyager_get_all_conversations(
                max_pages=50,
                stop_at_timestamp=since_ts,  # don't fetch convos older than --since
            )
            print(f'  [fetch] {len(convs)} conversations retrieved across pages')
            if limit:
                convs = convs[:limit]
            if existing_only:
                convs = [c for c in convs if c['conversation_urn'] in existing_urns]
            print(f'\n→ {len(convs)} conversations to sync' +
                  (f' (since {since_date})' if since_date else '') + '\n')
            total_new = 0
            for idx, c in enumerate(convs, 1):
                MS.upsert_conversation(c)
                # Decide stop cutoff
                if full:
                    stop_at = 0
                elif since_ts:
                    # Use max(since_ts, last_synced) so we don't double-fetch
                    stop_at = max(since_ts, MS.latest_message_timestamp(c['conversation_urn']))
                else:
                    stop_at = MS.latest_message_timestamp(c['conversation_urn'])
                msgs = br.voyager_get_messages_paginated(
                    c['conversation_urn'],
                    stop_at_timestamp=stop_at,
                    max_pages=100,
                )
                # If --since set, hard-filter messages older than the cutoff
                if since_ts:
                    msgs = [m for m in msgs if m['sent_at'] >= since_ts]
                added = MS.insert_messages(msgs)
                total_new += added
                status = '🟢' if added > 0 else '⚪'
                print(f'  {status} [{idx}/{len(convs)}] {c["participant_name"]}: {len(msgs)} fetched, +{added} new')
        print(f'\n✅ Sync complete — {total_new} new messages added')

    elif command == 'messages-stats':
        import messages_store as MS
        s = MS.stats()
        print(f'\n📊 LinkedIn message DB')
        print(f'  DB:             {s["db_path"]}')
        print(f'  Conversations:  {s["conversations"]}')
        print(f'  Messages:       {s["messages"]}')
        print(f'  Unique senders: {s["unique_senders"]}')
        print(f'  Last message:   {s["last_message"]}')
        print(f'\nTop 20 by message volume:')
        for name, slug, n, last in s['top_by_volume']:
            print(f'  {n:>5}  {name:<35}  last: {last or "-"}')

    elif command == 'sync-thread':
        # sync-thread <thread_url_or_id> [participant_name]
        # Accepts:
        #   https://www.linkedin.com/messaging/thread/2-Xxxxx==/
        #   2-Xxxxx==
        #   urn:li:msg_conversation:(urn:li:fsd_profile:HASH,2-Xxxxx==)
        if len(sys.argv) < 3:
            print('❌ Usage: sync-thread <thread_url_or_id_or_urn> [participant_name]')
            return
        raw = sys.argv[2]
        name = sys.argv[3] if len(sys.argv) > 3 else ''
        import re as _re, messages_store as MS
        from browser import LinkedInBrowser
        # Already a full conversation URN?
        if raw.startswith('urn:li:msg_conversation:'):
            conv_urn = raw
        else:
            # Extract thread_id from a /messaging/thread/X/ URL or raw token
            m = _re.search(r'/messaging/thread/([^/?#]+)', raw)
            thread_id = m.group(1) if m else raw.strip('/').split('/')[-1]
            with LinkedInBrowser(headless=True) as br_tmp:
                mailbox = br_tmp._voyager_my_urn()
            conv_urn = f'urn:li:msg_conversation:({mailbox},{thread_id})'
        print(f'  Conversation URN: {conv_urn}')
        with LinkedInBrowser(headless=True) as br:
            msgs = br.voyager_get_messages_paginated(conv_urn, max_pages=100)
            if not msgs:
                print(f'❌ No messages returned (URN may be invalid or no thread exists)')
                return
            # Derive participant name from the messages if not provided
            if not name:
                # Find a non-me sender
                ME = br._voyager_my_urn().split(':')[-1]
                for m in msgs:
                    if m.get('sender_slug') and m['sender_slug'] != ME:
                        name = m.get('sender_name', '')
                        break
            MS.upsert_conversation({
                'conversation_urn': conv_urn,
                'participant_name': name or '(unknown)',
                'participant_url':  '',
                'last_message_text':'',
                'last_message_at':  msgs[-1]['sent_at'],
                'unread_count':     0,
            })
            added = MS.insert_messages(msgs)
        print(f'✅ {name or conv_urn}: {len(msgs)} fetched, +{added} new in DB')

    elif command == 'sync-messages-with':
        # sync-messages-with <slug_or_profile_url>
        if len(sys.argv) < 3:
            print('❌ Usage: sync-messages-with <slug_or_profile_url>')
            return
        slug = sys.argv[2].rstrip('/').split('/')[-1].split('?')[0]
        import messages_store as MS
        from browser import LinkedInBrowser
        with LinkedInBrowser(headless=True) as br:
            r = br.voyager_find_conversation_with(slug)
            if r.get('error'):
                print(f'❌ {r["error"]}'); return
            if r.get('is_new'):
                print(f'⚠ No existing conversation with {slug} (LinkedIn opened compose for new thread)')
                return
            conv_urn = r['conversation_urn']
            print(f'✓ Found conversation: {conv_urn}')
            # Pull all messages
            msgs = br.voyager_get_messages_paginated(conv_urn, max_pages=100)
            # Upsert conversation row (use slug for participant_name fallback)
            MS.upsert_conversation({
                'conversation_urn': conv_urn,
                'participant_name': slug.replace('-', ' ').title(),
                'participant_url':  f'https://www.linkedin.com/in/{slug}/',
                'last_message_text':'',
                'last_message_at':  msgs[-1]['sent_at'] if msgs else 0,
                'unread_count':     0,
            })
            added = MS.insert_messages(msgs)
        print(f'✅ {slug}: {len(msgs)} fetched, +{added} new in DB')

    elif command == 'messages-with':
        if len(sys.argv) < 3:
            print('❌ Usage: messages-with <slug_or_name> [limit]'); return
        target = sys.argv[2]
        limit = int(sys.argv[3]) if len(sys.argv) > 3 else 200
        import messages_store as MS
        rows = MS.messages_with(target, limit=limit)
        print(f'\n{len(rows)} messages with "{target}":\n')
        for ts, sender, text in rows:
            who = sender or 'me'
            print(f'  [{ts}] {who}: {text[:200]}')

    elif command == 'recent-connections':
        # recent-connections [count] [--since-hours N] [--since-days N]
        args = sys.argv[2:]
        count = 50
        since_hours = None
        i = 0
        while i < len(args):
            a = args[i]
            if a.startswith('--since-hours='):
                since_hours = int(a.split('=', 1)[1])
            elif a == '--since-hours' and i + 1 < len(args):
                since_hours = int(args[i + 1]); i += 1
            elif a.startswith('--since-days='):
                since_hours = int(a.split('=', 1)[1]) * 24
            elif a == '--since-days' and i + 1 < len(args):
                since_hours = int(args[i + 1]) * 24; i += 1
            elif a.isdigit():
                count = int(a)
            i += 1
        from browser import LinkedInBrowser
        with LinkedInBrowser(headless=True) as br:
            conns = br.voyager_get_recent_connections(count=count, since_hours=since_hours)
        label = f'last {since_hours}h' if since_hours else 'recently added'
        print(f'\n{len(conns)} connections ({label}):\n')
        for c in conns:
            print(f'  {c["name"]}')
            print(f'    {c["headline"]}')
            print(f'    🕒 {c["connected_at_iso"]}')
            print(f'    {c["profile_url"]}')
            print()

    elif command == 'invites-received':
        count = int(sys.argv[2]) if len(sys.argv) > 2 else 50
        from browser import LinkedInBrowser
        with LinkedInBrowser(headless=True) as br:
            invs = br.voyager_get_invites_received(count=count)
        print(f'\n{len(invs)} invites received:\n')
        for i in invs:
            print(f'  {i["from_name"]}')
            print(f'    {i["from_headline"]}')
            if i['message']: print(f'    Note: "{i["message"][:120]}"')
            print(f'    URN: {i["invitation_urn"]}')
            print()

    elif command == 'invites-sent':
        count = int(sys.argv[2]) if len(sys.argv) > 2 else 50
        from browser import LinkedInBrowser
        with LinkedInBrowser(headless=True) as br:
            invs = br.voyager_get_invites_sent(count=count)
        print(f'\n{len(invs)} invites sent (pending):\n')
        for i in invs:
            print(f'  {i["to_name"]}  ({i["to_headline"]})')
            print(f'    {i["invitation_urn"]}')

    elif command == 'invite-accept':
        # invite-accept <invitation_urn> <shared_secret>
        if len(sys.argv) < 4:
            print('❌ Usage: invite-accept <invitation_urn> <shared_secret>'); return
        urn = sys.argv[2]; ss = sys.argv[3]
        from browser import LinkedInBrowser
        with LinkedInBrowser(headless=True) as br:
            ok = br.voyager_invite_action(urn, ss, action='accept')
        print('✅ Accepted' if ok else '❌ Failed')

    elif command == 'invite-ignore':
        if len(sys.argv) < 4:
            print('❌ Usage: invite-ignore <invitation_urn> <shared_secret>'); return
        urn = sys.argv[2]; ss = sys.argv[3]
        from browser import LinkedInBrowser
        with LinkedInBrowser(headless=True) as br:
            ok = br.voyager_invite_action(urn, ss, action='ignore')
        print('✅ Ignored' if ok else '❌ Failed')

    elif command == 'create-post':
        if len(sys.argv) < 3:
            print('❌ Usage: create-post "<text>" [PUBLIC|CONNECTIONS]'); return
        text = sys.argv[2]
        visibility = sys.argv[3].upper() if len(sys.argv) > 3 else 'PUBLIC'
        from browser import LinkedInBrowser
        with LinkedInBrowser(headless=True) as br:
            res = br.voyager_create_post(text, visibility=visibility)
        if res:
            print(f'✅ Post created: {res["url"] or res["urn"]}')
        else:
            print(f'❌ Failed to create post')

    elif command == 'react-post':
        if len(sys.argv) < 3: print('❌ Usage: react-post <url_or_urn> [LIKE|PRAISE|EMPATHY|INTEREST|APPRECIATION|ENTERTAINMENT]'); return
        post_urn = urn_from_url(sys.argv[2])
        reaction = sys.argv[3].upper() if len(sys.argv) > 3 else 'LIKE'
        from browser import LinkedInBrowser
        with LinkedInBrowser(headless=True) as br:
            ok = br.voyager_react_post(post_urn, reaction=reaction)
        print(f'✅ {reaction} reaction added to {post_urn}' if ok else '❌ Failed to react')

    elif command == 'comment-post':
        if len(sys.argv) < 4: print('❌ Usage: comment-post <url_or_urn> "<text>"'); return
        post_urn = urn_from_url(sys.argv[2])
        text = ' '.join(sys.argv[3:])
        from browser import LinkedInBrowser
        with LinkedInBrowser(headless=True) as br:
            ok = br.voyager_comment_post(post_urn, text)
        print(f'✅ Comment posted on {post_urn}' if ok else '❌ Failed to comment')

    elif command == 'message-person':
        # message-person "Name to search" "message text"
        if len(sys.argv) < 4:
            print('❌ Usage: message-person "<name>" "<message text>"')
            return
        name_query   = sys.argv[2]
        message_text = ' '.join(sys.argv[3:])
        from browser import LinkedInBrowser
        with LinkedInBrowser(headless=True) as br:
            # 1. Find the person via search
            people = br.voyager_search_people(name_query, count=5)
            if not people:
                print(f'❌ No LinkedIn profile found for "{name_query}"')
                return
            person = people[0]
            print(f'Found: {person["name"]} — {person["headline"]}')
            print(f'  {person["profile_url"]}')

            # 2. Check for existing conversation
            convs = br.voyager_get_conversations(count=100)
            slug = person['slug']
            existing = next(
                (c for c in convs if slug in c.get('participant_url', '')),
                None
            )
            if existing:
                print(f'Found existing conversation — sending via Voyager API...')
                ok = br.voyager_send_message(existing['conversation_urn'], message_text)
            else:
                print(f'No existing conversation — starting new one via Voyager API...')
                # Extract fsd_profile URN from EntityResultViewModel URN
                import re as _re
                m = _re.search(r'(urn:li:fsd_profile:[^,)]+)', person.get('urn', ''))
                fsd_urn = m.group(1) if m else person.get('urn', '')
                ok = br.voyager_start_conversation(fsd_urn, message_text)

        if ok:
            print(f'✅ Message sent to {person["name"]}')
        else:
            print(f'❌ Failed to send message')

    elif command == 'message-url':
        # message-url "<linkedin_url_or_slug>" "<message text>"
        # Uses slug exact-match so we hit the RIGHT person, not a random namesake
        if len(sys.argv) < 4:
            print('❌ Usage: message-url "<linkedin_url_or_slug>" "<message text>"')
            return
        url_or_slug  = sys.argv[2]
        message_text = ' '.join(sys.argv[3:])

        # Extract slug from URL
        import re as _re
        slug = url_or_slug.rstrip('/').split('/')[-1].split('?')[0]
        print(f'Resolving slug: {slug}')

        from browser import LinkedInBrowser
        with LinkedInBrowser(headless=True) as br:
            # Resolve slug directly via profile API (works for numeric suffixes too)
            fsd_urn = br.voyager_resolve_slug_to_urn(slug)
            if not fsd_urn:
                print(f'❌ Could not resolve slug to URN: {slug}')
                return
            print(f'Resolved URN: {fsd_urn}')

            # Check for existing conversation
            convs = br.voyager_get_conversations(count=100)
            existing = next(
                (c for c in convs if slug in c.get('participant_url', '')),
                None
            )
            if existing:
                print(f'Found existing conversation — sending...')
                ok = br.voyager_send_message(existing['conversation_urn'], message_text)
                person_name = slug
            else:
                print(f'No existing conversation — starting new one...')
                ok = br.voyager_start_conversation(fsd_urn, message_text)
                person_name = slug

        if ok:
            print(f'✅ Message sent to {person_name}')
        else:
            print(f'❌ Failed to send message')

    else:
        print(f'❌ Unknown command: {command}')
        print_help()


def show_config():
    from config import (
        ICP_QUERIES, ICP_TITLE_KEYWORDS,
        DAILY_INVITE_CAP, DAILY_WITHDRAW_CAP,
        WITHDRAW_AFTER_DAYS, BUSINESS_HOURS_START, BUSINESS_HOURS_END,
        ACCOUNT_TIMEZONE, DB_PATH, BRAVE_PROFILE
    )
    print('📋 LinkedIn Voyager Configuration\n')
    print(f'Database:      {DB_PATH}')
    print(f'Browser:       {BRAVE_PROFILE}')
    print(f'Timezone:      {ACCOUNT_TIMEZONE}')
    print(f'Business Hours:{BUSINESS_HOURS_START}am – {BUSINESS_HOURS_END}pm\n')

    print(f'ICP Queries ({len(ICP_QUERIES)}):')
    for i, q in enumerate(ICP_QUERIES, 1):
        print(f'  {i}. "{q}"')

    print(f'\nICP Title Keywords ({len(ICP_TITLE_KEYWORDS)}):')
    for i, kw in enumerate(ICP_TITLE_KEYWORDS, 1):
        print(f'  {i}. "{kw}"')

    print(f'\nDaily Caps:  Invites {DAILY_INVITE_CAP}/day  |  Withdrawals {DAILY_WITHDRAW_CAP}/day')
    print(f'Withdraw after: {WITHDRAW_AFTER_DAYS} days with no response')


def print_help():
    print('''
LinkedIn Voyager Skill — v3.0

USAGE:
  python main.py [command] [options]

VOYAGER API via Brave browser (li_at auto-included — no manual token needed):
  search-people <query> [--1st] [--title "Job Title"]
                                    Search people. --1st = 1st-degree only.
  search-posts  <query>             Search posts by keyword
  post-likers   <url_or_urn>        Who liked a post (Reaction objects)
  post-comments <url_or_urn>        Comments + commenter names on a post
  conversations [count]             List inbox conversations (default 20)
  messages      <conversation_urn>  Full message thread history
  send-message  <conversation_urn> "<text>"  Send a message to an existing conversation
  message-person "<name>" "<text>"           Search for person then send them a message

BROWSER AUTOMATION (Playwright + Brave — UI clicks):
  config                            Show ICP configuration
  status                            Show queue + daily counters
  search [query]                    Search people, queue ICP prospects
  connect [limit]                   Send no-note invites from queue
  withdraw [limit]                  Withdraw stale (21+ day) invites
  run [--skip-hours]                Full cycle: search → invite → withdraw

EXAMPLES:
  python main.py search-people "VP Sales"
  python main.py search-people --title "Head of Engineering"
  python main.py search-posts "AI sales demo"
  python main.py post-likers "https://www.linkedin.com/feed/update/urn:li:activity:123/"
  python main.py post-comments urn:li:activity:7321498765432109876
  python main.py conversations 10
  python main.py messages "urn:li:msg_conversation:(...)"
  python main.py connect 5

AUTH:
  All Voyager API + browser → ~/.brave-paginator/profile (logged into LinkedIn)

DATABASE: ~/Job Apply/linked-voyager.db
''')


if __name__ == '__main__':
    main()
