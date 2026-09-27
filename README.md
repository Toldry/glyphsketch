# glyphsketch

Offline recognizer for hand-drawn Unicode characters. You draw a character, it returns
ranked Unicode candidates. It is built for later integration into the
[Thumb-Key](https://github.com/dessalines/thumb-key) Android keyboard.

It works by retrieval instead of classification. A small CNN encoder maps both the drawing
and rendered font glyphs into the same embedding space, and the nearest glyphs are the
candidates. The glyph embeddings are precomputed and shipped as an index. Because the
index comes from fonts, adding a character needs a font that covers it, not new
handwriting data.

Status: in development. See `PLAN.md` for the milestones and their status, and
`DECISIONS.md` for the design decisions made so far.

## Layout

| Path | Contents |
|------|----------|
| `training/` | Python (PyTorch) pipeline: charset, rendering, synthetic data, training, evaluation, export |
| `export/` | Exported int8 model, glyph index and charset metadata |
| `web/` | TypeScript library and demo web app |
| `android/` | Kotlin library and demo app |
| `docs/` | Project brief and longer write-ups |

## Development

The repository is meant to be opened in the devcontainer (`.devcontainer/`). Large files
go to `$DATA_DIR` (`/data` in the container), never into the repository.

```sh
make sync     # install the locked Python environment
make test     # run the tests
make lint     # ruff + mypy
make all      # run the whole pipeline (stages are cached in $DATA_DIR)
```

## License

AGPL-3.0-only (see `LICENSE`). Fonts, datasets and dependencies are listed with their
licenses in `THIRD_PARTY.md`.
