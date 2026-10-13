#!/usr/bin/env python3
"""Fail if the app could use any AI model other than the four class models.

  macOS / Windows (venv active):  python scripts/check_models.py
  Check another folder (tests):   python scripts/check_models.py --root path/to/repo

The allowed models, their ports, and which feature may use which are defined in
scripts/model_policy.json (mirrored in PROJECT.md section 7.0). This checks:

  1. Dependencies: no AI SDKs, local model libraries, or other TTS/LLM/image packages
     in requirements*.txt
  2. Imports: none of those libraries imported anywhere in app code or scripts
  3. Hosts: no URLs of other AI providers (OpenAI, Anthropic, Hugging Face, ...)
  4. Code patterns: no gr.load (hosted models), no browser speech synthesis, no local pipelines
  5. Network calls only inside jukebox/clients/ (and scripts/check_endpoints.py)
  6. Each client talks to its own service only (qwen.py never mentions FLUX, etc.)
  7. Each feature imports only its allowed clients (songs: Qwen + ACE-Step, covers: Qwen + FLUX,
     DJ: Qwen + Chatterbox, player and UI: none)
  8. Ports: service URLs use exactly 9001 / 9006 / 9007 / 9008 for the right variable; never 9000;
     no other ports hard-coded in app code

Never prints secrets: from .env it reads only the *_BASE_URL lines. Exit code 1 on any violation.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
POLICY = json.loads((HERE / "model_policy.json").read_text(encoding="utf-8"))
SELF_EXEMPT = {"scripts/check_models.py", "scripts/model_policy.json"}
CODE_SUFFIXES = {".py", ".js", ".html", ".htm", ".css", ".sh", ".bat", ".ps1"}


def rel(p: Path, root: Path) -> str:
    return p.relative_to(root).as_posix()


def code_files(root: Path) -> list[Path]:
    """App code and scripts (not tests, docs, or the venv)."""
    files: list[Path] = []
    for sub in ("jukebox", "scripts"):
        d = root / sub
        if d.exists():
            files += [p for p in d.rglob("*") if p.is_file() and p.suffix in CODE_SUFFIXES]
    for name in ("app.py", "run.sh", "run.bat"):
        if (root / name).exists():
            files.append(root / name)
    return [p for p in files if rel(p, root) not in SELF_EXEMPT and "__pycache__" not in p.parts]


def norm_pkg(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def check_requirements(root: Path, out: list[str]) -> None:
    banned = {norm_pkg(p) for p in POLICY["banned_packages"]}
    for req in sorted(root.glob("requirements*.txt")):
        for i, line in enumerate(req.read_text(encoding="utf-8").splitlines(), 1):
            line = line.split("#", 1)[0].strip()
            if not line or line.startswith("-"):
                continue
            name = norm_pkg(re.split(r"[\s\[<>=!~;@]", line, maxsplit=1)[0])
            if name in banned:
                out.append(
                    f"{req.name}:{i}: dependency '{name}' is not allowed (only the 4 class models may be used)"
                )


def check_code(root: Path, out: list[str]) -> None:
    banned_mods = POLICY["banned_imports"]
    import_re = re.compile(r"^\s*(?:import|from)\s+([A-Za-z_][\w.]*)", re.M)
    host_res = [(h, re.compile(re.escape(h), re.I)) for h in POLICY["banned_hosts"]]
    pattern_res = [(re.compile(k), v) for k, v in POLICY["banned_code_patterns"].items()]
    net_re = re.compile(
        r"^\s*(?:import|from)\s+(httpx|requests|aiohttp|urllib3|urllib\.request|http\.client|websockets?)\b",
        re.M,
    )
    allowed_net = POLICY["network_allowed_files"]

    for path in code_files(root):
        name = rel(path, root)
        text = path.read_text(encoding="utf-8", errors="replace")

        def line_of(pos: int, text: str = text) -> int:
            return text.count("\n", 0, pos) + 1

        if path.suffix == ".py":
            for m in import_re.finditer(text):
                mod = m.group(1)
                for b in banned_mods:
                    if mod == b or mod.startswith(b + "."):
                        out.append(
                            f"{name}:{line_of(m.start())}: imports '{mod}', which is not one of the class models"
                        )
            if not any(name.startswith(a) for a in allowed_net):
                for m in net_re.finditer(text):
                    out.append(
                        f"{name}:{line_of(m.start())}: network library '{m.group(1)}' outside jukebox/clients/. "
                        "All AI calls must go through the four clients."
                    )
        for host, rx in host_res:
            for m in rx.finditer(text):
                out.append(f"{name}:{line_of(m.start())}: references '{host}', another AI provider")
        for rx, why in pattern_res:
            for m in rx.finditer(text):
                out.append(f"{name}:{line_of(m.start())}: '{m.group(0)}': {why}")
        # hard-coded ports in URLs inside app code
        if name.startswith("jukebox/") or name == "app.py":
            ok_ports = {s["port"] for s in POLICY["services"].values()} | {POLICY["app_port"]}
            for m in re.finditer(r"https?://[^\s'\"<>]*?:(\d{2,5})", text):
                port = int(m.group(1))
                if port not in ok_ports:
                    out.append(
                        f"{name}:{line_of(m.start())}: hard-coded URL port {port} (only the 4 class ports allowed)"
                    )


def check_client_isolation(root: Path, out: list[str]) -> None:
    services = POLICY["services"]
    aliases = POLICY["service_aliases"]
    for svc, spec in services.items():
        path = root / spec["client"]
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for other, other_spec in services.items():
            if other == svc:
                continue
            words = [*aliases[other], other_spec["env_url"], other_spec["env_model"]]
            for w in words:
                for m in re.finditer(re.escape(w), text, re.I):
                    out.append(
                        f"{spec['client']}:{text.count(chr(10), 0, m.start()) + 1}: mentions '{w}'. "
                        f"The {svc} client may only talk to {spec['model']} on port {spec['port']}."
                    )
            if re.search(rf"\b{other_spec['port']}\b", text):
                out.append(
                    f"{spec['client']}: contains port {other_spec['port']} ({other_spec['model']}'s port)"
                )


def imported_clients(text: str) -> set[str]:
    found: set[str] = set()
    for m in re.finditer(r"clients\.(\w+)", text):
        found.add(m.group(1))
    for m in re.finditer(r"clients\s+import\s+\(?([\w,\s]+)\)?", text):
        found |= {x.strip().split(" as ")[0] for x in m.group(1).split(",") if x.strip()}
    return found


def check_feature_clients(root: Path, out: list[str]) -> None:
    allow = {k: set(v) for k, v in POLICY["feature_clients"].items() if not k.startswith("_")}
    known = set(POLICY["services"])
    for path in code_files(root):
        name = rel(path, root)
        if path.suffix != ".py" or name.startswith("jukebox/clients/"):
            continue
        used = imported_clients(path.read_text(encoding="utf-8", errors="replace")) & (known | {"base"})
        permitted = allow.get(name, set())
        for c in sorted(used - permitted):
            if c == "base" and name.startswith("scripts/"):
                continue
            out.append(
                f"{name}: uses the '{c}' client, but this file may only use: {sorted(permitted) or 'no clients'} "
                "(PROJECT.md section 7.0)"
            )


def check_ports(root: Path, out: list[str]) -> None:
    services = POLICY["services"]
    for fname in (".env.example", ".env"):
        f = root / fname
        if not f.exists():
            continue
        for i, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            m = re.match(r"\s*([A-Z_]+_BASE_URL)\s*=\s*(\S*)", line)
            if not m:
                continue  # only URL lines are read; keys are never touched
            var, url = m.groups()
            pm = re.search(r":(\d+)(?:/|$)", url)
            port = int(pm.group(1)) if pm else None
            if port in POLICY["forbidden_ports"]:
                out.append(f"{fname}:{i}: {var} uses port {port}, which is forbidden")
            svc = next((s for s, spec in services.items() if spec["env_url"] == var), None)
            if svc is None:
                out.append(f"{fname}:{i}: {var} is not one of the four class services")
            elif port != services[svc]["port"]:
                out.append(
                    f"{fname}:{i}: {var} must use port {services[svc]['port']} "
                    f"({services[svc]['model']}), found {port}"
                )


def scan(root: Path) -> list[str]:
    out: list[str] = []
    check_requirements(root, out)
    check_code(root, out)
    check_client_isolation(root, out)
    check_feature_clients(root, out)
    check_ports(root, out)
    return out


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=HERE.parent)
    args = ap.parse_args()
    problems = scan(args.root.resolve())
    if problems:
        print(f"MODEL CHECK FAILED: {len(problems)} problem(s). Only these models may be used:")
        for svc in POLICY["services"].values():
            print(f"  - {svc['model']} on port {svc['port']}: {svc['purpose']}")
        print()
        for p in problems:
            print(f"  - {p}")
        return 1
    print(
        "Model check passed: only Qwen (9001), FLUX (9006), ACE-Step (9007), and Chatterbox (9008) are used."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
