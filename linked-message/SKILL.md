---
name: linked-message
description: Send personalized LinkedIn messages using Chrome DevTools Protocol automation
version: 1.0.0
---

# LinkedIn Message Automation Skill

Send personalized outreach messages to LinkedIn first-degree connections using reliable Chrome DevTools Protocol automation.

## Features

- **Non-detected automation**: Uses persistent Chrome context (appears as normal user)
- **Reliable element detection**: Multiple selector strategies for finding Message buttons
- **Persistent authentication**: No re-login required between runs
- **Batch processing**: Handles multiple prospects with configurable delays
- **Comprehensive logging**: Tracks all sends, failures, and reasons
- **Error recovery**: Graceful handling of timeouts and navigation issues

## Usage

### Basic Run (All unsent prospects)
```
npm run
```

### Test Run (Single prospect)
```
npm run test
```

### Batch Run (First N prospects)
```
node linkedin-messaging-cdp.js 10
```

## Requirements

1. **Chrome Profile Setup** (One-time):
   - Opens Chrome with persistent profile at: `~/Library/Application Support/Google/Chrome/LinkedIn-Outreach`
   - Must be logged into LinkedIn
   - Sessions persist for weeks

2. **Prospect Data**:
   - File: `/Users/matthew_dewstowe/Job Apply/ruby-prospects-merged.json`
   - Format: `{ "people": [{ "name", "profile_url", "degree" }] }`

3. **Outreach Log**:
   - File: `/Users/matthew_dewstowe/Job Apply/ruby-outreach-log.json`
   - Automatically created and updated on first run

## Configuration

Edit `/Users/matthew_dewstowe/Job Apply/linkedin-messaging-cdp.js`:

```javascript
const CONFIG = {
  batchSize: 5,                    // Prospects per batch
  delayBetweenMessages: 45000,    // 45 seconds between sends
  pageLoadTimeout: 15000,          // 15 seconds to load profile
  clickTimeout: 10000,             // 10 seconds for clicks
};
```

## Message Template

The skill sends a personalized Ruby outreach message:

```
Hi {firstName}, we're connected and given your role I wanted to reach out directly.

When a prospect shows interest but isn't ready for an AE yet, or simply not well enough qualified to be worth the AE's time, what actually happens to them?

We're building Ruby at Sonesse.ai, a real-time, human-like AI avatar that delivers a fully personalised, interactive demo just as a human would...
```

First name is auto-populated from prospect data.

## How It Works

1. Loads prospects from JSON
2. Identifies unsent prospects from log
3. Launches persistent Chrome context
4. For each prospect:
   - Navigates to LinkedIn profile
   - Finds and clicks Message button (multiple selector strategies)
   - Types personalized message
   - Sends message
   - Logs result with timestamp
   - Waits configured delay before next message

## Success Indicators

✅ Log file updated with sent messages
✅ Chrome window opens (visible, not headless)
✅ Status shows "sent" in ruby-outreach-log.json
✅ No "message_unavailable" errors (unlike LinkedIn MCP)

## Troubleshooting

### Chrome profile not found
- Ensure Chrome has been authenticated to LinkedIn
- Profile path: `~/Library/Application Support/Google/Chrome/LinkedIn-Outreach`

### Message button not found
- Skill tries 5 different selectors (button, link, data attributes, etc.)
- If all fail: LinkedIn may have changed HTML structure
- Check browser window for button visibility

### Session expired
- Delete Chrome profile directory to re-authenticate
- Persistent context should prevent this, but manual refresh available

### Blocked by LinkedIn
- Delays between messages prevent detection
- Non-headless mode prevents webdriver detection
- If still blocked: increase delayBetweenMessages

## Skill Files

- `linkedin-messaging-cdp.js` — Main automation script
- `package.json` — Dependencies (Playwright)
- `SKILL.md` — This file

## Next Steps

1. Test with single prospect: `npm run test`
2. Monitor Chrome window for proper behavior
3. Check log file for "sent" status
4. Run full batch when confident: `npm run`
