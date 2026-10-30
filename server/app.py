"""Synthetic course state shared by HTTP and MCP; never contacts an upstream."""

from contextlib import asynccontextmanager
from copy import deepcopy
import json
import os
from pathlib import Path
from threading import RLock
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import Body, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

if TYPE_CHECKING:
    from server.gate import Gate

Text = Annotated[str, Field(strict=True, min_length=1, max_length=20000, pattern=r"\S")]
# Argument names and required sets mirror the official course MCP 1:1
# (verified against its tool schemas, 2026-10-28). The official uuid pattern,
# verbatim, including its two sentinel values:
UUID_PATTERN = (
    r"^([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}"
    r"-[0-9a-fA-F]{12}|00000000-0000-0000-0000-000000000000"
    r"|ffffffff-ffff-ffff-ffff-ffffffffffff)$"
)
Uuid = Annotated[str, Field(strict=True, pattern=UUID_PATTERN)]


class Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Challenge(Arguments):
    uuid: Uuid


class Resume(Challenge):
    receipts: dict[str, str]


class Claim(Resume):
    answer: dict[str, Any]


class Brief(Arguments):
    lesson: Text
    brief: Text


class Snag(BaseModel):
    # Nested shapes accept every payload the official schema allows; only the
    # official required trio is enforced, so an agent built against the real
    # course never gets refused here for a field the mock does not know.
    model_config = ConfigDict(extra="allow")
    snag: Annotated[str, Field(min_length=1, max_length=160)]
    resolve: Annotated[str, Field(min_length=1, max_length=160)]
    by: Annotated[str, Field(pattern=r"^(harness|human|pair)$")]


class Debrief(Arguments):
    uuid: Uuid
    snags: list[Snag]
    story: Text | None = None
    takeaway: Text | None = None
    catches: list[dict[str, Any]] | None = None
    extras: list[dict[str, Any]] | None = None
    toolbox: list[dict[str, Any]] | None = None
    smooth: list[dict[str, Any]] | None = None
    rightCall: dict[str, Any] | None = None
    model: Text | None = None


class Artifact(Challenge):
    answer: Annotated[str, Field(pattern=r"^(y|n|install)$")] | None = None


class Lane(Arguments):
    need: Text
    probe: dict[str, Any] | None = None
    proof: dict[str, Any] | None = None


class Rook(Arguments):
    input: Annotated[str, Field(strict=True, min_length=1, max_length=4000, pattern=r"\S")]


TOOL_MODELS = {
    "mega-start": Arguments,
    "list-challenges": Arguments,
    "start-challenge": Challenge,
    "resume-challenge": Resume,
    "claim-challenge": Claim,
    "save-brief": Brief,
    "debrief": Debrief,
    "check-lane": Lane,
    "artifact": Artifact,
    "rook": Rook,
}


class CourseError(Exception):
    def __init__(self, status: int, code: str, instruction: str):
        self.status = status
        self.envelope = {"instruction": instruction, "error": code}
        super().__init__(instruction)


class Progress(BaseModel):
    model_config = ConfigDict(extra="forbid")
    started: set[str] = Field(default_factory=set)
    solved: set[str] = Field(default_factory=set)
    briefs: dict[str, str] = Field(default_factory=dict)
    debriefs: dict[str, str] = Field(default_factory=dict)
    artifacts: dict[str, str] = Field(default_factory=dict)
    save_calls: int = Field(default=0, ge=0)


