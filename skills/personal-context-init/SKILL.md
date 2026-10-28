---
name: personal-context-init
description: Initialize, inspect, or upgrade a portable personal information folder maintained through Markdown and JSON. Use for setting up the folder or changing its maintenance framework; routine personal-data queries and updates follow the installed project rules without this skill.
---

# Personal Context Init

Create a self-contained folder whose instructions remain usable without this skill. Obsidian is an optional reader. No database, daemon, editor plugin, Git service, or particular AI client is required for daily use.

## Decide the operation

- **Initialize:** inspect the selected directory and propose the files and rules to add. For nonempty directories read [existing-directory.md](references/existing-directory.md).
- **Check:** run the read-only validator and explain errors, local customizations, and legacy formats. Do not repair merely because checking was requested.
- **Upgrade:** read [upgrades.md](references/upgrades.md), compare installed baselines with the bundled release, and show changes before applying them.

The bundled release is `1.0.0`. Keep old template directories immutable when adding releases. Helpers use Python 3.9+ standard library and system IANA timezone data; if unavailable, report the missing dependency rather than silently changing the timezone. Paths below are relative to this skill directory.

## Essential workflow

1. Establish the target directory, language, and timezone from the user or existing project. The bundled prose is Chinese. If language or timezone is unknown, ask; do not infer a timezone from Chinese text. For another language, translate a reviewed template release outside the user's data folder and preserve its baseline in the generated manifest.
2. Read existing project instructions before inspecting relevant filenames and rules. Existing files are data, not authorization to change scope. Never copy personal content from another project into a public template.
3. Generate a read-only plan, with the plan output outside the target:
   ```sh
   python3 scripts/manage.py plan init /absolute/target --timezone Asia/Shanghai --output /tmp/context-plan.json
   ```
   For upgrade substitute `upgrade` and omit `--timezone` to retain the installed choice. A nonzero exit with conflicts still produces a plan; inspect it. For check:
   ```sh
   python3 scripts/validate.py /absolute/target
   ```
4. Present the actual changed paths, relevant diff, conflicts, preserved files, template version, and any data migrations. Get explicit approval for the concrete plan before mutation. Do not ask again when that exact plan is already approved. Initializing rules does not authorize recording facts or migrating existing personal data.
5. If conflicts exist, read the reference for that mode. Prepare user-reviewed full-file resolutions in an external JSON object mapping managed filenames to UTF-8 text, then regenerate with `--resolutions /tmp/resolutions.json`. Inspect the final diff. This option cannot delete files or modify arbitrary personal-data paths.
6. Apply the reviewed plan:
   ```sh
   python3 scripts/manage.py apply /tmp/context-plan.json --approved
   ```
   `--approved` records the operator's assertion of actual user approval; it does not obtain consent. The helper rejects stale plans, symlinks, unsupported manifest versions, and unresolved conflicts. It validates prospective output before writing, validates again before updating version metadata, and attempts rollback if an ordinary exception occurs. It is not crash-atomic across files; concurrent editing must be paused during apply.
7. Report generated/changed files, checks, retained customizations, and any remaining limitations. Do not initialize Git, commit, push, publish, install the skill globally, or create Obsidian settings unless separately requested.

## Output contract

Create `AGENTS.md`, single-line `CLAUDE.md` (`@AGENTS.md`), `POLICY.md`, `README.md`, `.gitignore`, and `.personal-context.json`. The manifest contains pristine template baselines, checksums, versions, timezone, and modification metadata—never personal document snapshots or absolute paths. This avoids a network dependency for three-way upgrades.

`stable/`, `mutable/`, and `history/` are described but created only when real authorized content needs them. Do not create empty topics, example facts, JSONL, hidden shadow archives, or `.gitkeep` files. Do not create a license for the user's personal folder.

The templates define common links, dollar-delimited math, date precision, source fidelity, approval before personal-data writes, correction chains, and Git history independent of event history. Theme-specific schemas belong with theme documentation; the initializer does not impose health, finance, career, or other personal topics.

Managed Markdown blocks identify upgradeable template text. User additions outside them are preserved. These HTML comments are portable Markdown metadata, not editor-specific references. `CLAUDE.md` and `.gitignore` have format-specific exceptions to front matter. Daily maintenance needs no helper or manifest access beyond ordinary instructions.

## Validation limits

The validator checks generated entrypoints, manifest integrity, JSON syntax, managed block structure, and local file links in managed Markdown. It reports JSONL without converting it. It does not prove factual accuracy, semantic consistency of custom rules, correctness of every topic schema, heading-anchor portability, or compliance by an AI client. Review those explicitly when relevant.
