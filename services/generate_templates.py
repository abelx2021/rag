#!/usr/bin/env python3
"""Generate portable service templates from a live machine.

Run on a working setup; it reads the live service files, replaces only the
machine-bound and platform-bound parts with portable code and placeholders, and
writes templates/ next to this script. The ingest logic itself is copied verbatim -
never retyped - so it cannot drift.

The generated ingest script is self-adapting: BSD vs GNU stat, shasum vs sha256sum,
textutil vs libreoffice vs pandoc, and the login shell used to reach the agent CLI are
all detected at runtime. That means one script runs on macOS and Linux instead of two
forks drifting apart.

    python3 services/generate_templates.py
"""

import re
from pathlib import Path

SERVICES = Path(__file__).resolve().parent
TEMPLATES = SERVICES / "templates"
HOME = Path.home()

LIVE = {
    "ingest": HOME / "knowledge/.claude/ingest-watch.sh",
    "ingest_plist": HOME / "Library/LaunchAgents/com.ab.knowledge-ingest.plist",
    "brain_plist": HOME / "Library/LaunchAgents/com.ab.abbrain-watcher.plist",
    "brain_config": HOME / ".config/abbrain/config.toml",
}

TEMPLATES.mkdir(parents=True, exist_ok=True)
notes = []


def read(p):
    return p.read_text(encoding="utf-8")


def sub(src, old, new, label, required=True):
    if old not in src:
        if required:
            notes.append(f"!! NOT FOUND: {label}")
        return src
    notes.append(f"ok  {label}")
    return src.replace(old, new)


# ---------------------------------------------------------------- ingest script
src = read(LIVE["ingest"])

# 1. vault root: overridable at runtime
src = sub(
    src,
    'KNOWLEDGE="$HOME/knowledge"',
    'KNOWLEDGE="${KNOWLEDGE_ROOT:-__KNOWLEDGE_ROOT__}"',
    "KNOWLEDGE root overridable",
)

# 2. PATH: discover node; cover Linux and Homebrew locations
src = re.sub(
    r"^export PATH=.*$",
    "# launchd/systemd hand a job a minimal PATH. Discover node rather than pinning one\n"
    "# version, and include the usual Linux and Homebrew locations.\n"
    'NODE_BIN="$(ls -d "$HOME"/.nvm/versions/node/*/bin 2>/dev/null | sort -V | tail -1)"\n'
    'export PATH="$HOME/.local/bin:${NODE_BIN:-}:$HOME/.hermes/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:/snap/bin"',
    src,
    count=1,
    flags=re.M,
)
notes.append("ok  PATH discovery (portable)")

