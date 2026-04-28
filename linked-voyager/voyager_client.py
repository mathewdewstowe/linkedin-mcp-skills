"""
LinkedIn Voyager API Client — Working Endpoints Only

Most LinkedIn UI actions (invite, withdraw, search) migrated to SDUI in 2024-2025
and cannot be driven from Python HTTP. Only the endpoints below still work directly.

Working endpoints (confirmed 2026-04-28):
  GET  /voyager/api/me                          — auth check, current user
  GET  /voyager/api/graphql                     — profile URN lookup (see get_profile_urn)
  GET  /voyager/api/relationships/invitationsSummaryV2 — invite counts
  POST /voyagerMessagingDashMessengerMessages   — send messages (see ruby-outreach-extension)

NOT working via direct HTTP (SDUI-only):
  - Send invite           → use browser.py / ConnectorAgent
  - Withdraw invite       → use browser.py / WithdrawerAgent
  - People search         → use browser.py / PostSearchAgent
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
            elements = (
                data.get('data', {})
                    .get('identityDashProfilesByMemberIdentity', {})
                    .get('elements', [])
            )
            if elements:
                return elements[0].get('entityUrn')
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
        return r.json() if r.status_code == 200 else None

    # ------------------------------------------------------------------ #
    #  Messaging (ruby-outreach-extension pattern)
    # ------------------------------------------------------------------ #

    def send_message(self, recipient_urn: str, message_text: str) -> dict | None:
        """
        POST /voyagerMessagingDashMessengerMessages?action=createMessage
        Send a direct message to an existing connection.

        Args:
            recipient_urn: Full URN like "urn:li:fsd_profile:ACoAAA..."
            message_text:  Plain text message body
        """
        self._throttle()
        url = 'https://www.linkedin.com/voyagerMessagingDashMessengerMessages?action=createMessage'
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
    #  Helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _gen_tracking_id() -> str:
        """Generate a random 16-byte base64-like tracking token."""
        import base64
        import os
        return base64.b64encode(os.urandom(16)).decode('utf-8')
