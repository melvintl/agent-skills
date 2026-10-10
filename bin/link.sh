#!/usr/bin/env bash
# Link each skill in skills/ into the skills directory of every agent it is
# for. skills.conf lists the exceptions; a skill not listed there goes to all
# agents.
# Safe to re-run: only links that point into this repo are ever changed or
# removed, and anything else already in the way is reported and left alone.

set -euo pipefail

# AGENT_SKILLS_REPO lets the tests point the script at a fixture repo.
REPO="${AGENT_SKILLS_REPO:-$(dirname "${BASH_SOURCE[0]}")/..}"
REPO="$(cd "$REPO" && pwd -P)"
SKILLS="$REPO/skills"
MANIFEST="$REPO/skills.conf"

# name|skills directory. Adding an agent is one line here.
AGENT_DIRS=(
  "claude|$HOME/.claude/skills"
  "pi|${PI_CODING_AGENT_DIR:-${PI_AGENT_DIR:-$HOME/.pi/agent}}/skills"
)

# skill|environment variable the skill needs at runtime (doctor only).
REQUIRED_ENV=(
  "brave-search|BRAVE_API_KEY"
)

# pi also reads this directory, and on a name collision keeps one skill only.
SHARED_SKILLS="$HOME/.agents/skills"

MODE="apply"
PREFIX=""
problems=0

usage() {
  cat <<'EOF'
Usage: bin/link.sh [--dry-run|--doctor]

  (no option)  Link skills into each agent's skills directory
  --dry-run    Print what would change without writing
  --doctor     Report link, dependency and environment status
  -h, --help   Show this help
EOF
}

case "${1:-}" in
  "") ;;
  -n|--dry-run) MODE="dry-run"; PREFIX="would " ;;
  --doctor) MODE="doctor" ;;
  -h|--help) usage; exit 0 ;;
  *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
esac
if (($# > 1)); then
  usage >&2
  exit 2
fi

report() { printf '%s%-8s %-7s %s\n' "$PREFIX" "$1" "$2" "$3"; }
problem() { report "$@"; problems=$((problems + 1)); }
die() { echo "error: $*" >&2; exit 2; }

run() {
  if [[ "$MODE" == "apply" ]]; then
    "$@"
  fi
}

all_agents() {
  local entry
  for entry in "${AGENT_DIRS[@]}"; do
    printf '%s ' "${entry%%|*}"
  done
}

agent_dir() {
  local entry
  for entry in "${AGENT_DIRS[@]}"; do
    if [[ "${entry%%|*}" == "$1" ]]; then
      printf '%s\n' "${entry#*|}"
    fi
  done
}

is_skill() { [[ -f "$SKILLS/$1/SKILL.md" ]]; }

skill_names() {
  local dir
  for dir in "$SKILLS"/*/; do
    dir="${dir%/}"
    if is_skill "${dir##*/}"; then
      printf '%s\n' "${dir##*/}"
    fi
  done
}

# Manifest lines as "skill agent...", without comments and blank lines.
manifest_lines() {
  local line name agents
  [[ -f "$MANIFEST" ]] || return 0
  while IFS= read -r line || [[ -n "$line" ]]; do
    read -r name agents <<<"${line%%#*}" || true
    if [[ -n "$name" ]]; then
      printf '%s %s\n' "$name" "$agents"
    fi
  done <"$MANIFEST"
}

check_manifest() {
  local name agents agent
  while read -r name agents; do
    is_skill "$name" || die "skills.conf: no such skill: $name"
    [[ -n "$agents" ]] || die "skills.conf: $name lists no agents"
    for agent in $agents; do
      [[ -n "$(agent_dir "$agent")" ]] || die "skills.conf: $name: unknown agent: $agent"
    done
  done < <(manifest_lines)
}

audience() {
  local name agents
  while read -r name agents; do
    if [[ "$name" == "$1" ]]; then
      printf '%s\n' "$agents"
      return 0
    fi
  done < <(manifest_lines)
  all_agents
}

# wants <agent> <name>: is <name> a skill meant for <agent>?
wants() {
  local agent
  is_skill "$2" || return 1
  for agent in $(audience "$2"); do
    if [[ "$agent" == "$1" ]]; then
      return 0
    fi
  done
  return 1
}

# ours <path>: is <path> a link into this repo's skills?
ours() { [[ -L "$1" && "$(readlink "$1")" == "$SKILLS"/* ]]; }

# state <dir> <name>: ok, missing, stale (ours, wrong target) or foreign.
state() {
  local path="$1/$2"
  if [[ -L "$path" && "$(readlink "$path")" == "$SKILLS/$2" ]]; then
    echo ok
  elif ours "$path"; then
    echo stale
  elif [[ -e "$path" || -L "$path" ]]; then
    echo foreign
  else
    echo missing
  fi
}

describe() {
  if [[ -L "$1" ]]; then
    printf '%s -> %s' "${1##*/}" "$(readlink "$1")"
  else
    printf '%s (not a link)' "${1##*/}"
  fi
}

# The skills directory is itself a link to a directory elsewhere. Replace it
# with a real directory, naming whatever it held that we will not link back.
convert_dir() {
  local agent="$1" dir="$2" path
  report convert "$agent" "$dir was a link to $(readlink "$dir")"
  for path in "$dir"/*; do
    [[ -e "$path" || -L "$path" ]] || continue
    wants "$agent" "${path##*/}" && continue
    if [[ -L "$path" ]]; then
      echo "  relink by hand: $(describe "$path")"
    else
      echo "  not carried over: ${path##*/}"
    fi
  done
  run rm "$dir"
  run mkdir -p "$dir"
}

prune_agent() {
  local agent="$1" dir="$2" path name
  for path in "$dir"/*; do
    ours "$path" || continue
    name="${path##*/}"
    if [[ "$(state "$dir" "$name")" == "ok" ]] && wants "$agent" "$name"; then
      continue
    fi
    report prune "$agent" "$name"
    run rm "$path"
  done
}

