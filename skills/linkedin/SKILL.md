---
name: linkedin
description: LinkedIn skill — runs through the Voyager API for everything. Search people (with strict job-title filter, OR-list filter, server-side location/geoUrn filter, defaults to UK), search posts, get post likers and comments, list and read inbox conversations, send messages, fetch a person's recent posts and full activity feed, look up companies and find their employees by job title, list pending invites, and browse the homepage feed. All operations go through LinkedIn's internal Voyager API via headless Playwright + a dedicated logged-in Brave profile (~/.brave-paginator/profile). No UI clicks, no Chrome plugin needed at runtime. Trigger phrases include "linkedin", "search linkedin", "find people on linkedin", "find sales directors", "who liked this post", "post likers", "post comments", "linkedin messages", "send linkedin message", "message X on linkedin", "list conversations", "search posts on linkedin", "find employees at X", "company info", "who works at X", "my linkedin feed", "pending invites", "linkedin invites", "what is X posting".
---

# LinkedIn Voyager API skill

**Voyager-API-only. No UI clicks, no Chrome plugin at runtime.**

## 🚨 Hard rule — message sync date cutoff
**Never sync messages dated before 2026-04-20.** Always pass `--since 2026-04-20` on any `sync-messages` / `sync-thread` / message-history command. Pre-April-20 conversations and messages stay out of both the local SQLite DB and the Supabase `global_messaging` table.



**Skill location:** `${CLAUDE_PLUGIN_ROOT}/linked-voyager/main.py`
**Auth:** `~/.brave-paginator/profile` — already logged in. Headless Playwright, self-contained.

## How to invoke

Always run via the Bash tool — Matthew does NOT use the terminal manually:

```bash
cd "${CLAUDE_PLUGIN_ROOT}/linked-voyager"
python3 main.py <command> [args]
```

Always wait ~5–8 seconds between consecutive runs (Playwright profile lock).

---

## ✅ Confirmed working (run these freely)

### People & profiles
| Command | What it does |
|---|---|
| `search-people [<query>] [--1st] [--title "X"] [--title-any "A,B,C"] [--location "Y"] [--no-location] [--industry "X"] [--industry-any "A,B"]` | People search. **Default location = UK**. `--title` strict (headline-only) when no free-text query. `--title-any` matches if ANY title appears. `--industry` / `--industry-any` filter by current company industry (resolves to LinkedIn industryUrn). `--location` resolves to `geoUrn` server-side. Hardcoded geoUrns: UK, England, Scotland, Wales, NI, London, Manchester, Birmingham, Bristol, Edinburgh, Cardiff, etc. |
| `profile-current-company <linkedin_url>` | Current employer for a person — slug, name, job title, industry, employee count. |
| `company-jobs <slug_or_id> [keywords] [count]` | Job postings at a company. |
| `profile-posts <slug_or_url> [count]` | Person's recent original posts with reaction/comment counts. |
| `profile-activity <slug_or_url> [count]` | All recent activity (posts + likes + comments + reposts). |

### Posts & feed
| Command | What it does |
|---|---|
| `search-posts <query>` | Search posts by keyword. |
| `post-likers <url_or_urn>` | Who liked a post — name, headline, profile URL. |
| `post-comments <url_or_urn>` | Comments + commenter profiles + comment text. |
| `my-feed [count]` | My homepage chronological feed. |

### Companies
| Command | What it does |
|---|---|
| `company <slug>` | Company basics: name, tagline, industry, location, description, URN. Uses search-based lookup (legacy `/organization/companies` is dead). |
| `company-employees <slug> [--title "X"] [--location "Y"] [--1st]` | Employees at a company, filterable by title/location. |
| `company-size <slug>` | Accurate employee count + size band. |
| `company-jobs <slug_or_id> [keywords] [count]` | Posted job listings at a company. |

### Connections
| Command | What it does |
|---|---|
| `recent-connections [count] [--since-hours N] [--since-days N]` | List your most recently-accepted connections, sorted newest first. Equivalent to "My Network → Connections → Sort by Recently Added". Use `--since-hours 24` for last 24h. |

### Conversations (read)
| Command | What it does |
|---|---|
| `conversations [count]` | Inbox conversations (default 20) with participant + last message. |
| `messages <conversation_urn>` | Full message thread. |

### Message sync (SQLite)
| Command | What it does |
|---|---|
| `sync-messages [--full] [--limit N] [--since YYYY-MM-DD] [--existing-only]` | Pull ALL messages from every conversation into SQLite at `~/Job Apply/linked-voyager.db`. **Now walks the entire inbox** via the cursor-based pagination queryId (`messengerConversations.9501074288a12f3ae9e3c7ea243bccbf`) — no longer capped at 20 conversations. Default = incremental (only new since last run). `--full` re-fetches everything. `--limit N` caps how many conversations to walk. Per-thread message history uses `deliveredAt` cursor. |
| `messages-stats` | DB summary: total conversations, total messages, top 20 contacts by message volume. |
| `messages-with <slug_or_name> [limit]` | All messages exchanged with a person, chronological. |

### Messaging (write — Voyager API)
| Command | What it does |
|---|---|
| `send-message <conversation_urn> "<text>"` | Send to existing conversation. |
| `message-person "<name>" "<text>"` | Search person → send to existing convo OR start new. |

---

## ⚠️ Built but need LinkedIn payload-capture to work

These hit endpoints that exist but reject the current payloads (LinkedIn changes formats often). To fix any of these, capture the real request via the Chrome plugin (see "Capturing payloads" below) and update the method.

