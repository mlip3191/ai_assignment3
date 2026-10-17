"""Tests for jukebox/config.py: required variables, one port per service, no port 9000, no secrets in output."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jukebox.config import Config, ConfigError, evaluate, load_config  # noqa: E402

KEY = "test-key-0123456789"
FORBIDDEN_PORT = 9 * 1000  # built from a number so no literal URL with this port appears in the repo
PORTS = {"QWEN": 9001, "FLUX": 9006, "ACESTEP": 9007, "CHATTERBOX": 9008}


def url(port: int, path: str = "") -> str:
    return f"http://class.example:{port}{path}"


def good_env() -> dict[str, str]:
    env = {"CLASS_API_KEY": KEY}
    for name, port in PORTS.items():
        env[f"{name}_BASE_URL"] = url(port)
        env[f"{name}_MODEL"] = f"{name.lower()}-model"
    return env


def load(env: dict[str, str], tmp_path: Path) -> Config:
    """Load with an explicit env and no file, so the real settings are never touched."""
    return load_config(env=env, env_file=tmp_path / "missing-file")


def problems(env: dict[str, str], tmp_path: Path) -> list[str]:
    with pytest.raises(ConfigError) as exc:
        load(env, tmp_path)
    return exc.value.problems


# ---- happy path -------------------------------------------------------------------------------


def test_valid_env_loads(tmp_path: Path) -> None:
    cfg = load(good_env(), tmp_path)
    assert cfg.qwen.base_url == url(9001)
    assert cfg.flux.base_url == url(9006)
    assert cfg.acestep.base_url == url(9007)
    assert cfg.chatterbox.base_url == url(9008)
    assert cfg.api_key.reveal() == KEY


def test_models_are_loaded(tmp_path: Path) -> None:
    cfg = load(good_env(), tmp_path)
    assert cfg.qwen.model == "qwen-model"
    assert cfg.chatterbox.model == "chatterbox-model"


@pytest.mark.parametrize("name", list(PORTS))
@pytest.mark.parametrize("suffix", ["/v1", "/v1/", "/"])
def test_trailing_v1_and_slash_are_removed(name: str, suffix: str, tmp_path: Path) -> None:
    env = good_env() | {f"{name}_BASE_URL": url(PORTS[name], suffix)}
    assert getattr(load(env, tmp_path), name.lower()).base_url == url(PORTS[name])


def test_optional_values_default(tmp_path: Path) -> None:
    cfg = load(good_env(), tmp_path)
    assert (cfg.acestep.timeout_s, cfg.flux.timeout_s) == (300.0, 120.0)
    assert (cfg.chatterbox.timeout_s, cfg.qwen.timeout_s) == (120.0, 90.0)
    assert (cfg.app_host, cfg.app_port) == ("127.0.0.1", 7860)


def test_optional_values_override(tmp_path: Path) -> None:
    env = good_env() | {"ACESTEP_TIMEOUT_S": "42.5", "APP_PORT": "8080", "APP_HOST": "0.0.0.0"}
    cfg = load(env, tmp_path)
    assert (cfg.acestep.timeout_s, cfg.app_port, cfg.app_host) == (42.5, 8080, "0.0.0.0")


def test_model_is_optional(tmp_path: Path) -> None:
    env = good_env()
    del env["FLUX_MODEL"]
    assert load(env, tmp_path).flux.model is None


def test_model_placeholder_counts_as_not_set(tmp_path: Path) -> None:
    env = good_env() | {"FLUX_MODEL": "REPLACE_WITH_FLUX.2_KLEIN_4B_NAME_FROM_DOCS"}
    assert load(env, tmp_path).flux.model is None


# ---- sources ----------------------------------------------------------------------------------


def write_env_file(path: Path, env: dict[str, str]) -> Path:
    lines = ["# a comment", "", *(f"{k}={v}" for k, v in env.items())]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_reads_the_env_file(tmp_path: Path) -> None:
    f = write_env_file(tmp_path / "settings", good_env())
    cfg = load_config(env={}, env_file=f)
    assert cfg.api_key.reveal() == KEY
    assert cfg.acestep.base_url == url(9007)


def test_env_file_handles_quotes_and_export(tmp_path: Path) -> None:
    f = tmp_path / "settings"
    f.write_text(
        "\n".join(
            [
                f"export CLASS_API_KEY='{KEY}'",
                f'QWEN_BASE_URL="{url(9001)}"',
                f"FLUX_BASE_URL={url(9006)}  # trailing comment",
                f"ACESTEP_BASE_URL={url(9007)}",
                f"CHATTERBOX_BASE_URL={url(9008)}",
            ]
        ),
        encoding="utf-8",
    )
    cfg = load_config(env={}, env_file=f)
    assert cfg.api_key.reveal() == KEY
    assert cfg.qwen.base_url == url(9001)
    assert cfg.flux.base_url == url(9006)


def test_process_env_wins_over_file(tmp_path: Path) -> None:
    f = write_env_file(tmp_path / "settings", good_env())
    cfg = load_config(env={"CLASS_API_KEY": "other-key-9876543210"}, env_file=f)
    assert cfg.api_key.reveal() == "other-key-9876543210"
    assert cfg.qwen.base_url == url(9001)


def test_real_process_env_only_supplies_known_names(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Other tools set variables such as ANTHROPIC_BASE_URL; those must not break startup."""
    f = write_env_file(tmp_path / "settings", good_env())
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://example.invalid")
    assert load_config(env=None, env_file=f).qwen.base_url == url(9001)


