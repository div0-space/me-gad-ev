"""Proof-of-MCP gate: a visitor's agent answers the question of the day, known only to
someone wired into the official course MCP. No accounts, no passwords, no upstream calls.

The server never holds course credentials. The operator rotates the expected answer
(GATE_EXPECTED or GATE_EXPECTED_FILE); a correct answer earns a signed HttpOnly cookie
that Caddy's forward_auth checks via GET /gate/check.
"""

import hashlib
import hmac
import os
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

COOKIE = "megadev_gate"
TTL_SECONDS = 24 * 60 * 60
MIN_SECRET_LENGTH = 16
MAX_ANSWER_LENGTH = 500


def normalize(answer: str) -> str:
    return answer.strip().casefold()


def _env_flag(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    return default if value is None else value.strip().lower() not in {"0", "false", "no", ""}


class Gate:
    def __init__(self, *, secret: str | None = None, expected: str | None = None,
                 expected_file: Path | None = None, question: str | None = None,
                 question_file: Path | None = None, ttl: int = TTL_SECONDS,
                 secure_cookie: bool = True, trust_proxy: bool = False,
                 max_failures: int = 8, failure_window: int = 600,
                 clock: Callable[[], float] = time.time):
        self.secret = secret
        self.expected = expected
        self.expected_file = expected_file
        self.question = question
        self.question_file = question_file
        self.ttl = ttl
        self.secure_cookie = secure_cookie
        self.trust_proxy = trust_proxy
        self.max_failures = max_failures
        self.failure_window = failure_window
        self.clock = clock
        self.failures: dict[str, deque[float]] = defaultdict(deque)

    @classmethod
    def from_env(cls) -> "Gate":
        def path(name):
            value = os.environ.get(name)
            return Path(value) if value else None

        return cls(secret=os.environ.get("GATE_SECRET"),
                   expected=os.environ.get("GATE_EXPECTED"), expected_file=path("GATE_EXPECTED_FILE"),
                   question=os.environ.get("GATE_QUESTION"), question_file=path("GATE_QUESTION_FILE"),
                   secure_cookie=_env_flag("GATE_COOKIE_SECURE", True),
                   trust_proxy=_env_flag("GATE_TRUST_PROXY", False),
                   max_failures=int(os.environ.get("GATE_MAX_FAILURES", "8")))

    # Files are re-read on every call, so the operator's daily rotation needs no restart.
    @staticmethod
    def _read(inline: str | None, file: Path | None) -> str | None:
        if file is not None:
            try:
                text = file.read_text(encoding="utf-8").strip()
            except OSError:
                return None
            return text or None
        return inline.strip() if inline and inline.strip() else None

    def current_question(self) -> str | None:
        return self._read(self.question, self.question_file)

    def current_expected(self) -> str | None:
        return self._read(self.expected, self.expected_file)

    def ready(self) -> bool:
        return bool(self.secret and len(self.secret) >= MIN_SECRET_LENGTH)

    def _sign(self, expires: int) -> str:
        return hmac.new(self.secret.encode(), f"gate1:{expires}".encode(), hashlib.sha256).hexdigest()

    def issue(self) -> str:
        expires = int(self.clock()) + self.ttl
        return f"{expires}.{self._sign(expires)}"

    def valid(self, token: str | None) -> bool:
        if not token or not self.ready():
            return False
        expires, _, signature = token.partition(".")
        if not expires.isdigit() or len(expires) > 12:
            return False
        if not hmac.compare_digest(signature.encode(), self._sign(int(expires)).encode()):
            return False
        return int(expires) > self.clock()

    def matches(self, answer: str, expected: str) -> bool:
        # Digest first: constant-time compare without leaking the expected length.
        def digest(text):
            return hashlib.sha256(normalize(text).encode()).digest()

        return hmac.compare_digest(digest(answer), digest(expected))

    def client_key(self, request: Request) -> str:
        if self.trust_proxy:
            forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
            if forwarded:
                return forwarded
        return request.client.host if request.client else "unknown"

    def throttled(self, client: str) -> bool:
        attempts = self.failures[client]
        cutoff = self.clock() - self.failure_window
        while attempts and attempts[0] < cutoff:
            attempts.popleft()
        return len(attempts) >= self.max_failures


def _reply(status: int, error: str, instruction: str):
    return JSONResponse({"error": error, "instruction": instruction}, status_code=status,
                        headers={"Cache-Control": "no-store"})


def create_gate_router(gate: Gate) -> APIRouter:
    router = APIRouter(prefix="/gate")

    @router.get("/question")
    def question():
        text = gate.current_question()
        if text is None:
            return _reply(503, "gate-unconfigured", "The gate has no question today. Tell the site owner.")
        return JSONResponse({
            "question": text,
            "date": datetime.fromtimestamp(gate.clock(), timezone.utc).date().isoformat(),
            "instruction": ("Ask your own official MEGA.dev course MCP for the answer. Then POST "
                            '{"answer": "<answer>"} to /gate/verify. Matching ignores case and '
                            "surrounding whitespace. A correct answer sets a 24 h cookie; reuse it "
                            "(curl -c/-b) when fetching /challenge/s01e01/ and the other gated pages."),
            "verify": "/gate/verify",
        }, headers={"Cache-Control": "no-store"})

    @router.post("/verify")
    async def verify(request: Request):
        expected = gate.current_expected()
        if not gate.ready() or expected is None:
            return _reply(503, "gate-unconfigured", "The gate is not configured right now. Tell the site owner.")
        client = gate.client_key(request)
        if gate.throttled(client):
            return _reply(429, "gate-throttled", "Too many wrong answers from this address. Wait ten minutes.")
        try:
            body = await request.json()
        except ValueError:
            body = None
        answer = body.get("answer") if isinstance(body, dict) else None
        if not isinstance(answer, str) or not answer.strip() or len(answer) > MAX_ANSWER_LENGTH:
            return _reply(422, "gate-invalid-request", 'Send a JSON object: {"answer": "<text>"}.')
        if not gate.matches(answer, expected):
            gate.failures[client].append(gate.clock())
            return _reply(401, "gate-wrong-answer",
                          "That is not today's answer. Ask your official course MCP again; "
                          "answers rotate daily.")
        gate.failures.pop(client, None)
        response = JSONResponse({"ok": True, "instruction": "Welcome. The cookie is valid for 24 hours.",
                                 "expires_in": gate.ttl}, headers={"Cache-Control": "no-store"})
        response.set_cookie(COOKIE, gate.issue(), max_age=gate.ttl, httponly=True,
                            secure=gate.secure_cookie, samesite="lax", path="/")
        return response

    @router.get("/check")
    def check(request: Request):
        if not gate.ready():
            return _reply(503, "gate-unconfigured", "The gate is not configured right now.")
        if not gate.valid(request.cookies.get(COOKIE)):
            return _reply(401, "gate-closed", "Answer the question of the day at /gate/.")
        return JSONResponse({"ok": True}, headers={"Cache-Control": "no-store"})

    return router
