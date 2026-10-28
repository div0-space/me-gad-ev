# Contributing

This is a personal course log built in public — one student, one agent fleet.
It is not looking for features, but fixes are welcome: typos, broken links,
wrong facts, dead code, a failing selftest.

## Ground rules

1. **No course spoilers.** Nothing that reveals accepted answers, receipts,
   tickets or sign-in links — in code, docs, issues or PR descriptions. The
   journal documents the work, never the solution.
2. **Small, honest PRs.** One concern per PR, with a body that says what
   changed and why. "Fixed stuff" bodies are rejected by the hooks anyway.
3. **Verify before you claim.** If you touch `server/`, run the verifier:

   ```sh
   uv sync --project server && python3 server/selftest.py
   # expected: today=mock-ok, exit 0
   ```

   If you touch `docs/`, open the pages locally and click what you changed.

## Commit convention

- Title: `[<agent>/<workflow>] <description>` for agent commits — e.g.
  `[claude/vc-partner] fix(docs): dead link in journal`. Human commits may
  omit the bracket prefix.
- Body is required, never empty.
- Agents sign their own work: `Authored-By: <agent> <agents@vetcoders.io>`,
  one line per actual author. Signing another agent's work is not acceptable.

## Conduct and security

See [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) and [`SECURITY.md`](SECURITY.md).

—

𝚅𝚒𝚋𝚎𝚌𝚛𝚊𝚏𝚝𝚎𝚍. with AI Agents by Vetcoders (c)2024-2026 LibraxisAI
