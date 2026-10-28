#!/usr/bin/env python3
"""Create an offline story skeleton from an Operator-frozen day package.

Contract: frontier-megadev-261028, W1-3 brief sections 2–6. Python 3.11+.
Only selected metadata is rendered; challenge descriptions stay in the copy.
"""

import argparse
import json
from datetime import date
from pathlib import Path


def cell(value):
    """Keep package text inside a single Markdown table cell or heading."""
    return (str(value).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace("|", "&#124;")
            .replace("`", "&#96;").replace("[", "&#91;")
            .replace("]", "&#93;").replace("*", "&#42;")
            .replace("_", "&#95;").replace("\\", "&#92;")
            .replace("#", "&#35;").replace("\r", " ").replace("\n", " "))


def record(package, key):
    value = package.get(key)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be an object")
    return value


def sequence(value, label):
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return value


def render(package, day):
    lesson = record(package, "lesson")
    assessment = record(package, "assessment")
    record(package, "local_state")
    challenges = []
    today = record(package, "challenge_of_the_day")
    if today:
        challenges.append((today, "/challenge_of_the_day"))
    for index, challenge in enumerate(sequence(package.get("previously_open"), "previously_open")):
        if not isinstance(challenge, dict):
            raise ValueError("previously_open entries must be objects")
        challenges.append((challenge, f"/previously_open/{index}"))

    lines = [
        f"# Drop {day}", "",
        "<!-- Generated skeleton, not a completion receipt. Edit this story in place.",
        "Source: ./package.json; evidence paths below are JSON pointers into that frozen input.",
        "Before publication, record the source/tool commit and verify every outcome. -->", "",
        "## The lesson", "",
        f"{cell(lesson.get('title') or 'TODO: name the lesson')} "
        f"({cell(lesson.get('id') or 'no lesson ID supplied')}).", "",
        "Source: `package.json#/lesson`. TODO: explain what changed in our practice.", "",
    ]
    for topic in sequence(lesson.get("topics"), "lesson.topics"):
        lines.append(f"- {cell(topic)}")
    lines.extend(["", "## Challenges on the table", "",
                  "Metadata only; consult the frozen package locally for the full briefs.", "",
                  "| Code | Title | Package reports solved | Source |",
                  "| --- | --- | --- | --- |"])
    tasks = [("[AGENT]", "Review the lesson and extract a practical takeaway", "/lesson")]
    for challenge, pointer in challenges:
        code = cell(challenge.get("code") or "Unspecified")
        title = cell(challenge.get("title") or "Untitled")
        solved = challenge.get("solved")
        state = "yes" if solved is True else "no" if solved is False else "unknown"
        lines.append(f"| {code} | {title} | {state} | `package.json#{pointer}` |")
        tasks.append(("[AGENT]", f"Prepare a work plan and evidence for {code}: {title}", pointer))
        for index, step in enumerate(sequence(challenge.get("human_steps"), f"{pointer}/human_steps")):
            if not isinstance(step, str):
                raise ValueError(f"{pointer}/human_steps entries must be strings")
            tasks.append(("[HUMAN]", f"{code}: {cell(step)}", f"{pointer}/human_steps/{index}"))
    if not challenges:
        lines.append("| — | No challenges supplied | unknown | `package.json` |")
    if assessment:
        tasks.append(("[AGENT]", "Prepare an assessment checklist; record the actual outcome separately", "/assessment"))
    tasks.append(("[AGENT]", "Develop this skeleton into an evidence-backed story and scaffold", ""))
    lines.extend(["", "## Who does what", "",
                  "Owners are roles to assign, not claims of authorization or completed work.", "",
                  "| Task | Owner | Evidence |", "| --- | --- | --- |"])
    for marker, task, pointer in tasks:
        owner = "Founder (assign)" if marker == "[HUMAN]" else "Agent (assign)"
        lines.append(f"| {marker} {task} | {owner} | Input: `package.json#{pointer}`; TODO: outcome receipt |")
    lines.extend([
        "", "## Mishaps & lessons", "",
        "<!-- Constructive mishaps are the product: record what broke, the evidence,",
        "what it taught, and the next change. Do not invent an incident or a successful fix. -->",
        "", "## Scaffold seed", "",
        f"- Date: {day}; frozen input: `package.json`.",
        "- Goal: turn the lesson and open challenges into bounded work with explicit evidence.",
        "- Inputs: package metadata above; inspect local_state.worker_briefs locally if supplied.",
        "- Tasks: use each matrix row as a candidate cut; preserve every [HUMAN] dependency.",
        "- API contact belongs to the Operator; workers consume this frozen package only.",
        "- Boundaries: no network calls in daily_drop; no challenge descriptions or accepted answers in docs/ or server/.",
        "- Acceptance: define a reproducible verifier per cut before dispatch; TODO: assign owners and dependencies.",
        "- Evidence: capture baseline SHA, terminal SHA, actual command outputs and remaining unknowns.",
        "",
    ])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=Path, help="Operator-frozen JSON input")
    parser.add_argument("--out", required=True, type=Path, help="drop directory, normally drops/YYYY-MM-DD")
    parser.add_argument("--force", action="store_true", help="replace the story and any different package copy")
    args = parser.parse_args()
    try:
        raw = args.package.read_bytes()
        package = json.loads(raw)
        if not isinstance(package, dict):
            raise ValueError("package must be a JSON object")
        # A frozen date wins over the wall clock, making historical reruns stable.
        stamp = package.get("date") or package.get("frozen_at")
        if stamp:
            day = date.fromisoformat(str(stamp)[:10]).isoformat()
        else:
            try:
                day = date.fromisoformat(args.out.name).isoformat()
            except ValueError:
                day = date.today().isoformat()
        story = render(package, day)
        story_path = args.out / "story.md"
        copy_path = args.out / "package.json"
        if story_path.resolve() == args.package.resolve():
            raise ValueError("the input package cannot also be the output story")
        for target in (story_path, copy_path):
            if target.is_symlink() or (target.exists() and not target.is_file()):
                raise ValueError(f"refusing non-regular output: {target}")
        if story_path.exists() and not args.force:
            raise ValueError(f"{story_path} already exists; use --force to replace the story")
        same_copy = copy_path.exists() and copy_path.read_bytes() == raw
        if copy_path.exists() and not same_copy and not args.force:
            raise ValueError(f"{copy_path} differs from input; use --force to replace the package")
        args.out.mkdir(parents=True, exist_ok=True)
        if not same_copy:
            with copy_path.open("wb" if args.force else "xb") as output:
                output.write(raw)
        with story_path.open("w" if args.force else "x", encoding="utf-8", newline="\n") as output:
            output.write(story)
    except (OSError, ValueError, UnicodeError) as error:
        parser.exit(1, f"daily_drop: {error}\n")
    print(f"Created {story_path} and {copy_path}")


if __name__ == "__main__":
    main()