# ---- missing / placeholder values -------------------------------------------------------------


@pytest.mark.parametrize("var", ["CLASS_API_KEY", *(f"{n}_BASE_URL" for n in PORTS)])
def test_each_missing_required_variable_is_named(var: str, tmp_path: Path) -> None:
    env = good_env()
    del env[var]
    found = problems(env, tmp_path)
    assert any(var in p and "missing" in p for p in found)


def test_all_problems_are_reported_together(tmp_path: Path) -> None:
    found = problems({}, tmp_path)
    assert len(found) == 5  # the key and four URLs


def test_empty_value_counts_as_missing(tmp_path: Path) -> None:
    assert any("CLASS_API_KEY" in p for p in problems(good_env() | {"CLASS_API_KEY": ""}, tmp_path))


@pytest.mark.parametrize(
    ("var", "value"),
    [
        ("CLASS_API_KEY", "your-class-api-key-here"),
        ("QWEN_BASE_URL", "http://CLASS_HOST:9001"),
    ],
)
def test_template_placeholders_count_as_missing(var: str, value: str, tmp_path: Path) -> None:
    found = problems(good_env() | {var: value}, tmp_path)
    assert any(var in p and "placeholder" in p for p in found)


# ---- ports ------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", list(PORTS))
def test_port_9000_is_refused_for_any_service(name: str, tmp_path: Path) -> None:
    found = problems(good_env() | {f"{name}_BASE_URL": url(FORBIDDEN_PORT)}, tmp_path)
    assert any(f"{name}_BASE_URL" in p and "never allowed" in p for p in found)


def test_each_url_must_use_its_own_port(tmp_path: Path) -> None:
    env = good_env() | {"QWEN_BASE_URL": url(9006), "FLUX_BASE_URL": url(9001)}
    found = problems(env, tmp_path)
    assert any("QWEN_BASE_URL" in p and "9001" in p for p in found)
    assert any("FLUX_BASE_URL" in p and "9006" in p for p in found)


def test_url_without_a_port_is_refused(tmp_path: Path) -> None:
    found = problems(good_env() | {"QWEN_BASE_URL": "http://class.example"}, tmp_path)
    assert any("QWEN_BASE_URL" in p and "9001" in p for p in found)


@pytest.mark.parametrize(
    "bad", ["ftp://class.example:9001", "class.example:9001", "http://:9001", "not a url"]
)
def test_malformed_url_is_refused(bad: str, tmp_path: Path) -> None:
    found = problems(good_env() | {"QWEN_BASE_URL": bad}, tmp_path)
    assert any("QWEN_BASE_URL" in p for p in found)


# ---- no fifth AI service ----------------------------------------------------------------------


def test_unknown_base_url_variable_is_rejected(tmp_path: Path) -> None:
    found = problems(good_env() | {"OPENAI_BASE_URL": url(9002)}, tmp_path)
    assert any("OPENAI_BASE_URL" in p and "not one of" in p for p in found)


def test_unknown_base_url_in_the_file_is_rejected(tmp_path: Path) -> None:
    f = write_env_file(tmp_path / "settings", good_env() | {"HERMES_BASE_URL": url(FORBIDDEN_PORT)})
    with pytest.raises(ConfigError) as exc:
        load_config(env={}, env_file=f)
    assert any("HERMES_BASE_URL" in p for p in exc.value.problems)


