# /linked-voyager — LinkedIn Outbound Agent

**Skill type:** LinkedIn outbound via Playwright browser automation + Voyager API (Python).
**Auth:** Dedicated Brave profile at `~/.brave-paginator/profile` (already logged in).
**Database:** SQLite at `~/Job Apply/linked-voyager.db`

---

## Commands

| Command | Description |
|---------|-------------|
| `/linked-voyager status` | Show queue size, pending invites, daily counters |
| `/linked-voyager search [query]` | Run people search, queue ICP prospects |
| `/linked-voyager connect` | Send no-note invites from queue (browser automation) |
| `/linked-voyager withdraw` | Withdraw stale invites >21 days (browser automation) |
| `/linked-voyager run` | Full orchestrator: search → invite → withdraw |

---

## How to Run

Execute via Desktop Commander (no terminal needed):
```
python /Users/matthew_dewstowe/.codex/skills/linked-voyager/main.py <command>
```

---

## Architecture

```
browser.py            — Playwright automation:
                        • send_invite, withdraw, search_people (existing)
                        • search_posts, get_post_likers, get_post_commenters, get_post_comments (new)
                        • get_profile_urn
voyager_client.py     — Direct HTTP: /me, profile GraphQL, messaging (still Voyager)
store.py              — SQLite: invite_queue, invites_sent, daily_counters
config.py             — ICP queries, title keywords, caps, browser settings
agents/
  post_search.py      — People search via browser → queues profiles
  connector.py        — Browser automation: navigate + click Connect + shadow DOM
  withdrawer.py       — Browser automation: navigate + click Withdraw
orchestrator.py       — Schedules agents, enforces caps + business hours
main.py               — CLI entry point
```

---

## Why Browser Automation (not direct Voyager HTTP)

LinkedIn migrated most UI actions to **SDUI (Server-Driven UI)** in 2024-2025:
- **Invite send**: Uses SDUI endpoints `/V6iULndpiCPH` + `/uwKVGS9e0oz`
  - These accept requests only from React's pre-captured native fetch (not overrideable)
  - Body format uses `proto.sdui.actions.requests.RequestedArguments` (JSON-encoded protobuf)
  - All direct `window.fetch()` attempts return 400
- **Search results**: RSC server-rendered (no Voyager search API calls in browser)
- **Invitation list**: RSC server-rendered (no Voyager list API available)
- **Invite withdrawal**: SDUI — same issue as send

**What still works via direct HTTP:**
- `GET /voyager/api/me` — auth check
- `GET /voyager/api/graphql?variables=(memberIdentity:{slug})&queryId=voyagerIdentityDashProfiles.273a499c117721535e6da078bee17e9c` — profile URN lookup ✅
- `GET /voyager/api/relationships/invitationsSummaryV2` — invite counts ✅
- `POST /voyagerMessagingDashMessengerMessages?action=createMessage` — send messages ✅ (see ruby-outreach-extension)

---

## Connect Flow (Browser)

1. Navigate to `/in/{slug}/`
2. Find `<span>Connect</span>` at y=400–580, walk up to parent `<A>`, click it
3. Wait for `#interop-outlet` shadow root modal to render
4. Find `button[text="Send without a note"]` in shadow root, click it
5. Wait for SDUI endpoints `/V6iULndpiCPH` + `/uwKVGS9e0oz` to fire (200 = success)

---

## Withdraw Flow (Browser)

1. Navigate to `/in/{slug}/`
2. Find "Pending" button in profile header, click it
3. Find "Withdraw" in shadow root modal or dropdown, click it

---

## Post Engagement Flow (Browser — New Methods)

Four new methods for scraping LinkedIn post engagement data:

### 1. `search_posts(query: str, max_results: int = 20) → list`
**Search LinkedIn posts by keyword. Returns list of posts with author, title, timestamp.**

```python
posts = browser.search_posts("product strategy", max_results=5)
# Returns:
# [
#   {
#     'post_url': 'https://www.linkedin.com/feed/...',
#     'author_slug': 'janedoe',
#     'author_name': 'Jane Doe',
#     'post_title': 'Product strategy insights...',
#     'timestamp': '2 days ago'
#   },
#   ...
# ]
```

