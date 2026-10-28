# A practice course you can hand to a stranger

Two imaginary lessons, two imaginary challenges, one shared state machine. A cardboard
rook and a clockwork teacup let an agent rehearse the full course workflow without a
course account, credentials, or upstream requests. Every fixture title and body begins
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
