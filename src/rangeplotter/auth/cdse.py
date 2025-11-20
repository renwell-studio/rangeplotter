"""Copernicus Data Space Ecosystem (CDSE) authentication helper.

Implements token acquisition using Resource Owner Password Credentials grant
and refresh via refresh_token grant for the public client `cdse-public`.

DO NOT store real usernames or passwords in committed configuration. Prefer
storing only a refresh token (longer lived) once initially obtained.
"""
from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Optional
import sys
import requests
from pathlib import Path
import re


@dataclass
class TokenInfo:
    access_token: str
    refresh_token: Optional[str]
    expires_at: float


class CdseAuth:
    def __init__(
        self,
        token_url: str,
        client_id: str = "cdse-public",
        username: Optional[str] = None,
        password: Optional[str] = None,
        refresh_token: Optional[str] = None,
        early_refresh_seconds: int = 60,
        verbose: int = 0,
    ):
        self.token_url = token_url.rstrip("/")
        self.client_id = client_id or "cdse-public"
        self.username = username
        self.password = password
        self.refresh_token = refresh_token
        self.early_refresh_seconds = early_refresh_seconds
        self.verbose = verbose
        self._token: Optional[TokenInfo] = None

    def _log(self, msg: str, is_error: bool = False, level: int = 1) -> None:
        """
        Log message if verbosity allows.
        
        Args:
            msg: Message to log
            is_error: If True, always log (unless suppressed by very strict settings, but here we treat as critical)
            level: Verbosity level required to show this message (default 1 = Info)
        """
        if is_error:
            sys.stderr.write(f"[CDSE AUTH ERROR] {msg}\n")
            sys.stderr.flush()
        elif self.verbose >= level:
            sys.stderr.write(f"[CDSE AUTH] {msg}\n")
            sys.stderr.flush()

    def _update_env_file(self, new_refresh_token: str) -> None:
        """Update the .env file with the new refresh token."""
        try:
            env_path = Path(".env")
            if not env_path.exists():
                return
            
            content = env_path.read_text(encoding="utf-8")
            # Regex to replace COPERNICUS_REFRESH_TOKEN=...
            pattern = r"^(COPERNICUS_REFRESH_TOKEN\s*=\s*)(.*)$"
            if re.search(pattern, content, re.MULTILINE):
                new_content = re.sub(pattern, f"\\1{new_refresh_token}", content, flags=re.MULTILINE)
                env_path.write_text(new_content, encoding="utf-8")
                self._log("Updated .env with new refresh token.")
            else:
                with open(env_path, "a", encoding="utf-8") as f:
                    f.write(f"\nCOPERNICUS_REFRESH_TOKEN={new_refresh_token}\n")
                self._log("Appended new refresh token to .env.")
        except Exception as e:
            self._log(f"Failed to update .env: {e}", is_error=True)

    def _password_grant(self) -> Optional[TokenInfo]:
        if not (self.username and self.password):
            self._log("Password grant requested but username/password missing.", is_error=True)
            return None
        data = {
            "grant_type": "password",
            "client_id": self.client_id,
            "username": self.username,
            "password": self.password,
        }
        try:
            r = requests.post(self.token_url, data=data, timeout=30)
            status = r.status_code
            if status != 200:
                self._log(f"Password grant HTTP {status}, content-type={r.headers.get('Content-Type')}", is_error=True)
            r.raise_for_status()
            try:
                j = r.json()
            except Exception as je:
                self._log(f"Password grant JSON parse failed: {je}; body prefix={r.text[:200]!r}", is_error=True)
                return None
            access = j.get("access_token")
            refresh = j.get("refresh_token")
            exp = j.get("expires_in", 0)
            if not access:
                self._log("No access_token returned from password grant response.", is_error=True)
                return None
            ti = TokenInfo(access_token=access, refresh_token=refresh, expires_at=time.time() + exp)
            self._log("CDSE password grant successful.")
            # Cache refresh token if newly provided
            if refresh:
                self.refresh_token = refresh
                self._update_env_file(refresh)
            return ti
        except Exception as e:
            self._log(f"Password grant failed: {e}", is_error=True)
            return None

    def _refresh_grant(self) -> Optional[TokenInfo]:
        if not self.refresh_token:
            return None
        data = {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "refresh_token": self.refresh_token,
        }
        try:
            r = requests.post(self.token_url, data=data, timeout=30)
            status = r.status_code
            if status != 200:
                self._log(f"Refresh grant HTTP {status}, content-type={r.headers.get('Content-Type')}", is_error=True)
            r.raise_for_status()
            try:
                j = r.json()
            except Exception as je:
                self._log(f"Refresh grant JSON parse failed: {je}; body prefix={r.text[:200]!r}", is_error=True)
                return None
            access = j.get("access_token")
            refresh = j.get("refresh_token") or self.refresh_token
            exp = j.get("expires_in", 0)
            if not access:
                self._log("No access_token returned from refresh grant response.", is_error=True)
                return None
            ti = TokenInfo(access_token=access, refresh_token=refresh, expires_at=time.time() + exp)
            self._log("CDSE refresh grant successful.")
            self.refresh_token = refresh
            if j.get("refresh_token"):
                self._update_env_file(refresh)
            return ti
        except Exception as e:
            self._log(f"Refresh grant failed: {e}", is_error=True)
            return None

    def ensure_access_token(self) -> Optional[str]:
        # If current token valid for > early_refresh_seconds keep it
        if self._token and time.time() < (self._token.expires_at - self.early_refresh_seconds):
            return self._token.access_token
        # Try refresh grant first if we have refresh_token
        if self.refresh_token:
            ti = self._refresh_grant()
            if ti:
                self._token = ti
                return ti.access_token
        # Fallback to password grant if possible
        ti = self._password_grant()
        if ti:
            self._token = ti
            return ti.access_token
        return None

__all__ = ["CdseAuth", "TokenInfo"]