# Security policy

## Scope

In scope:

- `server/` — the synthetic practice course (FastAPI + MCP), deployed at
  `megadev.div0.space` behind a bearer gate.
- `tools/` — the static publisher and cached Art API/OG builders.
- `docs/` — the static site served at `megadev.div0.space`.

Out of scope: the MEGA.dev course itself (report to the course, not here),
`hq.mega.dev`, and private course inputs, logs or accepted answers. Those materials
do not belong in this public repository.

## Reporting a vulnerability

Email **void@div0.space** with the usual: what you found, where, how to
reproduce it, and what an attacker gains. A human reads it. You get a first
reply within **72 hours** and an honest status, not a form letter.

Please do not open a public issue for an unpatched vulnerability and do not
test against the live `megadev.div0.space` instance beyond what proves the
finding — it is a shared, resettable practice box, and other people's practice
state lives there.

## What to expect

- No bug bounty; this is a public learning repo. Credit in the journal, if you
  want it, is real and public.
- The mock server deliberately has **no authentication or tenant boundary in
  its code** — the bearer gate lives in the reverse proxy. Reports that
  restate this are known behavior, not findings.
- Secrets never belong in the repo (`.env*` is ignored by policy). If you find
  one anyway, that IS a finding — report it.

—

𝚅𝚒𝚋𝚎𝚌𝚛𝚊𝚏𝚝𝚎𝚍. with AI Agents by Vetcoders (c)2024-2026 LibraxisAI
