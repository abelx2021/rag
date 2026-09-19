#!/usr/bin/env bash
# Portable installer for the vault stack: Obsidian + raw/ ingester + AB-Brain watcher.
# Runs on macOS (launchd) and Linux (systemd --user).
#
#   ./install.sh --check                     report what is present/missing (default, no writes)
#   ./install.sh --render DIR                write rendered service files into DIR
#   ./install.sh --apply                     install to live locations (backs up anything it replaces)
#   ./install.sh --apply --load              ... and (re)load the services
#
# Options:
#   --knowledge DIR      vault root                      (default: $HOME/knowledge)
#   --vault NAME         vault to register (repeatable)  (default: every dir under --knowledge with a wiki/)
#   --claude-cmd CMD     agent CLI the ingester drives   (default: cla if defined in your shell rc, else claude)
#   --abbrain-repo DIR   AB-Brain checkout               (default: $HOME/abbrain if present)
#   --platform P         macos | linux | auto            (default: auto)
#   --force              overwrite existing files (a .bak-<timestamp> is kept either way)

set -u

SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
TEMPLATES="$SELF_DIR/templates"
RENDER="$SELF_DIR/render.py"

MODE="check"
RENDER_OUT=""
LOAD=0
FORCE=0
KNOWLEDGE_ROOT="${HOME}/knowledge"
VAULTS=()
CLAUDE_CMD_OPT=""
ABBRAIN_REPO_OPT=""
PLATFORM="auto"

while [ $# -gt 0 ]; do
  case "$1" in
    --check)        MODE="check" ;;
    --render)       MODE="render"; RENDER_OUT="${2:-}"; shift ;;
    --apply)        MODE="apply" ;;
    --load)         LOAD=1 ;;
    --force)        FORCE=1 ;;
    --knowledge)    KNOWLEDGE_ROOT="${2:-}"; shift ;;
    --vault)        VAULTS+=("${2:-}"); shift ;;
    --claude-cmd)   CLAUDE_CMD_OPT="${2:-}"; shift ;;
    --abbrain-repo) ABBRAIN_REPO_OPT="${2:-}"; shift ;;
    --platform)     PLATFORM="${2:-}"; shift ;;
    -h|--help)      sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "unknown option: $1 (try --help)" >&2; exit 2 ;;
  esac
  shift
done

say()  { printf '%s\n' "$*"; }
ok()   { printf '  [ ok ]    %s\n' "$*"; }
miss() { printf '  [MISSING] %s\n' "$*"; }
warn() { printf '  [ warn ]  %s\n' "$*"; }

# ---------------------------------------------------------------- platform
if [ "$PLATFORM" = "auto" ]; then
  case "$(uname -s)" in
    Darwin) PLATFORM="macos" ;;
    Linux)  PLATFORM="linux" ;;
    *)      PLATFORM="unsupported" ;;
  esac
fi

case "$PLATFORM" in
  macos)
    SERVICE_DIR="$HOME/Library/LaunchAgents"
    INGEST_UNIT="com.ab.knowledge-ingest.plist"
    BRAIN_UNIT="com.ab.abbrain-watcher.plist"
    ;;
  linux)
    SERVICE_DIR="$HOME/.config/systemd/user"
    INGEST_UNIT="knowledge-ingest.service"
    BRAIN_UNIT="abbrain-watcher.service"
    ;;
  *)
    say "unsupported platform '$PLATFORM': this bundle targets macOS (launchd) and Linux (systemd)."
    exit 3
    ;;
esac

KNOWLEDGE_ROOT="${KNOWLEDGE_ROOT/#\~/$HOME}"
[ "$PLATFORM" = "linux" ] && KNOWLEDGE_ROOT="${KNOWLEDGE_ROOT/#\$HOME/$HOME}"

