"""
LinkedInBrowser — Playwright browser automation for LinkedIn actions
that cannot be done via direct Voyager API (invite send, withdraw, search).

LinkedIn has migrated most UI actions to SDUI (Server-Driven UI) which
calls Voyager server-side. Browser automation is the only reliable path.

Uses the dedicated Brave profile at ~/.brave-paginator/profile which
already has an active LinkedIn session.
"""

import time
import random
from urllib.parse import quote
from datetime import datetime


BRAVE_EXE = '/Applications/Brave Browser.app/Contents/MacOS/Brave Browser'
PROFILE_DIR = '/Users/matthew_dewstowe/.brave-paginator/profile'


class LinkedInBrowser:
    """Context manager that wraps a persistent Brave/Chromium browser session."""

    def __init__(self, headless=False, slow_mo=400):
        self.headless = headless
        self.slow_mo = slow_mo
        self._pw = None
        self._context = None
        self._page = None

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._context = self._pw.chromium.launch_persistent_context(
            user_data_dir=PROFILE_DIR,
            executable_path=BRAVE_EXE,
            headless=self.headless,
            slow_mo=self.slow_mo,
            args=['--no-sandbox', '--disable-blink-features=AutomationControlled']
        )
        pages = self._context.pages
        if pages:
            # Reuse the first existing tab — never open a new one
            self._page = pages[0]
        else:
            self._page = self._context.new_page()
        return self

    def __exit__(self, *args):
        # Close only the Playwright connection — leave Brave running with its tabs intact
        try:
            if self._context:
                self._context.close()
        except Exception:
            pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    #  Invite send
    # ------------------------------------------------------------------ #

    def send_invite(self, profile_slug: str) -> dict:
        """
        Navigate to /in/{slug}/ and click Connect → Send without a note.

        Returns: {'success': bool, 'error': str | None}
        """
        page = self._page
        print(f'  [Browser] Loading /in/{profile_slug}/')
        page.goto(f'https://www.linkedin.com/in/{profile_slug}/', wait_until='domcontentloaded', timeout=20000)
        page.wait_for_timeout(3000)
        # Scroll to top so y-coordinates are consistent
        page.evaluate('window.scrollTo(0, 0)')
        page.wait_for_timeout(500)

        # Step 1 — get Connect button coords then native-click.
        # JS el.click() doesn't fire React's event listeners; page.mouse.click() does.
        coords = page.evaluate('''() => {
            const spans = Array.from(document.querySelectorAll("span"));
            const s = spans.find(s => {
                const r = s.getBoundingClientRect();
                return s.textContent.trim() === "Connect" && r.y > 380 && r.y < 600 && r.width > 0;
            });
            if (!s) return null;
            let el = s;
            for (let i = 0; i < 6; i++) {
                el = el.parentElement;
                if (!el) break;
                if (el.tagName === "A" || el.tagName === "BUTTON") {
                    const r = el.getBoundingClientRect();
                    return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
                }
            }
            return null;
        }''')

        if not coords:
            return {'success': False, 'error': 'Connect button not found on profile page'}

        print(f'  [Browser] Clicking Connect at ({coords["x"]:.0f}, {coords["y"]:.0f})')
        page.mouse.click(coords['x'], coords['y'])

        # Wait for shadow modal — poll up to 5s
        send_coords = None
        for _ in range(10):
            page.wait_for_timeout(500)
            btn_coords = page.evaluate('''() => {
                const interop = document.querySelector("#interop-outlet");
                if (!interop || !interop.shadowRoot) return null;
                const btns = Array.from(interop.shadowRoot.querySelectorAll("button"));
                const sendBtn = btns.find(b => b.textContent.trim() === "Send without a note");
                if (!sendBtn) return null;
                const r = sendBtn.getBoundingClientRect();
                return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
            }''')
            if btn_coords:
                send_coords = btn_coords
                break

        if not send_coords:
            # Capture what's in shadow for debugging
            debug = page.evaluate('''() => {
                const i = document.querySelector("#interop-outlet");
                if (!i || !i.shadowRoot) return "no shadow";
                return Array.from(i.shadowRoot.querySelectorAll("button"))
                    .map(b => b.textContent.trim().substring(0, 30)).join("|");
            }''')
            return {'success': False, 'error': f'Send without a note not found. Shadow: {debug}'}

        page.mouse.click(send_coords['x'], send_coords['y'])
        page.wait_for_timeout(2000)
        print(f'  [Browser] ✓ Invite sent to {profile_slug}')
        return {'success': True}

    # ------------------------------------------------------------------ #
    #  Invite withdrawal
    # ------------------------------------------------------------------ #

    def withdraw_invite(self, profile_slug: str) -> dict:
        """
        Navigate to a profile and withdraw a pending invite by clicking
        the Withdraw button (either on profile page or via invitation manager).

        Returns: {'success': bool, 'error': str | None}
        """
        page = self._page
        print(f'  [Browser] Withdrawing invite for {profile_slug}')
        page.goto(f'https://www.linkedin.com/in/{profile_slug}/', wait_until='domcontentloaded')
        page.wait_for_load_state('load')
        page.wait_for_timeout(3500)

        # Look for "Pending" button in the profile header (y > 350 filters out nav badges)
        clicked = page.evaluate('''() => {
            const allSpans = Array.from(document.querySelectorAll("span, button, a, [role=button]"));
            const pending = allSpans.find(el => {
                const t = el.textContent.trim();
                const r = el.getBoundingClientRect();
                return (t === "Pending" || t.includes("Withdraw invitation"))
                    && r.width > 0
                    && r.y > 350;
            });
            if (!pending) return false;
            // Walk up to clickable ancestor (A or BUTTON)
            let el = pending;
            let depth = 0;
            while (el && el.tagName !== "BUTTON" && el.tagName !== "A" && !el.getAttribute("role") && depth < 6) {
                el = el.parentElement;
                depth++;
            }
            if (el) { el.click(); return true; }
            pending.click();
            return true;
        }''')

        if not clicked:
            return {'success': False, 'error': 'No pending invite button found on profile page'}

        page.wait_for_timeout(1200)

        # Click Withdraw in shadow root modal or dropdown
        result = page.evaluate('''() => {
            // Check shadow root
            const interop = document.querySelector("#interop-outlet");
            if (interop && interop.shadowRoot) {
                const btns = Array.from(interop.shadowRoot.querySelectorAll("button"));
                const wb = btns.find(b => b.textContent.trim().toLowerCase().includes("withdraw"));
                if (wb) { wb.click(); return "shadow"; }
            }
            // Regular DOM fallback (dropdown items)
            const allBtns = Array.from(document.querySelectorAll("button, [role=menuitem]"));
            const wb = allBtns.find(b => b.textContent.trim().toLowerCase() === "withdraw");
            if (wb) { wb.click(); return "dom"; }
            return null;
        }''')

        if result:
            page.wait_for_timeout(1500)
            print(f'  [Browser] ✓ Invite withdrawn ({result})')
            return {'success': True}
        else:
            return {'success': False, 'error': 'Withdraw button not found in modal'}

    # ------------------------------------------------------------------ #
    #  People search
    # ------------------------------------------------------------------ #

    def search_people(self, query: str, first_degree_only: bool = False, max_results: int = 20) -> list:
        """
        Navigate to LinkedIn people search and return profile list.

        Returns list of dicts: {slug, name, title, company, profile_url}
        """
        page = self._page
        network_param = '&network=%5B%22F%22%5D' if first_degree_only else ''
        url = f'https://www.linkedin.com/search/results/people/?keywords={quote(query)}{network_param}'

        print(f'  [Browser] Searching people: {query}')
        page.goto(url, wait_until='domcontentloaded')
        page.wait_for_timeout(2500)

        people = page.evaluate('''() => {
            // LinkedIn dropped semantic class names in 2025 — use structural approach.
            // Primary result cards are identified by profile links that contain an <img>
            // (the photo link). Mutual-connection links have no img.
            const photoLinks = Array.from(document.querySelectorAll('a[href*="/in/"]'))
                .filter(a => a.querySelector('img'));

            const results = [];
            const seen = new Set();

            for (const link of photoLinks) {
                const slug = (link.href.match(/\\/in\\/([^/?#]+)/) || [])[1];
                if (!slug || seen.has(slug)) continue;
                seen.add(slug);

                // Walk up to a card ancestor: find the div that also has a sibling
                // containing the person's name text (not just the photo)
                let card = link.parentElement;
                for (let i = 0; i < 6; i++) {
                    if (!card) break;
                    if (card.children.length >= 2) break;
                    card = card.parentElement;
                }

                // Extract lines from card innerText (preserves line breaks)
                const raw = card ? (card.innerText || card.textContent) : link.innerText;
                const lines = raw.split("\\n")
                    .map(l => l.trim())
                    .filter(l => l.length > 1
                        && !l.match(/^(Connect|Follow|Message|·|•|1st|2nd|3rd|and \\d+ other)$/)
                        && !l.match(/^\\d+ (mutual|connection)/)
                    );

                // Name is first meaningful line (strip degree indicator)
                const name = lines[0]
                    ? lines[0].replace(/\\s*[•·]\\s*(1st|2nd|3rd).*/, "").trim()
                    : null;
                const title = lines[1] || null;
                const company = lines[2] || null;

                results.push({
                    slug,
                    name,
                    title,
                    company,
                    profile_url: "https://www.linkedin.com/in/" + slug + "/"
                });
            }
            return results.slice(0, 25);
        }''')

        print(f'  [Browser] Found {len(people)} people')
        return people

    # ------------------------------------------------------------------ #
    #  Get sent invitations from invitation manager
    # ------------------------------------------------------------------ #

    def get_sent_invitations(self) -> list:
        """
        Scrape /mynetwork/invitation-manager/sent/ to get pending sent invites.

        Returns list of dicts: {name, slug, profile_url, sent_days_ago}
        """
        page = self._page
        page.goto('https://www.linkedin.com/mynetwork/invitation-manager/sent/', wait_until='domcontentloaded')
        page.wait_for_timeout(2000)

        items = page.evaluate('''() => {
            const listItems = Array.from(document.querySelectorAll("[role=listitem]"));
            return listItems.filter(li => li.textContent.includes("Withdraw")).map(li => {
                const profileLink = li.querySelector('a[href*="/in/"]');
                const href = profileLink ? profileLink.href : "";
                const slug = href.match(/\\/in\\/([^/?#]+)/)?.[1] || null;

                // Name — from the profile link's aria-label or visible text span
                let name = null;
                if (profileLink) {
                    name = profileLink.getAttribute("aria-label");
                    if (!name) {
                        const nameSpan = profileLink.querySelector("span[aria-hidden='true']") || profileLink.querySelector("span");
                        name = nameSpan ? nameSpan.textContent.trim() : null;
                    }
                }
                if (!name) {
                    // Fallback: first bold or heading-like element
                    const h = li.querySelector("span.t-bold, .t-16, .entity-result__title-text span");
                    name = h ? h.textContent.trim() : null;
                }

                // Sent time text
                const bodyText = li.textContent;
                const daysMatch = bodyText.match(/Sent (\\d+) days? ago/);
                const weeksMatch = bodyText.match(/Sent (\\d+) weeks? ago/);
                const monthsMatch = bodyText.match(/Sent (\\d+) months? ago/);
                let sentDaysAgo = 0; // default 0 = sent today
                if (daysMatch) sentDaysAgo = parseInt(daysMatch[1]);
                else if (weeksMatch) sentDaysAgo = parseInt(weeksMatch[1]) * 7;
                else if (monthsMatch) sentDaysAgo = parseInt(monthsMatch[1]) * 30;

                return {
                    name: name,
                    slug: slug,
                    profile_url: href.split("?")[0] || null,
                    sent_days_ago: sentDaysAgo
                };
            }).filter(i => i.slug);
        }''')

        return items

    # ------------------------------------------------------------------ #
    #  Post engagement — search, likers, commenters, comments
    # ------------------------------------------------------------------ #

    def search_posts(self, query: str, max_results: int = 20) -> list:
        """
        Search LinkedIn posts by keyword and return list of post objects.

        Returns list of dicts: {post_url, author_slug, author_name, post_title, timestamp}
        """
        page = self._page
        from urllib.parse import quote
        url = f'https://www.linkedin.com/search/results/content/?keywords={quote(query)}&type=posts'

        print(f'  [Browser] Searching posts: {query}')
        page.goto(url, wait_until='domcontentloaded')
        page.wait_for_timeout(2500)

        posts = page.evaluate('''() => {
            // Post containers are typically role="listitem" or divs with post structure
            // LinkedIn uses structural matching (no semantic classes after 2025)
            const listItems = Array.from(document.querySelectorAll('[role="listitem"], [data-test-id*="post"], .feed-shared-update-v2'));
            const results = [];
            const seen = new Set();

            for (const item of listItems) {
                // Extract author link — posts have author profile links
                const authorLink = item.querySelector('a[href*="/in/"]');
                if (!authorLink) continue;

                const authorHref = authorLink.href;
                const authorSlug = (authorHref.match(/\\/in\\/([^/?#]+)/) || [])[1];
                if (!authorSlug || seen.has(authorSlug)) continue;
                seen.add(authorSlug);

                // Extract post URL — look for main post link or feed link
                let postUrl = null;
                const postLink = item.querySelector('a[href*="/posts/"], a[href*="/feed/"]');
                if (postLink) {
                    postUrl = postLink.href.split('?')[0];
                } else {
                    // Fallback: construct from feed share ID if present
                    postUrl = authorHref.split('?')[0]; // Use author profile as fallback
                }

                // Extract post title (first 50 chars of text content)
                const textContent = item.innerText || item.textContent;
                const lines = textContent.split("\\n").filter(l => l.trim().length > 0);
                // Skip author name and filter UI elements
                const postTitle = lines.slice(1).join(" ").substring(0, 50).trim();

                // Extract timestamp (look for "X days ago", "X hours ago", etc.)
                const timeMatch = textContent.match(/(\\d+)\\s*(hours?|days?|weeks?|months?) ago/i);
                const timestamp = timeMatch ? timeMatch[0] : null;

                // Get author name from aria-label or visible text
                let authorName = authorLink.getAttribute('aria-label') || '';
                if (!authorName) {
                    const nameSpan = authorLink.querySelector('span[aria-hidden="true"]') || authorLink.querySelector('span');
                    authorName = nameSpan ? nameSpan.textContent.trim() : '';
                }

                results.push({
                    post_url: postUrl,
                    author_slug: authorSlug,
                    author_name: authorName,
                    post_title: postTitle || '(no title)',
                    timestamp: timestamp
                });

                if (results.length >= 25) break; // Hard limit to prevent memory issues
            }
            return results.slice(0, 25);
        }''')

        print(f'  [Browser] Found {len(posts)} posts')
        return posts

    def get_post_likers(self, post_url: str) -> list:
        """
        Navigate to a post and extract people who liked it.

        Returns list of dicts: {slug, name, title, company, profile_url}
        """
        page = self._page
        print(f'  [Browser] Getting likers for post')
        page.goto(post_url, wait_until='domcontentloaded')
        page.wait_for_timeout(3000)

        # Find and click "X likes" button
        likes_coords = page.evaluate('''() => {
            const allElements = Array.from(document.querySelectorAll('button, a, span, [role="button"]'));
            const likesEl = allElements.find(el => {
                const text = el.textContent.trim();
                return /^\\d+\\s*likes?$/.test(text);
            });
            if (!likesEl) return null;
            // Walk up to clickable ancestor
            let el = likesEl;
            for (let i = 0; i < 6; i++) {
                if (!el) break;
                if (el.tagName === 'BUTTON' || el.tagName === 'A' || el.getAttribute('role') === 'button') {
                    const r = el.getBoundingClientRect();
                    return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
                }
                el = el.parentElement;
            }
            return null;
        }''')

        if not likes_coords:
            print(f'  [Browser] ⚠ No likes button found on post')
            return []

        print(f'  [Browser] Clicking likes at ({likes_coords["x"]:.0f}, {likes_coords["y"]:.0f})')
        page.mouse.click(likes_coords['x'], likes_coords['y'])
        page.wait_for_timeout(1500)

        # Extract likers from modal or inline list
        likers = page.evaluate('''() => {
            // Check shadow root modal first (like send_invite pattern)
            let likerElements = [];
            const interop = document.querySelector("#interop-outlet");
            if (interop && interop.shadowRoot) {
                likerElements = Array.from(interop.shadowRoot.querySelectorAll('[role="listitem"], .artdeco-modal__content [role="listitem"]'));
            }
            // Fallback to inline list in regular DOM
            if (likerElements.length === 0) {
                likerElements = Array.from(document.querySelectorAll('[data-test-id*="like"] [role="listitem"], .modal-content [role="listitem"]'));
            }

            const results = [];
            const seen = new Set();

            for (const item of likerElements) {
                const profileLink = item.querySelector('a[href*="/in/"]');
                if (!profileLink) continue;

                const slug = (profileLink.href.match(/\\/in\\/([^/?#]+)/) || [])[1];
                if (!slug || seen.has(slug)) continue;
                seen.add(slug);

                // Extract name, title, company from text lines
                const textContent = item.innerText || item.textContent;
                const lines = textContent.split("\\n")
                    .map(l => l.trim())
                    .filter(l => l.length > 1);

                const name = lines[0] || null;
                const title = lines[1] || null;
                const company = lines[2] || null;

                results.push({
                    slug: slug,
                    name: name,
                    title: title,
                    company: company,
                    profile_url: profileLink.href.split("?")[0]
                });
            }
            return results;
        }''')

        print(f'  [Browser] ✓ Found {len(likers)} likers')
        return likers

    def get_post_commenters(self, post_url: str) -> list:
        """
        Navigate to a post and extract people who commented on it.

        Returns list of dicts: {slug, name, title, company, profile_url, timestamp}
        """
        page = self._page
        print(f'  [Browser] Getting commenters for post')
        page.goto(post_url, wait_until='domcontentloaded')
        page.wait_for_timeout(3000)
        page.evaluate('window.scrollTo(0, 0)')

        # Scroll down to load comments
        page.wait_for_timeout(500)
        page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
        page.wait_for_timeout(2000)

        commenters = page.evaluate('''() => {
            // Comment containers are role="listitem" under comments section
            const commentItems = Array.from(document.querySelectorAll('.comments-comments-list [role="listitem"], [data-test-id*="comment"] [role="listitem"]'));
            const results = [];
            const seen = new Set();

            for (const item of commentItems) {
                const profileLink = item.querySelector('a[href*="/in/"]');
                if (!profileLink) continue;

                const slug = (profileLink.href.match(/\\/in\\/([^/?#]+)/) || [])[1];
                if (!slug || seen.has(slug)) continue;
                seen.add(slug);

                // Extract name, title, company
                const textContent = item.innerText || item.textContent;
                const lines = textContent.split("\\n")
                    .map(l => l.trim())
                    .filter(l => l.length > 1 && !l.match(/^(Reply|Like|More|·|•)$/));

                const name = lines[0] || null;
                const title = lines[1] || null;
                const company = lines[2] || null;

                // Extract timestamp
                const timeMatch = textContent.match(/(\\d+)\\s*(hours?|days?|weeks?|months?) ago/i);
                const timestamp = timeMatch ? timeMatch[0] : null;

                results.push({
                    slug: slug,
                    name: name,
                    title: title,
                    company: company,
                    profile_url: profileLink.href.split("?")[0],
                    timestamp: timestamp
                });
            }
            return results;
        }''')

        print(f'  [Browser] ✓ Found {len(commenters)} commenters')
        return commenters

    def get_post_comments(self, post_url: str) -> list:
        """
        Navigate to a post and extract comments with text content.

        Returns list of dicts: {author_slug, author_name, comment_text, timestamp, reply_count}
        """
        page = self._page
        print(f'  [Browser] Getting comments for post')
        page.goto(post_url, wait_until='domcontentloaded')
        page.wait_for_timeout(3000)

        # Scroll to load comments
        page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
        page.wait_for_timeout(2000)

        comments = page.evaluate('''() => {
            const commentItems = Array.from(document.querySelectorAll('.comments-comments-list [role="listitem"], [data-test-id*="comment"] [role="listitem"]'));
            const results = [];

            for (const item of commentItems) {
                const profileLink = item.querySelector('a[href*="/in/"]');
                if (!profileLink) continue;

                const authorSlug = (profileLink.href.match(/\\/in\\/([^/?#]+)/) || [])[1];
                if (!authorSlug) continue;

                // Extract author name
                let authorName = profileLink.getAttribute('aria-label') || '';
                if (!authorName) {
                    const nameSpan = profileLink.querySelector('span[aria-hidden="true"]') || profileLink.querySelector('span');
                    authorName = nameSpan ? nameSpan.textContent.trim() : '';
                }

                // Extract comment text (skip profile info and metadata)
                const textContent = item.innerText || item.textContent;
                const lines = textContent.split("\\n").map(l => l.trim());
                // Find the actual comment text (skip author name and metadata)
                let commentText = '';
                let foundStart = false;
                for (const line of lines) {
                    if (foundStart && line.match(/^(Reply|Like|\\d+ replies?)/)) break;
                    if (foundStart) commentText += line + " ";
                    if (!foundStart && line === authorName) foundStart = true;
                }
                commentText = commentText.trim().substring(0, 300); // Limit to 300 chars

                // Extract timestamp
                const timeMatch = textContent.match(/(\\d+)\\s*(hours?|days?|weeks?|months?) ago/i);
                const timestamp = timeMatch ? timeMatch[0] : null;

                // Extract reply count
                const replyMatch = textContent.match(/(\\d+)\\s*replies?/i);
                const replyCount = replyMatch ? parseInt(replyMatch[1]) : 0;

                results.push({
                    author_slug: authorSlug,
                    author_name: authorName,
                    comment_text: commentText || '(empty)',
                    timestamp: timestamp,
                    reply_count: replyCount
                });
            }
            return results;
        }''')

        print(f'  [Browser] ✓ Found {len(comments)} comments')
        return comments

    # ------------------------------------------------------------------ #
    #  Voyager API — all routed through Brave browser (li_at auto-included)
    # ------------------------------------------------------------------ #
    #
    #  These methods execute JS fetch() inside the Playwright-controlled
    #  Brave page.  Because the browser already has an active LinkedIn
    #  session, li_at is sent automatically — no need to extract it.
    #
    #  Encoding note: urllib.parse.quote(safe='') encodes ( → %28 and
    #  ) → %29 which LinkedIn's Restli variables parser requires.
    # ------------------------------------------------------------------ #

    def _ensure_linkedin_page(self):
        """Make sure the current page is on linkedin.com so cookies are accessible."""
        current = self._page.url or ''
        if 'linkedin.com' not in current:
            self._page.goto('https://www.linkedin.com/feed/', wait_until='domcontentloaded', timeout=20000)
            self._page.wait_for_timeout(1500)

    def _voyager_fetch(self, url: str) -> dict | None:
        """Run a Voyager API GET in the browser page and return parsed JSON."""
        self._ensure_linkedin_page()
        result = self._page.evaluate('''async (url) => {
            const m = document.cookie.match(/JSESSIONID="?([^";]+)"?/);
            const csrf = m ? m[1] : "";
            try {
                const r = await fetch(url, {
                    credentials: "include",
                    headers: {
                        "csrf-token": csrf,
                        "accept": "application/vnd.linkedin.normalized+json+2.1",
                        "x-restli-protocol-version": "2.0.0",
                        "x-li-lang": "en_US"
                    }
                });
                return {status: r.status, body: await r.json()};
            } catch(e) { return {status: 0, error: String(e)}; }
        }''', url)
        if not result or result.get('status') != 200:
            return None
        return result.get('body')

    def _venc(self, urn: str) -> str:
        """Encode a URN for Restli variables — encodes : ( ) , =."""
        return quote(urn, safe='')

    def _voyager_my_urn(self) -> str | None:
        """Return cached fsd_profile URN, resolving via /me if needed."""
        if not getattr(self, '_my_urn', None):
            self.voyager_get_me()
        return getattr(self, '_my_urn', None)

    # ── Auth ──────────────────────────────────────────────────────────── #

    def voyager_get_me(self) -> dict | None:
        """
        GET /voyager/api/me via browser.
        Caches fsd_profile URN in self._my_urn.
        Returns MiniProfile dict with firstName, lastName, headline, etc.
        """
        d = self._voyager_fetch('https://www.linkedin.com/voyager/api/me')
        if not d:
            return None
        payload = d.get('data', {})
        mini_urn = payload.get('*miniProfile', '')
        self._my_urn = (
            mini_urn.replace('fs_miniProfile:', 'fsd_profile:')
            if mini_urn else None
        )
        included = d.get('included', [])
        return next(
            (i for i in included if 'MiniProfile' in i.get('$type', '')),
            payload,
        )

    # ── Conversations ─────────────────────────────────────────────────── #

    def voyager_get_conversations(self, count: int = 20) -> list:
        """
        GET messengerConversations via browser.

        Returns list of dicts:
          conversation_urn, participant_name, participant_url,
          last_message_text, last_message_at, unread_count
        """
        mailbox_urn = self._voyager_my_urn()
        if not mailbox_urn:
            return []

        url = (
            'https://www.linkedin.com/voyager/api/voyagerMessagingGraphQL/graphql'
            f'?queryId=messengerConversations.0d5e6781bbee71c3e51c8843c6519f48'
            f'&variables=(mailboxUrn:{self._venc(mailbox_urn)})'
        )
        d = self._voyager_fetch(url)
        if not d:
            return []

        included = d.get('included', [])
        participant_map = {
            i['entityUrn']: i
            for i in included
            if i.get('$type') == 'com.linkedin.messenger.MessagingParticipant'
               and i.get('entityUrn')
        }
        message_map = {
            i['entityUrn']: i
            for i in included
            if i.get('$type') == 'com.linkedin.messenger.Message'
               and i.get('entityUrn')
        }
        my_part_urn = f'urn:li:msg_messagingParticipant:{mailbox_urn}'

        conversations = []
        for conv in included:
            if conv.get('$type') != 'com.linkedin.messenger.Conversation':
                continue
            conv_urn = conv.get('entityUrn', '')
            unread   = conv.get('unreadCount', 0)
            last_at  = conv.get('lastActivityAt', 0)
            title    = (conv.get('title') or {}).get('text', '')

            p_name = p_url = ''
            for ref in (conv.get('*conversationParticipants') or []):
                if ref == my_part_urn:
                    continue
                p = participant_map.get(ref, {})
                member = (p.get('participantType') or {}).get('member', {})
                if not member:
                    continue
                first  = (member.get('firstName') or {}).get('text', '')
                last_n = (member.get('lastName') or {}).get('text', '')
                raw_url = member.get('profileUrl', '')
                p_url = raw_url.split('?')[0] if raw_url else ''
                candidate = f'{first} {last_n}'.strip()
                if candidate:
                    p_name = candidate
                    break

            snippet = ''
            msg_refs = (conv.get('messages') or {}).get('*elements', [])
            for mref in reversed(msg_refs):
                txt = (message_map.get(mref, {}).get('body') or {}).get('text', '')
                if txt:
                    snippet = txt[:200]
                    break

            conversations.append({
                'conversation_urn':   conv_urn,
                'participant_name':   p_name or title,
                'participant_url':    p_url,
                'last_message_text':  snippet,
                'last_message_at':    last_at,
                'unread_count':       unread,
            })
        return conversations

    # ── Messages ──────────────────────────────────────────────────────── #

    def voyager_get_messages(self, conversation_urn: str) -> list:
        """
        GET messengerMessages via browser.
        conversation_urn: entityUrn from voyager_get_conversations()
          e.g. 'urn:li:msg_conversation:(urn:li:fsd_profile:HASH,thread_id)'

        Returns list of dicts (oldest → newest):
          message_urn, sender_name, sender_url, text, sent_at
        """
        url = (
            'https://www.linkedin.com/voyager/api/voyagerMessagingGraphQL/graphql'
            f'?queryId=messengerMessages.5846eeb71c981f11e0134cb6626cc314'
            f'&variables=(conversationUrn:{self._venc(conversation_urn)})'
        )
        d = self._voyager_fetch(url)
        if not d:
            return []

        included = d.get('included', [])
        participant_map = {
            i['entityUrn']: i
            for i in included
            if i.get('$type') == 'com.linkedin.messenger.MessagingParticipant'
               and i.get('entityUrn')
        }

        messages = []
        for item in included:
            if item.get('$type') != 'com.linkedin.messenger.Message':
                continue
            text    = (item.get('body') or {}).get('text', '') or ''
            sent_at = item.get('deliveredAt', 0)

            sender_name = sender_url = ''
            sender_ref = item.get('*sender') or ''
            if sender_ref:
                p = participant_map.get(sender_ref, {})
                member = (p.get('participantType') or {}).get('member', {})
                first  = (member.get('firstName') or {}).get('text', '')
                last_n = (member.get('lastName') or {}).get('text', '')
                sender_name = f'{first} {last_n}'.strip()
                raw_url = member.get('profileUrl', '')
                sender_url = raw_url.split('?')[0] if raw_url else ''

            messages.append({
                'message_urn': item.get('entityUrn', ''),
                'sender_name': sender_name,
                'sender_url':  sender_url,
                'text':        text,
                'sent_at':     sent_at,
            })

        messages.sort(key=lambda m: m['sent_at'])
        return messages

    # ── Send message ──────────────────────────────────────────────────── #

    def voyager_start_conversation(self, recipient_profile_urn: str, text: str) -> bool:
        """
        Start a new conversation via Voyager API (createMessage with hostRecipientUrns).

        recipient_profile_urn: fsd_profile URN e.g. 'urn:li:fsd_profile:ACoAAA...'
        text: first message body

        Returns True on success, False on failure.
        """
        mailbox_urn = self._voyager_my_urn()
        self._ensure_linkedin_page()
        result = self._page.evaluate('''async ([recipientUrn, bodyText, mailboxUrn]) => {
            const m = document.cookie.match(/JSESSIONID="?([^";]+)"?/);
            const csrf = m ? m[1] : "";
            const originToken = crypto.randomUUID();
            const trackingId = String.fromCharCode(...crypto.getRandomValues(new Uint8Array(16)));
            const payload = {
                message: {
                    body: { attributes: [], text: bodyText },
                    renderContentUnions: [],
                    originToken: originToken
                },
                mailboxUrn: mailboxUrn,
                hostRecipientUrns: [recipientUrn],
                trackingId: trackingId,
                dedupeByClientGeneratedToken: false
            };
            try {
                const r = await fetch(
                    "https://www.linkedin.com/voyager/api/voyagerMessagingDashMessengerMessages?action=createMessage",
                    {
                        method: "POST",
                        credentials: "include",
                        headers: {
                            "csrf-token": csrf,
                            "content-type": "application/json",
                            "accept": "application/json",
                            "x-restli-protocol-version": "2.0.0",
                            "x-li-lang": "en_US"
                        },
                        body: JSON.stringify(payload)
                    }
                );
                const txt = await r.text();
                return {status: r.status, body: txt.slice(0, 400)};
            } catch(e) { return {status: 0, error: String(e)}; }
        }''', [recipient_profile_urn, text, mailbox_urn])
        if not result:
            return False
        status = result.get('status', 0)
        if status not in (200, 201, 204):
            print(f'  [start_conversation] HTTP {status}: {result.get("body", "")[:200]}')
            return False
        return True

    def voyager_send_message(self, conversation_urn: str, text: str,
                             participant_name: str = '') -> bool:
        """
        Send a message via Voyager API (voyagerMessagingDashMessengerMessages?action=createMessage).

        conversation_urn: entityUrn from voyager_get_conversations()
        text: message body
        participant_name: unused (kept for backward compat)

        Returns True on success, False on failure.
        """
        mailbox_urn = self._voyager_my_urn()
        self._ensure_linkedin_page()
        result = self._page.evaluate('''async ([convUrn, bodyText, mailboxUrn]) => {
            const m = document.cookie.match(/JSESSIONID="?([^";]+)"?/);
            const csrf = m ? m[1] : "";
            const originToken = crypto.randomUUID();
            // 16-byte binary trackingId — required by LinkedIn
            const trackingId = String.fromCharCode(...crypto.getRandomValues(new Uint8Array(16)));
            const payload = {
                message: {
                    body: { attributes: [], text: bodyText },
                    renderContentUnions: [],
                    conversationUrn: convUrn,
                    originToken: originToken
                },
                mailboxUrn: mailboxUrn,
                trackingId: trackingId,
                dedupeByClientGeneratedToken: false
            };
            try {
                const r = await fetch(
                    "https://www.linkedin.com/voyager/api/voyagerMessagingDashMessengerMessages?action=createMessage",
                    {
                        method: "POST",
                        credentials: "include",
                        headers: {
                            "csrf-token": csrf,
                            "content-type": "application/json",
                            "accept": "application/json",
                            "x-restli-protocol-version": "2.0.0",
                            "x-li-lang": "en_US"
                        },
                        body: JSON.stringify(payload)
                    }
                );
                const txt = await r.text();
                return {status: r.status, body: txt.slice(0, 400)};
            } catch(e) { return {status: 0, error: String(e)}; }
        }''', [conversation_urn, text, mailbox_urn])
        if not result:
            return False
        status = result.get('status', 0)
        if status not in (200, 201, 204):
            print(f'  [send_message] HTTP {status}: {result.get("body", "")[:200]}')
            return False
        return True

    # ── Post engagement via Voyager API (faster than UI scraping) ──────── #

    def voyager_get_post_likers(self, post_urn: str) -> list:
        """
        GET /feed/updates/{urn}?updateType=MAIN_FEED via browser.
        Extracts Reaction objects from included[].

        post_urn: 'urn:li:activity:XXXXX'
        Returns list of dicts: slug, name, headline, profile_url, reaction_type.
        """
        url = (
            f'https://www.linkedin.com/voyager/api/feed/updates/{self._venc(post_urn)}'
            '?updateType=MAIN_FEED'
        )
        d = self._voyager_fetch(url)
        if not d:
            return []

        likers = []
        for item in d.get('included', []):
            if item.get('$type') != 'com.linkedin.voyager.feed.social.Reaction':
                continue
            name     = (item.get('name') or {}).get('text', '')
            headline = (item.get('description') or {}).get('text', '')
            nav_url  = (item.get('navigationContext') or {}).get('actionTarget', '')
            profile_url = nav_url.split('?')[0] if nav_url else ''
            slug = profile_url.rstrip('/').split('/')[-1] if profile_url else ''
            likers.append({
                'slug':          slug,
                'name':          name,
                'headline':      headline,
                'urn':           item.get('actorUrn', ''),
                'profile_url':   profile_url,
                'reaction_type': item.get('reactionType', 'LIKE'),
            })
        return likers

    def voyager_get_post_comments(self, post_urn: str) -> list:
        """
        GET /feed/updates/{urn}?updateType=MAIN_FEED via browser.
        Extracts Comment objects; auto-resolves ugcPost URN if needed.

        post_urn: 'urn:li:activity:XXXXX'
        Returns list of dicts:
          author_slug, author_name, author_headline, comment_text, profile_url, timestamp
        """
        url = (
            f'https://www.linkedin.com/voyager/api/feed/updates/{self._venc(post_urn)}'
            '?updateType=MAIN_FEED'
        )
        d = self._voyager_fetch(url)
        if not d:
            return []

        included = d.get('included', [])

        # Auto-resolve activity URN → ugcPost URN for full comment list
        sd = next(
            (i for i in included if i.get('$type') == 'com.linkedin.voyager.feed.SocialDetail'),
            None,
        )
        if sd:
            thread_id = sd.get('threadId', '')
            if thread_id and (thread_id.startswith('ugcPost:') or thread_id.startswith('article:')):
                ugc_urn = f'urn:li:{thread_id}'
                if ugc_urn != post_urn:
                    d2 = self._voyager_fetch(
                        f'https://www.linkedin.com/voyager/api/feed/updates/{self._venc(ugc_urn)}'
                        '?updateType=MAIN_FEED'
                    )
                    if d2:
                        included = d2.get('included', [])

        profiles = {}
        for item in included:
            if 'MiniProfile' not in item.get('$type', ''):
                continue
            hash_id = (item.get('entityUrn') or '').split(':')[-1]
            if hash_id:
                profiles[hash_id] = item

        comments = []
        for item in included:
            if item.get('$type') != 'com.linkedin.voyager.feed.Comment':
                continue
            text     = (item.get('commentV2') or {}).get('text', '') or item.get('comment', '')
            hash_id  = item.get('commenterProfileId', '')
            profile  = profiles.get(hash_id, {})
            slug     = profile.get('publicIdentifier', '')
            name     = f"{profile.get('firstName', '')} {profile.get('lastName', '')}".strip()
            headline = profile.get('occupation', '') or profile.get('headline', '')
            comments.append({
                'author_slug':     slug,
                'author_name':     name,
                'author_headline': headline,
                'comment_text':    text,
                'timestamp':       item.get('createdTime', 0),
                'profile_url':     f'https://www.linkedin.com/in/{slug}/' if slug else '',
            })
        return comments

    # ── People / post search ──────────────────────────────────────────── #

    # Hardcoded geoUrns for fast/reliable UK + common locations
    GEO_URN_MAP = {
        'united kingdom':   '101165590',
        'uk':               '101165590',
        'great britain':    '101165590',
        'england':          '102299470',
        'scotland':         '100536993',
        'wales':            '101750022',
        'northern ireland': '105572676',
        'london':           '90009496',
        'greater london':   '90009496',
        'london area':      '90009496',
        'manchester':       '102257491',
        'birmingham':       '105712376',
        'bristol':          '105778963',
        'edinburgh':        '105530811',
        'glasgow':          '102299470',
        'leeds':            '101165590',  # fallback to UK if uncertain
        'cardiff':          '101750022',  # Wales
        'liverpool':        '105712376',
        'oxford':           '105778963',
        'cambridge':        '105778963',
        'bath':             '105778963',
        # Common non-UK
        'new york':         '105080838',
        'san francisco':    '102277331',
        'paris':            '104246759',
        'berlin':            '106967730',
        'dublin':            '104738515',
    }

    # ── Profile (full) ────────────────────────────────────────────────── #

    def voyager_get_profile_full(self, slug: str) -> dict | None:
        """
        Get profile data — uses search + profile activity since legacy
        /profileView endpoint is deprecated. Returns name, headline, location,
        recent posts (as a proxy for activity).
        Note: detailed positions/educations require modern GraphQL profile
        cards which need queryId capture (TODO).
        """
        slug = slug.rstrip('/').split('/')[-1].split('?')[0]
        # Step 1: search to find the profile + URN
        people = self.voyager_search_people(slug.replace('-', ' '), count=10)
        match = next((p for p in people if p.get('slug', '').lower() == slug.lower()),
                     people[0] if people else None)
        if not match:
            return None

        # Step 2: get recent posts for context
        posts = self.voyager_get_profile_posts(match['urn'].split(',')[0].split('(')[-1] if '(' in match['urn'] else slug, count=5)

        return {
            'name':       match['name'],
            'headline':   match['headline'],
            'location':   match.get('location', ''),
            'industry':   '',
            'summary':    '',
            'public_id':  match['slug'],
            'profile_url': match['profile_url'],
            'urn':        match['urn'],
            'positions':  [],
            'educations': [],
            'skills':     [],
            'recent_posts': posts,
        }

    def voyager_get_profile_contact(self, slug: str) -> dict | None:
        """
        Get contact info via /voyager/api/identity/profiles/{slug}/profileContactInfo.
        Returns dict with: email, phones[], websites[], twitter, ims, birthday.
        Only fields the user has chosen to share with you.
        """
        slug = slug.rstrip('/').split('/')[-1].split('?')[0]
        d = self._voyager_fetch(
            f'https://www.linkedin.com/voyager/api/identity/profiles/{quote(slug, safe="")}/profileContactInfo'
        )
        if not d:
            return None
        data = d.get('data') or d
        return {
            'email':     data.get('emailAddress', ''),
            'phones':    [p.get('number', '') for p in (data.get('phoneNumbers') or [])],
            'websites':  [w.get('url', '') for w in (data.get('websites') or [])],
            'twitter':   [t.get('name', '') for t in (data.get('twitterHandles') or [])],
            'ims':       [{'provider': im.get('provider', ''), 'id': im.get('id', '')}
                          for im in (data.get('ims') or [])],
            'birthday':  data.get('birthDateOn', {}),
            'address':   data.get('address', ''),
            'connected_at': data.get('connectedAt', 0),
        }

    def voyager_get_profile_activity(self, slug_or_urn: str, count: int = 20) -> list:
        """
        Get all recent profile activity (posts + likes + comments + reposts).
        Uses identity/profileUpdatesV2 with q=memberFeed (more inclusive than memberShareFeed).
        """
        if slug_or_urn.startswith('urn:li:fsd_profile:'):
            profile_urn = slug_or_urn
        else:
            slug = slug_or_urn.rstrip('/').split('/')[-1].split('?')[0]
            people = self.voyager_search_people(slug.replace('-', ' '), count=10)
            match = next((p for p in people if p.get('slug', '').lower() == slug.lower()),
                         people[0] if people else None)
            if not match:
                return []
            import re as _re
            m = _re.search(r'(urn:li:fsd_profile:[^,)]+)', match.get('urn', ''))
            profile_urn = m.group(1) if m else ''
        if not profile_urn:
            return []

        # memberFeed includes all activity types
        url = (
            'https://www.linkedin.com/voyager/api/identity/profileUpdatesV2'
            f'?profileUrn={quote(profile_urn, safe="")}'
            f'&q=memberFeed&count={count}'
        )
        d = self._voyager_fetch(url)
        if not d:
            return []
        included = d.get('included', [])
        social_counts = {
            it.get('entityUrn', ''): {
                'reactions': it.get('numLikes', 0),
                'comments':  it.get('numComments', 0),
            }
            for it in included
            if it.get('$type') == 'com.linkedin.voyager.feed.shared.SocialActivityCounts'
        }

        activities = []
        for it in included:
            if it.get('$type') != 'com.linkedin.voyager.feed.render.UpdateV2':
                continue
            urn = (it.get('updateMetadata') or {}).get('urn', '')
            commentary = it.get('commentary') or {}
            text = (commentary.get('text') or {}).get('text', '') or ''
            actor = (it.get('actor') or {})
            actor_name = (actor.get('name') or {}).get('text', '')
            social_ref = it.get('*socialDetail', '')
            sc = social_counts.get(social_ref, {})
            if not sc and urn:
                for c_key, c_val in social_counts.items():
                    if urn in c_key:
                        sc = c_val; break
            # Determine activity type
            header = it.get('header') or {}
            header_text = (header.get('text') or {}).get('text', '') if header else ''
            activities.append({
                'type':      'repost' if 'reposted' in header_text.lower() else
                             ('like'  if 'liked'    in header_text.lower() else
                             ('comment' if 'commented' in header_text.lower() else 'post')),
                'header':    header_text,
                'actor':     actor_name,
                'post_urn':  urn,
                'post_url':  f'https://www.linkedin.com/feed/update/{urn}/' if urn else '',
                'text':      text,
                'reactions': sc.get('reactions', 0),
                'comments':  sc.get('comments', 0),
            })
            if len(activities) >= count:
                break
        return activities

    # ── Company ───────────────────────────────────────────────────────── #

    def voyager_get_company(self, slug: str) -> dict | None:
        """
        Get company info via search (legacy /organization/companies is deprecated).
        Returns dict with: name, tagline, industry, urn, company_id, public_url.
        """
        slug = slug.rstrip('/').split('/')[-1].split('?')[0]
        # Use search to find the company
        keywords = slug.replace('-', ' ').replace('_', ' ')
        variables = (
            f'(query:(keywords:{quote(keywords, safe="")},'
            f'flagshipSearchIntent:SEARCH_SRP,'
            f'queryParameters:List((key:resultType,value:List(COMPANIES))),'
            f'includeFiltersInResponse:false))'
        )
        url = (
            'https://www.linkedin.com/voyager/api/graphql'
            '?queryId=voyagerSearchDashClusters.b0928897b71bd00a5a7291755dcd64f0'
            f'&variables={variables}'
        )
        d = self._voyager_fetch(url)
        if not d:
            return None
        # Collect candidates, prefer exact slug match
        import re as _re
        candidates = []
        for item in d.get('included', []):
            if 'EntityResultViewModel' not in item.get('$type', ''):
                continue
            nav_url = (item.get('navigationContext') or {}).get('url', '') or item.get('navigationUrl', '')
            if '/company/' not in nav_url:
                continue
            company_slug = nav_url.split('/company/')[-1].split('?')[0].rstrip('/')
            candidates.append((item, company_slug, nav_url))
        # Sort: exact match > startswith > contains
        slug_l = slug.lower()
        def rank(c):
            cs = c[1].lower()
            if cs == slug_l: return 0
            if cs.startswith(slug_l): return 1
            if slug_l in cs: return 2
            return 3
        candidates.sort(key=rank)
        for item, company_slug, nav_url in candidates:
            if rank((item, company_slug, nav_url)) <= 2:
                name     = (item.get('title') or {}).get('text', '')
                tagline  = (item.get('primarySubtitle') or {}).get('text', '')
                location = (item.get('secondarySubtitle') or {}).get('text', '')
                summary  = (item.get('summary') or {}).get('text', '') if item.get('summary') else ''
                urn      = item.get('entityUrn', '')
                # Extract numeric company id
                m = _re.search(r'urn:li:fsd_company:(\d+)', urn) or _re.search(r'(\d+)', urn)
                company_id = m.group(1) if m else ''
                # Also check trackingUrn for company id
                track = item.get('trackingUrn', '')
                m2 = _re.search(r'urn:li:company:(\d+)', track)
                if m2:
                    company_id = m2.group(1)
                return {
                    'name':       name,
                    'tagline':    tagline,
                    'industry':   tagline,  # LinkedIn shows industry in primarySubtitle
                    'location':   location,
                    'description':summary,
                    'urn':        urn,
                    'company_id': company_id,
                    'slug':       company_slug,
                    'public_url': f'https://www.linkedin.com/company/{company_slug}/',
                    'employee_count': '',  # not available in search hit
                    'follower_count': '',
                    'website':    '',
                    'hq':         {'country': '', 'city': location, 'line1': ''},
                }
        # Nothing matched
        return None

    def voyager_get_company_employees(self, slug: str, title: str | None = None,
                                      count: int = 20, first_degree_only: bool = False,
                                      location: str | None = None) -> list:
        """
        Get employees at a company, optionally filtered by job title.
        Uses voyagerSearchDashClusters with currentCompany filter.
        """
        # First resolve company slug → company ID
        company = self.voyager_get_company(slug)
        if not company:
            return []
        company_id = company['company_id']

        kw = title or ''
        filters = f'List((key:resultType,value:List(PEOPLE)),(key:currentCompany,value:List({company_id}))'
        if first_degree_only:
            filters += ',(key:network,value:List(F))'
        if location:
            geo_id = self.voyager_geo_lookup(location)
            if geo_id:
                filters += f',(key:geoUrn,value:List({geo_id}))'
        filters += ')'

        variables = (
            f'(query:(keywords:{quote(kw, safe="")},'
            f'flagshipSearchIntent:SEARCH_SRP,'
            f'queryParameters:{filters},'
            f'includeFiltersInResponse:false))'
        )
        url = (
            'https://www.linkedin.com/voyager/api/graphql'
            '?queryId=voyagerSearchDashClusters.b0928897b71bd00a5a7291755dcd64f0'
            f'&variables={variables}'
        )
        d = self._voyager_fetch(url)
        if not d:
            return []

        people, seen = [], set()
        for item in d.get('included', []):
            if 'EntityResultViewModel' not in item.get('$type', ''):
                continue
            name     = (item.get('title') or {}).get('text', '')
            headline = (item.get('primarySubtitle') or {}).get('text', '')
            loc      = (item.get('secondarySubtitle') or {}).get('text', '')
            nav_url  = (item.get('navigationContext') or {}).get('url', '') or item.get('navigationUrl', '')
            ps       = nav_url.split('/in/')[-1].split('?')[0].strip('/') if '/in/' in nav_url else ''
            urn      = item.get('entityUrn', '')
            if not name or not ps or ps in seen:
                continue
            if title and title.lower() not in headline.lower():
                continue
            seen.add(ps)
            people.append({
                'slug':        ps,
                'name':        name,
                'headline':    headline,
                'location':    loc,
                'urn':         urn,
                'profile_url': f'https://www.linkedin.com/in/{ps}/',
            })
            if len(people) >= count:
                break
        return people

    # ── Feed ──────────────────────────────────────────────────────────── #

    def voyager_get_my_feed(self, count: int = 20) -> list:
        """Get my homepage feed posts. Returns list of dicts with author, text, urn, counts."""
        url = (
            'https://www.linkedin.com/voyager/api/feed/updatesV2'
            f'?q=chronFeed&count={count}'
        )
        d = self._voyager_fetch(url)
        if not d:
            return []
        included = d.get('included', [])
        social_counts = {
            it.get('entityUrn', ''): {
                'reactions': it.get('numLikes', 0),
                'comments':  it.get('numComments', 0),
            }
            for it in included
            if it.get('$type') == 'com.linkedin.voyager.feed.shared.SocialActivityCounts'
        }
        posts = []
        for it in included:
            if it.get('$type') != 'com.linkedin.voyager.feed.render.UpdateV2':
                continue
            urn = (it.get('updateMetadata') or {}).get('urn', '')
            commentary = it.get('commentary') or {}
            text = (commentary.get('text') or {}).get('text', '') or ''
            actor = it.get('actor') or {}
            actor_name = (actor.get('name') or {}).get('text', '')
            actor_sub = (actor.get('subDescription') or actor.get('description') or {}).get('text', '')
            social_ref = it.get('*socialDetail', '')
            sc = social_counts.get(social_ref, {})
            if not sc and urn:
                for c_key, c_val in social_counts.items():
                    if urn in c_key:
                        sc = c_val; break
            posts.append({
                'author':    actor_name,
                'sub':       actor_sub,
                'post_urn':  urn,
                'post_url':  f'https://www.linkedin.com/feed/update/{urn}/' if urn else '',
                'text':      text,
                'reactions': sc.get('reactions', 0),
                'comments':  sc.get('comments', 0),
            })
            if len(posts) >= count:
                break
        return posts

    # ── Invites ───────────────────────────────────────────────────────── #

    def voyager_get_invites_received(self, count: int = 50) -> list:
        """Pending invites received (people asking to connect with me)."""
        url = (
            'https://www.linkedin.com/voyager/api/relationships/invitationViews'
            f'?q=receivedInvitation&start=0&count={count}'
        )
        d = self._voyager_fetch(url)
        if not d:
            return []
        invites = []
        for el in d.get('elements', []):
            inv = (el.get('invitation') or {})
            inviter = el.get('genericInvitationView') or {}
            from_member = (inv.get('fromMember') or inviter.get('inviterMiniProfile') or {})
            invites.append({
                'invitation_urn': inv.get('entityUrn', ''),
                'invitation_id':  inv.get('invitationId', '') or inv.get('entityUrn', '').split(':')[-1],
                'shared_secret':  inv.get('sharedSecret', ''),
                'message':        (inv.get('customMessage') or {}).get('text', ''),
                'from_name':      f"{from_member.get('firstName', '')} {from_member.get('lastName', '')}".strip(),
                'from_headline':  from_member.get('occupation', '') or from_member.get('headline', ''),
                'from_slug':      from_member.get('publicIdentifier', ''),
                'sent_at':        inv.get('sentTime', 0),
            })
        return invites

    def voyager_get_invites_sent(self, count: int = 50) -> list:
        """Pending invites I've sent (still waiting for accept)."""
        url = (
            'https://www.linkedin.com/voyager/api/relationships/invitationViews'
            f'?q=sentInvitation&start=0&count={count}'
        )
        d = self._voyager_fetch(url)
        if not d:
            return []
        invites = []
        for el in d.get('elements', []):
            inv = (el.get('invitation') or {})
            recipient = (inv.get('toMember') or {})
            invites.append({
                'invitation_urn': inv.get('entityUrn', ''),
                'invitation_id':  inv.get('invitationId', '') or inv.get('entityUrn', '').split(':')[-1],
                'shared_secret':  inv.get('sharedSecret', ''),
                'to_name':        f"{recipient.get('firstName', '')} {recipient.get('lastName', '')}".strip(),
                'to_headline':    recipient.get('occupation', '') or recipient.get('headline', ''),
                'to_slug':        recipient.get('publicIdentifier', ''),
                'sent_at':        inv.get('sentTime', 0),
            })
        return invites

    def voyager_invite_action(self, invitation_urn: str, shared_secret: str,
                              action: str = 'accept') -> bool:
        """
        Accept or ignore a received invite.
        action: 'accept' | 'ignore'
        """
        if action not in ('accept', 'ignore'):
            return False
        endpoint = 'closeInvitations' if action == 'ignore' else 'acceptInvite'
        # Use REST endpoint for accept/ignore
        self._ensure_linkedin_page()
        result = self._page.evaluate('''async ([url, payload]) => {
            const m = document.cookie.match(/JSESSIONID="?([^";]+)"?/);
            const csrf = m ? m[1] : "";
            const r = await fetch(url, {
                method: "POST", credentials: "include",
                headers: {"csrf-token": csrf, "content-type": "application/json",
                          "accept": "application/json", "x-restli-protocol-version": "2.0.0"},
                body: JSON.stringify(payload)
            });
            return {status: r.status, body: (await r.text()).slice(0, 200)};
        }''', [
            f'https://www.linkedin.com/voyager/api/relationships/invitations?action={endpoint}',
            {'invitationId': invitation_urn.split(':')[-1], 'sharedSecret': shared_secret,
             'isGenericInvitation': False}
        ])
        return result and result.get('status') in (200, 201, 204)

    # ── Reactions / comments ──────────────────────────────────────────── #

    def voyager_create_post(self, text: str, visibility: str = 'PUBLIC') -> dict | None:
        """
        Create a new LinkedIn post.
        visibility: PUBLIC | CONNECTIONS
        Returns: {'urn': '...', 'url': '...'} on success, None on failure.
        """
        my_urn = self._voyager_my_urn()
        # Convert fsd_profile URN to person URN if needed
        person_urn = my_urn.replace('fsd_profile:', 'person:') if my_urn else ''
        self._ensure_linkedin_page()
        result = self._page.evaluate('''async ([text, visibility, ownerUrn]) => {
            const m = document.cookie.match(/JSESSIONID="?([^";]+)"?/);
            const csrf = m ? m[1] : "";
            const trackingId = String.fromCharCode(...crypto.getRandomValues(new Uint8Array(16)));
            const originToken = crypto.randomUUID();
            const payload = {
                visibleToConnectionsOnly: visibility === "CONNECTIONS",
                allowedCommentersScope: "ALL",
                origin: "FEED",
                commentary: { text: text, attributes: [] },
                contentEntities: [],
                media: null,
                trackingId: trackingId,
                originToken: originToken
            };
            const url = "https://www.linkedin.com/voyager/api/contentcreation/normShares";
            const r = await fetch(url, {
                method: "POST",
                credentials: "include",
                headers: {
                    "csrf-token": csrf,
                    "content-type": "application/json",
                    "accept": "application/json",
                    "x-restli-protocol-version": "2.0.0",
                    "x-li-lang": "en_US"
                },
                body: JSON.stringify(payload)
            });
            const txt = await r.text();
            return {status: r.status, body: txt.slice(0, 500)};
        }''', [text, visibility, person_urn])
        if not result:
            return None
        if result.get('status') not in (200, 201):
            print(f'  [create_post] HTTP {result.get("status")}: {result.get("body","")[:300]}')
            return None
        # Parse activity URN from response
        import json as _json, re as _re
        try:
            body = _json.loads(result.get('body', '{}'))
            urn = body.get('updateUrn', '') or body.get('entityUrn', '') or ''
            if not urn:
                # Fallback: scan response for activity URN
                m = _re.search(r'urn:li:activity:\d+', result.get('body', ''))
                urn = m.group(0) if m else ''
        except Exception:
            urn = ''
        return {
            'urn': urn,
            'url': f'https://www.linkedin.com/feed/update/{urn}/' if urn else '',
        }

    def voyager_react_post(self, post_urn: str, reaction: str = 'LIKE') -> bool:
        """
        React to a post.
        reaction: LIKE | PRAISE | EMPATHY | INTEREST | APPRECIATION | ENTERTAINMENT
        """
        # Resolve activity URN if needed
        if not post_urn.startswith('urn:li:'):
            import re as _re
            m = _re.search(r'urn:li:\w+:\d+', post_urn)
            post_urn = m.group(0) if m else post_urn
        my_urn = self._voyager_my_urn()
        self._ensure_linkedin_page()
        result = self._page.evaluate('''async ([postUrn, reaction, myUrn]) => {
            const m = document.cookie.match(/JSESSIONID="?([^";]+)"?/);
            const csrf = m ? m[1] : "";
            // Use the dash voyager actions endpoint
            const url = "https://www.linkedin.com/voyager/api/voyagerSocialDashReactions?threadUrn=" + encodeURIComponent(postUrn);
            const payload = {reactionType: reaction};
            const r = await fetch(url, {
                method: "POST", credentials: "include",
                headers: {"csrf-token": csrf, "content-type": "application/json",
                          "accept": "application/json", "x-restli-protocol-version": "2.0.0"},
                body: JSON.stringify(payload)
            });
            return {status: r.status, body: (await r.text()).slice(0, 200)};
        }''', [post_urn, reaction, my_urn])
        if not result:
            return False
        if result.get('status') not in (200, 201, 204):
            print(f'  [react_post] HTTP {result.get("status")}: {result.get("body", "")[:200]}')
            return False
        return True

    def voyager_comment_post(self, post_urn: str, text: str) -> bool:
        """Comment on a post."""
        if not post_urn.startswith('urn:li:'):
            import re as _re
            m = _re.search(r'urn:li:\w+:\d+', post_urn)
            post_urn = m.group(0) if m else post_urn
        my_urn = self._voyager_my_urn()
        self._ensure_linkedin_page()
        result = self._page.evaluate('''async ([postUrn, text, myUrn]) => {
            const m = document.cookie.match(/JSESSIONID="?([^";]+)"?/);
            const csrf = m ? m[1] : "";
            const url = "https://www.linkedin.com/voyager/api/feed/comments?action=create";
            const payload = {
                actor: myUrn,
                threadUrn: postUrn,
                commentV2: {text: text, attributes: []}
            };
            const r = await fetch(url, {
                method: "POST", credentials: "include",
                headers: {"csrf-token": csrf, "content-type": "application/json",
                          "accept": "application/json", "x-restli-protocol-version": "2.0.0"},
                body: JSON.stringify(payload)
            });
            return {status: r.status, body: (await r.text()).slice(0, 300)};
        }''', [post_urn, text, my_urn])
        if not result:
            return False
        if result.get('status') not in (200, 201, 204):
            print(f'  [comment_post] HTTP {result.get("status")}: {result.get("body", "")[:200]}')
            return False
        return True

    def voyager_geo_lookup(self, location: str) -> str | None:
        """Resolve a location string to a LinkedIn geoUrn id.
        Uses hardcoded map first, then typeahead as fallback."""
        key = location.lower().strip()
        if key in self.GEO_URN_MAP:
            return self.GEO_URN_MAP[key]
        # Typeahead fallback (queryId may rotate — best-effort)
        url = (
            'https://www.linkedin.com/voyager/api/graphql'
            '?queryId=voyagerSearchDashReusableTypeahead.b8f1adee2f8def6d50d4d54b2b8b4a76'
            f'&variables=(query:(typeaheadFilterQuery:(geoSearchTypes:List(MARKET_AREA,COUNTRY_REGION,ADMIN_DIVISION_1,CITY)),'
            f'typeaheadUseCase:GEO,keywords:{quote(location, safe="")}))'
        )
        d = self._voyager_fetch(url)
        if not d:
            return None
        import json as _json, re as _re
        m = _re.search(r'urn:li:geo:(\d+)', _json.dumps(d))
        return m.group(1) if m else None

    def voyager_search_people(self, query: str = '', title: str | None = None,
                              first_degree_only: bool = False, count: int = 20,
                              location: str | None = None,
                              title_strict: bool = False,
                              titles_any: list | None = None) -> list:
        """
        Search people via Voyager GraphQL search.

        Args:
          query: keywords for full-text search
          title: job title — when title_strict=True, ONLY headline is matched
          first_degree_only: filter to 1st-degree connections
          location: optional location filter (matched against secondarySubtitle)
          title_strict: if True, require `title` substring to appear in headline

        Returns list of dicts: slug, name, headline, location, profile_url, urn.
        """
        # Build keyword: free-text query, or first title in list, or single title
        kw = query
        if not kw:
            if titles_any:
                kw = ' OR '.join(f'"{t}"' for t in titles_any)
            elif title:
                kw = title
        # Resolve location → geoUrn for server-side filtering
        geo_id = None
        if location:
            geo_id = self.voyager_geo_lookup(location)
            if geo_id:
                print(f'  [search] Resolved "{location}" → geoUrn {geo_id}')
            else:
                print(f'  [search] Could not resolve location "{location}" — falling back to client-side filter')
        filters = 'List((key:resultType,value:List(PEOPLE))'
        if first_degree_only:
            filters += ',(key:network,value:List(F))'
        if geo_id:
            filters += f',(key:geoUrn,value:List({geo_id}))'
        filters += ')'
        variables = (
            f'(query:(keywords:{quote(kw, safe="")},'
            f'flagshipSearchIntent:SEARCH_SRP,'
            f'queryParameters:{filters},'
            f'includeFiltersInResponse:false))'
        )
        url = (
            'https://www.linkedin.com/voyager/api/graphql'
            '?queryId=voyagerSearchDashClusters.b0928897b71bd00a5a7291755dcd64f0'
            f'&variables={variables}'
        )
        d = self._voyager_fetch(url)
        people, seen = [], set()

        if d:
            for item in d.get('included', []):
                t = item.get('$type', '')
                if 'EntityResultViewModel' not in t:
                    continue
                name     = (item.get('title') or {}).get('text', '')
                headline = (item.get('primarySubtitle') or {}).get('text', '')
                loc      = (item.get('secondarySubtitle') or {}).get('text', '')
                nav_url  = (item.get('navigationContext') or {}).get('url', '') or item.get('navigationUrl', '')
                slug     = nav_url.split('/in/')[-1].split('?')[0].strip('/') if '/in/' in nav_url else ''
                urn      = item.get('entityUrn', '')
                if not name or not slug or slug in seen:
                    continue

                # OR list of titles — match if ANY appears in headline
                if titles_any:
                    if not any(t.lower() in headline.lower() for t in titles_any):
                        continue
                # Single strict title filter — must appear in headline
                elif title and title_strict:
                    if title.lower() not in headline.lower():
                        continue
                elif title and not title_strict:
                    if title.lower() not in (headline + ' ' + name).lower():
                        continue

                # Client-side location filter only if geoUrn lookup failed
                if location and not geo_id:
                    if location.lower() not in loc.lower():
                        continue

                seen.add(slug)
                people.append({
                    'slug':        slug,
                    'name':        name,
                    'headline':    headline,
                    'location':    loc,
                    'urn':         urn,
                    'profile_url': f'https://www.linkedin.com/in/{slug}/',
                })
                if len(people) >= count:
                    break
        return people

    def voyager_get_profile_posts(self, slug_or_urn: str, count: int = 10) -> list:
        """
        Get a member's recent posts via identity/profileUpdatesV2 (memberShareFeed).

        slug_or_urn: search-result fsd_profile URN OR a public identifier like 'zhu-amanda'.
        Returns list of dicts: post_urn, post_url, text, reactions, comments, share_url.
        """
        # Resolve slug → fsd_profile URN
        if slug_or_urn.startswith('urn:li:fsd_profile:'):
            profile_urn = slug_or_urn
        else:
            slug = slug_or_urn.rstrip('/').split('/')[-1].split('?')[0]
            people = self.voyager_search_people(slug.replace('-', ' '), count=10)
            match = next((p for p in people if p.get('slug', '').lower() == slug.lower()), None) \
                    or (people[0] if people else None)
            if not match:
                return []
            import re as _re
            m = _re.search(r'(urn:li:fsd_profile:[^,)]+)', match.get('urn', ''))
            profile_urn = m.group(1) if m else ''
        if not profile_urn:
            return []

        url = (
            'https://www.linkedin.com/voyager/api/identity/profileUpdatesV2'
            f'?profileUrn={quote(profile_urn, safe="")}'
            f'&q=memberShareFeed&count={count}'
        )
        d = self._voyager_fetch(url)
        if not d:
            return []

        included = d.get('included', [])
        # Build lookup: socialDetail URN -> counts
        social_counts = {}
        for it in included:
            if it.get('$type') == 'com.linkedin.voyager.feed.shared.SocialActivityCounts':
                key = it.get('entityUrn', '')
                social_counts[key] = {
                    'reactions': it.get('numLikes', 0) or it.get('numImpressions', 0),
                    'comments':  it.get('numComments', 0),
                }

        # Now scan UpdateV2 items
        posts = []
        for it in included:
            if it.get('$type') != 'com.linkedin.voyager.feed.render.UpdateV2':
                continue
            meta = it.get('updateMetadata') or {}
            urn = meta.get('urn', '')
            share_url = (it.get('socialContent') or {}).get('shareUrl', '')
            commentary = it.get('commentary') or {}
            text = (commentary.get('text') or {}).get('text', '') or ''

            # Counts via socialDetail ref
            social_ref = it.get('*socialDetail', '')
            sc = social_counts.get(social_ref, {})
            # Fallback: scan included for SocialActivityCounts whose entityUrn contains this activity
            if not sc and urn:
                for c_key, c_val in social_counts.items():
                    if urn in c_key:
                        sc = c_val; break

            posts.append({
                'post_urn':   urn,
                'post_url':   f'https://www.linkedin.com/feed/update/{urn}/' if urn else '',
                'share_url':  share_url,
                'text':       text,
                'reactions':  sc.get('reactions', 0),
                'comments':   sc.get('comments', 0),
            })
            if len(posts) >= count:
                break
        return posts

    def voyager_search_posts(self, query: str, count: int = 20) -> list:
        """
        Search posts via feed/updatesV2 + local keyword filter.
        Returns list of dicts: post_urn, post_url, author_slug, author_name, text_snippet.
        """
        url = (
            'https://www.linkedin.com/voyager/api/feed/updatesV2'
            f'?q=chronFeed&count={min(count * 3, 100)}&updateType=CHRONOLOGICAL'
        )
        d = self._voyager_fetch(url)
        if not d:
            return []

        included = d.get('included', [])
        profiles = {
            i.get('entityUrn', ''): i
            for i in included
            if i.get('$type') == 'com.linkedin.voyager.identity.shared.MiniProfile'
        }

        posts = []
        for update in included:
            if update.get('$type') != 'com.linkedin.voyager.feed.render.UpdateV2':
                continue
            activity_urn = (
                update.get('updateMetadata', {}).get('urn', '')
                or update.get('entityUrn', '')
            )
            if not activity_urn:
                continue
            commentary = update.get('commentary', {}) or {}
            text = (commentary.get('text', {}) or {}).get('text', '')
            if query and query.lower() not in text.lower():
                continue
            actor_ref = update.get('*actor', '')
            profile   = profiles.get(actor_ref, {})
            slug      = profile.get('publicIdentifier', '')
            author    = f"{profile.get('firstName', '')} {profile.get('lastName', '')}".strip()
            posts.append({
                'post_urn':    activity_urn,
                'post_url':    f'https://www.linkedin.com/feed/update/{activity_urn}/',
                'author_slug': slug,
                'author_name': author,
                'text_snippet': text[:300],
            })
            if len(posts) >= count:
                break
        return posts

    # ------------------------------------------------------------------ #
    #  Helpers
    # ------------------------------------------------------------------ #

    def _random_wait(self, min_s=2, max_s=6):
        """Human-like random delay."""
        time.sleep(random.uniform(min_s, max_s))

    def get_csrf_token(self) -> str:
        """Extract CSRF token (= JSESSIONID without quotes) from page cookies."""
        token = self._page.evaluate('''() => {
            const m = document.cookie.match(/JSESSIONID="?([^";]+)"?/);
            return m ? m[1] : "";
        }''')
        return token

    def get_profile_urn(self, slug: str) -> str | None:
        """
        Get fsd_profile URN for a LinkedIn slug via GraphQL Voyager API.
        Returns urn:li:fsd_profile:ACoAA... or None.
        """
        result = self._page.evaluate('''async (slug) => {
            const m = document.cookie.match(/JSESSIONID="?([^";]+)"?/);
            const token = m ? m[1] : "";
            const url = "https://www.linkedin.com/voyager/api/graphql?includeWebMetadata=true&variables=(memberIdentity:" + slug + ")&queryId=voyagerIdentityDashProfiles.273a499c117721535e6da078bee17e9c";
            try {
                const r = await fetch(url, {
                    headers: {"csrf-token": token, "accept": "application/vnd.linkedin.normalized+json+2.1", "x-restli-protocol-version": "2.0.0"},
                    credentials: "include"
                });
                const d = await r.json();
                const included = d.included || [];
                const profile = included.find(i => i && i.entityUrn && i.entityUrn.includes("fsd_profile"));
                return profile ? profile.entityUrn : null;
            } catch(e) { return null; }
        }''', slug)
        return result
