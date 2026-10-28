# 2026-10-28 — The night we named our homework

At 3 a.m. Maciej named the debt: we had not done our homework. The course snapshot put a number on it: three challenges open, none solved. A brief is a starting line, not a finish. [Entry #1 at `edf613b`, lines 49–60](../../docs/journal/index.html#entry-1); [frozen package](package.json), `/challenge_of_the_day/solved` and `/previously_open/*/solved`.

## The lesson

Lesson s01e03, **Building Knowledge Systems**, opened today. Its practical claim: shape an environment where agents can build and maintain the knowledge base. Retrieval needs relevance, context needs provenance and freshness, and the work needs an inbox and a way to update itself. Our matrix and journal are one small application of that lesson, not proof that the whole system works. The daily brief was saved to the dashboard after one retry. [Package](package.json), `/lesson`; [`MATRIX.md` at `1f2cfed`, lines 17–20](../../MATRIX.md).

## Challenges on the table

The frozen snapshot says all three are unsolved. The briefs are ready; their dispatch is still waiting for Maciej in the working record. No result is implied by a prepared brief. [Package](package.json), `/challenge_of_the_day`, `/previously_open`; [`MATRIX.md` at `1f2cfed`, lines 21–25](../../MATRIX.md).

| Challenge | Status at snapshot | Working brief |
| --- | --- | --- |
| S01E01 · somebody slow | Open, unsolved | [S01E01](../../challenges/S01E01/brief.md) |
| S01E02 · who said what | Open, unsolved | [S01E02](../../challenges/S01E02/brief.md) |
| S01E03 · what it shows | Open, unsolved | [S01E03](../../challenges/S01E03/brief.md) |

The assessment is also untaken; the two offline benchmarks wait for their respective solves. Earlier lesson brief statuses are unknown, not failures. [`MATRIX.md` at `1f2cfed`, lines 17–25](../../MATRIX.md); [package](package.json), `/assessment`.

## Who does what

Maciej decided on one `gpt-6.1-sol` worker per challenge on the omp harness, with dispatch by Maciej personally. These are assignments and stop points, not claims that workers ran. [`MATRIX.md` at `1f2cfed`, lines 21–43](../../MATRIX.md); the three linked briefs above.

| Task | Owner | Boundary or evidence |
| --- | --- | --- |
| [HUMAN] Dispatch the three workers | Maciej | The briefs are ready; the matrix records dispatch as pending. |
| [HUMAN] Supply course access and decisions | Maciej | S01E01 access and changes after submission, S01E02 fresh session, S01E03 public-repository choice: see the respective briefs. |
| [AGENT] Lesson brief | Klaudiusz | Saved; dashboard receipt is reported in the package and matrix. |
| [AGENT] S01E01 | omp / gpt-6.1-sol | Work within its challenge directory; keep a log, debrief and spoiler-free entry. |
| [AGENT] S01E02 | omp / gpt-6.1-sol | Keep evidence with locations; pause for the fresh session. |
| [AGENT] S01E03 | omp / gpt-6.1-sol | Work from evidence; pause for Maciej's repository choice. |
| [AGENT] Frontier rebuild and this drop | Codex and the plan's workers | The plan separates shell, daily-drop tooling and story; admission and publication remain separate decisions. |

## Mishaps & lessons

Entry #1 already records the failed save, the duplicate dispatch after a fork, and the earlier benchmark without a comparative report. We keep those accounts there rather than retelling them as new incidents. [Entry #1 at `edf613b`, lines 61–72](../../docs/journal/index.html#entry-1).

- The save needed a second attempt. **Lesson:** record the retry and its outcome; an error response is not a saved brief.
- The fork exposed ambiguous ownership. **Lesson:** divide work before dispatch and identify runs so duplicates can be caught.
- The earlier matrix exposed a missing synthesis. **Lesson:** a completed set of cells still needs a comparative report before it can support a verdict.

## Scaffold seed

We turned the day into a frontier rebuild: a shared visual shell, a repeatable offline drop, and this narrative, with a synthetic course mock on a separate track. The plan's dependency order puts the shell and drop tool before this story; it does not turn a local cut into a public release. Plan `frontier-megadev-261028`, local `DRIVER.md` sections 1–2; source baseline `1f2cfed96899899737eaf74a27b6183929fe8095`. The plan itself is a local artifact, not evidence of a deployed site.

To reproduce the skeleton from the frozen input in a fresh checkout, run `python3 tools/daily_drop.py --package <frozen-package.json> --out <new-drop-directory>`. It copies the input and writes a draft; it does not verify the story. Keep full challenge material and accepted answers out of public `docs/` and `server/`. Each live worker must leave a log, debrief and spoiler-free journal entry; only a course-confirmed claim/debrief can move a challenge to solved. [`tools/daily_drop.py` at `1f2cfed`, lines 111–156](../../tools/daily_drop.py); [`MATRIX.md` at `1f2cfed`, lines 27–36](../../MATRIX.md).

Next: Maciej dispatches when ready. We do not yet have the three runs, their outcomes, or a public release. The snapshot is dated 2026-10-28; it is not a live course query.
