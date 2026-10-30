# Private practice MCP for our agents

Two imaginary lessons, two imaginary challenges, one shared state machine. A cardboard
rook and a clockwork teacup let our agents rehearse the full course workflow without
official course credentials or upstream requests. The hosted instance is private
to our team and requires its own Bearer token. Every fixture title and body begins
with `MOCK-`; the only unprefixed fixture strings are synthetic challenge UUIDs and
references to them. Read the entire source of that guarantee in
[`fixtures_mock.json`](fixtures_mock.json#L1), and its recursive check in
[`selftest.py`](selftest.py#L28).

This is a **workflow mirror** of the official course MCP. Tool names, argument
names, required sets and key constraints (uuid pattern, enums, length caps) were
aligned 1:1 against the official server's tool schemas on 2026-10-28; nested
debrief shapes accept every payload the official schema allows and enforce only
its required trio per snag. Claims accept any nonempty answer object; this
server cannot grade course work. The implementation is
[`CourseStore._execute`](app.py).

## Take the shortest path to a working server

From the repository root, with Python 3.11+ and [uv](https://docs.astral.sh/uv/):

```sh
uv sync --project server
uv run --project server uvicorn server.app:create_app --factory --host 127.0.0.1 --port 8000
```

Keep that terminal open. In another terminal, ask for the first lesson:

```sh
curl --fail-with-body http://127.0.0.1:8000/api/mega-start \
  -H 'Content-Type: application/json' -d '{}'
```

The reply includes `instruction`, `lesson`, `challenge`, `previously`, `rook`, `brief`,
and `briefInstruction`. Copy `challenge.uuid` into subsequent calls. Plain HTTP uses
`POST /api/<tool-name>` with a JSON object, including `{}` for tools without arguments.
`GET /api/tools` returns JSON schemas; `GET /health` returns `synthetic: true`.
Routes and the shared store are wired in [`create_app`](app.py#L201).

## Wire an agent to MCP

For clients whose configuration supports `mcpServers` and HTTP transports:

```json
{
  "mcpServers": {
    "mock-course": {
      "type": "http",
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

Select **Streamable HTTP**, rather than SSE, in clients with a transport selector.
Configuration keys vary by client; the endpoint is always `/mcp`. The official Python
SDK supplies initialization, discovery, and tool calls. The parent FastAPI lifespan
starts its session manager, as required by the
[SDK mounting contract](https://github.com/modelcontextprotocol/python-sdk/blob/v1.30.0/README.md#mounting-to-an-existing-asgi-server).
See [`create_mcp`](mcp_server.py#L14) and [`create_app`](app.py#L201).

### Hosted private instance

Our endpoint is `https://megadev.div0.space/mcp`, using Streamable HTTP and a
team-only token supplied privately by the owner:

```json
{
  "mcpServers": {
    "megadev-private": {
      "type": "http",
      "url": "https://megadev.div0.space/mcp",
      "headers": {
        "Authorization": "Bearer <private-team-token>"
      }
    }
  }
}
```

Use the client's secure token/header configuration; do not commit a configured
token or paste it into chat. Clients must support static Bearer authentication
or custom HTTP headers. OAuth-only connectors are not supported by this endpoint.

Missing or incorrect tokens receive HTTP `401`, `Cache-Control: no-store`,
`WWW-Authenticate: Bearer realm="private-mcp"` and a JSON `private_mcp` error.
The response explicitly identifies a private team service, names the
`Authorization` header and states that OAuth is unsupported; it never includes
the token. The same policy protects `/api/*`.

This token grants access only to our synthetic practice service, not the
official course. The Journal's human enrollment OAuth gate is separate and
unchanged. Production policy is implemented by Caddy; see
[`deploy/caddy-gate.snippet`](../deploy/caddy-gate.snippet).

## The workflow and its deliberate friction

All successful tool replies carry `instruction`. Some add a `rook` story line.
HTTP domain errors carry `instruction` and `error` with a non-2xx status. MCP domain
errors carry the same envelope in `structuredContent`, plus `isError: true` and a text
instruction. SDK-level malformed JSON-RPC or invalid tool arguments follow SDK errors.
The shared validation boundary is [`CourseStore.call`](app.py#L118); the MCP error
adapter is [`invoke`](mcp_server.py#L17).

| Tool | Arguments (JSON keys) | Mock behavior / source |
|---|---|---|
| `mega-start` | optional `lesson_id` | First unsolved lesson, or final lesson after completion; includes context and saved brief. [Source](app.py#L149) |
| `list-challenges` | none | Both challenges with `uuid`, `code`, `title`, `description`, `startPoint`, `solved`. [Source](app.py#L158) |
| `start-challenge` | `challenge_id` | Start by UUID; already solved → 409. [Source](app.py#L160) |
| `resume-challenge` | `challenge_id` | Return an already started challenge; not started → 409. [Source](app.py#L167) |
| `claim-challenge` | `challenge_id`, `answer` | Mark started challenge solved; repeat → 409. Any nonblank answer passes. [Source](app.py#L169) |
| `save-brief` | `lesson_id`, `brief` | Replace saved text; configurable transient failure. [Source](app.py#L181) |
| `debrief` | `lesson_id`, `debrief` | File or replace lesson reflection. [Source](app.py#L190) |
| `check-lane` | none | Shared started/solved UUIDs and remaining count. [Source](app.py#L193) |
| `artifact` | `challenge_id`, optional `content` | Save or read inline text for a started challenge; never executes text or fetches a URL. [Source](app.py#L175) |
| `rook` | none | Invented cardboard-rook story. [Source](app.py#L196) |

Lesson IDs are `MOCK-L01` and `MOCK-L02`. Unknown IDs/tools return 404; malformed,
blank, oversized, or unexpected HTTP arguments return 422. Text fields allow up to
20,000 characters. The schemas are in [`app.py`](app.py#L16).

## Retry practice and optional persistence

```sh
MOCK_SAVE_BRIEF_FAIL_EVERY=2 MOCK_SNAPSHOT=/tmp/mock-course-progress.json \
  uv run --project server uvicorn server.app:create_app --factory --host 127.0.0.1 --port 8000
```

`MOCK_SAVE_BRIEF_FAIL_EVERY=0` disables injection (the default). With `N >= 2`, every
Nth **valid** save attempt fails: N=2 gives success, failure, successful retry. Failed
saves preserve the prior brief, while consuming their call number. N=1 and negative
values fail startup because retries could never succeed. This is deterministic
failure injection, implemented in [`save-brief`](app.py#L184).

Without `MOCK_SNAPSHOT`, restarting loses progress. With it, mutations are atomically
written through a sibling `.tmp` file; startup validates the snapshot and restores
progress and the failure counter. A corrupt snapshot fails startup rather than silently
resetting progress. Run **one process / one uvicorn worker**: a thread lock protects
one process; JSON snapshots provide no coordination between processes. Everyone connected
to that process shares one learner. Sources: [`Progress`](app.py#L70),
[`CourseStore`](app.py#L80), [`_persist`](app.py#L99), [`call`](app.py#L118).

## Let the verifier decide

```sh
uv sync --project server && python3 server/selftest.py
# Expected stdout: today=mock-ok; exit 0
python3.12 server/selftest.py
# The dispatch plan's declared verifier (when python3.12 is installed).
```

The entry script uses only the standard library until it selects `server/.venv/bin/python`
(Windows: `Scripts/python.exe`) created by `uv sync`. It never installs dependencies
itself. Missing dependencies or failed expectations print `today=mock-missing` and exit 1.
Checks stay active under `python -O`. Sources: [`require`](selftest.py#L17),
[`main`](selftest.py#L153), [`pyproject.toml`](pyproject.toml#L1).

The test calls the actual mounted ASGI application via TestClient, without network
connections: HTTP happy path, solved refusal, save failure/retry/replacement, invalid
inputs, artifact roundtrip, lesson progression, snapshot reload, plus initialization,
discovery and all ten tools through MCP JSON-RPC. It checks that HTTP changes are visible
via MCP and vice versa. Source: [`exercise`](selftest.py#L22).

Two implementation mishaps explain the checks: the SDK's Host allowlist rejected a
test URL without a port, and a bare `dict` return annotation produced text-only MCP
results. Explicit localhost allowlisting and `dict[str, Any]` return annotations fixed
those paths; initialization and `structuredContent` checks now make both failures
observable. See [`create_mcp`](mcp_server.py#L26) and the MCP section of
[`selftest.py`](selftest.py#L90). The test verdict, rather than this narrative, is the
delivery instrument.

## Hosting on libraxis-vm is a separate action

This cut supplies an ASGI application; it does not deploy it. The Agent-Operator prepares
the host admission, and the Founder retains the deployment button. Use the same launch
command behind the host's TLS reverse proxy, with one worker. For a public hostname,
set `MOCK_ALLOWED_HOSTS=mock.example.test` (include `:port` when using a nonstandard port).
If a client sends an Origin header, explicitly allow it with
`MOCK_ALLOWED_ORIGINS=https://mock.example.test`. Both variables accept comma-separated
values and extend the SDK's localhost allowlists without disabling its DNS-rebinding
protection. Source: [`mcp_server.py`](mcp_server.py#L26).

There is no authentication or tenant boundary. A shared demonstration instance is resettable
practice state, and inputs may be read by other participants. The synthetic guarantee
covers the shipped fixture and server-authored replies; the API stores caller-supplied
briefs, debriefs and artifacts as text. Use invented inputs and keep snapshots outside
the public checkout. Nothing reads course fixtures, credentials, or other repository
directories: the only content file opened is [`fixtures_mock.json`](app.py#L84), with
an optional explicitly configured progress snapshot. Production auth, multi-tenancy,
upstream fidelity, and deployment remain outside this cut.

## Course enrollment gate

Two editorial levels share one enrollment gate for humans and agents. `/journal/`
and public summaries tell a self-contained story without course internals.
English is canonical at unprefixed public routes; Polish public pages use `/pl/`.
`/members/journal/` holds the English detailed record and `/members/pl/journal/`
its Polish counterpart. Both remain under the protected `/members/*` tree, never
`/pl/members/*`. Full course entries retain their language-independent routes
`/challenge/s01e0[1-3]/entry/`. Both private trees stay outside this repository.
Gate pages are `/gate/` and `/pl/gate/`, but all OAuth/API endpoints remain
unprefixed `/gate/*`. The unchanged production OAuth allowlist returns member logins
to `/members/journal/`. Shared scripts keep a validated, same-origin member language
and story intent in session storage, then clear it on one authenticated resume.
No backend restart or Caddy routing change is needed. Without JavaScript or session
storage, Polish login can land at the English member archive; its language switch
still opens the Polish archive. Original protected course return routes are unchanged.
The gate uses fresh OAuth PKCE, not an operator-configured answer.
Visitors can ask their agent to read `/gate/handshake`, explain the permission,
and drive the returned login URL in the browser they want to use. The human
completes course sign-in and consent. A normal browser may do the same: this
is agent-friendly, not agent-exclusive.

The backend exchanges a single-use authorization code, verifies a read-only
`list-challenges` call through the official MCP, attempts to revoke fresh credentials
and discards them. Revocation is best-effort if the course is unavailable; the site
never persists the tokens and never reads the visitor's existing harness credentials.
This briefly gives the backend access to a new course token; it is **not**
a course-signed attestation. Course terms and redistribution permissions still apply.

| Endpoint | Contract |
|---|---|
| `GET /gate/handshake?next=...` | No-store agent instructions, readiness and same-origin login URL. |
| `GET /gate/login?next=...` | Browser-bound expiring state and S256 challenge; redirect to official consent. |
| `GET /gate/callback` | Consume state once, exchange code, verify official MCP, discard credentials, issue cookie. |
| `GET /gate/check` | 200 for a valid site cookie, otherwise 401 or 503 if unconfigured. |

Configuration: `GATE_SECRET` (at least 16 characters), `GATE_OAUTH_CLIENT_ID`,
`GATE_OAUTH_REDIRECT_URI` (the registered callback), `GATE_COOKIE_SECURE` (default1;
set0 only for loopback HTTP). The official issuer/endpoints are fixed, not supplied
by a visitor. Run one worker: pending handshake state lives in memory and expires.
Restarting drops unfinished logins. Changing the signing key revokes site cookies.

### Local acceptance preview

`server/preview.py` serves the integrated public docs with private entry files from
an explicitly supplied external directory. Its public source baseline was captured
read-only from `/srv/megadev-landing` and `/home/libraxis/megadev-mock/server` on
libraxis-vm, not reconstructed from an older git revision.

```sh
GATE_SECRET=<local-random-key> \
GATE_OAUTH_CLIENT_ID=<registered-public-client-id> \
GATE_OAUTH_REDIRECT_URI=http://127.0.0.1:18745/gate/callback \
GATE_COOKIE_SECURE=0 \
MEGADEV_PRIVATE_ROOT=<external-copy-of-megadev-gated> \
uv run --project server uvicorn server.preview:create_preview --factory \
  --host 127.0.0.1 --port 18745 --no-access-log
```

Do not enable callback query logging: authorization codes must not enter access
logs. Keep raw course files outside `docs/` and outside the public repository.
The local OAuth client is not a production registration. Deploying requires a
separately approved production client/callback and an explicit deployment action.

### Production routing

`deploy/caddy-gate.snippet` is a proposal only. Proxy the new handshake/login/callback
and check endpoints, preserve the protected private-root forward_auth boundary,
and redact OAuth callback query strings in access logs. No command here changes
Caddy or the running VM. Existing production remains on its deployed version
until the operator accepts and deploys the candidate.

### Verification

`python3 server/selftest.py` exercises synthetic course behavior plus gate
security boundaries. Actual OAuth success additionally needs a human-approved
official sign-in; controlled upstream tests are not proof of real enrollment.
Inspect local navigation, public pages, anonymous private-entry redirects and
the real official consent redirect before accepting the preview.
