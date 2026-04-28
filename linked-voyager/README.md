# LinkedIn Voyager Outbound Agent

Multi-agent system for targeted LinkedIn outbound, invocable from Claude chat with `/linked-voyager`.

## Quick Start

### 1. Authenticate

Get your LinkedIn session cookies from Chrome DevTools:

1. Open LinkedIn in Chrome
2. Open DevTools (F12 → Application tab)
3. Go to Cookies → linkedin.com
4. Copy the values of `li_at` and `JSESSIONID`

Then set environment variables:
```bash
export LI_AT="<your_li_at_value>"
export JSESSIONID="<your_jsessionid_value>"
```

### 2. Configure Your ICP

Edit `config.py`:

```python
QUERIES = [
    'VP Sales OR "Head of Sales"',
    'RevOps OR "Revenue Operations"',
    # ... more search queries
]

SIGNAL_KEYWORDS = [
    'sales challenge',
    'deal velocity',
    'team enablement',
    # ... keywords that indicate ICP fit
]

DAILY_INVITE_CAP = 15        # Platform allows ~100/week
DAILY_COMMENT_CAP = 6        # Warmth + visibility
WITHDRAW_AFTER_DAYS = 21     # Remove stale invites
```

### 3. Run from Claude Chat

```
/linked-voyager run
```

## What It Does

### Outbound Flow

```
Search posts → Find signal keywords → Queue author
    ↓
Comment on post (warmth + visibility, 1–2 days before invite)
    ↓
Send no-note invite (higher accept rate)
    ↓
On accept → Message via free endpoint
    ↓
On no-accept after 21 days → Withdraw (keep hygiene)
```

### The Four Agents

| Agent | Action | Daily Cap | Purpose |
|-------|--------|-----------|---------|
| **PostSearchAgent** | Search posts for signal keywords | Unlimited | Find ICP-fit prospects |
| **CommenterAgent** | Post contextual comments | 5–8/day | Warm account + visibility |
| **ConnectorAgent** | Send no-note invites | 15/day | Main outreach action |
| **WithdrawerAgent** | Remove 21+ day pending | 20/day batch | Account hygiene |

## Database

SQLite store at `~/Job Apply/linked-voyager.db` tracks:

- **posts** — found via search, matched against signal keywords
- **invite_queue** — authors ready to invite (FIFO)
- **invites_sent** — sent invites, status, response
- **comments_sent** — posted comments for warming
- **daily_counters** — daily action count (resets at midnight)

## Safety Features

✅ **Business hours only** — Runs 9am–5pm in account timezone
✅ **Daily caps enforced** — Hard-stop when limit hit
✅ **Throttling** — 4–12s reads, 8–20s writes, 5–15min between phases
✅ **Challenge detection** — Halts on `/checkpoint/` or `/uas/` (manual re-auth needed)
✅ **Residential IP only** — Datacenter IPs get challenged
✅ **Dedicated SDR account** — Never run on personal network

## Commands

### `/linked-voyager config`
Show current ICP (queries, keywords, caps)

### `/linked-voyager status`
Check queue size, pending invites, daily counters

### `/linked-voyager search [query]`
Run post search, find signal authors
- Optional: provide custom query override

### `/linked-voyager comment`
Post comments on queued posts (warming, before invites)

### `/linked-voyager connect`
Send no-note invites from queue (respecting daily cap)

### `/linked-voyager withdraw`
Withdraw stale pending invites (>21 days)

### `/linked-voyager run [--skip-hours]`
Run full orchestrator cycle: search → comment → invite → withdraw
- `--skip-hours`: Bypass business hours check (testing only)

## Architecture

```
main.py                    — CLI entry point
orchestrator.py            — Schedules agents, enforces caps
voyager_client.py          — Auth, throttled API requests
store.py                   — SQLite database
config.py                  — ICP queries, keywords, caps
agents/
  post_search.py           — Find signal posts
  commenter.py             — Warm with comments
  connector.py             — Send no-note invites
  withdrawer.py            — Stale invite cleanup
```

## API Integration

### Real Request Shapes Needed

The `voyager_client.py` contains template request shapes. These need **real captures from Chrome DevTools** for:

1. **POST search** — `/search/dash/clusters` params/response
2. **Send invite** — `/growth/normInvitationsList` payload body
3. **Withdraw invite** — `/relationships/invitations/{id}` payload
4. **List pending** — `/relationships/sentInvitationViewsV2` response
5. **Create comment** — `/feed/normComments` payload
6. **Get me** — `/me` response shape

**To capture:**
1. Open LinkedIn, log in
2. Open DevTools (F12 → Network tab)
3. Do the action manually (search, send invite, etc.)
4. Right-click the request → Copy as cURL
5. Paste into a text file (redact `li_at`, `JSESSIONID`, `bcookie`)
6. Use the actual request shapes to update payloads in `voyager_client.py`

## Limitations

❌ **No automated posting** — Post manually (too risky)
❌ **No concurrent agents** — Sequential phases with throttling
❌ **Template API shapes** — Need real captures for 100% accuracy
❌ **No message auto-reply** — Can message accepted connections manually

## Future Enhancements

- [ ] Claude API integration for contextual comment generation
- [ ] Real-time monitoring dashboard
- [ ] Chrome extension message passing for auth/control
- [ ] Acceptance rate tracking + adaptive withdraw threshold
- [ ] Warm-up scheduler for new accounts
- [ ] A/B test different comment templates

## Account Hygiene Checklist

- [ ] Dedicated SDR account, not personal network
- [ ] Warmed for 2–3 weeks with manual usage before automation
- [ ] Residential IP / home machine only
- [ ] Profile complete, professional photo, decent headline
- [ ] Content posted manually 2–3x/week
- [ ] Existing connections (50+) before outbound starts
- [ ] Monitor daily: check acceptance rate, withdrawals

## Troubleshooting

**Q: "Auth failed" error**
A: Check `li_at` and `JSESSIONID` cookies. LinkedIn sessions expire; get fresh cookies from DevTools.

**Q: "Account requires manual auth" (challenge)**
A: LinkedIn detected unusual activity. Log in via browser, solve CAPTCHA, then restart skill.

**Q: Comments not posting / invites not sending**
A: Real API request shapes needed. See "API Integration" section.

**Q: Daily cap hit too early**
A: Check time zone in config (ACCOUNT_TIMEZONE). Counters reset at midnight local time.

**Q: Running outside business hours**
A: Edit BUSINESS_HOURS_START/END in config, or use `/linked-voyager run --skip-hours` for testing.

## Version

v1.0 — MVP with template API shapes, ready for real request integration.