class CourseStore:
    def __init__(self, *, fail_every: int = 0, snapshot: Path | None = None):
        if fail_every < 0 or fail_every == 1:
            raise ValueError("MOCK_SAVE_BRIEF_FAIL_EVERY must be 0 or >=2")
        self.fixture = json.loads(Path(__file__).with_name("fixtures_mock.json").read_text())
        self.lessons = {row["id"]: row for row in self.fixture["lessons"]}
        self.challenges = {row["uuid"]: row for row in self.fixture["challenges"]}
        self.fail_every = fail_every
        self.snapshot = snapshot
        self.lock = RLock()
        self.progress = Progress()
        if snapshot and snapshot.exists():
            self.progress = Progress.model_validate_json(snapshot.read_text())
            p = self.progress
            if (not (p.started | p.solved | p.artifacts.keys() | p.debriefs.keys())
                    <= self.challenges.keys()
                    or not p.briefs.keys() <= self.lessons.keys()
                    or not p.solved <= p.started):
                raise ValueError("Snapshot refers to unknown or unstarted MOCK content")

    def _persist(self):
        if self.snapshot:
            self.snapshot.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.snapshot.with_suffix(self.snapshot.suffix + ".tmp")
            temporary.write_text(self.progress.model_dump_json(indent=2) + "\n")
            temporary.replace(self.snapshot)

    def _challenge(self, challenge_id):
        if challenge_id not in self.challenges:
            raise CourseError(404, "mock-challenge-missing", "MOCK-Choose a listed challenge UUID.")
        row = deepcopy(self.challenges[challenge_id])
        row["solved"] = challenge_id in self.progress.solved
        return row

    def _lesson(self, lesson_id):
        if lesson_id not in self.lessons:
            raise CourseError(404, "mock-lesson-missing", "MOCK-Choose MOCK-L01 or MOCK-L02.")
        return deepcopy(self.lessons[lesson_id])

    def call(self, name: str, arguments: dict[str, Any]):
        if name not in TOOL_MODELS:
            raise CourseError(404, "mock-tool-missing", "MOCK-Choose a tool from /api/tools.")
        try:
            data = TOOL_MODELS[name].model_validate(arguments).model_dump()
        except ValidationError as error:
            raise CourseError(422, "mock-invalid-arguments", "MOCK-Use the documented argument schema.") from error
        with self.lock:
            before = self.progress.model_copy(deep=True)
            try:
                result = self._execute(name, data)
            except CourseError:
                # An injected failure consumes its call number, but never saves the brief.
                try:
                    if self.progress != before:
                        self._persist()
                except OSError:
                    self.progress = before
                    raise
                raise
            try:
                if self.progress != before:
                    self._persist()
            except OSError:
                self.progress = before
                raise
            return result

    def _receipts(self, uuid):
        # Deterministic per challenge, so a new session can be handed the same
        # receipts the start reply issued; the official course requires them
        # back whole and unchanged on resume and claim.
        return {"mock-receipt": f"MOCK-receipt-{uuid[:13]}"}

    def _execute(self, name, data):
        p = self.progress
        result = {"instruction": "MOCK-Present this as synthetic practice; never as real course progress."}
        if name == "mega-start":
            lesson_id = next(
                (key for key, row in self.lessons.items() if row["challenge"] not in p.solved),
                next(reversed(self.lessons)),
            )
            lesson = self._lesson(lesson_id)
            result.update(lesson=lesson, challenge=self._challenge(lesson["challenge"]),
                          previously=sorted(p.solved), rook=self.fixture["rook"],
                          brief=p.briefs.get(lesson_id), briefInstruction="MOCK-Save a short invented practice brief.")
        elif name == "list-challenges":
            result["challenges"] = [self._challenge(key) for key in self.challenges]
        elif name in {"start-challenge", "resume-challenge", "claim-challenge"}:
            key = data["uuid"]
            self._challenge(key)
            if name == "start-challenge":
                if key in p.solved:
                    raise CourseError(409, "mock-already-solved", "MOCK-This challenge is already solved.")
                p.started.add(key)
            else:
                if key not in p.started:
                    raise CourseError(409, "mock-not-started", "MOCK-Start this challenge first.")
                if data["receipts"] != self._receipts(key):
                    raise CourseError(409, "mock-wrong-receipts",
                                      "MOCK-Send the receipts start-challenge handed you, whole and unchanged.")
            if name == "claim-challenge":
                if key in p.solved:
                    raise CourseError(409, "mock-already-solved", "MOCK-This challenge is already solved; do not claim again.")
                if not data["answer"]:
                    raise CourseError(422, "mock-empty-answer", "MOCK-Send a nonempty answer object.")
                p.solved.add(key)
                result["accepted"] = True
                result["instruction"] = "MOCK-Any nonempty answer is accepted. This is workflow practice, not grading."
                result["debriefInstruction"] = "MOCK-Call debrief with this uuid and your snags."
            result.update(challengeId=key, receipts=self._receipts(key),
                          challenge=self._challenge(key), rook=self.fixture["rook"])
        elif name == "save-brief":
            key = data["lesson"]
            self._lesson(key)
            p.save_calls += 1
            if self.fail_every and p.save_calls % self.fail_every == 0:
                raise CourseError(500, "mock-injected-failure", "MOCK-Retry save-brief with the same arguments.")
            p.briefs[key] = data["brief"]
            result.update(lesson=key, brief=p.briefs[key])
        elif name == "debrief":
            key = data["uuid"]
            self._challenge(key)
            if key not in p.solved:
                raise CourseError(409, "mock-not-solved", "MOCK-Solve this challenge before filing its debrief.")
            p.debriefs[key] = json.dumps({field: value for field, value in data.items() if value is not None})
            result.update(challengeId=key, debrief=json.loads(p.debriefs[key]))
        elif name == "check-lane":
            result.update(need=data["need"], started=sorted(p.started), solved=sorted(p.solved),
                          remaining=len(self.challenges) - len(p.solved),
                          route="MOCK-Practice the workflow here, then take the real lane.")
        elif name == "artifact":
            self._challenge(data["uuid"])
            result["instruction"] = ("MOCK-Artifacts are paused while the imaginary course fixes "
                                     "a security problem in them; no files come back.")
        elif name == "rook":
            result["rook"] = self.fixture["rook"]
        return result


def create_app(store: CourseStore | None = None, gate: "Gate | None" = None) -> FastAPI:
    from server.gate import Gate, create_gate_router
    from server.mcp_server import create_mcp

    gate = gate or Gate.from_env()

    if store is None:
        snapshot = os.environ.get("MOCK_SNAPSHOT")
        store = CourseStore(fail_every=int(os.environ.get("MOCK_SAVE_BRIEF_FAIL_EVERY", "0")),
                            snapshot=Path(snapshot) if snapshot else None)
    mcp = create_mcp(store)
    mcp_app = mcp.streamable_http_app()

    @asynccontextmanager
    async def lifespan(app):
        async with mcp.session_manager.run():
            yield

    app = FastAPI(title="MOCK-Course practice", lifespan=lifespan)
    app.state.course = store

    @app.exception_handler(CourseError)
    async def course_error(request: Request, error: CourseError):
        return JSONResponse(error.envelope, status_code=error.status)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, error: RequestValidationError):
        return JSONResponse({"instruction": "MOCK-Send a JSON object matching /api/tools.",
                             "error": "mock-invalid-request"}, status_code=422)

    @app.get("/health")
    def health():
        return {"status": "MOCK-ok", "synthetic": True}

    @app.get("/api/tools")
    def tools():
        return {"instruction": "MOCK-POST arguments to /api/{tool}.",
                "tools": {name: model.model_json_schema() for name, model in TOOL_MODELS.items()}}

    @app.post("/api/{tool}")
    def call_tool(tool: str, arguments: Annotated[dict[str, Any], Body()]):
        return store.call(tool, arguments)

    app.state.gate = gate
    app.include_router(create_gate_router(gate))
    app.mount("/", mcp_app)
    return app
