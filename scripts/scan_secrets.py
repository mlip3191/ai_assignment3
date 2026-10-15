#!/usr/bin/env python3
"""Fail if credentials, forbidden files, or port-9000 usage are in the repo or a release ZIP.

Usage:
  python scripts/scan_secrets.py                 # scan files tracked by git
  python scripts/scan_secrets.py --zip path.zip  # scan a downloaded release ZIP

Checks:
  1. Forbidden files: .env, anything under runtime/, audio outside samples/audio/
  2. Key-like strings (api_key=..., Bearer ..., sk-...) that aren't obvious placeholders
  3. The literal values from your local .env (if present) appearing anywhere
  4. Port 9000 in app code or .env.example (rule H5)

Never prints a matched secret; shows file:line and a masked preview only.
Exit code 1 if anything is found.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIO_EXT = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac"}
BINARY_EXT = AUDIO_EXT | {".png", ".jpg", ".jpeg", ".gif", ".webp", ".zip", ".pdf", ".ico"}
PLACEHOLDER = re.compile(
    r"(your[-_]|replace|example|placeholder|changeme|xxx|\*\*\*|<.*>|dummy|test[-_]?key|fake)", re.I
)
PATTERNS = [
    re.compile(r"(?i)(\w*(?:key|token|secret|password)|authorization)\s*[:=]\s*['\"]?([A-Za-z0-9_\-.]{16,})"),
    re.compile(r"(?i)bearer\s+([A-Za-z0-9_\-.]{20,})"),
    re.compile(r"\b(sk-[A-Za-z0-9_\-]{20,})"),
]
PORT_9000 = re.compile(r":9000(?!\d)")
PORT_CHECK_PREFIXES = ("jukebox/", "app.py", ".env.example", "run.sh", "run.bat")
SELF_ALLOW = {"scripts/scan_secrets.py", ".claude/hooks/pre_bash_guard.py"}


def looks_secret(val: str) -> bool:
    """Filter out code like `api_key=settings.class_api_key`; keep random-looking strings."""
    if re.fullmatch(r"[A-Za-z_]+(\.[A-Za-z_]+)*", val):
        return False
    return bool(re.search(r"\d", val)) and bool(re.search(r"[A-Za-z]", val)) and len(set(val)) >= 8


def mask(s: str) -> str:
    return s[:3] + "…" + f"({len(s)} chars)"


def local_env_values() -> list[str]:
    env = ROOT / ".env"
    vals = []
    if env.exists():
        for line in env.read_text(encoding="utf-8", errors="ignore").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                v = v.strip().strip("'\"")
                # Unfilled template values (your-class-api-key-here) aren't secrets.
                if (
                    re.search(r"(?i)key|token|secret|password", k)
                    and len(v) >= 8
                    and not PLACEHOLDER.search(v)
                ):
                    vals.append(v)
    return vals


def scan_text(name: str, text: str, env_vals: list[str], findings: list[str]) -> None:
    if name in SELF_ALLOW:
        return
    for i, line in enumerate(text.splitlines(), 1):
        for pat in PATTERNS:
            for m in pat.finditer(line):
                val = m.group(m.lastindex or 0)
                if looks_secret(val) and not PLACEHOLDER.search(line):
                    findings.append(f"{name}:{i}: key-like value {mask(val)}")
        for v in env_vals:
            if v in line:
                findings.append(f"{name}:{i}: contains a value from your local .env {mask(v)}")
        if name.startswith(PORT_CHECK_PREFIXES) and PORT_9000.search(line):
            findings.append(f"{name}:{i}: uses port 9000 (forbidden for app requests)")


def check_path(name: str, findings: list[str]) -> None:
    p = Path(name)
    if p.name == ".env" or (p.name.startswith(".env.") and p.name != ".env.example"):
        findings.append(f"{name}: env file must never be committed or zipped")
    if name.startswith("runtime/") or "/runtime/" in name:
        findings.append(f"{name}: runtime/ (generated files, uploads) must never be committed or zipped")
    if p.suffix.lower() in AUDIO_EXT and "samples/audio/" not in name:
        findings.append(
            f"{name}: audio outside samples/audio/ (voice references/uploads must never be committed)"
        )


def scan_repo(env_vals: list[str]) -> list[str]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if out.returncode != 0:
        sys.exit("Not a git repository; run from the repo or use --zip.")
    findings: list[str] = []
    for name in out.stdout.splitlines():
        check_path(name, findings)
        path = ROOT / name
        if path.suffix.lower() in BINARY_EXT or not path.is_file():
            continue
        try:
            scan_text(name, path.read_text(encoding="utf-8"), env_vals, findings)
        except UnicodeDecodeError:
            continue
    return findings


def scan_zip(zpath: Path, env_vals: list[str]) -> list[str]:
    findings: list[str] = []
    with zipfile.ZipFile(zpath) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            # GitHub ZIPs wrap everything in "<repo>-<ref>/"
            name = info.filename.split("/", 1)[1] if "/" in info.filename else info.filename
            check_path(name, findings)
            if Path(name).suffix.lower() in BINARY_EXT:
                continue
            try:
                scan_text(name, z.read(info).decode("utf-8"), env_vals, findings)
            except UnicodeDecodeError:
                continue
    return findings


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", type=Path, help="scan a release ZIP instead of tracked files")
    args = ap.parse_args()

    env_vals = local_env_values()
    findings = scan_zip(args.zip, env_vals) if args.zip else scan_repo(env_vals)
    target = str(args.zip) if args.zip else "tracked files"
    if findings:
        print(f"SECRET SCAN FAILED ({target}): {len(findings)} finding(s)")
        for f in findings:
            print(f"  - {f}")
        sys.exit(1)
    extra = " (also checked your local .env values)" if env_vals else ""
    print(f"Secret scan passed: {target}{extra}")


if __name__ == "__main__":
    main()