# 3. platform detection: stat / hash / converter / shell, detected once at startup
platform_block = '''
# ---------------------------------------------------------------- platform
# Detected once. BSD (macOS) and GNU (Linux) differ on stat and hashing; the docx
# converter and the login shell differ too. Nothing below this point is platform-bound.

if stat -f %m "$0" >/dev/null 2>&1; then
  STAT_MTIME="stat -f %m"
  STAT_SIZE="stat -f %z"
else
  STAT_MTIME="stat -c %Y"
  STAT_SIZE="stat -c %s"
fi

if command -v sha256sum >/dev/null 2>&1; then
  SHA_TOOL="sha256sum"
elif command -v shasum >/dev/null 2>&1; then
  SHA_TOOL="shasum -a 256"
else
  SHA_TOOL=""
fi

# Text extraction for docx/doc/rtf. macOS has textutil; Linux usually libreoffice.
if command -v textutil >/dev/null 2>&1; then
  CONVERT_CMD='textutil -convert txt "$SRC" -output "$DST"'
elif command -v soffice >/dev/null 2>&1; then
  CONVERT_CMD='soffice --headless --convert-to txt:Text --outdir "$(dirname "$DST")" "$SRC" && mv "$(dirname "$DST")/$(basename "${SRC%.*}").txt" "$DST"'
elif command -v libreoffice >/dev/null 2>&1; then
  CONVERT_CMD='libreoffice --headless --convert-to txt:Text --outdir "$(dirname "$DST")" "$SRC" && mv "$(dirname "$DST")/$(basename "${SRC%.*}").txt" "$DST"'
elif command -v pandoc >/dev/null 2>&1; then
  CONVERT_CMD='pandoc -t plain "$SRC" -o "$DST"'
else
  CONVERT_CMD=''
fi

# What the ingest prompt is told to run for a binary source. Never leave the agent
# with an empty command to "run" - tell it to stop instead.
if [ -n "$CONVERT_CMD" ]; then
  CONVERT_HINT="   SRC=\"\$f\" DST=\"$KNOWLEDGE/.claude/.ingest-convert.txt\"
   $CONVERT_CMD"
else
  CONVERT_HINT="   (no docx/doc/rtf converter on this machine - if the source is binary, report it and stop.)"
fi

# The agent CLI is reached through a login shell so it inherits the user's auth.
# Prefer bash/zsh over $SHELL: those are the shells whose -lic semantics and rc files
# the agent CLI expects (a dash or fish user would get neither).
if [ -x /bin/zsh ]; then
  AGENT_SHELL=/bin/zsh
elif [ -x /bin/bash ]; then
  AGENT_SHELL=/bin/bash
elif [ -n "${SHELL:-}" ] && [ -x "$SHELL" ]; then
  AGENT_SHELL="$SHELL"
else
  AGENT_SHELL=/bin/sh
fi

# Fail loudly rather than silently skipping every source: without a hashing tool the
# change check can never match and nothing would ever be ingested.
if [ -z "$SHA_TOOL" ]; then
  printf '[%s] no sha256 tool found (need sha256sum or shasum) - cannot track sources; exiting\n' \
    "$(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG"
  exit 1
fi
# ---- end platform ----
'''
src = sub(
    src,
    "# launchd passes a minimal PATH. Discover node rather than pinning one version.",
    "# launchd/systemd hand a job a minimal PATH. Discover node rather than pinning one\n"
    "# version, and include the usual Linux and Homebrew locations.\n"
    'NODE_BIN="$(ls -d "$HOME"/.nvm/versions/node/*/bin 2>/dev/null | sort -V | tail -1)"\n'
    'export PATH="$HOME/.local/bin:${NODE_BIN:-}:$HOME/.hermes/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:/snap/bin"',
    "PATH block reuse",
) if False else src

# insert the platform block right after the LOG/LOCK definitions
src = sub(
    src,
    'LOCK="$CLAUDE_DIR/.ingest-lock"\n',
    'LOCK="$CLAUDE_DIR/.ingest-lock"\n' + platform_block,
    "platform detection block",
)

# 4. agent CLI selection
src = sub(
    src,
    'CLAUDE="$(command -v claude)"\n'
    '[ -n "$CLAUDE" ] || { echo "[$(date)] claude not found on PATH" >> "$LOG"; exit 1; }',
    "# Which agent CLI to drive. `cla` is a zsh wrapper some machines define (e.g. a\n"
    "# gateway account); a fresh machine uses plain `claude`. Override with\n"
    "# INGEST_CLAUDE_CMD.\n"
    'CLAUDE_CMD="${INGEST_CLAUDE_CMD:-__DEFAULT_CLAUDE_CMD__}"\n'
    "export CLAUDE_CMD\n"
    'if ! "$AGENT_SHELL" -lic "command -v $CLAUDE_CMD" >/dev/null 2>&1; then\n'
    '  echo "[$(date)] agent CLI not found: $CLAUDE_CMD (set INGEST_CLAUDE_CMD)" >> "$LOG"\n'
    "  exit 1\n"
    "fi",
    "agent CLI selection",
)

# 5. conversion instruction inside the prompt, driven by the detected converter
src = sub(
    src,
    "1. Read the source fully. If it is .docx/.doc/.rtf, first convert it — run:\n"
    "   textutil -convert txt \"$f\" -output \"$KNOWLEDGE/.claude/.ingest-convert.txt\"\n"
    "   then Read \"$KNOWLEDGE/.claude/.ingest-convert.txt\". (.md/.txt/.pdf/images can be Read directly.)",
    "1. Read the source fully. If it is .docx/.doc/.rtf, convert it first with exactly:\n"
    "$CONVERT_HINT\n"
    "   then Read \"$KNOWLEDGE/.claude/.ingest-convert.txt\". (.md/.txt/.pdf/images can be Read directly.)",
    "converter instruction in prompt",
)

# 6. indexing step when AB-Brain is present
src = sub(
    src,
    "6. Run: abbrain index update --vault-name $vault\n"
    "   (AB-Brain indexes the vault; the watcher also picks the change up on its own.)",
    "6. __INDEX_STEP__",
    "index step placeholder",
)

