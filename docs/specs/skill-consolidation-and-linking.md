# Skill consolidation and linking

## Problem Statement

I work with several coding agents, mainly Claude Code and pi. My skills are scattered: four live in this repo and are linked only into Claude Code, three live inside my dotfiles repo under pi's config and reach pi through a whole-directory symlink, and one of those is also linked into Claude Code by the dotfiles setup script. Others are installed by tools (Omarchy, hunk, workmux) into the same directories.

This causes several problems:

- There is no single place to add, edit or review a skill.
- Pi does not see the skills in this repo at all.
- I cannot say "this skill is for pi only" without it being an accident of where the file lives.
- Because pi's skills directory is a symlink into dotfiles, any tool that installs a skill for pi writes into my public dotfiles repo, which then needs ignore rules to compensate.
- The whiteboard skill tells the agent to run its script from Claude Code's skills directory, so it only works in pi because the Claude Code link happens to exist.
- Setting up a new machine means remembering which repo links what.

## Solution

This repo becomes the single home for every skill I author or vendor by hand. Each skill is a directory in one flat collection. A small manifest records which agents a skill is for; a skill not mentioned goes to every agent.

One command links each skill into the skills directory of each agent it is meant for, as individual symlinks. The same command can preview what it would do, and a doctor mode reports what is wrong. It is safe to run repeatedly, never overwrites anything it did not create, and cleans up its own links when a skill is removed or its audience narrows.

Dotfiles stops owning skills. Its setup calls this repo's link command when the repo is present and otherwise carries on with a hint.

## User Stories

1. As a multi-agent user, I want every hand-maintained skill in one repo, so that I have one place to edit and review them.
2. As a multi-agent user, I want a skill linked into both Claude Code and pi by default, so that adding a shared skill needs no extra configuration.
3. As a multi-agent user, I want to mark a skill as being for specific agents only, so that pi-only tools like web search and browser automation do not clutter Claude Code, which has those built in.
4. As a multi-agent user, I want to change a skill's audience by editing one line, so that I do not have to move directories around.
5. As a pi user, I want the grilling, grill-me, wait-what and to-spec skills available in pi, so that I can use them outside Claude Code.
6. As a pi user, I want the whiteboard skill to work without depending on a Claude Code link, so that it behaves the same in either agent.
7. As a user, I want one command that creates all the right links, so that I do not hand-craft symlinks.
8. As a user, I want that command to be idempotent, so that I can run it after every pull without worrying.
9. As a user, I want a dry-run mode, so that I can see what would change before anything does.
10. As a user, I want the command to refuse to touch a file or link it did not create, so that tool-installed skills from Omarchy, hunk or workmux are never clobbered.
11. As a user, I want a clear report naming each refused target, so that I know what to resolve by hand.
12. As a user, I want links to skills I have deleted or narrowed to be removed automatically, so that agents do not keep seeing stale skills.
13. As a user, I want pruning limited to links that point into this repo, so that nothing else in an agent's skills directory is ever removed.
14. As a pi user, I want pi's skills directory to be a real directory of per-skill links, so that tools installing skills for pi no longer write into my dotfiles repo.
15. As a user migrating this machine, I want the first run to convert pi's existing whole-directory symlink into a real directory, so that I do not have to do it by hand.
16. As a user, I want skills with Node dependencies to have them installed when missing, so that a freshly linked skill works on first use.
17. As a user on a machine without npm, I want a warning rather than a failure, so that the rest of the linking still happens.
18. As a user, I want a doctor mode that shows each skill and agent pair as correct, missing or blocked, so that I can diagnose a skill that is not showing up.
19. As a user, I want doctor to flag missing Node dependencies, so that I know why a skill fails at runtime.
20. As a user, I want doctor to flag an unset Brave API key, so that I know why web search fails.
21. As a pi user, I want doctor to flag a skill name that appears in both of pi's global skill locations, so that I know pi is silently keeping only the first.
22. As a user with several machines and operating systems, I want the command to work wherever the repo is cloned, so that no path is tied to one machine.
23. As a user who may adopt another agent later, I want adding an agent to be a one-line change, so that the design does not need rework.
24. As a dotfiles user, I want dotfiles setup to run the skill linking when this repo is present, so that one setup command still configures the whole machine.
25. As someone using my public dotfiles without access to this private repo, I want setup to carry on with a hint, so that dotfiles stays usable alone.
26. As a dotfiles maintainer, I want dotfiles to hold no skills and no skill-specific setup or ignore rules, so that there is one source of truth.
27. As a maintainer, I want a check command that lints the link script, so that shell mistakes are caught before they run against my home directory.
28. As a maintainer, I want every skill validated for a name matching its directory and a non-empty description, so that a malformed skill is caught before an agent silently ignores it.
29. As a maintainer, I want the whiteboard security regression tests to move with the skill and keep running in CI, so that the move does not lose coverage.
30. As a maintainer, I want CI to run the same check on every PR, so that the branch-and-PR workflow has a gate.
31. As a maintainer of vendored skills, I want each one's source, commit and local changes recorded, so that I can diff against upstream later.
32. As a maintainer, I want the upstream licence notice kept with the vendored skills, so that making the repo public later needs no cleanup.
33. As a maintainer, I want skills of unknown origin recorded as such, so that provenance is never guessed.
34. As a user, I want secrets kept out of this repo, so that the API key lives only in my local shell environment.
35. As a user, I want the migration ordered so the skills exist in both repos until linking is verified, so that neither agent loses a skill mid-move.
36. As a user with uncommitted dotfiles work, I want the dotfiles change made in a fresh worktree, so that my in-progress changes are untouched.
37. As a repo owner, I want every change to arrive through a branch and a PR that I merge, so that nothing lands on a default branch unreviewed.
38. As a new reader of the repo, I want a README explaining the layout, the manifest and the commands, so that I can use it without reading the script.

