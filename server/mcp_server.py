"""Official MCP SDK adapter; all mutations go through the shared course store."""

import os
from typing import TYPE_CHECKING, Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import CallToolResult, TextContent

if TYPE_CHECKING:
    from server.app import CourseStore


def create_mcp(store: "CourseStore") -> FastMCP:
    from server.app import CourseError

    def invoke(name, arguments):
        try:
            return store.call(name, arguments)
        except CourseError as error:
            return CallToolResult(
                isError=True, structuredContent=error.envelope,
                content=[TextContent(type="text", text=error.envelope["instruction"])],
            )

    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=["localhost", "localhost:*", "127.0.0.1", "127.0.0.1:*", "[::1]", "[::1]:*"],
        allowed_origins=["http://localhost:*", "http://127.0.0.1:*", "http://[::1]:*"],
    )
    for variable, destination in (("MOCK_ALLOWED_HOSTS", security.allowed_hosts),
                                  ("MOCK_ALLOWED_ORIGINS", security.allowed_origins)):
        destination.extend(item.strip() for item in os.environ.get(variable, "").split(",") if item.strip())
    mcp = FastMCP("MOCK-Course", stateless_http=True, json_response=True,
                  transport_security=security,
                  instructions="MOCK-Synthetic practice only; no connection to the real course.")

    # Argument names, required sets and key constraints mirror the official
    # course MCP 1:1 (verified against its tool schemas, 2026-10-28).
    from server.app import UUID_PATTERN
    from pydantic import Field
    from typing import Annotated

    Uuid = Annotated[str, Field(pattern=UUID_PATTERN,
                                description="MOCK-The challenge uuid (from list-challenges).")]

    @mcp.tool(name="mega-start")
    def mega_start() -> dict[str, Any]:
        """MOCK-Start the practice day: lesson, challenge, progress, brief instruction."""
        return invoke("mega-start", {})

    @mcp.tool(name="list-challenges")
    def list_challenges() -> dict[str, Any]:
        """MOCK-List both synthetic challenges with uuid, title, start point and solved flag."""
        return invoke("list-challenges", {})

    @mcp.tool(name="start-challenge")
    def start_challenge(uuid: Uuid) -> dict[str, Any]:
        """MOCK-Start a challenge by its uuid; the reply hands you its receipts."""
        return invoke("start-challenge", {"uuid": uuid})

    @mcp.tool(name="resume-challenge")
    def resume_challenge(uuid: Uuid, receipts: dict[str, str]) -> dict[str, Any]:
        """MOCK-Pick a started challenge back up with the receipts you were handed, whole and unchanged."""
        return invoke("resume-challenge", {"uuid": uuid, "receipts": receipts})

    @mcp.tool(name="claim-challenge")
    def claim_challenge(uuid: Uuid, receipts: dict[str, str],
                        answer: dict[str, Any]) -> dict[str, Any]:
        """MOCK-Send your answer object with the receipts; any nonempty answer is accepted here."""
        return invoke("claim-challenge", {"uuid": uuid, "receipts": receipts, "answer": answer})

    @mcp.tool(name="save-brief")
    def save_brief(lesson: str, brief: str) -> dict[str, Any]:
        """MOCK-Save the daily brief for a lesson id; saving again replaces it."""
        return invoke("save-brief", {"lesson": lesson, "brief": brief})

    @mcp.tool(name="debrief")
    def debrief(uuid: Uuid, snags: list[dict[str, Any]],
                story: str | None = None, takeaway: str | None = None,
                catches: list[dict[str, Any]] | None = None,
                extras: list[dict[str, Any]] | None = None,
                toolbox: list[dict[str, Any]] | None = None,
                smooth: list[dict[str, Any]] | None = None,
                rightCall: dict[str, Any] | None = None,
                model: str | None = None) -> dict[str, Any]:
        """MOCK-Save the debrief of a solve: the challenge uuid and your snags, plus the optional fields."""
        return invoke("debrief", {key: value for key, value in {
            "uuid": uuid, "snags": snags, "story": story, "takeaway": takeaway,
            "catches": catches, "extras": extras, "toolbox": toolbox,
            "smooth": smooth, "rightCall": rightCall, "model": model,
        }.items() if value is not None})

    @mcp.tool(name="check-lane")
    def check_lane(need: str, probe: dict[str, Any] | None = None,
                   proof: dict[str, Any] | None = None) -> dict[str, Any]:
        """MOCK-Name a need to check what your practice lane can do; direction only."""
        arguments: dict[str, Any] = {"need": need}
        if probe is not None:
            arguments["probe"] = probe
        if proof is not None:
            arguments["proof"] = proof
        return invoke("check-lane", arguments)

    @mcp.tool(name="artifact")
    def artifact(uuid: Uuid,
                 answer: Annotated[str, Field(pattern=r"^(y|n|install)$")] | None = None
                 ) -> dict[str, Any]:
        """MOCK-Answer an artifact offer; artifacts are paused here, so no files come back."""
        arguments: dict[str, Any] = {"uuid": uuid}
        if answer is not None:
            arguments["answer"] = answer
        return invoke("artifact", arguments)

    @mcp.tool(name="rook")
    def rook(input: Annotated[str, Field(max_length=4000)]) -> dict[str, Any]:
        """MOCK-Pass one line from your human to the cardboard rook and read his answer."""
        return invoke("rook", {"input": input})

    return mcp
