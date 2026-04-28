# /mcp-skills — MCP Skills GitHub Manager

**Skill type:** Git management for `~/.codex/skills/` → `github.com/mathewdewstowe/linkedin-mcp-skills`
**Repo:** https://github.com/mathewdewstowe/linkedin-mcp-skills
**Local root:** `~/.codex/skills/`

---

## Commands

| Command | Description |
|---------|-------------|
| `/mcp-skills push [message]` | Commit all changes and push to GitHub |
| `/mcp-skills pull` | Pull latest from GitHub |
| `/mcp-skills status` | Show uncommitted changes across all skills |
| `/mcp-skills list` | List all skills with their last commit |
| `/mcp-skills log` | Show recent commits |

---

## How to Run

```
python /Users/matthew_dewstowe/.codex/skills/mcp-skills/main.py <command> [args]
```

---

## Architecture

```
mcp-skills/
  main.py     — CLI entry point
  SKILL.md    — This file
```

The skill runs git commands against `~/.codex/skills/` which is the local
clone of `github.com/mathewdewstowe/linkedin-mcp-skills`.

---

## Skills in this repo

| Skill | Description |
|-------|-------------|
| linked-voyager | LinkedIn outbound automation (Playwright + Voyager API) |
| workday-job-apply | Workday ATS application automation |
| linked-message | LinkedIn messaging utilities |
| codex-primary-runtime | Codex primary runtime skill |
| mcp-skills | This skill — manages GitHub sync |
