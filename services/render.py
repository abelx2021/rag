#!/usr/bin/env python3
"""Render the service templates for a target machine.

Substitution is done here rather than with sed so that multi-line values (the
ingest prompt's indexing step) survive intact, and so leftover placeholders are a
hard error instead of a silently broken service.

    python3 services/render.py --out DIR --knowledge-root PATH \
        --default-claude-cmd claude --abbrain ... --vault ianus:/path ...
"""

import argparse
import re
import stat
import sys
from pathlib import Path

INDEX_STEP_WITH_ABBRAIN = (
    "Run: abbrain index update --vault-name $vault\n"
    "   (AB-Brain indexes the vault; the watcher also picks the change up on its own.)"
)
INDEX_STEP_WITHOUT_ABBRAIN = (
    "No AB-Brain on this machine - skip indexing. The vault is plain markdown and\n"
    "   works in Obsidian as-is."
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--templates", default=str(Path(__file__).resolve().parent / "templates"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--knowledge-root", required=True)
    ap.add_argument("--default-claude-cmd", required=True)
    ap.add_argument("--abbrain-python", required=True)
    ap.add_argument("--abbrain-venv-bin", required=True)
    ap.add_argument("--abbrain-config", required=True)
    ap.add_argument("--abbrain-home", required=True)
    ap.add_argument("--local-bin", required=True)
    ap.add_argument("--with-abbrain", action="store_true")
    ap.add_argument("--vault", action="append", default=[], metavar="NAME:PATH")
    ap.add_argument("--existing-config", default="",
                    help="reuse per-vault extra keys and ordering from this config")
    args = ap.parse_args()

    # vault blocks: keep any per-vault keys the existing config carries beyond
    # name/path (e.g. a vault-specific `include` override), and keep its order.
    known: list[tuple[str, str, str]] = []   # name, path, extra
    if args.existing_config and Path(args.existing_config).exists():
        text = Path(args.existing_config).read_text(encoding="utf-8")
        for block in re.findall(r"\[\[vault\]\](.*?)(?=\n\[|\Z)", text, re.S):
            name = re.search(r'name\s*=\s*"([^"]*)"', block)
            path = re.search(r'path\s*=\s*"([^"]*)"', block)
            if not name or not path:
                continue
            extra = [
                line.strip() for line in block.strip().splitlines()
                if "=" in line and not line.strip().startswith(("name", "path"))
            ]
            known.append((name.group(1), path.group(1), "\n".join(extra)))

    want = {}
    for spec in args.vault:
        name, _, path = spec.partition(":")
        want[name] = path

    ordered = [(n, want.pop(n), e) for n, p, e in known if n in want]
    ordered += [(n, p, "") for n, p in want.items()]

    vault_blocks = []
    for name, path, extra in ordered:
        block = f'[[vault]]\nname = "{name}"\npath = "{path}"'
        if extra:
            block += "\n" + extra
        vault_blocks.append(block)

    mapping = {
        "__KNOWLEDGE_ROOT__": args.knowledge_root,
        "__DEFAULT_CLAUDE_CMD__": args.default_claude_cmd,
        "__INDEX_STEP__": INDEX_STEP_WITH_ABBRAIN if args.with_abbrain else INDEX_STEP_WITHOUT_ABBRAIN,
        "__ABBRAIN_PYTHON__": args.abbrain_python,
        "__ABBRAIN_VENV_BIN__": args.abbrain_venv_bin,
        "__ABBRAIN_CONFIG__": args.abbrain_config,
        "__ABBRAIN_HOME__": args.abbrain_home,
        "__LOCAL_BIN__": args.local_bin,
        "__VAULT_BLOCKS__": "\n\n".join(vault_blocks).rstrip(),
    }

    tmpl_dir = Path(args.templates)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    written = []
    problems = []
    for tmpl in sorted(tmpl_dir.rglob("*.tmpl")):
        text = tmpl.read_text(encoding="utf-8")
        for key, value in mapping.items():
            text = text.replace(key, value)
        # any placeholder left unsubstituted is a bug, not a warning
        leftovers = sorted({t for t in text.split() if t.startswith("__") and t.endswith("__")})
        if leftovers:
            problems.append(f"{tmpl.name}: unsubstituted {leftovers}")
            continue
        rel = tmpl.relative_to(tmpl_dir)
        target = out_dir / str(rel)[: -len(".tmpl")]
        target.parent.mkdir(parents=True, exist_ok=True)
        # TOML: collapse the blank lines the placeholder leaves behind. Live configs
        # use exactly one blank line between blocks; this keeps rendering byte-identical.
        if target.suffix == ".toml":
            text = re.sub(r"\n{3,}", "\n\n", text)
        target.write_text(text, encoding="utf-8")
        if target.suffix in (".sh", ".py"):
            target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        written.append(target)

    for w in written:
        print(f"  rendered {w}")
    if problems:
        print("\n".join(f"  ERROR {p}" for p in problems), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
