# glyphsketch

Offline handwritten Unicode character recognizer: retrieval over font-glyph embeddings,
for later integration into the Thumb-Key Android keyboard (AGPL-3.0, F-Droid).

- `docs/BRIEF.md`: the original brief (goal, hard constraints, deliverables). Read it first.
- `PLAN.md`: approved milestones and the decisions made so far. Work through the
  milestones in order and update the status there as they complete.
- `DECISIONS.md`: log every non-trivial design decision and trade-off (create it in M0).

## Hard constraints (details in the brief)
- Fully offline at runtime; buildable from source (F-Droid); no Google Play Services/ML Kit.
- AGPL-3.0. Every font, dataset and dependency must be license-compatible and recorded in
  `THIRD_PARTY.md` with its license and URL. Verify each license from the source itself.
- Model + index ≤ ~15 MB (raised from the brief's 10 MB by the user on 2026-09-29, D40);
  ≤ ~300 ms per query on a mid-range phone (relaxed from the brief's 50 ms by the user on
  2026-09-28, D32).
- Adding a character must never require new handwriting data.

## Working style
- Ask the user before downloading anything over ~500 MB or starting any run expected to
  take more than an hour.
- Write all the code yourself. Don't leave TODOs for the user to fill in.
- Descriptive names, line length ≤ 100, type hints in Python.
- Tests for the data pipeline, the inference engines, and (later) the Kotlin inference.
- Small, focused commits with clear messages. Push only after the user has set up the
  GitHub remote. Never create or publish repositories yourself.
- Web demo first; Android/Kotlin/Pixel 8 work is the last milestone.

## Environment
- In the devcontainer, `$DATA_DIR` (`/data`) is a named volume. Put downloads, renders,
  synthetic data and checkpoints there, never in the repo.
- Python: `training/` is managed with uv (`pyproject.toml` + `uv.lock`). The venv lives at
  `$UV_PROJECT_ENVIRONMENT`.
- CPU only inside the container. For long training runs, prepare a Kaggle notebook and
  ask the user.