# ---------------------------------------------------------------- discovery
if [ "${#VAULTS[@]}" -eq 0 ] && [ -d "$KNOWLEDGE_ROOT" ]; then
  for d in "$KNOWLEDGE_ROOT"/*/; do
    n="$(basename "$d")"
    case "$n" in _*|.*) continue ;; esac
    [ -d "$d/wiki" ] && VAULTS+=("$n")
  done
fi
VAULT_SPECS=()
for v in "${VAULTS[@]:-}"; do
  [ -n "$v" ] && VAULT_SPECS+=("${v}:${KNOWLEDGE_ROOT}/${v}")
done

if [ -n "$CLAUDE_CMD_OPT" ]; then
  CLAUDE_CMD="$CLAUDE_CMD_OPT"
else
  CLAUDE_CMD="claude"
  for rc in "$HOME/.zshrc" "$HOME/.bashrc"; do
    [ -f "$rc" ] || continue
    if grep -qE '^[[:space:]]*(function[[:space:]]+)?cla[[:space:]]*\(\)' "$rc"; then
      CLAUDE_CMD="cla"
    fi
  done
fi

ABBRAIN_REPO=""
if [ -n "$ABBRAIN_REPO_OPT" ]; then
  ABBRAIN_REPO="$ABBRAIN_REPO_OPT"
elif [ -d "$HOME/abbrain" ]; then
  ABBRAIN_REPO="$HOME/abbrain"
fi

WITH_ABBRAIN=0
ABBRAIN_PYTHON="$(command -v python3 || echo /usr/bin/python3)"
ABBRAIN_VENV_BIN="$(dirname "$ABBRAIN_PYTHON")"
if [ -n "$ABBRAIN_REPO" ] && [ -x "$ABBRAIN_REPO/.venv/bin/python" ]; then
  ABBRAIN_PYTHON="$ABBRAIN_REPO/.venv/bin/python"
  ABBRAIN_VENV_BIN="$ABBRAIN_REPO/.venv/bin"
  WITH_ABBRAIN=1
elif command -v abbrain >/dev/null 2>&1; then
  WITH_ABBRAIN=1
  ABBRAIN_PYTHON="$(command -v python3 || echo /usr/bin/python3)"
fi

ABBRAIN_HOME="$HOME/.local/share/abbrain"
ABBRAIN_CONFIG="$HOME/.config/abbrain/config.toml"
LOCAL_BIN="$HOME/.local/bin"
INGEST_SCRIPT="$KNOWLEDGE_ROOT/.claude/ingest-watch.sh"

CONVERTER=""
for c in textutil soffice libreoffice pandoc; do
  if command -v "$c" >/dev/null 2>&1; then CONVERTER="$c"; break; fi
done

say "resolved configuration"
say "  platform          $PLATFORM  (services: $SERVICE_DIR)"
say "  vault root        $KNOWLEDGE_ROOT"
say "  vaults            ${VAULTS[*]:-<none found>}"
say "  agent CLI         $CLAUDE_CMD"
say "  converter         ${CONVERTER:-<none: binary sources cannot be ingested>}"
say "  AB-Brain          $([ "$WITH_ABBRAIN" = 1 ] && echo "${ABBRAIN_REPO:-<on PATH>}" || echo '<not installed>')"
say "  AB-Brain python   $ABBRAIN_PYTHON"
say "  AB-Brain config   $ABBRAIN_CONFIG"
say ""

# ---------------------------------------------------------------- render
render_into() {
  local out="$1"
  if ! python3 -c 'import sys' >/dev/null 2>&1; then
    echo "python3 is required to render the service files." >&2
    [ "$PLATFORM" = "macos" ] && echo "On a fresh Mac: xcode-select --install" >&2
    [ "$PLATFORM" = "linux" ] && echo "Install it, e.g.: sudo apt install python3" >&2
    return 1
  fi
  python3 "$RENDER" \
    --templates "$TEMPLATES" --out "$out" \
    --knowledge-root "$KNOWLEDGE_ROOT" \
    --default-claude-cmd "$CLAUDE_CMD" \
    --abbrain-python "$ABBRAIN_PYTHON" \
    --abbrain-venv-bin "$ABBRAIN_VENV_BIN" \
    --abbrain-config "$ABBRAIN_CONFIG" \
    --abbrain-home "$ABBRAIN_HOME" \
    --local-bin "$LOCAL_BIN" \
    --existing-config "$ABBRAIN_CONFIG" \
    $( [ "$WITH_ABBRAIN" = 1 ] && echo --with-abbrain ) \
    $(for s in "${VAULT_SPECS[@]:-}"; do [ -n "$s" ] && printf -- '--vault %s ' "$s"; done)
}

if [ "$MODE" = "render" ]; then
  [ -n "$RENDER_OUT" ] || { echo "--render needs an output directory" >&2; exit 2; }
  render_into "$RENDER_OUT" || exit 1
  say "rendered into $RENDER_OUT"
  exit 0
fi

# ---------------------------------------------------------------- apply
if [ "$MODE" = "apply" ]; then
  TMP="$(mktemp -d)"
  render_into "$TMP" || exit 1

  STAMP="$(date +%Y%m%d-%H%M%S)"
  install_file() {
    local src="$1" dst="$2" label="$3"
    mkdir -p "$(dirname "$dst")"
    if [ -e "$dst" ] && [ "$FORCE" != 1 ]; then
      warn "$label exists, not overwritten (use --force): $dst"
      return 0
    fi
    if [ -e "$dst" ]; then
      cp -p "$dst" "$dst.bak-$STAMP" && say "  backed up $dst.bak-$STAMP"
    fi
    cp -p "$src" "$dst" && ok "$label -> $dst"
  }

  say "installing"
  install_file "$TMP/ingest-watch.sh" "$INGEST_SCRIPT" "ingest watcher script"
  if [ "$PLATFORM" = "macos" ]; then
    install_file "$TMP/$INGEST_UNIT" "$SERVICE_DIR/$INGEST_UNIT" "ingest LaunchAgent"
    [ "$WITH_ABBRAIN" = 1 ] && install_file \
      "$TMP/$BRAIN_UNIT" "$SERVICE_DIR/$BRAIN_UNIT" "AB-Brain LaunchAgent"
  else
    install_file "$TMP/systemd/$INGEST_UNIT" "$SERVICE_DIR/$INGEST_UNIT" "ingest systemd unit"
    [ "$WITH_ABBRAIN" = 1 ] && install_file \
      "$TMP/systemd/$BRAIN_UNIT" "$SERVICE_DIR/$BRAIN_UNIT" "AB-Brain systemd unit"
  fi
  [ "$WITH_ABBRAIN" = 1 ] && install_file \
    "$TMP/abbrain-config.toml" "$ABBRAIN_CONFIG" "AB-Brain config"

  mkdir -p "$KNOWLEDGE_ROOT/.claude" "$ABBRAIN_HOME/logs" "$LOCAL_BIN"
  if [ ! -f "$KNOWLEDGE_ROOT/CLAUDE.md" ] && [ -f "$TEMPLATES/knowledge-CLAUDE.md" ]; then
    cp -p "$TEMPLATES/knowledge-CLAUDE.md" "$KNOWLEDGE_ROOT/CLAUDE.md" \
      && ok "seeded the shared schema -> $KNOWLEDGE_ROOT/CLAUDE.md"
  fi

  if [ "$LOAD" = 1 ]; then
    say "loading services"
    if [ "$PLATFORM" = "macos" ]; then
      for label in com.ab.knowledge-ingest com.ab.abbrain-watcher; do
        [ "$label" = "com.ab.abbrain-watcher" ] && [ "$WITH_ABBRAIN" != 1 ] && continue
        launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
        if launchctl bootstrap "gui/$(id -u)" "$SERVICE_DIR/$label.plist" 2>/dev/null; then
          ok "loaded $label"
        else
          miss "could not load $label"
        fi
      done
    else
      if ! command -v systemctl >/dev/null 2>&1; then
        miss "systemctl not found; start the services yourself"
      else
        systemctl --user daemon-reload
        for unit in knowledge-ingest.service abbrain-watcher.service; do
          [ "$unit" = "abbrain-watcher.service" ] && [ "$WITH_ABBRAIN" != 1 ] && continue
          if systemctl --user enable --now "$unit" 2>/dev/null; then
            ok "enabled + started $unit"
          else
            miss "could not start $unit"
          fi
        done
        warn "user services stop at logout unless lingering is on: loginctl enable-linger $USER"
      fi
    fi
  else
    say "services not loaded (re-run with --load, or load them yourself)"
  fi
  say ""
  say "next: obsidian -> open folder as vault -> $KNOWLEDGE_ROOT/<vault>"
  exit 0
fi

# ---------------------------------------------------------------- check
say "prerequisites"
if [ "$PLATFORM" = "macos" ]; then
  command -v textutil >/dev/null 2>&1 \
    && ok "textutil (docx/rtf conversion)" \
    || miss "textutil — expected on macOS"
else
  if [ -n "$CONVERTER" ]; then
    ok "converter: $CONVERTER (docx/rtf for the ingester)"
  else
    warn "no docx converter — install libreoffice (or pandoc) if you ingest .docx/.doc/.rtf"
  fi
fi

if python3 -c 'import sys' >/dev/null 2>&1; then
  ok "python3 $(python3 -V 2>&1 | awk '{print $2}')"
else
  miss "python3 — macOS: xcode-select --install | Debian/Ubuntu: sudo apt install python3"
fi

if [ -d "/Applications/Obsidian.app" ] || [ -d "$HOME/Applications/Obsidian.app" ]; then
  ok "Obsidian.app installed"
elif command -v obsidian >/dev/null 2>&1; then
  ok "obsidian on PATH"
else
  miss "Obsidian — https://obsidian.md/download (macOS: brew install --cask obsidian | Debian: flatpak install flathub md.obsidian.Obsidian)"
fi

if [ -d "$KNOWLEDGE_ROOT" ]; then
  ok "vault root exists: $KNOWLEDGE_ROOT"
else
  miss "vault root missing: $KNOWLEDGE_ROOT — copy your knowledge folder here, or pass --knowledge"
fi

if [ -f "$KNOWLEDGE_ROOT/CLAUDE.md" ]; then
  ok "shared schema present: $KNOWLEDGE_ROOT/CLAUDE.md"
else
  miss "shared schema $KNOWLEDGE_ROOT/CLAUDE.md — the ingest prompt depends on it (seeded by --apply)"
fi

if [ "${#VAULTS[@]}" -gt 0 ]; then
  for v in "${VAULTS[@]}"; do
    extra=""
    [ -d "$KNOWLEDGE_ROOT/$v/raw" ] || extra=" (no raw/ dir)"
    ok "vault $v$extra"
  done
else
  miss "no vaults found under $KNOWLEDGE_ROOT (a vault is a dir containing wiki/)"
fi

if /bin/zsh -lic "command -v $CLAUDE_CMD" >/dev/null 2>&1 \
   || bash -lic "command -v $CLAUDE_CMD" >/dev/null 2>&1; then
  ok "agent CLI reachable: $CLAUDE_CMD"
  warn "the ingester reuses your shell's auth for it — make sure it is already logged in"
else
  miss "agent CLI not reachable from a login shell: $CLAUDE_CMD"
  warn "install/link it, or pass --claude-cmd <name>"
fi

if curl -s --max-time 3 http://127.0.0.1:11434/api/tags 2>/dev/null | grep -q embeddinggemma; then
  ok "ollama up and embeddinggemma present"
else
  miss "ollama + embeddinggemma — start ollama and: ollama pull embeddinggemma"
fi

if [ "$WITH_ABBRAIN" = 1 ]; then
  ok "AB-Brain found: ${ABBRAIN_REPO:-on PATH}"
  [ -x "$ABBRAIN_PYTHON" ] && ok "AB-Brain interpreter: $ABBRAIN_PYTHON" || warn "using python3: $ABBRAIN_PYTHON"
  [ -f "$ABBRAIN_CONFIG" ] && ok "AB-Brain config: $ABBRAIN_CONFIG" || warn "no AB-Brain config yet; --apply writes one"
else
  warn "AB-Brain not installed — the ingester will skip indexing, Obsidian still works"
fi

if [ -e "$INGEST_SCRIPT" ]; then
  ok "ingest watcher already installed: $INGEST_SCRIPT"
else
  warn "ingest watcher not installed yet — run --apply"
fi

if [ "$PLATFORM" = "macos" ]; then
  say ""
  say "service state:  launchctl print gui/$(id -u)/com.ab.knowledge-ingest"
else
  if command -v systemd-analyze >/dev/null 2>&1 && [ -d "$SERVICE_DIR" ]; then
    for u in "$SERVICE_DIR"/knowledge-ingest.service "$SERVICE_DIR"/abbrain-watcher.service; do
      [ -f "$u" ] || continue
      if systemd-analyze --user verify "$u" >/dev/null 2>&1; then
        ok "unit verifies: $(basename "$u")"
      else
        warn "systemd-analyze flagged $(basename "$u")"
      fi
    done
  fi
  say ""
  say "service state:  systemctl --user status knowledge-ingest.service"
fi

say ""
say "nothing was written. next steps:"
say "  1. review:  $0 --render /tmp/vault-stack-preview"
say "  2. install: $0 --apply --load"