link_agent() {
  local agent="$1" dir="$2" fresh="$3" name current
  while IFS= read -r name; do
    wants "$agent" "$name" || continue
    current="missing"
    if ((!fresh)); then
      current="$(state "$dir" "$name")"
    fi
    case "$current" in
      ok) ;;
      foreign) PREFIX="" problem refused "$agent" "$(describe "$dir/$name")" ;;
      *)
        report link "$agent" "$name"
        run mkdir -p "$dir"
        run ln -s "$SKILLS/$name" "$dir/$name"
        ;;
    esac
  done < <(skill_names)
}

needs_install() { [[ -f "$SKILLS/$1/package.json" && ! -d "$SKILLS/$1/node_modules" ]]; }

install_deps() {
  local name
  while IFS= read -r name; do
    needs_install "$name" || continue
    if ! command -v npm >/dev/null 2>&1; then
      echo "warn: npm not found; run 'npm ci' in skills/$name once it is installed"
      continue
    fi
    report install - "$name"
    if [[ "$MODE" == "apply" ]] && ! (cd "$SKILLS/$name" && npm ci --no-audit --no-fund); then
      problem failed - "npm ci in skills/$name"
    fi
  done < <(skill_names)
}

apply() {
  local entry agent dir fresh
  for entry in "${AGENT_DIRS[@]}"; do
    agent="${entry%%|*}"
    dir="${entry#*|}"
    fresh=0
    if [[ -L "$dir" ]]; then
      convert_dir "$agent" "$dir"
      fresh=1
    else
      prune_agent "$agent" "$dir"
    fi
    link_agent "$agent" "$dir" "$fresh"
  done
  install_deps
  if ((problems)); then
    echo "$problems problem(s); nothing above marked refused was touched"
    exit 1
  fi
}

doctor() {
  local entry agent dir name path current var pi_dir
  for entry in "${AGENT_DIRS[@]}"; do
    agent="${entry%%|*}"
    dir="${entry#*|}"
    if [[ -L "$dir" ]]; then
      problem unlinked "$agent" "$dir is a link to $(readlink "$dir"); run the link command to convert it"
      continue
    fi
    while IFS= read -r name; do
      wants "$agent" "$name" || continue
      current="$(state "$dir" "$name")"
      case "$current" in
        ok) report ok "$agent" "$name" ;;
        foreign) problem blocked "$agent" "$(describe "$dir/$name")" ;;
        *) problem "$current" "$agent" "$name" ;;
      esac
    done < <(skill_names)
    for path in "$dir"/*; do
      if ours "$path" && ! wants "$agent" "${path##*/}"; then
        problem stale "$agent" "$(describe "$path")"
      fi
    done
  done

  while IFS= read -r name; do
    if needs_install "$name"; then
      problem deps - "skills/$name has no node_modules"
    fi
  done < <(skill_names)

  for entry in "${REQUIRED_ENV[@]}"; do
    name="${entry%%|*}"
    var="${entry#*|}"
    if is_skill "$name" && [[ -z "${!var:-}" ]]; then
      problem env - "$var is not set ($name needs it)"
    fi
  done

  pi_dir="$(agent_dir pi)"
  for path in "$pi_dir"/*; do
    name="${path##*/}"
    if [[ -e "$path" && -e "$SHARED_SKILLS/$name" ]]; then
      problem clash pi "$name is in both $pi_dir and $SHARED_SKILLS"
    fi
  done

  echo "$problems problem(s)"
  if ((problems)); then
    exit 1
  fi
}

[[ -d "$SKILLS" ]] || die "no skills directory in $REPO"
check_manifest

if [[ "$MODE" == "doctor" ]]; then
  doctor
else
  apply
fi
