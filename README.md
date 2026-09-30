# glyphsketch

Offline recognizer for hand-drawn Unicode characters. You draw a character, it returns
ranked Unicode candidates. It runs entirely on the device, in the browser or on Android.

**[Try the web demo](https://toldry.github.io/glyphsketch/web/demo/)**: draw a character
with a mouse, finger or pen. It works offline once loaded and can be installed as an app.

<video src="docs/images/glyphsketch_web_demo.mp4" controls muted width="600"></video>

[Watch the demo video](docs/images/glyphsketch_web_demo.mp4) if it doesn't play above.

It works by retrieval instead of classification. A small CNN encoder maps both the drawing
and rendered font glyphs into the same embedding space, and the nearest glyphs are the
candidates. The glyph embeddings are precomputed and shipped as an index. Because the
index comes from fonts, adding a character needs a font that covers it, not new
handwriting data.

## Layout

| Path | Contents |
|------|----------|
| `training/` | Python (PyTorch) pipeline: charset, rendering, synthetic data, training, evaluation, export |
| `export/` | Exported int8 model, glyph index and charset metadata |
| `web/` | TypeScript library and demo web app |
| `android/` | Kotlin library and demo app |
| `docs/` | Model file format, reports and images |

## Development

The repository is meant to be opened in the devcontainer (`.devcontainer/`). Large files
go to `$DATA_DIR` (`/data` in the container), never into the repository.

```sh
make sync     # install the locked Python environment
make test     # run the tests
make lint     # ruff + mypy
make all      # run the whole pipeline (stages are cached in $DATA_DIR)
make web-test   # TypeScript engine: type-check and parity tests
make web-serve  # demo page at http://localhost:5173/web/demo/
make web-site   # the static site that GitHub Pages serves, in web/dist/site/
```

The web demo is published on GitHub Pages from the `gh-pages` branch, which the `Pages`
workflow rebuilds on every push to `main` that touches `web/` or `export/`.

### If the laptop gets slow

Pipeline stages and training runs can use many CPU cores for a long time. Everything in
the devcontainer shares the laptop's CPU and memory, so heavy jobs can slow down
Windows. To see what is running and pause or stop it, run this in a devcontainer
terminal:

```sh
make slowdown
# or: python3 training/src/glyphsketch/tools/slowdown.py
```

The script measures CPU use for a second, then lists the busy jobs with the cores and
memory each one uses, and names the most likely cause. VS Code and Claude Code are
listed too, but the script never touches them. Enter a job's number, then choose:

| Key | Action | Effect |
|-----|--------|--------|
| `p` | Pause now, continue later | The job freezes and keeps its progress. It still holds its memory until it continues |
| `r` | Stop now, restart later | Memory is freed. The same command runs again at the chosen time, in the same directory, with the same environment and log file. A pipeline run skips the stages it already finished |
| `s` | Stop for good | The job ends. Unsaved work is lost |

The script asks when the job should continue or restart. Enter a clock time such as
`01:00` (the next time the clock shows it), or an offset such as `+2h`, `+45m` or
`+1h30m`. Press Enter to accept the default, 01:00. A paused job can also be
continued by hand: run the script again, pick the job and press `c`. Run the script again
at any time to see what is scheduled, run a scheduled restart now, or cancel it.

A background process carries out scheduled actions, and they are recorded in
`$DATA_DIR/slowdown/` (`slowdown.log` lists what was done). **Keep the devcontainer running
until then.** Closing it ends paused jobs and cancels scheduled restarts; the script will
show those restarts as not going to happen. If the laptop sleeps past the chosen time,
the action runs when it wakes.

To print the report without any questions, run
`python3 training/src/glyphsketch/tools/slowdown.py --list`.

## License

AGPL-3.0-only (see `LICENSE`). Fonts, datasets and dependencies are listed with their
licenses in `THIRD_PARTY.md`.
