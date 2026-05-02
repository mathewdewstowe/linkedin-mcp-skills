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
        positional = []
        i = 0
        while i < len(args):
            a = args[i]
            if a == '--1st':
                pass
            elif a.startswith('--title='):
                title = a.split('=', 1)[1]
            elif a == '--title' and i + 1 < len(args):
                title = args[i + 1]
                i += 1
            else:
                positional.append(a)
            i += 1
        query = ' '.join(positional)
        if not query and not title:
            print('❌ Usage: search-people <query> [--1st] [--title "Job Title"]')
            return
        from browser import LinkedInBrowser
        with LinkedInBrowser() as br:
            people = br.voyager_search_people(query, title=title,
                                              first_degree_only=first_degree)
        label = f'"{query}"' + (f' title="{title}"' if title else '')
        print(f'\nFound {len(people)} people for {label}:\n')
        for p in people:
            print(f'  {p["name"]}')
            print(f'    {p["headline"]}')
            print(f'    {p["profile_url"]}')
            print()

    elif command == 'search-posts':
        query = ' '.join(sys.argv[2:]) if len(sys.argv) > 2 else None
        if not query:
            print('❌ Usage: search-posts <query>')
            return
        from browser import LinkedInBrowser
        with LinkedInBrowser() as br:
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
        with LinkedInBrowser() as br:
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
        with LinkedInBrowser() as br:
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
        with LinkedInBrowser() as br:
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
        with LinkedInBrowser() as br:
            msgs = br.voyager_get_messages(conversation_urn)
        print(f'\n{len(msgs)} messages:\n')
        for m in msgs:
            print(f'  {m["sender_name"] or "me"}: {m["text"][:120]}')

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
