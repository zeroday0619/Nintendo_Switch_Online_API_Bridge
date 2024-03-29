import base64
import hashlib
import os
import re

import keyring
import requests
from bs4 import BeautifulSoup

from nso_bridge.models import ServiceToken, UserInfo


class NintendoSwitchAccount:
    """Nintendo Switch Online authorization"""

    def __init__(self, version: str = "unknown", nso_app_version: str = "2.1.1"):
        """
        Args:
            version (str, optional): Client version. Defaults to "unknown".
            nso_app_version (str, optional): Nintendo Switch Online APP (AOS, IOS) version. Defaults to "2.1.1".
        """
        self.client_id = "71b963c1b7b6d119"
        self.urlScheme = "npf71b963c1b7b6d119"
        self.version = version
        self.nso_app_version = nso_app_version
        self.session = requests.Session()

        self.apple_app_store_url = (
            "https://apps.apple.com/us/app/nintendo-switch-online/id1234806557"
        )
        self.nso_api_token_url = "https://accounts.nintendo.com/connect/1.0.0/api/token"
        self.nso_authorize_url = "https://accounts.nintendo.com/connect/1.0.0/authorize"
        self.nso_session_token_url = (
            "https://accounts.nintendo.com/connect/1.0.0/api/session_token"
        )
        self.nso_user_me_url = "https://api.accounts.nintendo.com/2.0.0/users/me"

        self.state = base64.urlsafe_b64encode(os.urandom(36))
        self.verify = base64.urlsafe_b64encode(os.urandom(32))
        self.authHash = hashlib.sha256()
        self.authHash.update(self.verify.replace(b"=", b""))
        self.authCodeChallenge = base64.urlsafe_b64encode(self.authHash.digest())

    def get_nso_app_version(self):
        """
        Get Nintendo Switch Online APP version.

        Returns:
            str: Nintendo Switch Online APP version.
        """
        try:
            page = requests.get(
                self.apple_app_store_url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Linux; Android 12; Pixel 6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.61 Mobile Safari/537.36"
                },
            )
            soup = BeautifulSoup(page.text, "html.parser")
            elt = soup.find("p", {"class": "whats-new__latest__version"})
            ver = elt.get_text().replace("Version ", "").strip()
            return ver
        except Exception:
            return "2.1.1"

    def payload_auth(self):
        """Get payload for Nintendo Switch Online authorization

        Returns:
            dict: Payload for Nintendo Switch Online authorization
        """
        body = {
            "state": self.state,
            "redirect_uri": "npf%s://auth" % self.client_id,
            "client_id": self.client_id,
            "scope": "openid user user.birthday user.mii user.screenName",
            "response_type": "session_token_code",
            "session_token_code_challenge": self.authCodeChallenge.replace(b"=", b""),
            "session_token_code_challenge_method": "S256",
            "theme": "login_form",
        }
        return body

    def session_token_payload(self, session_token_code, auth_code_verifier):
        """Get session_token_code payload for Nintendo Switch Online authorization

        Returns:
            dict: Payload for Nintendo Switch Online authorization
        """
        body = {
            "client_id": self.client_id,
            "session_token_code": session_token_code,
            "session_token_code_verifier": auth_code_verifier.replace(b"=", b""),
        }
        return body

    def service_token_payload(self, session_token):
        """Get service_token payload for Nintendo Switch Online authorization

        Args:
            session_token (str): Session token

        Returns:
            dict: Payload for Nintendo Switch Online authorization
        """
        body = {
            "client_id": self.client_id,
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer-session-token",
            "session_token": session_token,
        }
        return body

    def nso_login(self, r_input):
        """Login to Nintendo Switch Online

        Args:
            r_input (str): Input from callback URL

        Returns:
            str: session token

        Raises:
            Exception: HTTP status code
        """
        resp = self.session.get(
            url=self.nso_authorize_url,
            headers={
                "Accept-Encoding": "gzip",
                "User-Agent": "OnlineLounge/%s NASDKAPI Android" % self.version,
            },
            params=self.payload_auth(),
        )
        if resp.status_code != 200:
            raise Exception("Error: %s" % resp.status_code)

        print("URL: " + str(resp.history[0].url))

        tokenPattern = re.compile(
            r"(eyJhbGciOiJIUzI1NiJ9\.[a-zA-Z0-9_-]*\.[a-zA-Z0-9_-]*)"
        )
        code = tokenPattern.findall(r_input())
        return self.get_session_token(code[0], self.verify.replace(b"=", b""))

    def m_input(self):
        return input("Enter the callback url: \n")

    def get_session_token(self, session_token_code, auth_code_verifier) -> str:
        """Get session token from Nintendo Switch Online

        Args:
            session_token_code (str): Session token code
            auth_code_verifier (str): Auth code verifier

        Returns:
            str: session token
        """
        resp = self.session.post(
            self.nso_session_token_url,
            headers={
                "Accept-Language": "en-US",
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
                "Content-Length": "540",
                "Host": "accounts.nintendo.com",
                "Connection": "Keep-Alive",
            },
            data=self.session_token_payload(session_token_code, auth_code_verifier),
        )
        if resp.status_code != 200:
            raise Exception("Error: %s" % resp.status_code)
        sess = resp.json()["session_token"]
        keyring.set_password("nso-bridge", "session_token", sess)
        return sess

    def get_service_token(self, session_token: str) -> ServiceToken:
        """Get a new NSO API service token .

        Args:
            session_token (str): Session token

        Raises:
            Exception: HTTP status code

        Returns:
            ServiceToken: NSO API service token
        """
        headers = {
            "User-Agent": "Coral/2.0.0 (com.nintendo.znca; build:1489; iOS 15.3.1) Alamofire/5.4.4",
            "Accept": "application/json",
            "Accept-Language": "en-US",
            "Accept-Encoding": "gzip, deflate",
        }
        resp = self.session.post(
            self.nso_api_token_url,
            headers=headers,
            data=self.service_token_payload(session_token),
        )
        if resp.status_code != 200:
            raise Exception("Error: %s" % resp.status_code)
        return ServiceToken(**resp.json())

    def get_user_info(self, service_token: str, user_lang: str = "en-US") -> UserInfo:
        """Get user info from Nintendo Switch Online

        Args:
            service_token (str): NSO API service token
            user_lang (str, optional): User language. Defaults to "en-US".

        Returns:
            UserInfo: User info

        Raises:
            Exception: HTTP status code
        """
        headers = {
            "User-Agent": "Coral/2.0.0 (com.nintendo.znca; build:1489; iOS 15.3.1) Alamofire/5.4.4",
            "Accept": "application/json",
            "Accept-Language": user_lang,
            "Authorization": "Bearer %s" % service_token,
            "Host": "api.accounts.nintendo.com",
            "Connection": "Keep-Alive",
            "Accept-Encoding": "gzip",
        }
        response = requests.get(url=self.nso_user_me_url, headers=headers)
        if response.status_code != 200:
            raise Exception("Error: %s" % response.status_code)
        json_data = response.json()
        return UserInfo(**json_data)
