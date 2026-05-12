#!/usr/bin/env python3
"""Verify lodestone is installed and configured, mirroring lodestone's
first-run flow.

This script does what `_system/llm/selection.py` does inside lodestone,
but as a standalone validator that runs BEFORE any lodestone CLI / MCP
tool call. It:

1. Detects an installed lodestone (Claude Code plugin cache or dev clone).
2. Reads / writes ``~/.config/lodestone/config.toml`` — the same XDG path
   lodestone itself uses (``$XDG_CONFIG_HOME/lodestone/config.toml``,
   defaulting to ``~/.config/lodestone/config.toml`` on POSIX).
3. If the config is missing and stdin is a TTY, prompts the user to pick
   a provider (from API keys present in the env) and a model from that
   provider's known-good catalog, then persists both.
4. Emits a single JSON object on stdout describing the final state.

SECURITY: We only test API-key *existence* with ``os.environ.get``. Key
values are never echoed or written to the JSON output.

Exit codes:
  0 — valid (lodestone present + config resolved)
  1 — config missing & no provider env vars set (cannot prompt)
  2 — config selects a provider whose API key is not set
  3 — config file exists but is malformed
  4 — lodestone install not found
  5 — multiple provider keys set, non-TTY (cannot disambiguate)
"""
from __future__ import annotations

import json
import os
import sys
import tomllib
from enum import StrEnum
from pathlib import Path


_APP_NAME = "lodestone"
DEFAULT_TEMPERATURE = 1.0


