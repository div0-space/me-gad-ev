"""Verify fresh official MEGA.dev MCP access before issuing a local gate cookie.

OAuth codes, PKCE verifiers and browser bindings live only in this worker's bounded,
five-minute pending state. Tokens are used transiently, revoked best-effort and
never returned, persisted or logged. Run a single worker; a restart cancels logins.
"""

import asyncio
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlencode, urlsplit

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse

COOKIE = "megadev_gate"
STATE_COOKIE = "megadev_gate_oauth"
TTL_SECONDS = 24 * 60 * 60
STATE_TTL_SECONDS = 5 * 60
MIN_SECRET_LENGTH = 16
ISSUER = "https://hq.mega.dev"
RESOURCE = ISSUER + "/mcp"
PROTOCOL_VERSIONS = {"2025-06-18", "2026-07-28"}
MAX_UPSTREAM_BYTES = 1024 * 1024
DEFAULT_NEXT = "/members/journal/"
ALLOWED_NEXT = frozenset({"/challenge/", "/members/journal/",
                          *(f"/challenge/s01e0{n}/entry/" for n in range(1, 4))})
NO_STORE = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}


def _env_flag(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    return default if value is None else value.strip().lower() not in {"0", "false", "no", ""}


def _safe_next(value: str | None) -> str:
    # Exact paths only: no origins, query strings, fragments, encodings or traversal.
    if value and value + "/" in ALLOWED_NEXT:
        return value + "/"
    return value if value in ALLOWED_NEXT else DEFAULT_NEXT


def _opaque(value: object, maximum: int = 8192) -> bool:
    return (isinstance(value, str) and 0 < len(value) <= maximum
            and value.isascii() and all(32 < ord(char) < 127 for char in value))


class GateFailure(Exception):
    """An upstream or protocol failure; never expose its underlying payload."""


@dataclass(frozen=True)
class OAuthState:
    expires: float
    verifier: str
    binding_digest: bytes
    next_path: str


class Gate:
    def __init__(self, *, secret: str | None = None, oauth_client_id: str | None = None,
                 oauth_redirect_uri: str | None = None, ttl: int = TTL_SECONDS,
                 secure_cookie: bool = True, state_ttl: int = STATE_TTL_SECONDS,
                 max_pending: int = 1024, clock: Callable[[], float] = time.time,
                 upstream_transport: httpx.AsyncBaseTransport | None = None):
        self.secret = secret
        self.oauth_client_id = oauth_client_id
        self.oauth_redirect_uri = oauth_redirect_uri
        self.ttl = ttl
        self.secure_cookie = secure_cookie
        self.state_ttl = state_ttl
        self.max_pending = max_pending
        self.clock = clock
        self.upstream_transport = upstream_transport
        self.pending: OrderedDict[str, OAuthState] = OrderedDict()

    @classmethod
    def from_env(cls) -> "Gate":
        return cls(secret=os.environ.get("GATE_SECRET"),
                   oauth_client_id=os.environ.get("GATE_OAUTH_CLIENT_ID"),
                   oauth_redirect_uri=os.environ.get("GATE_OAUTH_REDIRECT_URI"),
                   secure_cookie=_env_flag("GATE_COOKIE_SECURE", True))

    def ready(self) -> bool:
        if (not self.secret or len(self.secret) < MIN_SECRET_LENGTH
                or not _opaque(self.oauth_client_id, 512) or not self.oauth_redirect_uri
                or self.ttl <= 0 or self.state_ttl <= 0 or self.max_pending <= 0):
            return False
        try:
            callback = urlsplit(self.oauth_redirect_uri)
            _ = callback.port  # Reject malformed ports as configuration errors.
            return (callback.path == "/gate/callback" and not callback.query and not callback.fragment
                    and not callback.username and not callback.password and bool(callback.hostname)
                    and (callback.scheme == "https" or (callback.scheme == "http"
                         and callback.hostname in {"127.0.0.1", "localhost", "::1"})))
        except ValueError:
            return False

    def _sign(self, expires: int) -> str:
        # New purpose invalidates all cookies earned through the removed shared-answer gate.
        return hmac.new(self.secret.encode(), f"gate2:{expires}".encode(), hashlib.sha256).hexdigest()

    def issue(self) -> str:
        expires = int(self.clock()) + self.ttl
        return f"{expires}.{self._sign(expires)}"

    def valid(self, token: str | None) -> bool:
        if not token or not self.ready() or len(token) > 80:
            return False
        expires, _, signature = token.partition(".")
        if not expires.isascii() or not expires.isdigit() or len(expires) > 12:
            return False
        if not signature.isascii() or not hmac.compare_digest(signature, self._sign(int(expires))):
            return False
        return int(expires) > self.clock()

    def retire_expired(self) -> None:
        for state, pending in list(self.pending.items()):
            if pending.expires <= self.clock():
                del self.pending[state]

    def begin(self, next_path: str | None) -> tuple[str, str]:
        self.retire_expired()
        if len(self.pending) >= self.max_pending:
            raise GateFailure()
        state, binding, verifier = (secrets.token_urlsafe(32) for _ in range(3))
        self.pending[state] = OAuthState(self.clock() + self.state_ttl, verifier,
                                        hashlib.sha256(binding.encode()).digest(), _safe_next(next_path))
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        query = urlencode({"client_id": self.oauth_client_id, "redirect_uri": self.oauth_redirect_uri,
                           "response_type": "code", "state": state, "code_challenge": challenge,
                           "code_challenge_method": "S256", "resource": RESOURCE})
        return ISSUER + "/authorize?" + query, binding

    def consume(self, state: str | None, binding: str | None) -> OAuthState | None:
        self.retire_expired()
        if not state or not re.fullmatch(r"[A-Za-z0-9_-]{43}", state) or not _opaque(binding, 128):
            return None
        pending = self.pending.get(state)
        if pending is None or not hmac.compare_digest(pending.binding_digest,
                                                      hashlib.sha256(binding.encode()).digest()):
            return None
        # No await between lookup/binding check and consume: concurrent callbacks cannot replay.
        return self.pending.pop(state)

    @staticmethod
    async def _body(response: httpx.Response) -> bytes:
        body = bytearray()
        async for chunk in response.aiter_bytes():
            body.extend(chunk)
            if len(body) > MAX_UPSTREAM_BYTES:
                raise GateFailure()
        return bytes(body)

    async def _exchange(self, client: httpx.AsyncClient, code: str, verifier: str) -> dict:
        async with client.stream("POST", ISSUER + "/token", data={
            "grant_type": "authorization_code", "code": code, "code_verifier": verifier,
            "client_id": self.oauth_client_id, "redirect_uri": self.oauth_redirect_uri,
            "resource": RESOURCE,
        }) as response:
            if response.status_code != 200:
                raise GateFailure()
            payload = json.loads(await self._body(response))
            if not isinstance(payload, dict):
                raise GateFailure()
            return payload

    @staticmethod
    def _rpc_result(payload: object, request_id: str) -> dict | None:
        if not isinstance(payload, dict) or payload.get("id") != request_id:
            return None
        if (payload.get("jsonrpc") != "2.0" or "error" in payload
                or not isinstance(payload.get("result"), dict)):
            raise GateFailure()
        return payload["result"]

    async def _rpc(self, client: httpx.AsyncClient, headers: dict, request_id: str,
                   method: str, params: dict) -> tuple[dict, str | None]:
        async with client.stream("POST", RESOURCE, headers=headers, json={
            "jsonrpc": "2.0", "id": request_id, "method": method, "params": params,
        }) as response:
            if response.status_code != 200:
                raise GateFailure()
            session = response.headers.get("mcp-session-id")
            if session is not None and not _opaque(session, 512):
                raise GateFailure()
            content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            if content_type == "application/json":
                result = self._rpc_result(json.loads(await self._body(response)), request_id)
                if result is not None:
                    return result, session
            elif content_type == "text/event-stream":
                data, total, buffered, skip_lf = [], 0, bytearray(), False
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > MAX_UPSTREAM_BYTES:
                        raise GateFailure()
                    buffered.extend(chunk)
                    if skip_lf:
                        if buffered.startswith(b"\n"):
                            del buffered[:1]
                        skip_lf = False
                    while True:
                        ending = re.search(br"\r\n|\r|\n", buffered)
                        if ending is None:
                            break
                        # Process lone CR immediately, but do not count a split CRLF twice.
                        skip_lf = ending.group() == b"\r" and ending.end() == len(buffered)
                        line = bytes(buffered[:ending.start()]).decode("utf-8").removeprefix("\ufeff")
                        del buffered[:ending.end()]
                        if line.startswith("data:"):
                            data.append(line[5:].removeprefix(" "))
                        elif not line and data:
                            result = self._rpc_result(json.loads("\n".join(data)), request_id)
                            data.clear()
                            if result is not None:
                                return result, session
            raise GateFailure()

    async def _verify_mcp(self, client: httpx.AsyncClient, token: str) -> None:
        headers = {"Authorization": "Bearer " + token, "Accept": "application/json, text/event-stream"}
        initialized, session = await self._rpc(client, headers, "gate-initialize", "initialize", {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "me-gad-ev-enrollment-gate", "version": "1.0"},
        })
        protocol = initialized.get("protocolVersion")
        if (protocol not in PROTOCOL_VERSIONS or not isinstance(initialized.get("capabilities"), dict)
                or not isinstance(initialized.get("serverInfo"), dict)):
            raise GateFailure()
        headers["MCP-Protocol-Version"] = protocol
        if session:
            headers["Mcp-Session-Id"] = session
        async with client.stream("POST", RESOURCE, headers=headers,
                                 json={"jsonrpc": "2.0", "method": "notifications/initialized"}) as response:
            if response.status_code not in {200, 202, 204}:
                raise GateFailure()
        result, _ = await self._rpc(client, headers, "gate-challenges", "tools/call",
                                    {"name": "list-challenges", "arguments": {}})
        if result.get("isError", False) is not False:
            raise GateFailure()
        candidates = [result.get("structuredContent")]
        content = result.get("content", [])
        if not isinstance(content, list):
            raise GateFailure()
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
                try:
                    candidates.append(json.loads(item["text"]))
                except ValueError:
                    continue
        if not any(isinstance(item, dict) and isinstance(item.get("challenges"), list)
                   and all(isinstance(row, dict) for row in item["challenges"]) for item in candidates):
            raise GateFailure()

    async def _revoke(self, client: httpx.AsyncClient, tokens: dict) -> None:
        for field, hint in (("access_token", "access_token"), ("refresh_token", "refresh_token")):
            token = tokens.get(field)
            if not _opaque(token):
                continue
            try:
                async with asyncio.timeout(5):
                    async with client.stream("POST", ISSUER + "/revoke", data={
                        "token": token, "token_type_hint": hint, "client_id": self.oauth_client_id,
                    }):
                        pass
            except (httpx.HTTPError, TimeoutError):
                # Best effort only. No token is retained even if the issuer is unavailable.
                pass

    async def verify_code(self, code: str, verifier: str) -> bool:
        tokens = {}
        async with httpx.AsyncClient(transport=self.upstream_transport, follow_redirects=False,
                                     trust_env=False, timeout=10,
                                     headers={"User-Agent": "me-gad-ev-gate/1.0"}) as client:
            try:
                async with asyncio.timeout(30):
                    tokens = await self._exchange(client, code, verifier)
                    access = tokens.get("access_token")
                    token_type = tokens.get("token_type")
                    if not _opaque(access) or not isinstance(token_type, str) or token_type.lower() != "bearer":
                        raise GateFailure()
                    await self._verify_mcp(client, access)
                    return True
            except (GateFailure, httpx.HTTPError, ValueError, TypeError, UnicodeError,
                    RecursionError, TimeoutError):
                return False
            finally:
                await self._revoke(client, tokens)
                tokens.clear()


