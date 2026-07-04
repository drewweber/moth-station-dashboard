# Contributing

Station owners can contribute in three simple ways:

1. Add or edit a station in `stations.toml`.
2. Open an issue with the station query details if they do not want to edit code.
3. Improve dashboard code or docs through a pull request.

## Station Requirements

Each station needs:

- a stable `id`, using lowercase letters, numbers, and hyphens
- a clear display `name`
- an iNaturalist query, such as `project_id`, `user_login`, `place_id`, or
  `lat`/`lng`/`radius`
- county and state place IDs when first-record context is added later

Do not include private exact coordinates for a station unless the owner is
comfortable with them being public in the GitHub repo.

## Working With AI Coding Tools

Claude, Codex, Cursor, Copilot, and other tools are welcome. Keep AI-generated
changes reviewable:

- make small pull requests
- explain the behavior change
- include the command used to test it
- avoid committing `data/mothdash.db` or generated `public/index.html`
- do not rewrite unrelated files

The repository includes `AGENTS.md` and `CLAUDE.md` so different tools can read
the same project guidance.

## Local Check

Before opening a pull request:

```sh
python3 -m compileall mothdash
python3 -m mothdash render
```

Use `python3 -m mothdash build` when network access is available and you want to
refresh from iNaturalist.

