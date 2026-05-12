#!/usr/bin/env bash
# Environment validator for deep-sota plugin.
#
# Confirms lodestone is installed and configured (provider + model pinned
# at ~/.config/lodestone/config.toml — same path lodestone itself uses).
# On first run, when no config exists and a provider API key is set,
# walks the user through the same picker lodestone's CLI does and
# persists the choice.
#
# SECURITY:
# - API keys are checked with `[ -n "$VAR" ]` — existence only, never echoed.
# - The Python helper uses `os.environ.get` for the same purpose.
# - JSON output names the provider ("openai"/"gemini"/"anthropic") and the
#   chosen model, never the key value.
#
# Exit codes (forwarded from setup-lodestone.py):
#   0 — valid
#   1 — config missing and no provider env vars set
#   2 — config pins a provider whose API key is not set
#   3 — config file malformed
#   4 — lodestone install not found
#   5 — multiple provider keys set, non-TTY (cannot disambiguate)
#   6 — uv not installed (set here, before invoking Python)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

# Sanity check: plugin root should contain skills/deep-sota.
if [[ ! -d "$PLUGIN_ROOT/skills/deep-sota" ]]; then
    printf '{"valid": false, "errors": ["could not locate deep-sota plugin root from script location: %s"], "warnings": [], "lodestone_install": null, "config_path": null, "provider": null, "model": null}\n' \
        "$PLUGIN_ROOT"
    exit 4
fi

# uv is required to run the Python helper with stdlib + no project deps.
if ! command -v uv >/dev/null 2>&1; then
    printf '{"valid": false, "errors": ["uv not installed. Install from https://docs.astral.sh/uv/"], "warnings": [], "lodestone_install": null, "config_path": null, "provider": null, "model": null}\n'
    exit 6
fi

# Hand off to the Python helper. It owns the interactive flow + JSON
# emission. We forward its exit code unchanged. `--python 3.11` matches
# lodestone's floor (tomllib was added in 3.11).
exec uv run --python 3.11 --no-project "$SCRIPT_DIR/setup-lodestone.py"
