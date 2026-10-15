#!/usr/bin/env python3
"""Check your settings file and print one OK / MISSING / INVALID row per variable.

  python scripts/check_config.py
  python scripts/check_config.py --env-file path/to/settings

Never prints a value: not the key, not the URLs, not the model names. Exit code 0 when
everything is valid, 1 otherwise. Same command on macOS and Windows.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jukebox.config import DEFAULT_ENV_FILE, evaluate, read_values  # noqa: E402


def main(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    """`env=None` reads the real process environment; tests pass `{}` to stay isolated."""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE, help="settings file (default: .env)")
    args = ap.parse_args(argv)

    if not args.env_file.is_file():
        print(f"Settings file not found: {args.env_file}")
        print("Create it with `python scripts/setup_dev.py` (it copies .env.example), then fill it in.\n")

    rows, _ = evaluate(read_values(env, args.env_file))
    width = max(len(r.var) for r in rows)
    print(f"{'Variable'.ljust(width)}  Status   Note")
    for r in rows:
        print(f"{r.var.ljust(width)}  {r.status.ljust(7)}  {r.note}")

    bad = [r for r in rows if r.status != "OK"]
    print()
    if bad:
        print(f"{len(bad)} problem(s). Fix them in your settings file; see PROJECT.md section 7.4.")
        return 1
    print("Configuration OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
