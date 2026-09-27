# glyphsketch training pipeline

Python (PyTorch) pipeline that builds the character set, renders font glyphs, generates
synthetic handwriting, trains the encoder, evaluates it and exports the model and index.

```sh
cd training
uv sync                     # exact environment from uv.lock
uv run pytest               # tests
uv run ruff check . && uv run ruff format --check . && uv run mypy   # lint + types
```

Large artefacts go to `$DATA_DIR` (`/data` in the devcontainer), never into the repository.
