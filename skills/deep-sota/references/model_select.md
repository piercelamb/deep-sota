# Model selection + config write (read me after `provider_select.md`)

You've resolved a single `provider` (one of `anthropic` / `openai` /
`gemini`). Now elicit a model and persist the choice to
`~/.config/lodestone/config.toml`.

## Model catalogs

Recommended is listed first. Keep in sync with lodestone's adapter
catalogs — if lodestone adds a model, add it here too.

- **anthropic**
  - `claude-opus-4-7` — most capable (Recommended)
  - `claude-sonnet-4-6` — balanced speed + intelligence
  - `claude-haiku-4-5` — fastest, lowest cost
- **openai**
  - `gpt-5.4` — most capable (Recommended)
  - `gpt-5.4-mini` — faster, lower cost
  - `gpt-5.4-pro` — deepest reasoning
  - `gpt-5.4-nano` — cheapest, fastest
- **gemini**
  - `gemini-2.5-pro` — most capable GA (Recommended)
  - `gemini-2.5-flash` — fast, balanced
  - `gemini-2.5-flash-lite` — fastest, lowest cost
  - `gemini-3.1-pro-preview` — preview, experimental frontier

## Ask the user

Call `AskUserQuestion` exactly once:

- `question`: `"Lodestone makes one LLM call per ingestion, which {provider} model should classify-stage use?"`
  (substitute the provider name)
- `header`: `"Model"`
- `multiSelect`: `false`
- `options`: the catalog rows above for the chosen provider, in catalog
  order. Label the recommended row with the `(Recommended)` suffix per
  the AskUserQuestion convention. Cap at 4 options — the harness limit.

The harness automatically appends an "Other" option. **Allow it here**
— that slot lets the user type a custom model ID (e.g. a snapshot or
preview not yet in the catalog). Trust the string they enter verbatim.

## Persist `config.toml`

After the user picks (catalog or Other), write
`~/.config/lodestone/config.toml`. Resolve the path the same way
lodestone does:

1. If `$XDG_CONFIG_HOME` is set, use `$XDG_CONFIG_HOME/lodestone/config.toml`.
2. Otherwise on POSIX, use `~/.config/lodestone/config.toml`.
3. On Windows, use `%APPDATA%/lodestone/config.toml` (fall back to
   `~/.config/lodestone/config.toml` if `APPDATA` is unset).

Create the parent directory if it doesn't exist. Body:

```toml
[llm]
provider = "<provider>"
model = "<model>"
temperature = 1.0
```

Escape any backslashes or double-quotes in `<model>` for TOML basic
strings (`\` → `\\`, `"` → `\"`). Catalog IDs don't need escaping;
Other-supplied IDs might.

After the write, return to the calling SKILL.md step and start the
ingest.
