# One frozen input, one evolving story

A drop separates what the course supplied from what we actually did. The input
stays frozen; the story earns its claims through evidence. This convention
implements `frontier-megadev-261028`, W1-3 brief §§2–6, on baseline
`47149d7410f4d1654fba4776c39eebcdb64d2a5f` (the original stub was introduced in
`d3a7388b742e588af6a25bd43a0706e8d95e6871`). The executable contract lives in
[`tools/daily_drop.py:111`](../tools/daily_drop.py#L111): `main` owns file protection;
[`render:41`](../tools/daily_drop.py#L41) owns the six-section skeleton.

Each `drops/YYYY-MM-DD/` contains:

| File | Responsibility | How it changes |
| --- | --- | --- |
| `package.json` | Operator-frozen source, copied byte for byte | Freeze once; a later refresh needs a deliberate decision and a recorded reason. |
| `story.md` | English account of the work, initially a skeleton | Edit in place: lesson → challenges → owners/evidence → constructive mishaps → scaffold seed. |

## The morning command

The Operator obtains and freezes the day package separately. Workers and this
tool never call the course API. With Python 3.11+ installed, run from the repo root:

```bash
python3 tools/daily_drop.py \
  --package /path/to/frozen/package-2026-10-28.json \
  --out drops/2026-10-28
```

The input may already be `drops/2026-10-28/package.json`; an identical existing
copy is retained. The tool uses only Python's standard library and performs local
file reads/writes. The heading date comes from `date`, then `frozen_at` (first ten
characters, ISO date); without either, it uses an ISO output-folder date, then the
local current date. Use the package date for the folder name. Missing optional
sections produce placeholders; malformed JSON, object/array shapes or dates
produce a nonzero exit with a diagnostic.

An existing `story.md` stops the command **before either output is changed**.
A different existing package also stops it. This protects yesterday's writing
from today's automation. `--force` deliberately replaces the story and a different
package copy: review or save the current edits first. Output-file symlinks are
refused. A file-system write failure can leave a partial drop; an intact identical
package can be reused on retry. A successful exit means files were written;
it does not mean a challenge was solved or the story was verified.

## Turn the skeleton into a record someone can trust

`human_steps` on today's or previously open challenges become individual
`[HUMAN]` rows. The other generated tasks are `[AGENT]` rows. Assign the role
placeholders to actual owners, retain the `package.json#/...` input pointers,
and add outcome evidence: source SHA, reproducible command, observed result, and
the verifier responsible for the verdict. A package's `solved` flag is labelled
as a package report, never a fresh local verification. If no human steps were
supplied, the matrix creates no fictional human task.

The mishaps section starts empty on purpose. When something breaks, tell the
reader what happened, which evidence ruled out a tempting explanation, what it
taught, and what changed. Do not turn an unrun probe into a green receipt.
The scaffold seed is a bullet list for a later `vc-scaffold` run; it does not
dispatch work, authorize submissions, or schedule anything.

## No-spoilers fence

Full challenge content and accepted answers never belong under `docs/` or
`server/`. `package.json` is a working input, not a public page. The generator
renders selected lesson/challenge metadata and human steps; it omits challenge
descriptions, answers, and arbitrary extra fields. Human steps can themselves
contain sensitive content, so review the entire story before publishing excerpts.
Never point `--out` at a public-serving directory or copy the raw package there.

## Let a verifier own the verdict

On the exact candidate commit, outside a structural compile embargo, generate
into a fresh temporary directory. Compare the package bytes, inspect all six
headers and task rows, edit the story, and rerun: refusal must leave **both** files
unchanged. Exercise `--force`, a minimal `{}` package, and invalid input too.
The dispatch plan's W1-3 `today=drop-ok` probe is the machine acceptance command;
first run it against the baseline stub and confirm `today=drop-missing`, exit 1,
so the instrument has demonstrated it can reject a missing implementation.
Only recorded execution can supply those verdicts. During W1/W2 structural
embargo, hand off the checkpoint and these obligations to the integrator.
