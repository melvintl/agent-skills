# agent-skills

The skills I write or vendor by hand for my coding agents, in one place. Each
skill is symlinked into the skills directory of the agents it is for:
currently Claude Code and pi.

Skills that a tool installs and updates itself (Omarchy, hunk, workmux) are
not kept here.

## Setup

```sh
git clone git@github.com:melvintl/agent-skills.git
cd agent-skills
make link
```

`make link` is idempotent; run it again after `git pull`.

| Command | What it does |
| --- | --- |
| `make link` | Link skills into each agent's skills directory |
| `make link-dry-run` | Print what `link` would change, without writing |
| `make doctor` | Report link and dependency status |
| `make check` | Lint scripts, validate skills, run tests (what CI runs) |

## Layout

| Path | Contents |
| --- | --- |
| `skills/<name>/` | One skill per directory, each with a `SKILL.md` |
| `skills.conf` | Which agents a skill is for, when not all of them |
| `bin/link.sh` | The linker behind `make link`, `link-dry-run` and `doctor` |
| `bin/check.sh` | The checks behind `make check` |
| `tests/` | Tests for the linker |
| `UPSTREAM.md` | Where vendored skills came from, and local changes to them |

## Which agent gets which skill

A skill is linked to every agent unless `skills.conf` says otherwise:

```
browser-tools  pi
```

| Agent | Skills directory |
| --- | --- |
| Claude Code | `~/.claude/skills` |
| pi | `~/.pi/agent/skills` (honours `PI_CODING_AGENT_DIR` and `PI_AGENT_DIR`) |

To support another agent, add a line to `AGENT_DIRS` in `bin/link.sh`.

## What the linker will and will not touch

- It creates one symlink per skill per agent.
- It removes links that point into this repo but are no longer wanted: the
  skill was deleted, or `skills.conf` no longer includes that agent.
- It never changes anything else. If a file or a link to somewhere else is in
  the way, it reports it as `refused`, links the rest, and exits non-zero.
- If an agent's skills directory is itself a symlink to another directory, it
  replaces that symlink with a real directory and lists what the old directory
  held that it did not link back. The old directory is left untouched.
- For a skill with a `package.json` and no `node_modules`, it runs `npm ci`.
  Without `npm` it warns and carries on.

## Adding a skill

1. Create `skills/<name>/SKILL.md` with `name` (matching the directory) and
   `description` in its frontmatter.
2. If it is not for every agent, add a line to `skills.conf`.
3. If it is copied from another repo, record the source in `UPSTREAM.md`.
4. Run `make check` and `make link`.
