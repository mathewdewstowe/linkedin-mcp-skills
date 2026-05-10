# linkedin-voyager — Claude Code plugin

LinkedIn skill that runs entirely through LinkedIn's internal Voyager API. Search people, find post likers/comments, list employees at a company, send messages, browse your feed — all programmatic, no clicks, no Chrome plugin needed at runtime.

## Install (1 command)

In any Claude Code chat, run:

```
/plugin marketplace add mathewdewstowe/linkedin-mcp-skills
/plugin install linkedin-voyager@linkedin-voyager-marketplace
```

That's it for the plugin. Two one-time machine setup steps follow.

## One-time machine setup

### 1. Install Playwright + Chromium
```bash
python3 -m pip install playwright
python3 -m playwright install chromium
```

### 2. Log into LinkedIn in the dedicated Brave profile
```bash
mkdir -p ~/.brave-paginator/profile
"/Applications/Brave Browser.app/Contents/MacOS/Brave Browser" \
  --user-data-dir=$HOME/.brave-paginator/profile
```

Log into LinkedIn once in the Brave window that opens. Close it. Done.

The session cookie persists for months. The skill uses this profile headlessly — it doesn't disturb your normal Brave usage.

## Use it

In any Claude Code chat:

> "Search LinkedIn for sales directors in London, 1st degree only"
> "Who liked this post: <url>"
> "Send a LinkedIn message to Jane Doe"
> "What's Amanda Zhu been posting?"
> "Find all VPs at Recall.ai"
> "Who's the current employer of <linkedin-url>"

Claude routes through the `/linkedin` skill automatically. See [`skills/linkedin/SKILL.md`](skills/linkedin/SKILL.md) for the full command reference.

## What you get

**16 confirmed-working commands:**

| Category | Commands |
|---|---|
| **People** | `search-people` (with title, title-any, location, industry, 1st-degree filters), `profile-posts`, `profile-activity`, `profile-current-company` |
| **Posts** | `search-posts`, `post-likers`, `post-comments`, `my-feed` |
| **Companies** | `company`, `company-employees`, `company-size`, `company-jobs` |
| **Messages** | `conversations`, `messages`, `send-message`, `message-person` |

UK is the default location (resolves to LinkedIn `geoUrn` server-side). Use `--no-location` to disable.

## Architecture

```
User asks Claude something LinkedIn-related
        ↓
Claude triggers /linkedin skill
        ↓
Bash: python3 main.py <command>
        ↓
Headless Playwright launches with paginator profile
        ↓
page.evaluate(fetch …) → Voyager API call (cookies auto-included)
        ↓
JSON response parsed → returned to Claude
        ↓
Claude formats and shows you
```

## Privacy

- Runs entirely on YOUR machine with YOUR LinkedIn session
- Never sends cookies anywhere except `linkedin.com`
- Never modifies your LinkedIn settings or privacy
- Headless browser — invisible, doesn't disturb anything
- Uses a SEPARATE Brave profile so your main browser is untouched

## Sharing with coworkers (Cowork)

This repo is a Cowork-ready marketplace. Coworkers run:

```
/plugin marketplace add mathewdewstowe/linkedin-mcp-skills
/plugin install linkedin-voyager@linkedin-voyager-marketplace
```

Then do the same one-time machine setup above. Done.

## License

MIT
