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
        self._page = pages[0] if pages else self._context.new_page()
        return self

    def __exit__(self, *args):
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
