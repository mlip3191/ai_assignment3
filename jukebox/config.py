"""Settings for the AI Jukebox: loaded from the environment and an optional settings file.

Rules (PROJECT.md section 7.4):
  - Fail fast, naming every missing or invalid variable at once.
  - Each service URL must use its own port: Qwen 9001, FLUX 9006, ACE-Step 9007, Chatterbox 9008.
  - Port 9000 is never allowed (H5), and no fifth `*_BASE_URL` variable may exist (section 7.0).
  - A base URL is `scheme://host:port` only. A pasted trailing `/v1` is removed; any other path is refused.
  - Secrets are never printed (H8): the key is a `Secret`, and error text only names variables.

Standard library only, so it works before the app's dependencies are installed.
"""

from __future__ import annotations

import math
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE = ROOT / ".env"

FORBIDDEN_PORT = 9000
# service -> (its only allowed port, default read timeout in seconds)
SERVICES: dict[str, tuple[int, float]] = {
    "qwen": (9001, 90.0),
    "flux": (9006, 120.0),
    "acestep": (9007, 300.0),
    "chatterbox": (9008, 120.0),
}
KEY_VAR = "CLASS_API_KEY"
PLACEHOLDERS = ("CLASS_HOST", "REPLACE_WITH", "your-class-api-key-here")
DEFAULT_APP_HOST = "127.0.0.1"
DEFAULT_APP_PORT = 7860


def _var(service: str, suffix: str) -> str:
    return f"{service.upper()}_{suffix}"


KNOWN_VARS = frozenset(
    [KEY_VAR, "APP_HOST", "APP_PORT"]
    + [_var(s, suffix) for s in SERVICES for suffix in ("BASE_URL", "MODEL", "TIMEOUT_S")]
)


