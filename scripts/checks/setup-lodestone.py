#!/usr/bin/env python3
"""Detection-only env probe for deep-sota.

Reports lodestone install status, config status, and which provider API
keys are present in the environment. Never prompts, never writes config.
The skill's references/ files drive provider/model elicitation via
AskUserQuestion and Claude writes the config.toml itself.

SECURITY: only checks key *existence* via ``os.environ.get``. Key values
are never echoed or written to the JSON output.

Exit codes:
  0 — config exists, parses cleanly, provider key present (valid)
  1 — lodestone install not found
  2 — config exists but is malformed TOML / wrong shape
  3 — config selects a provider whose API key is not set
  4 — no usable config and zero provider keys in env
  5 — no usable config; ≥1 provider keys present (Claude must elicit)
"""
from __future__ import annotations

import json
import os
import sys
import tomllib
from enum import StrEnum
from pathlib import Path


_APP_NAME = "lodestone"


class Provider(StrEnum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GEMINI = "gemini"


class ConfigStatus(StrEnum):
    OK = "ok"
    MISSING = "missing"
    INCOMPLETE = "incomplete"
    MALFORMED = "malformed"
    KEY_MISSING = "key_missing"


# Mirror of lodestone's _system/llm/config.py:_ENV_KEYS
ENV_KEYS: dict[Provider, str] = {
    Provider.ANTHROPIC: "ANTHROPIC_API_KEY",
    Provider.OPENAI: "OPENAI_API_KEY",
    Provider.GEMINI: "GEMINI_API_KEY",
}


def lodestone_config_path() -> Path:
    """Same resolution as lodestone's ``_system/llm/config.py:config_path``."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        base = Path(xdg)
    elif sys.platform.startswith("win"):
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / ".config"
    else:
        base = Path.home() / ".config"
    return base / _APP_NAME / "config.toml"


def find_lodestone_install() -> str | None:
    """Locate an installed lodestone. Returns a human-readable path or None.

    Checks (in order):
      1. ``~/.claude/plugins/cache/*/lodestone/*/`` — marketplace install
      2. ``~/Personal/Code/lodestone`` — common dev clone
      3. ``lodestone-mcp`` on PATH (uv tool entry point)
    """
    cache_root = Path.home() / ".claude" / "plugins" / "cache"
    if cache_root.is_dir():
        for marketplace in cache_root.iterdir():
            ld = marketplace / "lodestone"
            if ld.is_dir():
                versions = [v for v in ld.iterdir() if v.is_dir()]
                if versions:
                    return str(sorted(versions)[-1])

    dev = Path.home() / "Personal" / "Code" / "lodestone"
    if (dev / "pyproject.toml").exists() and (dev / "_system").is_dir():
        return str(dev)

    for d in os.environ.get("PATH", "").split(os.pathsep):
        candidate = Path(d) / "lodestone-mcp"
        if candidate.exists():
            return str(candidate)

    return None


def providers_with_env_keys() -> list[str]:
    return [p.value for p, var in ENV_KEYS.items() if os.environ.get(var)]


def load_existing_config(path: Path) -> tuple[Provider, str | None] | None:
    """Return ``(provider, model)`` if the config parses, None if the file
    does not exist. Raises ValueError on malformed TOML / unknown provider.
    """
    if not path.exists():
        return None
    raw = path.read_bytes()
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"not valid TOML: {exc}") from exc
    llm = data.get("llm")
    if not isinstance(llm, dict):
        raise ValueError("missing [llm] section")
    provider_raw = llm.get("provider")
    if not isinstance(provider_raw, str):
        raise ValueError("[llm].provider missing or not a string")
    try:
        provider = Provider(provider_raw)
    except ValueError as exc:
        raise ValueError(
            f"[llm].provider={provider_raw!r} is not one of "
            f"{[p.value for p in Provider]}"
        ) from exc
    model = llm.get("model")
    if model is not None and not isinstance(model, str):
        raise ValueError("[llm].model must be a string if set")
    return provider, model


def emit(
    *,
    valid: bool,
    exit_code: int,
    config_status: ConfigStatus,
    install_path: str | None,
    config_path: Path,
    provider: str | None = None,
    model: str | None = None,
    keys: list[str] | None = None,
    errors: list[str] | None = None,
    warnings: list[str] | None = None,
) -> None:
    print(json.dumps({
        "valid": valid,
        "errors": errors or [],
        "warnings": warnings or [],
        "lodestone_install": install_path,
        "config_path": str(config_path),
        "config_status": config_status.value,
        "config_provider": provider,
        "config_model": model,
        "providers_with_keys": keys if keys is not None else providers_with_env_keys(),
    }))
    sys.exit(exit_code)


def main() -> None:
    config_path = lodestone_config_path()

    install_path = find_lodestone_install()
    if install_path is None:
        emit(
            valid=False,
            exit_code=1,
            config_status=ConfigStatus.MISSING,
            install_path=None,
            config_path=config_path,
            errors=[
                "lodestone install not found. Install via the Claude Code "
                "marketplace (piercelamb-plugins → lodestone) or clone "
                "https://github.com/piercelamb/lodestone."
            ],
        )

    try:
        existing = load_existing_config(config_path)
    except ValueError as exc:
        emit(
            valid=False,
            exit_code=2,
            config_status=ConfigStatus.MALFORMED,
            install_path=install_path,
            config_path=config_path,
            errors=[f"lodestone config at {config_path} is malformed: {exc}"],
        )
        return  # unreachable

    if existing is not None:
        provider, model = existing
        env_name = ENV_KEYS[provider]
        if not os.environ.get(env_name):
            emit(
                valid=False,
                exit_code=3,
                config_status=ConfigStatus.KEY_MISSING,
                install_path=install_path,
                config_path=config_path,
                provider=provider.value,
                model=model,
                errors=[
                    f"lodestone config selects provider={provider.value!r} "
                    f"but ${env_name} is not set. Either export ${env_name} "
                    f"or edit {config_path} to pick a provider whose key is "
                    f"present."
                ],
            )
            return  # unreachable

        if model is None:
            # provider pinned but no model — Claude must elicit model only
            emit(
                valid=False,
                exit_code=5,
                config_status=ConfigStatus.INCOMPLETE,
                install_path=install_path,
                config_path=config_path,
                provider=provider.value,
                model=None,
            )
            return  # unreachable

        emit(
            valid=True,
            exit_code=0,
            config_status=ConfigStatus.OK,
            install_path=install_path,
            config_path=config_path,
            provider=provider.value,
            model=model,
        )
        return  # unreachable

    # No config — let Claude drive the picker.
    present = providers_with_env_keys()
    if not present:
        names = ", ".join(f"${v}" for v in ENV_KEYS.values())
        emit(
            valid=False,
            exit_code=4,
            config_status=ConfigStatus.MISSING,
            install_path=install_path,
            config_path=config_path,
            keys=[],
            errors=[
                f"no lodestone config at {config_path} and no provider API "
                f"key in the environment. Set one of: {names}, then re-run."
            ],
        )
        return  # unreachable

    emit(
        valid=False,
        exit_code=5,
        config_status=ConfigStatus.MISSING,
        install_path=install_path,
        config_path=config_path,
        keys=present,
    )


if __name__ == "__main__":
    main()
