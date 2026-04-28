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
