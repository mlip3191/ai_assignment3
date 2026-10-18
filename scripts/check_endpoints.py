#!/usr/bin/env python3
"""Ask each class service which model it is serving, and print PASS or FAIL per service.

  python scripts/check_endpoints.py
  python scripts/check_endpoints.py --env-file path/to/settings

Sends one small request to each of the four services (GET /v1/models; it uses no GPU time) and checks
that the port answers as the model PROJECT.md section 7.0 expects. A port serving a different model
is a FAIL. Never prints the key or the server addresses. Exit code 0 when all four pass, else 1.
Same command on macOS and Windows.
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jukebox.clients.base import ServiceClient  # noqa: E402
from jukebox.config import DEFAULT_ENV_FILE, SERVICES, Config, ConfigError, load_config  # noqa: E402
from jukebox.errors import ServiceError, redact, user_message  # noqa: E402

# jukebox/config.py removes a pasted trailing /v1 from every base URL, so this is always appended whole
MODELS_PATH = "v1/models"
CHECK_TIMEOUT_S = 15.0  # a model list is instant; don't wait out the 300 s music timeout
MAX_LISTED = 3
MAX_ID_CHARS = 60

# service -> (name in PROJECT.md 7.0, lowercase text its model id must contain)
EXPECTED: dict[str, tuple[str, str]] = {
    "qwen": ("Qwen3.6-35B-A3B", "qwen3.6-35b-a3b"),
    "flux": ("FLUX.2 klein 4B", "flux.2-klein-4b"),
    "acestep": ("ACE-Step 1.5 XL Turbo", "acestep-v15-xl-turbo"),
    "chatterbox": ("Chatterbox Multilingual V3", "chatterbox-v3"),
}


@dataclass(frozen=True)
class Result:
    service: str
    passed: bool
    latency_ms: int
    note: str


def short(model_id: str) -> str:
    """Compare model ids without their organisation prefix: `ACE-Step/x` and `acestep/x` match."""
    return model_id.strip().lower().rsplit("/", 1)[-1]


def listed_models(body: object) -> list[str]:
    """The ids in an OpenAI-style models list: {"data": [{"id": ...}, ...]}. Empty if it isn't one."""
    items = body.get("data") if isinstance(body, dict) else None
    if not isinstance(items, list):
        return []
    return [
        i["id"] for i in items if isinstance(i, dict) and isinstance(i.get("id"), str) and i["id"].strip()
    ]


def judge(service: str, ids: list[str], configured: str | None, secrets: list[str]) -> tuple[bool, str]:
    """Decide PASS/FAIL from the model ids a service reported."""
    name, family = EXPECTED[service]
    if not ids:
        return False, f"answered, but did not list a model name where {name} was expected"
    shown = ", ".join(redact(i, secrets)[:MAX_ID_CHARS] for i in ids[:MAX_LISTED])
    if len(ids) > MAX_LISTED:
        shown += ", ..."
    if not any(family in short(i) for i in ids):
        return False, f"serves {shown}, but {name} was expected"
    if configured and short(configured) not in {short(i) for i in ids}:
        var = f"{service.upper()}_MODEL"
        return False, f"{var} in your settings file isn't offered by this service (it offers {shown})"
    return True, f"serves {shown}"


def check_service(
    service: str, config: Config, secrets: list[str], *, sleep: Callable[[float], None]
) -> Result:
    settings = getattr(config, service)
    quick = dataclasses.replace(settings, timeout_s=min(settings.timeout_s, CHECK_TIMEOUT_S))
    started = time.perf_counter()
    try:
        with ServiceClient(service, dataclasses.replace(config, **{service: quick}), sleep=sleep) as client:  # type: ignore[arg-type]
            response = client.request("GET", MODELS_PATH)
            elapsed = round((time.perf_counter() - started) * 1000)
            body = client.json_body(response)
    except ServiceError as e:
        return Result(service, False, round((time.perf_counter() - started) * 1000), user_message(e))
    ok, note = judge(service, listed_models(body), settings.model, secrets)
    return Result(service, ok, elapsed, note)


def main(
    argv: Sequence[str] | None = None,
    env: Mapping[str, str] | None = None,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
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
    try:
        config = load_config(env, args.env_file)
    except ConfigError as e:
        print("Can't check the services yet: your settings need fixing first.")
        for problem in e.problems:
            print(f"  - {problem}")
        print("Run `python scripts/check_config.py` for the full list.")
        return 1

    secrets = [config.api_key.reveal()]
    results = [check_service(s, config, secrets, sleep=sleep) for s in SERVICES]

    print(f"{'Service'.ljust(10)}  {'Port'.ljust(4)}  {'Result'.ljust(6)}  {'Latency'.ljust(8)}  Note")
    for r in results:
        latency = f"{r.latency_ms} ms"
        verdict = "PASS" if r.passed else "FAIL"
        port = str(SERVICES[r.service][0])
        print(f"{r.service.ljust(10)}  {port.ljust(4)}  {verdict.ljust(6)}  {latency.ljust(8)}  {r.note}")

    failed = [r for r in results if not r.passed]
    print()
    if failed:
        print(f"{len(failed)} of {len(results)} services failed. Fix the notes above, then run this again.")
        return 1
    print("All services answered as the expected models.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