# ---- invalid optional values ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("var", "value"),
    [
        ("QWEN_TIMEOUT_S", "soon"),
        ("QWEN_TIMEOUT_S", "0"),
        ("QWEN_TIMEOUT_S", "-5"),
        ("APP_PORT", "abc"),
        ("APP_PORT", "70000"),
    ],
)
def test_invalid_optional_values_are_reported(var: str, value: str, tmp_path: Path) -> None:
    assert any(var in p for p in problems(good_env() | {var: value}, tmp_path))


# ---- secrets never appear (H8) ----------------------------------------------------------------


def test_key_is_masked_in_repr_and_str(tmp_path: Path) -> None:
    cfg = load(good_env(), tmp_path)
    for text in (repr(cfg), str(cfg), repr(cfg.api_key), str(cfg.api_key), f"{cfg.api_key}", f"{cfg!r}"):
        assert KEY not in text
    assert "CLASS_API_KEY=****" in str(cfg)


def test_missing_key_is_shown_as_missing_not_blank(tmp_path: Path) -> None:
    found = problems({k: v for k, v in good_env().items() if k != "CLASS_API_KEY"}, tmp_path)
    assert any("CLASS_API_KEY" in p and "(missing)" in p for p in found)


def test_error_text_never_contains_the_key_or_url_credentials(tmp_path: Path) -> None:
    env = good_env() | {"QWEN_BASE_URL": f"http://user:hunter2pw@class.example:{FORBIDDEN_PORT}"}
    with pytest.raises(ConfigError) as exc:
        load(env, tmp_path)
    shown = str(exc.value) + repr(exc.value) + " ".join(exc.value.problems)
    assert KEY not in shown
    assert "hunter2pw" not in shown


def test_config_is_immutable(tmp_path: Path) -> None:
    cfg = load(good_env(), tmp_path)
    with pytest.raises(AttributeError):
        cfg.app_port = 1  # type: ignore[misc]


def test_str_hides_the_host_but_keeps_the_port(tmp_path: Path) -> None:
    text = str(load(good_env(), tmp_path))
    assert "class.example" not in text  # logging str(config) must not put the class hosts in a log
    assert "QWEN_BASE_URL=http://****:9001" in text


# ---- a base URL is only scheme://host:port; a pasted /v1 is removed, anything else is refused ----


def test_trailing_v1_is_noted_in_the_report() -> None:
    rows, config = evaluate(good_env() | {"QWEN_BASE_URL": url(9001, "/v1")})
    by_var = {r.var: r for r in rows}
    assert config is not None and by_var["QWEN_BASE_URL"].status == "OK"
    assert "/v1" in by_var["QWEN_BASE_URL"].note and "removed" in by_var["QWEN_BASE_URL"].note
    assert "removed" not in by_var["FLUX_BASE_URL"].note
    assert "class.example" not in by_var["QWEN_BASE_URL"].note  # names and notes only, never values


@pytest.mark.parametrize("path", ["/api", "/v2", "/v1/extra", "/v1/v1", "/a/b"])
def test_other_paths_are_refused(path: str, tmp_path: Path) -> None:
    found = problems(good_env() | {"QWEN_BASE_URL": url(9001, path)}, tmp_path)
    assert any("QWEN_BASE_URL" in p and "only http://host:9001" in p for p in found)


@pytest.mark.parametrize("suffix", ["?x=1", "#frag", "/v1?x=1"])
def test_query_and_fragment_are_refused(suffix: str, tmp_path: Path) -> None:
    found = problems(good_env() | {"QWEN_BASE_URL": url(9001, suffix)}, tmp_path)
    assert any("QWEN_BASE_URL" in p and "only http://host:9001" in p for p in found)


def test_port_rules_still_apply_when_the_url_has_v1(tmp_path: Path) -> None:
    found = problems(good_env() | {"QWEN_BASE_URL": url(FORBIDDEN_PORT, "/v1")}, tmp_path)
    assert any("QWEN_BASE_URL" in p and str(FORBIDDEN_PORT) in p for p in found)
    found = problems(good_env() | {"FLUX_BASE_URL": url(9001, "/v1")}, tmp_path)  # FLUX must use 9006
    assert any("FLUX_BASE_URL" in p and "9006" in p for p in found)
