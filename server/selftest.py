#!/usr/bin/env python3
"""Exercise the deployed ASGI app in-process, including MCP JSON-RPC. No HTTP sockets."""

import importlib.util
import json
import logging
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent


def require(condition, message):
    # Deliberately not `assert`: python -O must not disable the verifier.
    if not condition:
        raise AssertionError(message)


def exercise():
    sys.path.insert(0, str(ROOT))
    from fastapi.testclient import TestClient
    from server.app import CourseStore, TOOL_MODELS, create_app

    fixture = json.loads((ROOT / "server/fixtures_mock.json").read_text())
    require(len(fixture["lessons"]) == len(fixture["challenges"]) == 2, "two lessons and challenges")

    def synthetic(value, key=""):
        if isinstance(value, dict):
            for child_key, child in value.items():
                synthetic(child, child_key)
        elif isinstance(value, list):
            for child in value:
                synthetic(child, key)
        elif isinstance(value, str):
            if key not in {"uuid", "challenge"}:
                require(value.startswith("MOCK-"), f"non-synthetic fixture field: {key}")

    synthetic(fixture)
    with tempfile.TemporaryDirectory(prefix="mock-course-selftest-") as temporary:
        snapshot = Path(temporary) / "progress.json"
        store = CourseStore(fail_every=2, snapshot=snapshot)
        with TestClient(create_app(store), base_url="http://127.0.0.1:8000") as client:
            def call(name, data=None, status=200):
                response = client.post(f"/api/{name}", json=data or {})
                require(response.status_code == status, f"{name}: {response.status_code}: {response.text}")
                body = response.json()
                require("instruction" in body, f"{name}: missing envelope")
                return body

            require(client.get("/health").json()["synthetic"], "health")
            require(set(client.get("/api/tools").json()["tools"]) == set(TOOL_MODELS), "HTTP discovery")
            day = call("mega-start")
            lesson = day["lesson"]["id"]
            challenge = day["challenge"]["uuid"]
            rows = call("list-challenges")["challenges"]
            require(len(rows) == 2 and not any(row["solved"] for row in rows), "fresh challenges")
            for row in rows:
                require(set(("uuid", "code", "title", "description", "startPoint", "solved")) <= row.keys(), "shape")
                require(row["title"].startswith("MOCK-"), "title prefix")
            target = {"uuid": challenge}
            fake = {"mock-receipt": "MOCK-forged"}
            call("resume-challenge", {**target, "receipts": fake}, 409)
            call("claim-challenge", {**target, "receipts": fake, "answer": {"text": "MOCK-hello"}}, 409)
            started = call("start-challenge", target)
            receipts = started["receipts"]
            require(started["challengeId"] == challenge and receipts, "start hands receipts")
            wrong = call("resume-challenge", {**target, "receipts": fake}, 409)
            require(wrong["error"] == "mock-wrong-receipts", "forged receipts refusal")
            call("resume-challenge", {**target, "receipts": receipts})
            paused = call("artifact", target)
            require("paused" in paused["instruction"], "artifact pause notice")
            call("artifact", {**target, "answer": "y"})
            call("save-brief", {"lesson": lesson, "brief": "MOCK-first"})
            replacement = {"lesson": lesson, "brief": "MOCK-replacement"}
            failure = call("save-brief", replacement, 500)
            require(failure["error"] == "mock-injected-failure", "injected failure")
            require(store.progress.briefs[lesson] == "MOCK-first", "failed save must not mutate brief")
            require(call("save-brief", replacement)["brief"] == "MOCK-replacement", "retry replaces")
            require(len(store.progress.briefs) == 1, "replace rather than append")
            require(call("mega-start")["brief"] == "MOCK-replacement", "brief visible")
            call("debrief", {**target, "snags": [{"snag": "MOCK-cup stuck.", "resolve": "MOCK-turned it.",
                                                 "by": "harness"}]}, 409)
            call("claim-challenge", {**target, "receipts": receipts, "answer": {}}, 422)
            claimed = call("claim-challenge", {**target, "receipts": receipts,
                                               "answer": {"text": "MOCK-tick"}})
            require(claimed["accepted"], "claim")
            refusal = call("claim-challenge", {**target, "receipts": receipts,
                                               "answer": {"text": "MOCK-tick"}}, 409)
            require(refusal["error"] == "mock-already-solved", "solved refusal")
            call("start-challenge", target, 409)
            filed = call("debrief", {**target, "story": "MOCK-The imaginary cup ticked.",
                                     "snags": [{"snag": "MOCK-cup stuck.", "resolve": "MOCK-turned it.",
                                                "by": "harness"}]})
            require(filed["debrief"]["story"].startswith("MOCK-"), "debrief stored")
            require(call("mega-start")["lesson"]["id"] == "MOCK-L02", "day progression")
            lane = call("check-lane", {"need": "MOCK-practice"})
            require(lane["remaining"] == 1 and lane["need"] == "MOCK-practice", "lane progression")
            require(call("rook", {"input": "MOCK-who are you"})["rook"].startswith("MOCK-"), "rook")
            call("check-lane", {}, 422)
            call("rook", {}, 422)
            call("start-challenge", {"uuid": "MOCK-missing"}, 422)
            call("start-challenge", {"uuid": "00000000-0000-0000-0000-000000000000"}, 404)
            call("save-brief", {"lesson": lesson, "brief": " "}, 422)
            call("list-challenges", {"unexpected": True}, 422)
            call("MOCK-missing", status=404)
            malformed = client.post("/api/mega-start", json=[])
            require(malformed.status_code == 422 and "instruction" in malformed.json(), "malformed body envelope")

            # Real SDK transport and lifespan, reached through the mounted ASGI endpoint.
            headers = {"Accept": "application/json, text/event-stream"}
            sequence = 0

            def rpc(method, params=None):
                nonlocal sequence
                sequence += 1
                response = client.post("/mcp", headers=headers, json={
                    "jsonrpc": "2.0", "id": sequence, "method": method, "params": params or {},
                })
                require(response.status_code == 200, f"MCP transport: {response.status_code}: {response.text}")
                body = response.json()
                require("result" in body and "error" not in body, f"MCP JSON-RPC error: {body}")
                return body["result"]

            initialized = rpc("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                                             "clientInfo": {"name": "MOCK-selftest", "version": "1"}})
            headers["MCP-Protocol-Version"] = initialized["protocolVersion"]
            require(set(row["name"] for row in rpc("tools/list")["tools"]) == set(TOOL_MODELS), "MCP discovery")

            def mcp_call(name, data=None, error=False):
                result = rpc("tools/call", {"name": name, "arguments": data or {}})
                require(bool(result.get("isError")) == error, f"MCP tool error mismatch: {result}")
                envelope = result.get("structuredContent")
                require(isinstance(envelope, dict) and "instruction" in envelope, f"MCP reply envelope: {result}")
                return envelope

            require(mcp_call("check-lane", {"need": "MOCK-status"})["solved"] == [challenge],
                    "HTTP/MCP share state")
            mcp_call("mega-start")
            mcp_call("list-challenges")
            second = {"uuid": rows[1]["uuid"]}
            second_receipts = mcp_call("start-challenge", second)["receipts"]
            mcp_call("resume-challenge", {**second, "receipts": second_receipts})
            mcp_call("artifact", second)
            mcp_call("claim-challenge", {**second, "receipts": second_receipts,
                                         "answer": {"text": "MOCK-flash"}})
            mcp_call("claim-challenge", {**second, "receipts": second_receipts,
                                         "answer": {"text": "MOCK-flash"}}, error=True)
            mcp_call("debrief", {**second, "snags": [{"snag": "MOCK-beacon dim.",
                                                      "resolve": "MOCK-folded it.", "by": "pair"}]})
            mcp_brief = {"lesson": "MOCK-L02", "brief": "MOCK-Paper practice"}
            mcp_call("save-brief", mcp_brief, error=True)
            mcp_call("save-brief", mcp_brief)
            mcp_call("rook", {"input": "MOCK-who are you"})
            require(call("check-lane", {"need": "MOCK-status"})["remaining"] == 0,
                    "MCP mutation visible via HTTP")
        restored = CourseStore(snapshot=snapshot)
        require(restored.progress == store.progress, "snapshot restores all progress")
        require(restored.call("mega-start", {})["lesson"]["id"] == "MOCK-L02", "completed season")
        isolated = CourseStore()
        require(not isolated.progress.solved, "new store isolation")
        for _ in range(3):
            isolated.call("save-brief", {"lesson": lesson, "brief": "MOCK-no-failure"})
        for invalid in (-1, 1):
            try:
                CourseStore(fail_every=invalid)
            except ValueError:
                pass
            else:
                raise AssertionError("invalid failure interval accepted")


def exercise_gate():
    """OAuth gate invariants and fail-closed paths; no simulated enrollment success."""
    import asyncio
    import base64
    import hashlib
    import hmac
    from urllib.parse import parse_qs, urlencode, urlsplit
    import httpx
    sys.path.insert(0, str(ROOT))
    from fastapi.testclient import TestClient
    from server.app import CourseStore, create_app
    from server.gate import (COOKIE, STATE_COOKIE, DEFAULT_NEXT, ISSUER, RESOURCE,
                             Gate)

    now = [1_800_000_000.0]
    calls = []
    secret = "selftest-secret-not-a-credential"
    client_id = "selftest-public-client-id"
    redirect_uri = "https://gate.test/gate/callback"
    private = "SELFTEST-provider-private-data"

    def rejected_token(request):
        calls.append(request)
        return httpx.Response(401, json={"error": private})

    def make_gate(handler=rejected_token, **options):
        configuration = dict(secret=secret, oauth_client_id=client_id,
                             oauth_redirect_uri=redirect_uri, clock=lambda: now[0],
                             upstream_transport=httpx.MockTransport(handler))
        configuration.update(options)
        return Gate(**configuration)

    def open_client(gate):
        return TestClient(create_app(CourseStore(), gate=gate), base_url="https://gate.test")

    def start(client, next_path=DEFAULT_NEXT):
        response = client.get("/gate/login", params={"next": next_path}, follow_redirects=False)
        require(response.status_code == 302, "configured login starts OAuth")
        require(response.headers["cache-control"] == "no-store", "login is not cached")
        location = urlsplit(response.headers["location"])
        require(location.scheme == "https" and location.netloc == "hq.mega.dev"
                and location.path == "/authorize", "authorization origin is fixed")
        query = parse_qs(location.query)
        require(query["client_id"] == [client_id] and query["redirect_uri"] == [redirect_uri],
                "authorization uses configured client and callback")
        require(query["response_type"] == ["code"] and query["code_challenge_method"] == ["S256"]
                and query["resource"] == [RESOURCE] and "scope" not in query,
                "authorization uses PKCE and official resource without unsupported scopes")
        require("code_verifier" not in query and "access_token" not in query, "no secrets in login URL")
        header = response.headers["set-cookie"]
        require(all(flag in header for flag in ("HttpOnly", "Secure", "Max-Age=300",
                                               "SameSite=lax", "Path=/gate/callback")),
                "browser binding cookie flags")
        return query["state"][0], query["code_challenge"][0]

    def no_grant(response, client, status):
        require(response.status_code == status and COOKIE not in response.cookies,
                "failed flow does not issue an access cookie")
        require(response.headers["cache-control"] == "no-store"
                and response.headers["referrer-policy"] == "no-referrer",
                "callback responses cannot be cached or leak through referrers")
        require(private not in response.text and "SELFTEST-auth-code" not in response.text,
                "provider payload and authorization code are never reflected")
        require(client.get("/gate/check").status_code == 401, "failure leaves gate closed")

    gate = make_gate()
    with open_client(gate) as client:
        require(client.get("/gate/check").status_code == 401, "check without cookie")
        handshake = client.get("/gate/handshake", params={"next": "/challenge/s01e02/entry/"})
        data = handshake.json()
        require(handshake.status_code == 200 and data["available"] and data["configured"]
                and handshake.headers["cache-control"] == "no-store", "configured handshake")
        require(parse_qs(urlsplit(data["login_url"]).query)["next"] == ["/challenge/s01e02/entry/"]
                and "approval" in data["instruction"] and "login" in data["instruction"],
                "handshake mediates fresh visitor approval")
        require(not gate.pending and STATE_COOKIE not in handshake.cookies, "handshake does not start OAuth")
        require(client.get("/gate/question").status_code != 200
                and client.post("/gate/verify", json={"answer": "anything"}).status_code != 200,
                "removed shared-question API cannot grant access")
        require(client.get("/health").json()["synthetic"], "gate preserves mock routes")

        state, challenge = start(client)
        pending = gate.pending[state]
        expected_challenge = base64.urlsafe_b64encode(hashlib.sha256(pending.verifier.encode()).digest())
        require(challenge == expected_challenge.rstrip(b"=").decode(), "authorization binds the stored verifier")
        require(pending.next_path == DEFAULT_NEXT and pending.expires == now[0] + 300,
                "state stores bounded lifetime and validated destination")
        binding = client.cookies[STATE_COOKIE]
        require(pending.binding_digest == hashlib.sha256(binding.encode()).digest(),
                "state binds this browser without storing its raw cookie")
        before = len(calls)
        with open_client(gate) as other:
            denied = other.get("/gate/callback", params={"state": state, "code": "SELFTEST-auth-code"})
            no_grant(denied, other, 400)
            other.cookies.set(STATE_COOKIE, "different-browser-binding", domain="gate.test",
                              path="/gate/callback")
            denied = other.get("/gate/callback", params={"state": state, "code": "SELFTEST-auth-code"})
            no_grant(denied, other, 400)
        require(state in gate.pending and len(calls) == before, "CSRF failures cannot exchange or consume another login")
        denied = client.get("/gate/callback", params={"state": state, "code": "SELFTEST-auth-code", "iss": ISSUER})
        no_grant(denied, client, 403)
        require(state not in gate.pending and len(calls) == before + 1, "valid binding consumes state before exchange")
        request = calls[-1]
        form = parse_qs(request.content.decode())
        require(request.url == ISSUER + "/token" and form["code_verifier"] == [pending.verifier]
                and form["resource"] == [RESOURCE] and form["redirect_uri"] == [redirect_uri]
                and form["client_id"] == [client_id], "token request stays at fixed issuer with PKCE and resource")
        require(request.headers["user-agent"] == "me-gad-ev-gate/1.0"
                and "authorization" not in request.headers, "fresh public-client exchange, no harness credentials")
        replay = client.get("/gate/callback", params={"state": state, "code": "SELFTEST-auth-code"})
        no_grant(replay, client, 400)
        require(len(calls) == before + 1, "replayed callback never reaches upstream")
        require(STATE_COOKIE not in client.cookies, "consumed binding cookie is removed")

        for parameters in ({"error": private, "error_description": private},
                           {"code": "SELFTEST-auth-code", "iss": "https://untrusted.test"},
                           {}, {"code": ""}):
            state, _ = start(client)
            before = len(calls)
            no_grant(client.get("/gate/callback", params={"state": state, **parameters}), client, 400)
            require(state not in gate.pending and len(calls) == before,
                    "denial, wrong issuer and missing code consume state without exchange")

        state, _ = start(client)
        no_grant(client.get("/gate/callback?state=" + state + "&state=" + state
                            + "&code=SELFTEST-auth-code"), client, 400)
        require(not calls[-1].url.path.endswith("/mcp"), "duplicate callback fields do not call MCP")
        state, _ = start(client)
        now[0] += 300
        before = len(calls)
        no_grant(client.get("/gate/callback", params={"state": state, "code": "SELFTEST-auth-code"}), client, 400)
        require(state not in gate.pending and len(calls) == before, "state expires at the exact five-minute boundary")

        for unsafe in ("https://evil.test/challenge/", "//evil.test/challenge/", "/gate/callback",
                       "/challenge/../gate/", "/challenge/%2e%2e/gate/", "/challenge/?next=//evil.test",
                       "/challenge/#fragment", "/challenge/s01e01/entry/extra", "/challenge/\\evil"):
            state, _ = start(client, unsafe)
            require(gate.pending[state].next_path == DEFAULT_NEXT, "unsafe redirect falls back to private entry")
            handoff = client.get("/gate/handshake", params={"next": unsafe}).json()["login_url"]
            require(parse_qs(urlsplit(handoff).query)["next"] == [DEFAULT_NEXT],
                    "handshake applies the same redirect allowlist")
        for safe in ("/challenge/", "/challenge/s01e01/entry/", "/challenge/s01e02/entry",
                     "/challenge/s01e03/entry/"):
            state, _ = start(client, safe)
            require(gate.pending[state].next_path == safe.rstrip("/") + "/", "allowlisted redirect is canonical")

        # Signing is tested directly, not presented as an upstream enrollment success.
        token = gate.issue()
        expires, _, signature = token.partition(".")
        old_signature = hmac.new(secret.encode(), f"gate1:{expires}".encode(), hashlib.sha256).hexdigest()
        for forged in (f"{expires}.{'0' * 64}", f"{int(expires) + 86400}.{signature}", "garbage", ".",
                       f"-1.{signature}", f"{expires}.{old_signature}",
                       make_gate(secret="another-selftest-secret-xxx").issue()):
            client.cookies.clear()
            client.cookies.set(COOKIE, forged, domain="gate.test")
            require(client.get("/gate/check").status_code == 401, "forged or legacy cookie is rejected")
        for raw in (r'megadev_gate="\262.x"', r'megadev_gate="1800086400.\377"'):
            client.cookies.clear()
            require(client.get("/gate/check", headers={"cookie": raw}).status_code == 401,
                    "malformed Unicode cookie fails closed")
        client.cookies.clear()
        client.cookies.set(COOKIE, token, domain="gate.test")
        require(client.get("/gate/check").status_code == 200, "correct local HMAC validates")
        now[0] += 86400
        require(client.get("/gate/check").status_code == 401, "local cookie expires at exact deadline")

    bounded = make_gate(max_pending=2)
    with open_client(bounded) as client:
        start(client)
        start(client)
        require(client.get("/gate/login", follow_redirects=False).status_code == 429
                and len(bounded.pending) == 2, "pending state has a hard cap")
        now[0] += 300
        start(client)
        require(len(bounded.pending) == 1, "a new login retires expired states before capacity check")

    for configuration in ({"secret": None}, {"secret": "short"}, {"oauth_client_id": None},
                          {"oauth_redirect_uri": None}, {"oauth_redirect_uri": "https://gate.test/gate/callback?x=1"},
                          {"oauth_redirect_uri": "http://remote.test/gate/callback"}):
        with open_client(make_gate(**configuration)) as client:
            handshake = client.get("/gate/handshake").json()
            require(not handshake["available"] and not handshake["configured"], "missing config is advertised honestly")
            require(client.get("/gate/login", follow_redirects=False).status_code == 503
                    and client.get("/gate/check").status_code == 503, "unconfigured gate fails closed")

    # All upstream fixtures below fail. A 200 response or invented token never earns access.
    for failure in ("network", "token-json", "missing-token", "wrong-token-type", "http-redirect",
                    "mcp-http", "mcp-html", "mcp-rpc-error", "mcp-wrong-id", "tool-error", "tool-no-challenges"):
        observed = []

        def upstream(request, *, observed=observed, failure=failure):
            observed.append(request)
            if request.url.path == "/revoke":
                return httpx.Response(503, text=private)
            if request.url.path == "/token":
                if failure == "network":
                    raise httpx.ConnectError(private, request=request)
                if failure == "token-json":
                    return httpx.Response(200, text="not json " + private)
                if failure == "missing-token":
                    return httpx.Response(200, json={"token_type": "Bearer"})
                if failure == "http-redirect":
                    return httpx.Response(302, headers={"location": "https://evil.test/token"})
                return httpx.Response(200, json={"access_token": "SELFTEST-invalid-access",
                                                "refresh_token": "SELFTEST-invalid-refresh",
                                                "token_type": "MAC" if failure == "wrong-token-type" else "Bearer"})
            require(request.url == RESOURCE, "MCP transport cannot follow arbitrary upstream locations")
            payload = json.loads(request.content)
            if failure == "mcp-http":
                return httpx.Response(401, json={"error": private})
            if failure == "mcp-html":
                return httpx.Response(200, text=private, headers={"content-type": "text/html"})
            if failure == "mcp-rpc-error":
                return httpx.Response(200, json={"jsonrpc": "2.0", "id": payload["id"],
                                                "error": {"message": private}})
            if failure == "mcp-wrong-id":
                return httpx.Response(200, json={"jsonrpc": "2.0", "id": "unrelated", "result": {}})
            if payload["method"] == "initialize":
                return httpx.Response(200, json={"jsonrpc": "2.0", "id": payload["id"],
                                                "result": {"protocolVersion": "2025-06-18",
                                                           "capabilities": {}, "serverInfo": {}}},
                                      headers={"Mcp-Session-Id": "SELFTEST-session"})
            require(request.headers["mcp-session-id"] == "SELFTEST-session"
                    and request.headers["mcp-protocol-version"] == "2025-06-18",
                    "negotiated session and protocol are reused")
            if payload["method"] == "notifications/initialized":
                return httpx.Response(202)
            require(payload["method"] == "tools/call" and payload["params"] == {
                "name": "list-challenges", "arguments": {}}, "only read-only official challenges tool is called")
            result = {"isError": True, "content": [{"type": "text", "text": private}]} if failure == "tool-error" else {
                "content": [{"type": "text", "text": json.dumps({"instruction": private})}]}
            # A failing SSE result also exercises Streamable HTTP framing without pretending enrollment.
            return httpx.Response(200, text="event: message\ndata: " + json.dumps({
                "jsonrpc": "2.0", "id": payload["id"], "result": result}) + "\n\n",
                headers={"content-type": "text/event-stream"})

        with open_client(make_gate(upstream)) as client:
            state, _ = start(client)
            response = client.get("/gate/callback", params={"state": state, "code": "SELFTEST-auth-code"})
            no_grant(response, client, 403)
            require(all(request.url.host == "hq.mega.dev" for request in observed), "upstream origins remain fixed")
            revocations = [parse_qs(request.content.decode()) for request in observed if request.url.path == "/revoke"]
            if failure not in {"network", "token-json", "missing-token", "http-redirect"}:
                require({item["token_type_hint"][0] for item in revocations} == {"access_token", "refresh_token"},
                        "both transient tokens are revoked even after failure")

    async def concurrent_callbacks():
        entered, release = asyncio.Event(), asyncio.Event()
        exchanges = []

        async def delayed_rejection(request):
            exchanges.append(request)
            entered.set()
            await release.wait()
            return httpx.Response(401, json={"error": private})

        concurrent = make_gate(delayed_rejection)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(CourseStore(), gate=concurrent)),
                                     base_url="https://gate.test") as client:
            login = await client.get("/gate/login")
            state = parse_qs(urlsplit(login.headers["location"]).query)["state"][0]
            url = "/gate/callback?" + urlencode({"state": state, "code": "SELFTEST-auth-code"})
            first = asyncio.create_task(client.get(url))
            try:
                await asyncio.wait_for(entered.wait(), timeout=5)
                replay = await client.get(url)
                require(replay.status_code == 400 and COOKIE not in replay.cookies,
                        "parallel callback cannot replay consumed state while exchange awaits")
            finally:
                release.set()
                original = await first
            require(original.status_code == 403 and len(exchanges) == 1
                    and not concurrent.pending and COOKIE not in client.cookies,
                    "only one exchange can run and failed original grants nothing")

    asyncio.run(concurrent_callbacks())

    # Prove the actual preview's file boundary, not just /gate/check. A trusted
    # local test key exercises serving policy; it does not simulate enrollment.
    import os
    from server.preview import create_preview
    with tempfile.TemporaryDirectory(prefix="member-boundary-") as temporary:
        root = Path(temporary)
        targets = ["members/journal", "members/pl/journal",
                   *(f"challenge/s01e0{n}/entry" for n in range(1, 4))]
        for target in targets:
            directory = root / target
            directory.mkdir(parents=True)
            (directory / "index.html").write_text("MEMBER-ONLY-SYNTHETIC-RECORD", encoding="utf-8")
        with patch.dict(os.environ, {"MEGADEV_PRIVATE_ROOT": str(root), "GATE_SECRET": secret,
                                    "GATE_OAUTH_CLIENT_ID": client_id,
                                    "GATE_OAUTH_REDIRECT_URI": redirect_uri,
                                    "GATE_COOKIE_SECURE": "1"}):
            preview = create_preview()
        with TestClient(preview, base_url="https://gate.test") as reader:
            for target in targets:
                for suffix in ("/", "/index.html"):
                    closed = reader.get("/" + target + suffix, follow_redirects=False)
                    require(closed.status_code == 302 and "MEMBER-ONLY" not in closed.text,
                            "anonymous private-file variants never expose member bytes")
            require(reader.get("/journal/").status_code == 200,
                    "public story remains readable without enrollment")
            reader.cookies.set(COOKIE, "forged", domain="gate.test")
            require(reader.get("/members/journal/", follow_redirects=False).status_code == 302,
                    "forged session cannot read detailed histories")
            preview.state.gate.clock = lambda: now[0]
            reader.cookies.set(COOKIE, preview.state.gate.issue(), domain="gate.test")
            opened = reader.get("/members/journal/")
            require(opened.status_code == 200 and opened.text == "MEMBER-ONLY-SYNTHETIC-RECORD"
                    and opened.headers["cache-control"] == "private, no-store",
                    "valid site session reads separately rooted member record without shared caching")
            now[0] += preview.state.gate.ttl
            require(reader.get("/members/journal/", follow_redirects=False).status_code == 302,
                    "expired site session closes private histories")


def main():
    logging.disable(logging.INFO)
    # `uv sync --project server` supplies a local interpreter without mutating system Python.
    local = ROOT / "server/.venv"
    python = local / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if python.exists() and Path(sys.prefix).resolve() != local.resolve():
        return subprocess.run([str(python), "-B", str(Path(__file__).resolve())], check=False).returncode
    missing = [name for name in ("fastapi", "mcp", "httpx") if importlib.util.find_spec(name) is None]
    if missing:
        print("Missing dependencies; run: uv sync --project server", file=sys.stderr)
        print("today=mock-missing")
        return 1
    try:
        with patch("socket.socket.connect", side_effect=AssertionError("selftest attempted network I/O")), \
                patch("socket.socket.connect_ex", side_effect=AssertionError("selftest attempted network I/O")):
            exercise()
            exercise_gate()
    except Exception as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        print("today=mock-missing")
        return 1
    print("today=mock-ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