@dataclass(frozen=True, repr=False)
class Secret:
    """Holds a credential. Printing, logging, and formatting it all show ****."""

    _value: str = field(repr=False)

    def reveal(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return "Secret(****)"

    def __str__(self) -> str:
        return "****"


@dataclass(frozen=True)
class ServiceConfig:
    base_url: str
    model: str | None
    timeout_s: float


@dataclass(frozen=True)
class Config:
    api_key: Secret
    qwen: ServiceConfig
    flux: ServiceConfig
    acestep: ServiceConfig
    chatterbox: ServiceConfig
    app_host: str
    app_port: int

    def __str__(self) -> str:
        lines = [f"{KEY_VAR}={self.api_key}"]
        lines += [f"{_var(s, 'BASE_URL')}={_hide_host(getattr(self, s).base_url)}" for s in SERVICES]
        lines += [f"APP_HOST={self.app_host}", f"APP_PORT={self.app_port}"]
        return "\n".join(lines)


@dataclass(frozen=True)
class VarStatus:
    """One row of the variable report. `note` never contains a value."""

    var: str
    status: str  # "OK", "MISSING", or "INVALID"
    note: str


class ConfigError(Exception):
    """Raised at startup when settings are missing or invalid. Lists every problem."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("Invalid configuration:\n" + "\n".join(f"  - {p}" for p in problems))


# ---- reading values ---------------------------------------------------------------------------


def parse_env_file(path: Path) -> dict[str, str]:
    """Parse KEY=VALUE lines. Supports comments, `export`, and single or double quotes."""
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        line = line.removeprefix("export ").strip()
        key, sep, value = line.partition("=")
        if not sep:
            continue
        value = value.strip()
        if value[:1] in ("'", '"') and value.count(value[0]) >= 2:
            value = value[1 : value.index(value[0], 1)]
        else:
            value = re.split(r"\s+#", value, maxsplit=1)[0].strip()
        values[key.strip()] = value
    return values


def read_values(env: Mapping[str, str] | None, env_file: Path | None) -> dict[str, str]:
    """Settings file first, then the environment on top.

    With `env=None` the real process environment is used, but only for variables this app knows
    about, so unrelated tools' variables (for example ANTHROPIC_BASE_URL) can't break startup.
    """
    path = DEFAULT_ENV_FILE if env_file is None else env_file
    values = parse_env_file(path) if path.is_file() else {}
    if env is None:
        values.update({k: os.environ[k] for k in KNOWN_VARS if k in os.environ})
    else:
        values.update(env)
    return values


# ---- validation -------------------------------------------------------------------------------


def _is_placeholder(value: str) -> bool:
    return any(marker in value for marker in PLACEHOLDERS)


def _required(values: Mapping[str, str], var: str) -> tuple[str | None, VarStatus | None]:
    value = (values.get(var) or "").strip()
    if not value:
        return None, VarStatus(var, "MISSING", "(missing)")
    if _is_placeholder(value):
        return None, VarStatus(var, "MISSING", "still the template placeholder; set the real value")
    return value, None


def _url_problem(value: str, port: int) -> str | None:
    try:
        parts = urlsplit(value)
        found = parts.port
        host = parts.hostname
    except ValueError:
        return f"not a valid URL (expected http://host:{port})"
    if parts.scheme not in ("http", "https") or not host or " " in value:
        return f"not a valid URL (expected http://host:{port})"
    if parts.username or parts.password:
        return "must not contain a username or password"
    if found == FORBIDDEN_PORT:
        return f"port {FORBIDDEN_PORT} is never allowed (H5)"
    if found != port:
        return f"must use port {port}" + ("" if found is None else f" (not {found})")
    if parts.query or parts.fragment or parts.path.rstrip("/") not in ("", "/v1"):
        return (
            f"enter only http://host:{port} (no path, query or fragment; a trailing /v1 is removed for you)"
        )
    return None


def normalize_base_url(value: str) -> tuple[str, bool]:
    """The `scheme://host:port` form of a base URL that passed `_url_problem`, and whether a trailing
    `/v1` was removed. class-endpoints.txt lists some URLs with `/v1`, but the paths in PROJECT.md 7.1
    already include it, so keeping it would send every request to `/v1/v1/...`."""
    parts = urlsplit(value)
    return f"{parts.scheme}://{parts.netloc}", parts.path.rstrip("/") == "/v1"


def _hide_host(url: str) -> str:
    """`http://****:9001`: the port is useful in a log, the class server's address is not."""
    try:
        parts = urlsplit(url)
        return f"{parts.scheme}://****" + (f":{parts.port}" if parts.port else "")
    except ValueError:
        return "****"


def _positive_float(value: str) -> float | None:
    try:
        number = float(value)
    except ValueError:
        return None
    return number if math.isfinite(number) and number > 0 else None


def evaluate(values: Mapping[str, str]) -> tuple[list[VarStatus], Config | None]:
    """Check every variable. Returns the per-variable report, and the Config if all is valid."""
    rows: list[VarStatus] = []
    ok = True

    def add(row: VarStatus) -> None:
        nonlocal ok
        rows.append(row)
        ok = ok and row.status == "OK"

    key, bad = _required(values, KEY_VAR)
    add(bad or VarStatus(KEY_VAR, "OK", "set"))

    urls: dict[str, str] = {}
    for service, (port, _) in SERVICES.items():
        var = _var(service, "BASE_URL")
        value, bad = _required(values, var)
        note = f"set, port {port}"
        if bad is None and value is not None:
            problem = _url_problem(value, port)
            bad = VarStatus(var, "INVALID", problem) if problem else None
            if bad is None:
                urls[service], removed_v1 = normalize_base_url(value)
                if removed_v1:
                    note += " (trailing /v1 removed; the paths in PROJECT.md 7.1 already include it)"
        add(bad or VarStatus(var, "OK", note))

    models: dict[str, str | None] = {}
    for service in SERVICES:
        var = _var(service, "MODEL")
        value = (values.get(var) or "").strip()
        models[service] = value if value and not _is_placeholder(value) else None
        add(VarStatus(var, "OK", "set" if models[service] else "not set (optional)"))

    timeouts: dict[str, float] = {}
    for service, (_, default) in SERVICES.items():
        var = _var(service, "TIMEOUT_S")
        raw = (values.get(var) or "").strip()
        timeouts[service] = default
        if not raw:
            add(VarStatus(var, "OK", f"default {default:g}s"))
        elif (number := _positive_float(raw)) is None:
            add(VarStatus(var, "INVALID", "must be a positive number of seconds"))
        else:
            timeouts[service] = number
            add(VarStatus(var, "OK", "set"))

    app_host = (values.get("APP_HOST") or "").strip() or DEFAULT_APP_HOST
    add(VarStatus("APP_HOST", "OK", "set" if values.get("APP_HOST") else f"default {DEFAULT_APP_HOST}"))

    app_port = DEFAULT_APP_PORT
    raw_port = (values.get("APP_PORT") or "").strip()
    if not raw_port:
        add(VarStatus("APP_PORT", "OK", f"default {DEFAULT_APP_PORT}"))
    elif raw_port.isdigit() and 1 <= int(raw_port) <= 65535:
        app_port = int(raw_port)
        add(VarStatus("APP_PORT", "OK", "set"))
    else:
        add(VarStatus("APP_PORT", "INVALID", "must be a whole number from 1 to 65535"))

    for var in sorted(v for v in values if v.endswith("_BASE_URL") and v not in KNOWN_VARS):
        names = ", ".join(s.upper() for s in SERVICES)
        add(VarStatus(var, "INVALID", f"not one of the four class services ({names}); see PROJECT.md 7.0"))

    if not ok or key is None:
        return rows, None
    config = Config(
        api_key=Secret(key),
        **{s: ServiceConfig(urls[s], models[s], timeouts[s]) for s in SERVICES},
        app_host=app_host,
        app_port=app_port,
    )
    return rows, config


def load_config(env: Mapping[str, str] | None = None, env_file: Path | None = None) -> Config:
    """Load and validate settings, or raise ConfigError listing every problem (no secret values)."""
    rows, config = evaluate(read_values(env, env_file))
    if config is None:
        raise ConfigError([f"{r.var}: {r.note}" for r in rows if r.status != "OK"])
    return config
