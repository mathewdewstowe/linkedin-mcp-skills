# LinkedIn Message Skill - Setup Guide

## Initial Setup (One-time)

### 1. Install Dependencies

```bash
cd /Users/matthew_dewstowe/Job Apply
npm install
```

This installs Playwright (only dependency).

### 2. Authenticate Chrome Profile

The skill uses a persistent Chrome profile. You need to authenticate to LinkedIn once:

1. The first run will launch Chrome with the persistent profile
2. If not logged in, LinkedIn will show login screen
3. Log in with your account: `matthewdewstowe@gmail.com`
4. Chrome will stay logged in for weeks

### 3. Verify Prospect Data

Ensure you have:
- `/Users/matthew_dewstowe/Job Apply/ruby-prospects-merged.json` (191 prospects)
- `/Users/matthew_dewstowe/Job Apply/ruby-outreach-log.json` (existing sends tracked)

## Testing the Skill

### Single Prospect Test

```bash
cd /Users/matthew_dewstowe/Job Apply
npm run test
```

This sends to 1 prospect only. Watch the Chrome window to verify:
- ✓ Opens prospect's profile
- ✓ Finds Message button
- ✓ Types message
- ✓ Sends message
- ✓ Log file updated with "sent" status

**Expected time**: 1-2 minutes

### Batch Test (5 prospects)

```bash
node linkedin-messaging-cdp.js 5
```

Sends to first 5 unsent prospects with 45-second delays between.

**Expected time**: ~5 minutes

## Full Campaign

Once testing confirms it works:

```bash
node linkedin-messaging-cdp.js
```

This sends to ALL remaining unsent prospects (currently ~166).

**Expected time**: ~2.5 hours (with 45-second delays between sends)

## Monitoring

While running:
1. Chrome window stays open and visible
2. Terminal shows real-time progress:
   ```
   [2026-04-28T...] [INFO] Processing: Dave Davies (davidwdavies)
   [2026-04-28T...] [DEBUG] Navigating to https://www.linkedin.com/in/davidwdavies/
   [2026-04-28T...] [DEBUG] Found Message button with selector: a:has-text("Message")
   [2026-04-28T...] [DEBUG] Message button clicked
   [2026-04-28T...] [DEBUG] Typing message for Dave...
   [2026-04-28T...] [DEBUG] Found Send button with selector: button:has-text("Send")
   [2026-04-28T...] [DEBUG] Send button clicked
   [2026-04-28T...] [INFO] ✓ Message sent to Dave Davies
   ```

3. Check log file for updated entries:
   ```bash
   tail -20 /Users/matthew_dewstowe/Job Apply/ruby-outreach-log.json
   ```

## Troubleshooting

### "Chrome profile not found"
Profile directory may not exist or isn't authenticated.

**Solution**:
```bash
mkdir -p ~/Library/Application\ Support/Google/Chrome/LinkedIn-Outreach
# Run once to let it open Chrome for authentication
npm run test
# Log in to LinkedIn when prompted
```

### "Message button not found"
LinkedIn HTML structure changed or profile page didn't load properly.

**Check**:
- Is Chrome window showing the profile?
- Is there a blue "Message" button visible?
- Any 404 errors in console?

**Solution**:
- Increase `pageLoadTimeout` in script (currently 15s)
- Add more selector strategies for Message button

### "Session expired"
Less likely with persistent context, but if LinkedIn logs you out:

**Solution**:
1. Chrome window will appear
2. Log back in
3. Script will retry

### "Too many requests" / Blocked by LinkedIn
If LinkedIn rate-limits you:

**Solution**:
- Increase `delayBetweenMessages` (currently 45s)
- Run in smaller batches
- Wait 24 hours before retrying

## Performance Tips

1. **Don't close the Chrome window** during execution
2. **Run during off-peak hours** (late evening to avoid rate limits)
3. **Start with batches of 5-10** to ensure stability
4. **Monitor first batch** to catch any issues before full run
5. **Leave computer on** until campaign completes

## Safety Notes

✓ No credentials stored (uses persistent Chrome session)
✓ No API tokens exposed (direct browser automation)
✓ Non-headless mode (looks like normal user)
✓ Reasonable delays between messages (45+ seconds)
✓ No rapid-fire sends (won't trigger LinkedIn blocks)

## Next Steps

1. Run: `npm run test` (single prospect)
2. Verify log shows "sent" status
3. Run: `npm run test` (confirm it's consistent)
4. Run: `node linkedin-messaging-cdp.js 5` (small batch)
5. Check log for all 5 marked as "sent"
6. Run: `npm run` (full campaign)