### 2. `get_post_likers(post_url: str) → list`
**Extract people who liked a post. Expands likes modal and scrapes profiles.**

```python
likers = browser.get_post_likers('https://www.linkedin.com/feed/...')
# Returns:
# [
#   {
#     'slug': 'janedoe',
#     'name': 'Jane Doe',
#     'title': 'VP Product',
#     'company': 'Acme Inc',
#     'profile_url': 'https://www.linkedin.com/in/janedoe/'
#   },
#   ...
# ]
```

### 3. `get_post_commenters(post_url: str) → list`
**Extract people who commented on a post. Loads comment section and scrapes profiles.**

```python
commenters = browser.get_post_commenters('https://www.linkedin.com/feed/...')
# Returns:
# [
#   {
#     'slug': 'janedoe',
#     'name': 'Jane Doe',
#     'title': 'Director of Product',
#     'company': 'Acme Inc',
#     'profile_url': 'https://www.linkedin.com/in/janedoe/',
#     'timestamp': '1 day ago'
#   },
#   ...
# ]
```

### 4. `get_post_comments(post_url: str) → list`
**Extract comment text with author info. Includes comment body, timestamp, reply count.**

```python
comments = browser.get_post_comments('https://www.linkedin.com/feed/...')
# Returns:
# [
#   {
#     'author_slug': 'janedoe',
#     'author_name': 'Jane Doe',
#     'comment_text': 'Great insights on product roadmap...',
#     'timestamp': '1 day ago',
#     'reply_count': 3
#   },
#   ...
# ]
```

### Usage Example: Find Engaged Prospects

```python
# Search posts on a topic
posts = browser.search_posts("AI product strategy")

# Extract commenters (high-intent signal)
for post in posts[:3]:
    commenters = browser.get_post_commenters(post['post_url'])
    # Commenters are warm leads — they engaged with content
    
# Export prospects for outreach
prospects = [c for post in posts for c in browser.get_post_commenters(post['post_url'])]
```

---

## SDUI Endpoints (reference, not directly callable from Python)

| Action | URL | Method |
|--------|-----|--------|
| Open Connect drawer | `POST /V6iULndpiCPH` | `requestId: com.linkedin.sdui.impl.mynetwork.infra.components.relationshipbuildingdrawer` |
| Send invite | `POST /uwKVGS9e0oz` | (protobuf JSON body, not directly callable) |
| Post-send callback | `POST /V6iULndpiCPH` | `requestId: com.linkedin.sdui.requests.mynetwork.handlePostInteropConnection` |

---

## Voyager Endpoints (working, callable from Python)

All under `https://www.linkedin.com/voyager/api/`

| Action | Method | Endpoint |
|--------|--------|----------|
| Current user | GET | `/me` |
| Profile URN | GET | `/graphql?variables=(memberIdentity:{slug})&queryId=voyagerIdentityDashProfiles.273a499c117721535e6da078bee17e9c` |
| Invite counts | GET | `/relationships/invitationsSummaryV2?types=List(SENT_INVITATION_COUNT,PENDING_INVITATION_COUNT)` |
| Send message | POST | `/voyagerMessagingDashMessengerMessages?action=createMessage` |

---

## Throttling

- Between invites: 8–20s random delay
- Between phases: 5–15 min gap
- Business hours only: 09:00–17:00 Europe/London

---

## Daily Caps

- Invites: 15/day
- Withdrawals: 20/day

---

## ICP Titles (config.py)

VP Sales, Head of Sales Enablement, Sales Enablement Manager, Director of RevOps,
VP Revenue, CRO, Director of Sales, Head of Solutions Engineering, Product Marketing Manager

---

## Status

✅ Working — browser automation confirmed via test session (2026-04-28)
- Invite send: CONFIRMED via Playwright shadow DOM click
- Profile URN lookup: CONFIRMED via GraphQL endpoint
- People search: implemented via browser scraping

⚠️ Accidental test invites sent (2026-04-28): Nevan Burke, Fruzsina Rapavi, Kinnon Brash, Paul Wiltshire, Adrian Stafford
