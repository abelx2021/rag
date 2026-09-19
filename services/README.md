# Vault stack — portable install bundle

Take the vault setup to another Mac: **Obsidian + a raw/ ingester + a change-tracking
watcher**, installed from this folder with one command.

Copy **this repo** and **your `~/knowledge` folder** to the new machine, then:

    ./install.sh --check          # what's present / missing, with fixes (no writes)
    ./install.sh --render DIR     # inspect what would be installed
    ./install.sh --apply          # install to the live locations (backs up what it replaces)
    ./install.sh --apply --load   # ... and start the two LaunchAgents

## What's in here

| file | role |
|---|---|
| `install.sh` | the installer: discovers, checks prerequisites, renders, applies, loads |
| `render.py` | placeholder substitution (multi-line safe; leftover placeholders are a hard error) |
| `generate_templates.py` | regenerates `templates/` from a *live* machine, copying the ingest logic verbatim |
| `templates/ingest-watch.sh.tmpl` | the `raw/` ingester (LaunchAgent `com.ab.knowledge-ingest`) |
| `templates/com.ab.knowledge-ingest.plist.tmpl` | its LaunchAgent |
| `templates/com.ab.abbrain-watcher.plist.tmpl` | the AB-Brain watcher agent (index + graph) |
| `templates/systemd/*.service.tmpl` | the Linux equivalents (systemd --user units) |
| `templates/abbrain-config.toml.tmpl` | AB-Brain config: vaults, corpus globs, watcher timings |
| `templates/knowledge-CLAUDE.md` | the shared vault schema — the ingest prompt depends on it |
| `templates/vault-CLAUDE.md.example` | per-vault conventions template |
| `test_platform_detection.sh` | simulates each platform's tool availability and checks what the script picks |

## Prerequisites the installer checks (and does not install)

| requirement | why | install |
|---|---|---|
| macOS | launchd, `textutil`, BSD `stat` | — |
| Obsidian | you open the vault with it | https://obsidian.md/download or `brew install --cask obsidian` |
| an agent CLI (`claude`, or your own wrapper) already authenticated | the ingester drives it headlessly | install + log in yourself; `--claude-cmd NAME` to change it |
| ollama + `embeddinggemma` | AB-Brain's embeddings | start ollama, `ollama pull embeddinggemma` |
| AB-Brain checkout (`~/abbrain`) | keeps the FAISS index + graph current | optional — without it the ingester just skips indexing and Obsidian still works |

## Options

    --knowledge DIR      vault root                    (default: $HOME/knowledge)
    --vault NAME         register a vault (repeatable) (default: every dir under it with a wiki/)
    --claude-cmd CMD     agent CLI to drive            (default: cla if defined in ~/.zshrc, else claude)
    --abbrain-repo DIR   AB-Brain checkout             (default: $HOME/abbrain if present)
    --force              overwrite live files (a .bak-<timestamp> is always kept)
    --load               (re)load the LaunchAgents after installing

`--check` never writes. `--apply` refuses to overwrite an existing file unless `--force`,
and when it does overwrite it keeps a timestamped backup. `--vault` on a fresh machine
where the config does not exist yet is how you register vaults by hand.

## What is parameterised (the only deviations from the live files)

The ingest logic is copied verbatim from the live script, so only four things differ:

1. `KNOWLEDGE="${KNOWLEDGE_ROOT:-<rendered value>}"` instead of `KNOWLEDGE="$HOME/knowledge"`.
2. `PATH` discovers node (`$HOME/.nvm/versions/node/*/bin`) instead of pinning
   `v24.21.0`, and adds `$HOME/.hermes/bin` and `/opt/homebrew/bin`.
3. The agent CLI is `CLAUDE_CMD="${INGEST_CLAUDE_CMD:-<rendered default>}"` and is
   resolved through a login shell, instead of hardcoding the `cla` wrapper.
4. Every `~/knowledge/...` inside the prompt the agent reads became `$KNOWLEDGE/...`,
   so a non-default vault root works.

Verified: rendering for the machine these were taken from reproduces the live
`com.ab.knowledge-ingest.plist`, `com.ab.abbrain-watcher.plist` and `abbrain-config.toml`
**byte-identically** (including a vault-specific `include` override, which the renderer
carries over from an existing config). Rendering for a foreign `HOME` produces zero
absolute home paths, passes `bash -n`, and both plists pass `plutil -lint`.

## Platform

**macOS (launchd) and Linux (systemd --user).** `install.sh` detects the platform, or
take `--platform macos|linux` to force it. On macOS it installs LaunchAgents to
`~/Library/LaunchAgents`; on Linux it installs `knowledge-ingest.service` and
`abbrain-watcher.service` to `~/.config/systemd/user` and enables them with
`systemctl --user enable --now`.

One ingest script serves both. Platform differences are detected at startup instead of
being forked:

    stat -f %m       (BSD, macOS)      vs   stat -c %Y       (GNU, Linux)
    shasum -a 256    (macOS)           vs   sha256sum        (Linux)
    textutil         (macOS)           vs   soffice / libreoffice / pandoc
    /bin/zsh         (macOS)           vs   /bin/bash

Two platform notes worth knowing: Linux user services stop at logout unless you run
`loginctl enable-linger $USER`, and if neither `sha256sum` nor `shasum` exists the
ingester now exits loudly with a log line rather than silently ingesting nothing.

### What was verified where

| check | how |
|---|---|
| macOS rendering is byte-identical | rendered vs the live plists/config: `diff` clean |
| stock-Mac toolchain | `/bin/bash` 3.2.57, `/usr/bin/python3` 3.9.6, `env -i PATH=/usr/bin:/bin` |
| both platforms render | `--platform linux` from a Mac with a foreign `$HOME`: no `/Users/...` anywhere |
| Linux detection logic | `test_platform_detection.sh` stubs stat/shasum/converters/shell across 5 cases, including "no hashing tool" which must fail fast |
| installer behaviour | fresh install, refuse-to-clobber, and `--force`-with-backup all exercised against a throwaway `$HOME` |
| unit/plist syntax | `bash -n` on the scripts, `plutil -lint` on the plists |

**Not verified:** an actual Linux run. The units are rendered and their paths checked,
but nothing here has booted under real systemd, and `systemd-analyze --user verify` is
only invoked by `--check` when you run it on the Linux box. Same for `--load` on macOS,
which registers real launchd jobs. Run `./install.sh --check` on the target first.

## What this bundle is not

- It does not install Obsidian, ollama, AB-Brain or the agent CLI, and it cannot
  authenticate them for you.
- It does not touch the RAG pipeline in this repo. Note for later: `main.py` still
  hardcodes `WIKI = "/Users/ab/knowledge/ianus/wiki"`, so the retriever itself is not yet
  portable — that path wants to become a CLI flag or env var before you move machines.
- `--load` is the one path not exercised in the sandbox test (it registers real launchd
  jobs). Everything up to and including the file copies was tested against a throwaway
  `$HOME`, including the refuse-to-clobber and `--force`-with-backup paths.

## Regenerating the templates

On a machine whose services work:

    python3 generate_templates.py     # rewrites templates/ from the live files

It substitutes only the machine-bound parts and copies the script body verbatim, so the
templates cannot drift from the implementation they were taken from.
