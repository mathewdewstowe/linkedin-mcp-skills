"""
LinkedIn Voyager API Client — Direct HTTP Endpoints

Working endpoints (no browser/Playwright needed):
  GET  /voyager/api/me                                    — auth check
  GET  /voyager/api/graphql                               — profile URN lookup
  GET  /voyager/api/relationships/invitationsSummaryV2    — invite counts
  POST /voyager/api/voyagerMessagingDashMessengerMessages — send message
  GET  /voyager/api/search/blended (PEOPLE filter)        — people search
  GET  /voyager/api/search/blended (CONTENT filter)       — post search
  GET  /voyager/api/reactions/v2                          — post likers
  GET  /voyager/api/feed/comments                         — post comments

NOT working via direct HTTP (SDUI-only):
  - Send invite           → use browser.py / ConnectorAgent
  - Withdraw invite       → use browser.py / WithdrawerAgent
  - Invitation list       → use browser.py scraping
"""

import requests
import time
import random
import json

from config import THROTTLE_READ_MIN, THROTTLE_READ_MAX

VOYAGER_BASE = 'https://www.linkedin.com/voyager/api'
GRAPHQL_QUERY_ID = 'voyagerIdentityDashProfiles.273a499c117721535e6da078bee17e9c'


class VoyagerClient:
    def __init__(self, li_at=None, jsessionid=None):
        """
        Args:
            li_at: LinkedIn auth token (from browser cookie)
            jsessionid: Session ID — also used as CSRF token
        """
        self.li_at = li_at
        self.jsessionid = jsessionid
        self.csrf_token = jsessionid.strip('"') if jsessionid else None
        self.session = requests.Session()
        self._setup_session()

    def _setup_session(self):
        self.session.headers.update({
            'User-Agent': (
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
            ),
            'Accept': 'application/vnd.linkedin.normalized+json+2.1',
            'Accept-Language': 'en-US,en;q=0.9',
            'X-Restli-Protocol-Version': '2.0.0',
            'X-Li-Lang': 'en_US',
            'X-Li-Track': json.dumps({
                'clientVersion': '1.13.30000',
                'mpVersion': '1.13.30000',
                'osName': 'web',
                'timezoneOffset': 0,
                'timezone': 'Europe/London',
                'deviceFormFactor': 'DESKTOP',
                'mpName': 'voyager-web'
            }),
        })
        if self.li_at:
            self.session.cookies.set('li_at', self.li_at)
        if self.jsessionid:
            self.session.cookies.set('JSESSIONID', self.jsessionid)

    def _throttle(self):
        time.sleep(random.uniform(THROTTLE_READ_MIN, THROTTLE_READ_MAX))

    def _csrf_headers(self, extra=None):
        headers = {'csrf-token': self.csrf_token} if self.csrf_token else {}
        if extra:
            headers.update(extra)
        return headers

    def _check_challenge(self, response) -> bool:
        if response.status_code == 403:
            if '/checkpoint/' in response.url or '/uas/' in response.url:
                return True
        return False

    # ------------------------------------------------------------------ #
    #  Auth check
    # ------------------------------------------------------------------ #

    def get_me(self) -> dict | None:
        """GET /me — Check auth and return current user's profile."""
        self._throttle()
        r = self.session.get(f'{VOYAGER_BASE}/me')
        if self._check_challenge(r):
            raise RuntimeError('CHALLENGE: LinkedIn requires manual auth. Stop all agents.')
        return r.json() if r.status_code == 200 else None

    # ------------------------------------------------------------------ #
    #  Profile URN lookup (used by messaging)
    # ------------------------------------------------------------------ #

    def get_profile_urn(self, slug: str) -> str | None:
        """
        Resolve a LinkedIn profile slug to a URN string like
        "urn:li:fsd_profile:ACoAAA...".

        Uses GraphQL endpoint confirmed working 2026-04-28.
        """
        self._throttle()
        url = f'{VOYAGER_BASE}/graphql'
        params = {
            'includeWebMetadata': 'true',
            'variables': f'(memberIdentity:{slug})',
            'queryId': GRAPHQL_QUERY_ID,
        }
        r = self.session.get(url, params=params)
        if self._check_challenge(r):
            raise RuntimeError('CHALLENGE: LinkedIn requires manual auth. Stop all agents.')
        if r.status_code != 200:
            return None

        try:
            data = r.json()
            # URN lives in included[0], not in data.data.elements
            included = data.get('included', [])
            if included:
                return included[0].get('entityUrn')
        except (KeyError, ValueError, IndexError):
            pass
        return None

    # ------------------------------------------------------------------ #
    #  Invite counts
    # ------------------------------------------------------------------ #

    def get_invitation_counts(self) -> dict | None:
        """
        GET /relationships/invitationsSummaryV2
        Returns sent + pending counts.
        """
        self._throttle()
        url = f'{VOYAGER_BASE}/relationships/invitationsSummaryV2'
        params = {'types': 'List(SENT_INVITATION_COUNT,PENDING_INVITATION_COUNT)'}
        r = self.session.get(url, params=params)
        if self._check_challenge(r):
            raise RuntimeError('CHALLENGE: LinkedIn requires manual auth. Stop all agents.')
        if r.status_code != 200:
            return None
        try:
            # Counts live in data.data, not data.elements
            return r.json().get('data', {})
        except (ValueError, KeyError):
            return None

    # ------------------------------------------------------------------ #
    #  Messaging (ruby-outreach-extension pattern)
    # ------------------------------------------------------------------ #

    def send_message(self, recipient_urn: str, message_text: str) -> dict | None:
        """
        POST /voyager/api/voyagerMessagingDashMessengerMessages?action=createMessage
        Send a direct message to an existing connection.

        Args:
            recipient_urn: Full URN like "urn:li:fsd_profile:ACoAAA..."
            message_text:  Plain text message body
        """
        self._throttle()
        url = f'{VOYAGER_BASE}/voyagerMessagingDashMessengerMessages?action=createMessage'
        payload = {
            'message': {
                'body': {
                    'text': message_text
                },
                'renderContentUnions': []
            },
            'mailboxUrn': recipient_urn,
            'trackingId': self._gen_tracking_id(),
            'dedupeByClientGeneratedToken': False,
            'hostRecipientUrns': [recipient_urn],
        }
        headers = self._csrf_headers({'Content-Type': 'application/json'})
        r = self.session.post(url, json=payload, headers=headers)
        if self._check_challenge(r):
            raise RuntimeError('CHALLENGE: LinkedIn requires manual auth. Stop all agents.')
        return r.json() if r.status_code in (200, 201) else None

    # ------------------------------------------------------------------ #
    #  People search
    # ------------------------------------------------------------------ #

    def search_people(self, query: str, count: int = 20, start: int = 0,
                      first_degree_only: bool = False) -> list:
        """
        GET /search/blended — Search LinkedIn people by keyword.
        Returns list of dicts: slug, name, headline, urn, profile_url.
        """
        self._throttle()
        filters = 'List((key:resultType,value:List(PEOPLE))'
        if first_degree_only:
            filters += ',(key:network,value:List(F))'
        filters += ')'
        params = {
            'q': 'all',
            'keywords': query,
            'filters': filters,
            'count': count,
            'start': start,
            'origin': 'GLOBAL_SEARCH_HEADER',
        }
        r = self.session.get(f'{VOYAGER_BASE}/search/blended', params=params)
        if self._check_challenge(r):
            raise RuntimeError('CHALLENGE: LinkedIn requires manual auth. Stop all agents.')
        if r.status_code != 200:
            return []

        people = []
        try:
            data = r.json()
            for item in data.get('included', []):
                if item.get('$type') != 'com.linkedin.voyager.identity.shared.MiniProfile':
                    continue
                slug = item.get('publicIdentifier', '')
                people.append({
                    'slug': slug,
                    'name': f"{item.get('firstName', '')} {item.get('lastName', '')}".strip(),
                    'headline': item.get('headline', ''),
                    'urn': item.get('entityUrn', ''),
                    'profile_url': f'https://www.linkedin.com/in/{slug}/' if slug else '',
                })
        except (ValueError, KeyError):
            pass
        return people

    # ------------------------------------------------------------------ #
    #  Post search
    # ------------------------------------------------------------------ #

    def search_posts(self, query: str, count: int = 20, start: int = 0) -> list:
        """
        GET /search/blended — Search LinkedIn posts by keyword.
        Returns list of dicts: post_urn, post_url, author_slug, author_name, text_snippet.
        """
        self._throttle()
        params = {
            'q': 'all',
            'keywords': query,
            'filters': 'List((key:resultType,value:List(CONTENT)))',
            'count': count,
            'start': start,
            'origin': 'GLOBAL_SEARCH_HEADER',
        }
        r = self.session.get(f'{VOYAGER_BASE}/search/blended', params=params)
        if self._check_challenge(r):
            raise RuntimeError('CHALLENGE: LinkedIn requires manual auth. Stop all agents.')
        if r.status_code != 200:
            return []

        posts = []
        try:
            data = r.json()
            profiles = {
                item.get('entityUrn', ''): item
                for item in data.get('included', [])
                if item.get('$type') == 'com.linkedin.voyager.identity.shared.MiniProfile'
            }
            for cluster in data.get('elements', []):
                for hit in cluster.get('elements', []):
                    hit_info = hit.get('hitInfo', {})
                    content = (
                        hit_info.get('com.linkedin.voyager.search.SearchUpdate')
                        or hit_info.get('com.linkedin.voyager.search.SearchUpdateV2')
                    )
                    if not content:
                        continue
                    update_urn = content.get('updateUrn', '')
                    actor_urn = content.get('actorUrn', '')
                    summary = content.get('summary', {})
                    text = summary.get('text', '') if isinstance(summary, dict) else ''
                    profile = profiles.get(actor_urn, {})
                    slug = profile.get('publicIdentifier', '')
                    posts.append({
                        'post_urn': update_urn,
                        'post_url': f'https://www.linkedin.com/feed/update/{update_urn}/' if update_urn else '',
                        'author_slug': slug,
                        'author_name': f"{profile.get('firstName', '')} {profile.get('lastName', '')}".strip(),
                        'text_snippet': text[:300] if text else '',
                    })
        except (ValueError, KeyError):
            pass
        return posts

    # ------------------------------------------------------------------ #
    #  Post likers
    # ------------------------------------------------------------------ #

    def get_post_likers(self, post_urn: str, count: int = 100, start: int = 0) -> list:
        """
        GET /reactions/v2 — Who liked a post.
        post_urn: e.g. 'urn:li:activity:7321498765432109876'
        Returns list of dicts: slug, name, headline, urn, profile_url, reaction_type.
        """
        self._throttle()
        params = {
            'q': 'liked',
            'entityUrn': post_urn,
            'count': count,
            'start': start,
        }
        r = self.session.get(f'{VOYAGER_BASE}/reactions/v2', params=params)
        if self._check_challenge(r):
            raise RuntimeError('CHALLENGE: LinkedIn requires manual auth. Stop all agents.')
        if r.status_code != 200:
            return []

        likers = []
        try:
            data = r.json()
            profiles = {
                item.get('entityUrn', ''): item
                for item in data.get('included', [])
                if item.get('$type') == 'com.linkedin.voyager.identity.shared.MiniProfile'
            }
            for element in data.get('elements', []):
                reactor_urn = element.get('reactorUrn', '')
                profile = profiles.get(reactor_urn, {})
                if not profile:
                    # fuzzy match — reactor_urn sometimes uses a different URN scheme
                    for urn, p in profiles.items():
                        if reactor_urn and reactor_urn in urn:
                            profile = p
                            break
                slug = profile.get('publicIdentifier', '')
                likers.append({
                    'slug': slug,
                    'name': f"{profile.get('firstName', '')} {profile.get('lastName', '')}".strip(),
                    'headline': profile.get('headline', ''),
                    'urn': reactor_urn,
                    'profile_url': f'https://www.linkedin.com/in/{slug}/' if slug else '',
                    'reaction_type': element.get('reactionType', 'LIKE'),
                })
        except (ValueError, KeyError):
            pass
        return likers

    # ------------------------------------------------------------------ #
    #  Post comments
    # ------------------------------------------------------------------ #

    def get_post_comments(self, post_urn: str, count: int = 100, start: int = 0) -> list:
        """
        GET /feed/comments — Comments on a post with author info.
        post_urn: e.g. 'urn:li:activity:7321498765432109876'
        Returns list of dicts: author_slug, author_name, author_headline, comment_text, timestamp, profile_url.
        """
        self._throttle()
        params = {
            'updateKey': post_urn,
            'count': count,
            'start': start,
        }
        r = self.session.get(f'{VOYAGER_BASE}/feed/comments', params=params)
        if self._check_challenge(r):
            raise RuntimeError('CHALLENGE: LinkedIn requires manual auth. Stop all agents.')
        if r.status_code != 200:
            return []

        comments = []
        try:
            data = r.json()
            profiles = {
                item.get('entityUrn', ''): item
                for item in data.get('included', [])
                if item.get('$type') == 'com.linkedin.voyager.identity.shared.MiniProfile'
            }
            for element in data.get('elements', []):
                comment_v2 = element.get('commentV2', {})
                text = comment_v2.get('text', '') if isinstance(comment_v2, dict) else ''
                commenter = element.get('commenter', {})
                member_actor = (
                    commenter.get('com.linkedin.voyager.feed.MemberActor')
                    or commenter.get('com.linkedin.voyager.feed.shared.MemberActor')
                )
                slug = name = headline = ''
                if member_actor:
                    profile = profiles.get(member_actor.get('miniProfile', ''), {})
                    slug = profile.get('publicIdentifier', '')
                    name = f"{profile.get('firstName', '')} {profile.get('lastName', '')}".strip()
                    headline = profile.get('headline', '')
                comments.append({
                    'author_slug': slug,
                    'author_name': name,
                    'author_headline': headline,
                    'comment_text': text,
                    'timestamp': element.get('createdTime', 0),
                    'profile_url': f'https://www.linkedin.com/in/{slug}/' if slug else '',
                })
        except (ValueError, KeyError):
            pass
        return comments

    # ------------------------------------------------------------------ #
    #  Helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _gen_tracking_id() -> str:
        """Generate a random 16-byte base64-like tracking token."""
        import base64
        import os
        return base64.b64encode(os.urandom(16)).decode('utf-8')