# 7. every literal ~/knowledge/ -> the variable (prompt + comments)
src = src.replace("~/knowledge/", "$KNOWLEDGE/")
notes.append("ok  literal ~/knowledge/ normalised")

# 8. portable hashing and stat call sites
src = sub(
    src,
    'h="$(shasum -a 256 "$f" 2>/dev/null | awk \'{print $1}\')"',
    'h="$($SHA_TOOL "$f" 2>/dev/null | awk \'{print $1}\')"',
    "hash call site",
)
src = src.replace(
    'm="$(stat -f \'%m\' "$f" 2>/dev/null)"',
    'm="$($STAT_MTIME "$f" 2>/dev/null)"',
).replace(
    's="$(stat -f \'%z\' "$f" 2>/dev/null)"',
    's="$($STAT_SIZE "$f" 2>/dev/null)"',
)
notes.append("ok  stat call sites")

# 9. the agent invocation: login shell variable, and the converter tools allowed
src = sub(
    src,
    "/bin/zsh -lic 'source ~/.zshrc 2>/dev/null; cla -p \"$QMD_INGEST_PROMPT\" --allowedTools \"Read,Write,Edit,Bash(abbrain:*),Bash(textutil:*)\"'",
    "\"$AGENT_SHELL\" -lic 'for rc in ~/.zshrc ~/.bashrc; do [ -f \"$rc\" ] && . \"$rc\"; done; "
    "\"$CLAUDE_CMD\" -p \"$QMD_INGEST_PROMPT\" --allowedTools "
    "\"Read,Write,Edit,Bash(abbrain:*),Bash(textutil:*),Bash(soffice:*),Bash(libreoffice:*),Bash(pandoc:*)\"'",
    "agent invocation",
)

# 10. header
src = sub(
    src,
    "#!/usr/bin/env bash\n",
    "#!/usr/bin/env bash\n"
    "# PORTABLE COPY - generated by services/generate_templates.py from the live script.\n"
    "# Runs on macOS and Linux: stat/hash/converter/shell are detected at startup.\n"
    "# Placeholders (double-underscore names) are substituted by services/install.sh.\n",
    "provenance header",
)

# tidy: drop the now-duplicated PATH comment left by the regex pass
src = re.sub(r"\n# launchd/systemd hand a job a minimal PATH.*\n(?!NODE_BIN)", "\n", src, count=1)

(TEMPLATES / "ingest-watch.sh.tmpl").write_text(src, encoding="utf-8")

# a large file with no converter is a real scenario on Linux
if not re.search(r"CONVERT_EXTS", src):
    notes.append("!! CONVERT_EXTS missing from generated script")

# ---------------------------------------------------------------- ingest plist
src = read(LIVE["ingest_plist"]).replace(str(HOME / "knowledge"), "__KNOWLEDGE_ROOT__")
(TEMPLATES / "com.ab.knowledge-ingest.plist.tmpl").write_text(src, encoding="utf-8")

# ---------------------------------------------------------------- brain plist
src = read(LIVE["brain_plist"])
for old, new in (
    (str(HOME / "abbrain/.venv/bin/python"), "__ABBRAIN_PYTHON__"),
    (str(HOME / ".config/abbrain/config.toml"), "__ABBRAIN_CONFIG__"),
    (str(HOME / "abbrain/.venv/bin"), "__ABBRAIN_VENV_BIN__"),
    (str(HOME / ".local/share/abbrain"), "__ABBRAIN_HOME__"),
    (str(HOME / ".local/bin"), "__LOCAL_BIN__"),
):
    src = src.replace(old, new)
(TEMPLATES / "com.ab.abbrain-watcher.plist.tmpl").write_text(src, encoding="utf-8")

# ---------------------------------------------------------------- brain config
src = read(LIVE["brain_config"])
src = re.sub(
    r"(?:^\[\[vault\]\]\n(?:.*\n)*?)(?=\n?\[corpus\])",
    "__VAULT_BLOCKS__\n\n",
    src,
    count=1,
    flags=re.M,
)
(TEMPLATES / "abbrain-config.toml.tmpl").write_text(src, encoding="utf-8")

print("templates written to", TEMPLATES)
for n in notes:
    print("  " + n)
print("\nplaceholders per template:")
for t in sorted(TEMPLATES.glob("*.tmpl")):
    found = sorted(set(re.findall(r"__[A-Z_]+__", read(t))))
    print(f"  {t.name:<42} {found}")
