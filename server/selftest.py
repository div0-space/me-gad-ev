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
    """Proof-of-MCP gate: question -> wrong 401 -> right sets cookie -> check 200; forgeries 401."""
    sys.path.insert(0, str(ROOT))
    from fastapi.testclient import TestClient
    from server.app import CourseStore, create_app
    from server.gate import COOKIE, Gate

    now = [1_800_000_000.0]
    with tempfile.TemporaryDirectory(prefix="mock-gate-selftest-") as temporary:
        expected_file = Path(temporary) / "expected.txt"
        expected_file.write_text("  Teacup-42\n")
        gate = Gate(secret="selftest-secret-not-a-credential", expected_file=expected_file,
                    question="SELFTEST-What is the word of the day?", clock=lambda: now[0], max_failures=4)
        # https base: the cookie is Secure, and the client jar honours that like a browser.
        with TestClient(create_app(CourseStore(), gate=gate), base_url="https://gate.test") as client:
            question = client.get("/gate/question")
            require(question.status_code == 200 and question.json()["question"].startswith("SELFTEST-"), "gate question")
            require("official" in question.json()["instruction"], "gate question instructs the agent")
            require(client.get("/gate/check").status_code == 401, "check without cookie")
            bad = client.post("/gate/verify", json={"answer": "wrong"})
            require(bad.status_code == 401 and bad.json()["error"] == "gate-wrong-answer", "wrong answer")
            require(COOKIE not in bad.cookies and client.get("/gate/check").status_code == 401, "no cookie on failure")
            for malformed in ({}, {"answer": 7}, {"answer": "  "}, {"answer": "x" * 501}, []):
                require(client.post("/gate/verify", json=malformed).status_code == 422, f"malformed {malformed!r}")
            require(client.post("/gate/verify", content=b"{", headers={"content-type": "application/json"})
                    .status_code == 422, "non-JSON body")
            good = client.post("/gate/verify", json={"answer": " TEACUP-42 "})
            require(good.status_code == 200 and good.json()["ok"], "right answer, normalised")
            header = good.headers["set-cookie"]
            require(all(flag in header for flag in ("HttpOnly", "Secure", "Max-Age=86400", "SameSite=lax")),
                    f"cookie flags: {header}")
            require(client.get("/gate/check").status_code == 200, "check with cookie")
            token = client.cookies[COOKIE]
            # Forgeries: tampered signature, tampered expiry, garbage, wrong secret.
            expires, _, signature = token.partition(".")
            other = Gate(secret="another-selftest-secret-xxx", clock=lambda: now[0]).issue()
            for forged in (f"{expires}.{'0' * len(signature)}", f"{int(expires) + 86400}.{signature}",
                           "garbage", ".", other, f"-1.{signature}"):
                client.cookies.clear()
                client.cookies.set(COOKIE, forged, domain="gate.test")
                require(client.get("/gate/check").status_code == 401, f"forged cookie accepted: {forged}")
            client.cookies.clear()
            client.cookies.set(COOKIE, token, domain="gate.test")
            require(client.get("/gate/check").status_code == 200, "genuine cookie still fine")
            now[0] += 24 * 60 * 60 + 1
            require(client.get("/gate/check").status_code == 401, "cookie expires after 24 h")
            # Rotation without restart: the file changes, the old answer stops working.
            expected_file.write_text("kettle-7\n")
            require(client.post("/gate/verify", json={"answer": "teacup-42"}).status_code == 401, "rotated away")
            require(client.post("/gate/verify", json={"answer": "Kettle-7"}).status_code == 200, "rotated in")
            # Brute force: the 4th wrong answer from one address locks it out, even for the right one.
            fresh = Gate(secret="selftest-secret-not-a-credential", expected="a", question="q",
                         clock=lambda: now[0], max_failures=4)
            with TestClient(create_app(CourseStore(), gate=fresh), base_url="https://gate.test") as brute:
                for _ in range(4):
                    require(brute.post("/gate/verify", json={"answer": "b"}).status_code == 401, "wrong")
                require(brute.post("/gate/verify", json={"answer": "a"}).status_code == 429, "throttled")
                now[0] += 601
                require(brute.post("/gate/verify", json={"answer": "a"}).status_code == 200, "window passes")
        # Fail closed: no secret, no short secret, no answer, no question => 503, never a pass.
        for broken in (Gate(expected="a", question="q"), Gate(secret="short", expected="a", question="q"),
                       Gate(secret="selftest-secret-not-a-credential", question="q")):
            with TestClient(create_app(CourseStore(), gate=broken), base_url="https://gate.test") as closed:
                require(closed.post("/gate/verify", json={"answer": "a"}).status_code == 503, "unconfigured verify")
                require(closed.get("/gate/check").status_code in {401, 503}, "unconfigured check")
        with TestClient(create_app(CourseStore(), gate=Gate(secret="selftest-secret-not-a-credential")),
                        base_url="https://gate.test") as bare:
            require(bare.get("/gate/question").status_code == 503, "no question configured")
            require(bare.get("/health").json()["synthetic"], "gate does not shadow the mock routes")


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