| Command | Status |
|---|---|
| `create-post "<text>" [PUBLIC\|CONNECTIONS]` | Endpoint uses XHR not fetch — needs XHR interceptor capture |
| `react-post <url_or_urn> [LIKE\|PRAISE\|EMPATHY\|INTEREST\|APPRECIATION\|ENTERTAINMENT]` | Endpoint not yet captured |
| `comment-post <url_or_urn> "<text>"` | Endpoint not yet captured |
| `invites-received [count]` | May return 0 — endpoint may need update |
| `invites-sent [count]` | May return 0 — endpoint may need update |
| `invite-accept <urn> <shared_secret>` | Untested |
| `invite-ignore <urn> <shared_secret>` | Untested |
| `profile-full <slug_or_url>` | Returns basics + recent posts. Full positions/educations need GraphQL profile cards (TODO). |
| `profile-contact <slug_or_url>` | Endpoint may be deprecated. |

---

## Examples

```bash
# Search by job title with OR — UK is default
search-people --title-any "VP Sales,Vice President Sales,CRO,Chief Revenue Officer" --1st

# Strict title in a specific location
search-people --title "Founder" --location "Cardiff" --1st

# Disable default UK
search-people --title "VP Sales" --no-location

# Company workflow: find a company, then who works there
company recall-ai
company-employees recall-ai --title "Sales"

# Person research
profile-posts zhu-amanda 10
profile-activity zhu-amanda 30

# Engagement research
post-likers "https://www.linkedin.com/feed/update/urn:li:activity:7454908546422558721/"
post-comments "urn:li:activity:7454908546422558721"

# Messaging
message-person "Jane Doe" "Hi Jane, hope you're well..."
conversations 20
messages "urn:li:msg_conversation:(urn:li:fsd_profile:HASH,thread_id)"

# My own feed
my-feed 10
```

---

## Voyager API write payloads (for reference / debugging)

### Messaging — `voyagerMessagingDashMessengerMessages?action=createMessage`
Required (otherwise 400):
- `trackingId`: 16-byte binary — `String.fromCharCode(...crypto.getRandomValues(new Uint8Array(16)))`
- `dedupeByClientGeneratedToken: false`
- `accept: application/json` (NOT `application/vnd.linkedin.normalized+json+2.1`)

### Search — `voyagerSearchDashClusters.b0928897b71bd00a5a7291755dcd64f0`
Variables format: `(query:(keywords:URLENCODED,flagshipSearchIntent:SEARCH_SRP,queryParameters:List((key:resultType,value:List(PEOPLE)),(key:network,value:List(F)),(key:geoUrn,value:List(GEO_ID)))))`

Note the wrapper `(query:(...))` — top-level keywords without this wrapper returns a coercion error.

### Profile posts — `/voyager/api/identity/profileUpdatesV2?profileUrn=URN&q=memberShareFeed`
Posts in `included[]` as `com.linkedin.voyager.feed.render.UpdateV2`. SocialActivityCounts also in `included[]`, lookup by entityUrn.

### Inbox pagination — paginated `messengerConversations` queryId
LinkedIn has TWO `messengerConversations` queryIds:
- `0d5e6781bbee71c3e51c8843c6519f48` — non-paginating, caps at 20 (avoid)
- `9501074288a12f3ae9e3c7ea243bccbf` — paginating, returns `metadata.nextCursor`

Variables for paginated version:
```
(query:(predicateUnions:List((conversationCategoryPredicate:(category:INBOX)))),
 count:20,
 mailboxUrn:URN,
 nextCursor:CURSOR)   <-- optional; omit on first page
```

The cursor is base64 of `DESCENDING&TIMESTAMP&LAST_THREAD_ID`. Pass it back as `nextCursor:VALUE` (URL-encoded) on the next call. Stop when LinkedIn returns no `nextCursor`. Categories: `INBOX`, `ARCHIVE`, `OTHER`.

---

## Capturing payloads (when an endpoint returns 400)

Use the Chrome plugin (`mcp__Claude_in_Chrome__*`) as a debugger:
1. `select_browser` (Brave) → `tabs_context_mcp` → `navigate` to LinkedIn
2. Install fetch interceptor:
   ```js
   window.__captured = null;
   const orig = window.fetch;
   window.fetch = async function(...a) {
     const url = typeof a[0] === 'string' ? a[0] : a[0].url;
     if (a[1]?.method === 'POST' && url.includes('TARGET_KEYWORD')) {
       window.__captured = {url, headers: a[1].headers, body: a[1].body};
     }
     return orig.apply(this, a);
   };
   ```
3. Trigger the action via UI → read `window.__captured` → port to `browser.py`

For endpoints that use **XMLHttpRequest** (like `create-post`), patch `XMLHttpRequest.prototype.open` and `.send` instead.

---

## Architecture

```
python main.py <command>
        ↓
LinkedInBrowser (Playwright, headless, paginator profile)
        ↓
page.evaluate(fetch …)   ← Voyager API call from inside the browser
        ↓
LinkedIn responds
        ↓
parsed JSON → caller
```

Auth via cookies on the paginator profile — no manual tokens, no Chrome plugin at runtime.

---

## Database

SQLite at `~/Job Apply/linked-voyager.db` — used by the `connect`/`withdraw`/`run` Playwright-UI campaign commands (these are NOT part of the Voyager-only path; they exist in the same `main.py` for legacy reasons but aren't recommended).

---

## When the user asks for something this skill can't do yet

If the user asks for an action that's in the "needs payload capture" list, offer to:
1. Run the command anyway (it'll likely 400) and report
2. Use the Chrome plugin to capture the real format and update the skill in this session
3. Skip and use a workaround (e.g. for create-post, suggest typing it manually since composing is one click)
