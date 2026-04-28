"""
LinkedIn Voyager Skill — Main Entry Point
Usage from Claude Chat: `/linked-voyager [command]`

Auth: Uses dedicated Brave profile at ~/.brave-paginator/profile (already logged in).
No cookies needed — browser automation handles auth.
"""

import sys
import os
import json

SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SKILL_DIR)

from orchestrator import LinkedVoyagerOrchestrator
from store import LinkedVoyagerStore


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else 'help'

    if command in ['help', '-h', '--help']:
        print_help()
        return

    orchestrator = LinkedVoyagerOrchestrator()

    if command == 'config':
        show_config()

    elif command == 'status':
        orchestrator.check_status()

    elif command == 'search':
        query = sys.argv[2] if len(sys.argv) > 2 else None
        results = orchestrator.searcher.run(query_override=query)
        print(f'\nSearch complete: {results["queued_authors"]} new prospects queued')

    elif command == 'connect':
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else None
        results = orchestrator.connector.run(limit=limit)
        print(f'\nConnect complete: {results["sent_count"]} invites sent')
        if results['errors']:
            for e in results['errors']:
                print(f'  ⚠ {e}')

    elif command == 'withdraw':
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else None
        results = orchestrator.withdrawer.run(limit=limit)
        print(f'\nWithdraw complete: {results["withdrawn_count"]} invites withdrawn')

    elif command == 'run':
        skip_hours = '--skip-hours' in sys.argv
        results = orchestrator.run(skip_hours_check=skip_hours)
        if results:
            print('\n✅ Cycle complete')

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
LinkedIn Voyager Outbound Agent — v2.0

USAGE:
  python main.py [command] [options]

COMMANDS:
  config                  Show ICP configuration
  status                  Show queue + daily counters
  search [query]          Search LinkedIn people, queue ICP prospects
  connect [limit]         Send no-note invites from queue (browser)
  withdraw [limit]        Withdraw stale (21+ day) invites (browser)
  run [--skip-hours]      Run full cycle: search → invite → withdraw

EXAMPLES:
  python main.py status
  python main.py search "VP Sales"
  python main.py connect 5
  python main.py run --skip-hours

ARCHITECTURE:
  Browser automation (Playwright + Brave) handles:
    - People search (RSC server-rendered, no Voyager API)
    - Invite send (SDUI, not directly callable)
    - Invite withdrawal (SDUI)

  Direct Voyager HTTP handles:
    - Profile URN lookup
    - Messaging (via ruby-outreach-extension pattern)

DATABASE: ~/Job Apply/linked-voyager.db
BROWSER:  ~/.brave-paginator/profile (must be logged into LinkedIn)
''')


if __name__ == '__main__':
    main()