## Implementation Decisions

**Scope of the collection**

- The repo holds only skills authored or vendored by hand: grilling, grill-me, wait-what, to-spec, whiteboard, brave-search, browser-tools.
- Skills owned by a tool (Omarchy's omarchy and diagnose-crash, hunk's hunk-review, anything workmux installs) are not copied in. They update with their tool.
- The three skills in dotfiles are moved by plain copy and delete. Their git history is not carried over.

**Layout and manifest**

- One flat collection directory, one subdirectory per skill. No per-agent subdirectories.
- A plain-text manifest lists exceptions only: one line per skill, the skill name followed by the agents it is for. A skill with no line is linked to every known agent. Comments and blank lines are allowed.
- Initial manifest content: brave-search and browser-tools are for pi only.
- The format is chosen so the link script can parse it in plain bash with no extra tools, and so vendored skill files are not edited to carry audience data.

**Agents**

- Agents are a small table of name to skills directory inside the link script. Initial entries: Claude Code at `~/.claude/skills`, pi at `~/.pi/agent/skills`.
- Pi's directory honours the same environment overrides the dotfiles pi setup already honours for pi's agent directory.
- The shared `~/.agents/skills` location is not a link target. It stays with Omarchy. Pi reads it as well as its own directory, which is why collisions are checked (see doctor).

**Link script**

- A single bash script with three modes: apply (default), dry-run, doctor. A Makefile fronts it with link, link-dry-run, doctor and check targets, matching the dotfiles conventions.
- The script locates the repo from its own path. Nothing is hardcoded to a user or machine.
- For each skill and each agent in its audience, it ensures a symlink from the agent's skills directory to the skill directory.
- A target that already exists and is not a link into this repo is foreign: the script leaves it alone, reports it, and exits non-zero after finishing the rest.
- Any link in an agent's skills directory that resolves into this repo but is not wanted (skill removed, or audience no longer includes that agent) is removed.
- If an agent's skills directory is itself a symlink to a directory, the script replaces it with a real directory before linking. This is the one-time conversion of pi's whole-directory link. Links found inside the old target that point outside this repo are reported so they can be recreated by hand; they are not migrated automatically.
- For a skill with a package manifest and no installed modules, the script runs a clean lockfile install. If npm is not available it warns and continues.
- Dry-run prints every action apply would take and changes nothing.