def _reply(status: int, error: str, instruction: str):
    return JSONResponse({"error": error, "instruction": instruction}, status_code=status, headers=NO_STORE)


def _clear_state(response, gate: Gate):
    response.delete_cookie(STATE_COOKIE, path="/gate/callback", secure=gate.secure_cookie,
                           httponly=True, samesite="lax")
    return response


def create_gate_router(gate: Gate) -> APIRouter:
    router = APIRouter(prefix="/gate")

    @router.get("/handshake")
    def handshake(request: Request):
        configured = gate.ready()
        return JSONResponse({
            "available": configured, "configured": configured,
            "login_url": "/gate/login?" + urlencode({"next": _safe_next(request.query_params.get("next"))}),
            "instruction": (
                "Help the visitor open login_url in their browser. This site uses its own fresh OAuth consent "
                "with the official MEGA.dev course service; a new login and approval may be required. "
                "After consent, the server calls the real official MCP list-challenges tool to verify access, "
                "then attempts token revocation (best-effort), discards the tokens and sets a 24-hour browser cookie. "
                "Never paste harness tokens, authorization codes or PKCE verifiers here. "
                "An agent's statement alone cannot open this gate; this is not agent-exclusive access."
            ),
        }, headers=NO_STORE)

    @router.get("/login")
    async def login(request: Request):
        if not gate.ready():
            return _reply(503, "gate-unconfigured", "Official course login is not configured. Tell the site owner.")
        try:
            url, binding = gate.begin(request.query_params.get("next"))
        except GateFailure:
            return _reply(429, "gate-busy", "Too many pending logins. Wait five minutes and try again.")
        response = RedirectResponse(url, status_code=302, headers=NO_STORE)
        response.set_cookie(STATE_COOKIE, binding, max_age=gate.state_ttl, httponly=True,
                            secure=gate.secure_cookie, samesite="lax", path="/gate/callback")
        return response

    @router.get("/callback")
    async def callback(request: Request):
        if not gate.ready():
            return _clear_state(_reply(503, "gate-unconfigured", "Official course login is not configured."), gate)
        query = request.query_params
        if any(len(query.getlist(key)) > 1 for key in ("code", "state", "iss", "error")):
            return _clear_state(_reply(400, "gate-login-invalid", "Invalid login response. Start again at /gate/."), gate)
        pending = gate.consume(query.get("state"), request.cookies.get(STATE_COOKIE))
        if pending is None:
            return _clear_state(_reply(400, "gate-login-invalid", "Login expired or did not match this browser. Start again at /gate/."), gate)
        code = query.get("code")
        if ("error" in query or ("iss" in query and query["iss"] != ISSUER)
                or not _opaque(code, 4096)):
            return _clear_state(_reply(400, "gate-login-denied", "Official login was not completed. Start again at /gate/."), gate)
        if not await gate.verify_code(code, pending.verifier):
            return _clear_state(_reply(403, "gate-verification-failed", "Official course MCP access could not be verified. No access was granted; start again at /gate/."), gate)
        response = RedirectResponse(pending.next_path, status_code=303, headers=NO_STORE)
        response.set_cookie(COOKIE, gate.issue(), max_age=gate.ttl, httponly=True,
                            secure=gate.secure_cookie, samesite="lax", path="/")
        return _clear_state(response, gate)

    @router.get("/check")
    def check(request: Request):
        if not gate.ready():
            return _reply(503, "gate-unconfigured", "Official course login is not configured right now.")
        if not gate.valid(request.cookies.get(COOKIE)):
            return _reply(401, "gate-closed", "Verify official course MCP access through /gate/handshake or /gate/.")
        return JSONResponse({"ok": True}, headers=NO_STORE)

    return router
