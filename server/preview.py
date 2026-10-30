"""Local acceptance surface: deployed public layout, real gate, external private root.

Run with --no-access-log: OAuth callback codes must not enter request logs.
No production credentials or course files belong in this module or in docs/.
"""

import os
from pathlib import Path
import re
from urllib.parse import quote

from fastapi import Request
from fastapi.responses import FileResponse, RedirectResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from server.app import create_app
from server.gate import COOKIE, Gate

ROOT = Path(__file__).resolve().parent.parent


class MemberFiles(StaticFiles):
    """No private bytes, including detailed histories, before enrollment verification."""

    def __init__(self, directory: Path, gate: Gate):
        super().__init__(directory=directory, html=True)
        self.gate = gate

    async def get_response(self, path, scope):
        request = Request(scope)
        if not self.gate.valid(request.cookies.get(COOKIE)):
            target = quote(request.url.path, safe="/")
            gate_path = "/pl/gate/" if request.url.path.startswith("/members/pl/") else "/gate/"
            return RedirectResponse(f"{gate_path}?next={target}", status_code=302,
                                    headers={"Cache-Control": "no-store"})
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response


class CourseEntries(StaticFiles):
    """Public teasers and separately rooted, protected course entries."""

    def __init__(self, public: Path, private: Path, gate: Gate):
        super().__init__(directory=public, html=True)
        self.protected = MemberFiles(private, gate)

    async def get_response(self, path, scope):
        if re.match(r"^s01e0[1-3]/entry(?:/|$)", path, flags=re.IGNORECASE):
            return await self.protected.get_response(path, scope)
        return await super().get_response(path, scope)


def create_preview():
    """Use the actual application lifespan and routes, not a second mock backend."""
    docs = ROOT / "docs"
    configured_root = os.environ.get("MEGADEV_PRIVATE_ROOT")
    if not configured_root:
        raise RuntimeError("MEGADEV_PRIVATE_ROOT must name the external protected root")
    private = Path(configured_root).resolve()
    if private == docs.resolve() or docs.resolve() in private.parents:
        raise RuntimeError("Protected course files must stay outside docs/")
    gate = Gate.from_env()
    app = create_app(gate=gate)

    async def home(request):
        return FileResponse(docs / "index.html")

    async def agent_map(request):
        return FileResponse(docs / "llms.txt", media_type="text/plain")

    # Dynamic /gate endpoints and /api already precede these routes. Keep the
    # original mounted MCP application last, including its own /mcp endpoint.
    surfaces = [
        Route("/", home), Route("/index.html", home), Route("/llms.txt", agent_map),
        Mount("/assets", StaticFiles(directory=docs / "assets")),
        Mount("/journal", StaticFiles(directory=docs / "journal", html=True)),
        Mount("/making-of", StaticFiles(directory=docs / "making-of", html=True)),
        Mount("/pl", StaticFiles(directory=docs / "pl", html=True)),
        Mount("/members", MemberFiles(private / "members", gate)),
        Mount("/challenge", CourseEntries(docs / "challenge", private / "challenge", gate)),
        Mount("/gate", StaticFiles(directory=docs / "gate", html=True)),
    ]
    app.router.routes[-1:-1] = surfaces
    return app
