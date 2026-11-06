"""Minimal Enable Banking API client (account information only)."""

import time
from collections.abc import Iterator
from datetime import date, datetime

import httpx
import jwt


class EnableBankingError(Exception):
    def __init__(self, status: int, body: str):
        super().__init__(f"Enable Banking API {status}: {body[:500]}" if status else body)
        self.status = status
        self.body = body


class EnableBankingClient:
    def __init__(self, app_id: str, private_key: str, base_url: str, http: httpx.Client | None = None):
        self.app_id = app_id
        self.private_key = private_key
        self.http = http or httpx.Client(base_url=base_url, timeout=60)
        if http is not None and not http.base_url:
            self.http.base_url = base_url

    def _token(self) -> str:
        now = int(time.time())
        return jwt.encode(
            {"iss": "enablebanking.com", "aud": "api.enablebanking.com", "iat": now, "exp": now + 3600},
            self.private_key,
            algorithm="RS256",
            headers={"kid": self.app_id},
        )

    def _request(self, method: str, path: str, **kwargs) -> dict:
        try:
            token = self._token()
        except (ValueError, TypeError, jwt.PyJWTError) as e:
            raise EnableBankingError(0, f"Kunde inte signera med nyckeln, är det rätt .pem-fil? ({e})") from e
        try:
            r = self.http.request(method, path, headers={"Authorization": f"Bearer {token}"}, **kwargs)
        except httpx.HTTPError as e:
            raise EnableBankingError(0, f"Kunde inte nå {self.http.base_url}: {type(e).__name__}: {e}") from e
        if r.status_code >= 400:
            raise EnableBankingError(r.status_code, r.text)
        return r.json()

    def aspsps(self, country: str) -> list[dict]:
        return self._request("GET", "/aspsps", params={"country": country}).get("aspsps", [])

    def start_auth(self, aspsp_name: str, country: str, valid_until: datetime, state: str, redirect_url: str) -> dict:
        return self._request(
            "POST",
            "/auth",
            json={
                "access": {"valid_until": valid_until.isoformat()},
                "aspsp": {"name": aspsp_name, "country": country},
                "state": state,
                "redirect_url": redirect_url,
                "psu_type": "personal",
            },
        )

    def create_session(self, code: str) -> dict:
        return self._request("POST", "/sessions", json={"code": code})

    def get_session(self, session_id: str) -> dict:
        return self._request("GET", f"/sessions/{session_id}")

    def account_details(self, account_uid: str) -> dict:
        return self._request("GET", f"/accounts/{account_uid}/details")

    def transactions(self, account_uid: str, date_from: date | None = None) -> Iterator[dict]:
        """All transactions from date_from (or as far back as the bank allows), following pagination."""
        params: dict = {"date_from": date_from.isoformat()} if date_from else {"strategy": "longest"}
        while True:
            page = self._request("GET", f"/accounts/{account_uid}/transactions", params=params)
            yield from page.get("transactions") or []
            key = page.get("continuation_key")
            if not key:
                return
            params = {"continuation_key": key}
