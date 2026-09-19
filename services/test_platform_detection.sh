#!/usr/bin/env bash
# Exercise the generated ingest script's platform-detection block under simulated
# tool availability, so the Linux branch can be tested on a Mac.
#
#   ./test_platform_detection.sh /tmp/render-linux/ingest-watch.sh
#
# It stubs stat / command -v / [ and evals the *real* detection block taken from the
# generated script, then prints what the script would select - including the case where
# no hashing tool exists, which must fail loudly instead of silently ingesting nothing.

set -u

SCRIPT="${1:-}"
[ -n "$SCRIPT" ] && [ -f "$SCRIPT" ] || { echo "usage: $0 <rendered ingest-watch.sh>" >&2; exit 2; }

BLOCK="$(sed -n '/^# -\{10,\} platform$/,/^# ---- end platform ----$/p' "$SCRIPT")"
[ -n "$BLOCK" ] || { echo "could not find the platform block in $SCRIPT" >&2; exit 2; }
export BLOCK

run_case() {
  local label="$1" bsd="$2" sha256="$3" shasum="$4" conv="$5" zsh="$6" ushell="$7"
  local logfile; logfile="$(mktemp)"
  local out rc
  out="$(env -i BSD_STAT="$bsd" HAVE_SHA256="$sha256" HAVE_SHASUM="$shasum" \
         CONVERTER="$conv" HAVE_ZSH="$zsh" USER_SHELL="$ushell" BLOCK="$BLOCK" \
         KNOWLEDGE="/tmp/x/knowledge" LOG="$logfile" /bin/bash -c '
    # ---- stubs: the host has only what the case grants ------------------------
    stat() {
      if [ "$1" = "-f" ]; then
        [ "$BSD_STAT" = yes ] && { echo 17; return 0; } || return 1
      fi
      [ "$BSD_STAT" = yes ] && return 1 || { echo 17; return 0; }
    }
    command() {
      if [ "$1" = "-v" ]; then
        case "$2" in
          sha256sum)   [ "$HAVE_SHA256" = yes ] && { echo /usr/bin/sha256sum; return 0; } || return 1 ;;
          shasum)      [ "$HAVE_SHASUM" = yes ] && { echo /usr/bin/shasum; return 0; } || return 1 ;;
          textutil)    [ "$CONVERTER" = textutil ] && { echo /usr/bin/textutil; return 0; } || return 1 ;;
          soffice)     [ "$CONVERTER" = soffice ] && { echo /usr/bin/soffice; return 0; } || return 1 ;;
          libreoffice) [ "$CONVERTER" = libreoffice ] && { echo /usr/bin/libreoffice; return 0; } || return 1 ;;
          pandoc)      [ "$CONVERTER" = pandoc ] && { echo /usr/bin/pandoc; return 0; } || return 1 ;;
          *)           return 1 ;;
        esac
      fi
      builtin command "$@"
    }
    # the script probes zsh with [ -x /bin/zsh ]; inside the stub every test must use
    # `builtin [` or it recurses into itself
    function [ {
      if builtin [ "$1" = "-x" ] && builtin [ "$2" = "/bin/zsh" ]; then
        builtin [ "$HAVE_ZSH" = yes ]
        return $?
      fi
      builtin [ "$@"
    }
    SHELL="$USER_SHELL"
    # ---- the real block, unmodified -----------------------------------------
    eval "$BLOCK"
    printf "STAT_MTIME=%s\n" "$STAT_MTIME"
    printf "STAT_SIZE=%s\n" "$STAT_SIZE"
    printf "SHA_TOOL=%s\n" "${SHA_TOOL:-<none>}"
    printf "CONVERT=%s\n"  "$([ -n "$CONVERT_CMD" ] && echo "$(printf %s "$CONVERT_CMD" | cut -c1-38)..." || echo "<empty>")"
    printf "HINT=%s\n"     "$(printf %s "$CONVERT_HINT" | head -1 | cut -c1-58)"
    printf "AGENT_SHELL=%s\n" "${AGENT_SHELL:-<unset>}"
  ' 2>&1)"; rc=$?

  printf '\n  %s\n' "$label"
  printf '%s\n' "$out" | sed 's/^/      /'
  if [ "$rc" != 0 ]; then
    printf '      exit=%s  (fail-fast) log: %s\n' "$rc" "$(tail -1 "$logfile" | cut -c1-88)"
  fi
  rm -f "$logfile"
}

echo "detection block taken from: $SCRIPT"
run_case "macOS-like            BSD stat / shasum / textutil / zsh"       yes no  yes textutil    yes ""
run_case "Linux + libreoffice   GNU stat / sha256sum / soffice / bash"    no  yes no  soffice     no  /bin/bash
run_case "Linux + pandoc, dash  GNU stat / sha256sum / pandoc / no zsh"   no  yes no  pandoc      no  /bin/dash
run_case "Linux, no converter   GNU stat / sha256sum / none"              no  yes no  ""          no  /bin/bash
run_case "no hashing tool       must fail fast, not ingest nothing"       no  no  no  pandoc      no  /bin/bash