**Doctor**

- Per skill and agent: correct, missing, or blocked by a foreign target.
- Skills whose Node dependencies are not installed.
- Brave API key not set in the environment, when brave-search is linked for any agent.
- Any skill name present in both pi's own skills directory and the shared agents directory.
- Read-only, and exits non-zero when anything is wrong.

**Skill changes**

- The whiteboard skill's instructions refer to its script relative to the skill's own directory instead of naming Claude Code's skills directory.
- The upstream record gains the MIT notice for the Matt Pocock skills, and rows for brave-search and browser-tools marked source unknown.
- The Brave API key stays in the user's local shell environment file and is never stored here.

**Dotfiles changes**

- Remove the three skills, the whiteboard link entry in the main setup script, the skills entry from the pi setup's linked items, the whiteboard check target, and the ignore rules for workmux-installed pi skills.
- Main setup looks for this repo at a directory given by an environment variable, defaulting to a sibling of the dotfiles checkout. If found it runs the link script; if not it prints a one-line hint and continues. It never clones the repo.
- hunk-review for pi is relinked once by hand to hunk's latest install during migration. It is not managed by either repo.

**Process**

- The repo stays private.
- Every change goes through a branch and a PR that the owner merges. This applies to both repos.
- Order: build this repo and merge; run the link command on this machine and confirm with doctor; only then open the dotfiles PR from a fresh worktree off its default branch.

## Testing Decisions

- A good test here exercises the link script as a black box: given a collection of skills, a manifest and a home directory in some starting state, run the script and assert on the resulting filesystem, exit code and report. Tests do not reach into the script's functions or depend on its internal order of operations.
- There is one seam: the script's command line, run against a temporary home directory and a fixture skills collection. To make that possible the script takes the home directory from the environment and allows the repo root (the collection and its manifest) to be overridden; these are the only test affordances.
- Cases to cover through that seam: fresh home; second run is a no-op; pi-only skill absent from Claude Code; foreign file and foreign link are left intact and reported; stale link into the repo is pruned while unrelated links survive; whole-directory symlink is converted to a real directory; dry-run changes nothing; doctor reports each state and the pi name collision; missing npm warns without failing.
- Dependency installation is tested only for the decision to install or skip (a fake npm on the path), not by installing real packages.
- Skill validation (name matches directory, non-empty description) is a check over the real collection rather than a unit test.
- The whiteboard tests move unchanged and keep running as their own suite.
- Prior art: the whiteboard suite is stdlib Python unittest run through a Makefile target and CI; the link script tests follow the same style and drive the script by subprocess, so no new test dependency is added. The dotfiles check script is the model for shellcheck in the check target.
- CI runs the check target on every PR.

## Out of Scope

- Managing tool-owned skills, including linking hunk-review or Omarchy's skills for any agent.
- Supporting agents beyond Claude Code and pi.
- Project-level skills inside individual repositories.
- Preserving git history for the moved skills.
- Cloning this repo from dotfiles, or any bootstrap that needs credentials.
- Storing or provisioning the Brave API key.
- Automating upstream updates for vendored skills; diffing stays manual.
- Making the repo public.

## Further Notes

- The repo started with no commits, and a PR needs a base branch. The default branch was bootstrapped with one minimal commit containing only a stub README; everything else, including the four skills and the upstream record that were already present untracked, arrives by PR.
- The fact that pi reads the shared agents directory, and that it keeps the first skill on a name collision, comes from the pi 0.85.1 docs on this machine; the installed version is 1.1.0. Worth re-confirming against current docs during implementation.
- Pi's settings also accept a list of extra skill directories. That was not chosen because it loads a whole directory and cannot express a per-agent audience the way per-skill links can.
- Both agents honour the flag that hides a skill from model invocation, which three of the vendored skills use, so no per-agent frontmatter differences are needed.
- The dotfiles main checkout has uncommitted changes to its Makefile and README, which also touch the area this work edits. Expect a small rebase when that work lands.
