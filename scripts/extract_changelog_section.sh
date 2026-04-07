#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo "usage: $0 <tag> <changelog_path> <output_path>" >&2
  exit 2
fi

tag="$1"
changelog_path="$2"
output_path="$3"
version_heading="## ${tag}"

if [[ ! -f "$changelog_path" ]]; then
  echo "changelog file not found: ${changelog_path}" >&2
  exit 1
fi

awk -v heading="$version_heading" '
  BEGIN {
    in_section = 0
    found = 0
    started_output = 0
  }
  function is_target_heading(line, heading_text, next_char) {
    if (index(line, heading_text) != 1) {
      return 0
    }
    if (length(line) == length(heading_text)) {
      return 1
    }
    next_char = substr(line, length(heading_text) + 1, 1)
    return (next_char == " " || next_char == "(")
  }
  is_target_heading($0, heading) {
    in_section = 1
    found = 1
    next
  }
  /^## / && in_section && !is_target_heading($0, heading) {
    exit
  }
  in_section {
    if (!started_output && $0 ~ /^[[:space:]]*$/) {
      next
    }
    started_output = 1
    print
  }
  END {
    if (!found) {
      exit 3
    }
  }
' "$changelog_path" > "$output_path" || {
  status=$?
  if [[ $status -eq 3 ]]; then
    echo "no changelog section found for tag: ${tag}" >&2
  fi
  exit "$status"
}

if [[ ! -s "$output_path" ]]; then
  echo "extracted changelog section is empty for tag: ${tag}" >&2
  exit 1
fi