class Provider(StrEnum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GEMINI = "gemini"


# Mirror of _system/llm/config.py:_ENV_KEYS
ENV_KEYS: dict[Provider, str] = {
    Provider.ANTHROPIC: "ANTHROPIC_API_KEY",
    Provider.OPENAI: "OPENAI_API_KEY",
    Provider.GEMINI: "GEMINI_API_KEY",
}

# Mirror of each adapter's MODEL_CATALOG (kept in sync by hand — if
# lodestone adds a model, update here too). First entry is the default.
MODEL_CATALOGS: dict[Provider, list[tuple[str, str]]] = {
    Provider.ANTHROPIC: [
        ("claude-opus-4-7", "most capable, recommended"),
        ("claude-sonnet-4-6", "balanced speed + intelligence"),
        ("claude-haiku-4-5", "fastest, lowest cost"),
    ],
    Provider.OPENAI: [
        ("gpt-5.4", "most capable, recommended"),
        ("gpt-5.4-mini", "faster, lower cost"),
        ("gpt-5.4-pro", "deepest reasoning"),
        ("gpt-5.4-nano", "cheapest, fastest"),
    ],
    Provider.GEMINI: [
        ("gemini-2.5-pro", "most capable GA, recommended"),
        ("gemini-2.5-flash", "fast, balanced"),
        ("gemini-2.5-flash-lite", "fastest, lowest cost"),
        ("gemini-3.1-pro-preview", "preview — experimental frontier"),
    ],
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
    """Locate an installed lodestone. Returns a human-readable path or
    None. Checks (in order):

    1. ``~/.claude/plugins/cache/*/lodestone/*/`` — marketplace install
    2. ``~/Personal/Code/lodestone`` — common dev clone location
    3. ``lodestone-mcp`` on PATH (entry point installed via uv tool)
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


def providers_with_env_keys() -> list[Provider]:
    return [p for p, var in ENV_KEYS.items() if os.environ.get(var)]


def load_existing_config(path: Path) -> tuple[Provider, str | None, float | None] | None:
    """Return ``(provider, model, temperature)`` if the config parses,
    None if the file does not exist. Raises ValueError on malformed TOML
    or unknown provider.
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
    temperature = llm.get("temperature")
    if temperature is not None and not isinstance(temperature, (int, float)):
        raise ValueError("[llm].temperature must be a number if set")
    return provider, model, (float(temperature) if temperature is not None else None)


def _toml_escape(s: str) -> str:
    """Escape a string for a TOML basic string literal."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def write_config(path: Path, provider: Provider, model: str, temperature: float) -> None:
    """Write a minimal `[llm]` config TOML — same shape lodestone writes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    body = (
        "[llm]\n"
        f'provider = "{_toml_escape(provider.value)}"\n'
        f'model = "{_toml_escape(model)}"\n'
        f"temperature = {temperature}\n"
    )
    path.write_bytes(body.encode("utf-8"))


def print_intro() -> None:
    """Same wording lodestone prints on first run — explains what the
    LLM is used for and where the picked config lives.
    """
    print(
        "\n"
        "Lodestone uses an LLM to classify each ingested paper: given the\n"
        "paper and your current research taxonomy, it assigns a domain and\n"
        "collection and tags salient topics. That's the only place an LLM\n"
        "is called — fetch, convert, extract, and index run without it.\n"
        "\n"
        "Scope of LLM usage:\n"
        "  - one structured call per paper (classify stage only)\n"
        "  - prompt is your current taxonomy (domains + collections) plus\n"
        "    the first 8000 characters of the paper body\n"
        "  - response is constrained to a fixed JSON schema (index picks\n"
        "    into the taxonomy + short topic strings)\n"
        "  - your pick is saved to ~/.config/lodestone/config.toml and\n"
        "    reused silently on future runs; edit that file to change it\n",
        file=sys.stderr,
    )


def prompt_for_provider(candidates: list[Provider]) -> Provider:
    print(
        "Multiple provider API keys are set — pick one to use for classify:",
        file=sys.stderr,
    )
    for i, p in enumerate(candidates, start=1):
        print(f"  {i}. {p.value} ({ENV_KEYS[p]})", file=sys.stderr)
    while True:
        raw = input(f"Pick [1-{len(candidates)}]: ").strip()
        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(candidates):
                return candidates[idx - 1]
        print("invalid selection", file=sys.stderr)


def prompt_for_model(provider: Provider) -> str:
    catalog = MODEL_CATALOGS[provider]
    default = catalog[0][0]
    print(f"Model for {provider.value} [default: {default}]:", file=sys.stderr)
    for i, (mid, desc) in enumerate(catalog, start=1):
        print(f"  {i}. {mid} — {desc}", file=sys.stderr)
    while True:
        raw = input(
            f"Pick [1-{len(catalog)}], enter for default, "
            f"or type a custom model ID: "
        ).strip()
        if not raw:
            return default
        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(catalog):
                return catalog[idx - 1][0]
            print(
                f"invalid selection — pick 1-{len(catalog)} or type a model ID",
                file=sys.stderr,
            )
            continue
        return raw


def emit(result: dict, exit_code: int) -> None:
    print(json.dumps(result))
    sys.exit(exit_code)


def main() -> None:
    errors: list[str] = []
    warnings: list[str] = []

    install_path = find_lodestone_install()
    if install_path is None:
        emit(
            {
                "valid": False,
                "errors": [
                    "lodestone install not found. Install via the Claude Code "
                    "marketplace (piercelamb-plugins → lodestone) or clone "
                    "https://github.com/piercelamb/lodestone."
                ],
                "warnings": [],
                "lodestone_install": None,
                "config_path": str(lodestone_config_path()),
                "provider": None,
                "model": None,
            },
            4,
        )

    config_path = lodestone_config_path()

    try:
        existing = load_existing_config(config_path)
    except ValueError as exc:
        emit(
            {
                "valid": False,
                "errors": [f"lodestone config at {config_path} is malformed: {exc}"],
                "warnings": [],
                "lodestone_install": install_path,
                "config_path": str(config_path),
                "provider": None,
                "model": None,
            },
            3,
        )
        return  # unreachable, for type checkers

    if existing is not None:
        provider, model, temperature = existing
        env_name = ENV_KEYS[provider]
        if not os.environ.get(env_name):
            emit(
                {
                    "valid": False,
                    "errors": [
                        f"lodestone config selects provider={provider.value!r} "
                        f"but ${env_name} is not set. Either export ${env_name} "
                        f"or edit {config_path} to pick a provider whose key is "
                        f"present."
                    ],
                    "warnings": [],
                    "lodestone_install": install_path,
                    "config_path": str(config_path),
                    "provider": provider.value,
                    "model": model,
                },
                2,
            )
            return  # unreachable

        # Config valid + key present. Pin the model if it wasn't already
        # — keeps the runtime path identical to lodestone's selection.
        if model is None:
            if sys.stdin.isatty():
                model = prompt_for_model(provider)
                write_config(
                    config_path,
                    provider,
                    model,
                    temperature if temperature is not None else DEFAULT_TEMPERATURE,
                )
                warnings.append(
                    f"persisted model={model!r} to {config_path}"
                )
            else:
                model = MODEL_CATALOGS[provider][0][0]
                warnings.append(
                    f"config had no model pinned; using default {model!r} "
                    f"(non-TTY, not persisting)"
                )

        emit(
            {
                "valid": True,
                "errors": errors,
                "warnings": warnings,
                "lodestone_install": install_path,
                "config_path": str(config_path),
                "provider": provider.value,
                "model": model,
            },
            0,
        )
        return  # unreachable

    # No config — run the first-run flow.
    present = providers_with_env_keys()
    if not present:
        names = ", ".join(f"${v}" for v in ENV_KEYS.values())
        emit(
            {
                "valid": False,
                "errors": [
                    f"no lodestone config at {config_path} and no provider "
                    f"API key in the environment. Set one of: {names}, then "
                    f"re-run this script."
                ],
                "warnings": [],
                "lodestone_install": install_path,
                "config_path": str(config_path),
                "provider": None,
                "model": None,
            },
            1,
        )
        return  # unreachable

    is_tty = sys.stdin.isatty()
    if not is_tty and len(present) > 1:
        names = ", ".join(ENV_KEYS[p] for p in present)
        emit(
            {
                "valid": False,
                "errors": [
                    f"multiple provider keys set ({names}) and stdin is not "
                    f"a TTY — cannot prompt. Write {config_path} to pin one, "
                    f"or unset all but one provider key."
                ],
                "warnings": [],
                "lodestone_install": install_path,
                "config_path": str(config_path),
                "provider": None,
                "model": None,
            },
            5,
        )
        return  # unreachable

    if is_tty:
        print_intro()

    picked = present[0] if len(present) == 1 else prompt_for_provider(present)
    model = prompt_for_model(picked) if is_tty else MODEL_CATALOGS[picked][0][0]

    write_config(config_path, picked, model, DEFAULT_TEMPERATURE)
    warnings.append(
        f"persisted provider={picked.value!r} model={model!r} to {config_path}"
    )

    emit(
        {
            "valid": True,
            "errors": errors,
            "warnings": warnings,
            "lodestone_install": install_path,
            "config_path": str(config_path),
            "provider": picked.value,
            "model": model,
        },
        0,
    )


if __name__ == "__main__":
    main()
