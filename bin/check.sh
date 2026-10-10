#!/usr/bin/env bash
# Repository checks: lint the scripts, validate every skill's frontmatter and
# run the test suites. Writes nothing outside temporary directories.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

failures=0
warnings=0

info() { printf '==> %s\n' "$*"; }
ok() { printf 'ok: %s\n' "$*"; }
warn() { printf 'warn: %s\n' "$*"; warnings=$((warnings + 1)); }
fail() { printf 'FAIL: %s\n' "$*"; failures=$((failures + 1)); }

run_check() {
  local label="$1"
  shift

  if "$@"; then
    ok "$label"
  else
    fail "$label"
  fi
}

# Print the value of a top-level frontmatter key, without surrounding quotes.
frontmatter() {
  awk -v key="$2" '
    NR == 1 && $0 != "---" { exit }
    NR > 1 && $0 == "---" { exit }
    index($0, key ":") == 1 {
      value = substr($0, length(key) + 2)
      gsub(/^[ \t]+|[ \t]+$/, "", value)
      gsub(/^["\047]|["\047]$/, "", value)
      print value
      exit
    }
  ' "$1"
}

skill_is_valid() {
  local dir="$1" name
  name="$(basename "$dir")"
  if [[ ! -f "$dir/SKILL.md" ]]; then
    echo "$name: no SKILL.md"
    return 1
  fi
  if [[ "$(frontmatter "$dir/SKILL.md" name)" != "$name" ]]; then
    echo "$name: frontmatter name does not match the directory"
    return 1
  fi
  if [[ -z "$(frontmatter "$dir/SKILL.md" description)" ]]; then
    echo "$name: empty description"
    return 1
  fi
}

# A dry run against an empty home fails if skills.conf names an unknown skill
# or agent.
manifest_is_valid() {
  local home rc=0
  home="$(mktemp -d)"
  HOME="$home" bash bin/link.sh --dry-run >/dev/null || rc=$?
  rm -rf "$home"
  return "$rc"
}

info "bash syntax"
for path in bin/*.sh; do
  run_check "bash -n $path" bash -n "$path"
done

info "ShellCheck"
if command -v shellcheck >/dev/null 2>&1; then
  run_check "shellcheck bin/*.sh" shellcheck bin/*.sh
else
  warn "shellcheck not found; skipping shell lint (brew install shellcheck / apt install shellcheck / pacman -S shellcheck)"
fi

info "skills"
for dir in skills/*/; do
  run_check "${dir%/} frontmatter" skill_is_valid "${dir%/}"
done
run_check "skills.conf matches skills/" manifest_is_valid

info "tests"
run_check "link script tests" python3 -B -m unittest discover -s tests
run_check "whiteboard tests" python3 -B -m unittest discover -s skills/whiteboard -p 'test_*.py'

printf '\nSummary: %d failure(s), %d warning(s)\n' "$failures" "$warnings"

if ((failures > 0)); then
  exit 1
fi
