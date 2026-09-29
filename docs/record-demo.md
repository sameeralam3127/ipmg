# Recording the README visuals

Every image in the README is generated from something in this repository, so
it can be recreated after a UI change instead of drifting out of date. All
commands run from the repository root with IPMG installed in `.venv`
(`python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"`).

| File | Shows | Made with |
| --- | --- | --- |
| `docs/assets/ipmg-demo.gif` | A scan with live results | `docs/demo/record.py` + [agg](https://github.com/asciinema/agg) |
| `docs/assets/ipmg-compare.gif` | A scan, a new device, and `--compare` | `docs/demo/ipmg-compare.tape` + [VHS](https://github.com/charmbracelet/vhs) |
| `docs/assets/ipmg-web.png` | IPMG Web dashboard | `docs/demo/screenshots.cjs` + Playwright |
| `docs/assets/ipmg-changes.png` | IPMG Web Changes view | `docs/demo/screenshots.cjs` + Playwright |
| `docs/assets/ipmg-builder.png` | The website's command builder | no script yet |

The terminal recordings scan `docs/demo/targets.txt`: public DNS resolvers
plus TEST-NET addresses (RFC 5737) that never answer, so they show timeouts
without exposing a real network. They run for real, so latencies and the
exact changes found vary from one recording to the next.

## Scan GIF

```bash
brew install agg        # or: cargo install --git https://github.com/asciinema/agg
.venv/bin/python docs/demo/record.py
agg --theme monokai --font-size 16 docs/demo/ipmg-demo.cast docs/assets/ipmg-demo.gif
```

`record.py` runs each command in a pseudo-terminal and writes an asciicast;
only the typing is simulated. It needs macOS or Linux (it uses `pty`).

## Change detection GIF

```bash
brew install vhs        # also installs ttyd and ffmpeg; see the VHS README for Linux
vhs docs/demo/ipmg-compare.tape
```

The tape adds `.venv/bin` to `PATH`, works in a temporary directory with its
own history database, scans, appends `192.0.2.30` to the target file, and
scans again with `--compare`.

**If VHS finishes without writing the GIF** (seen with VHS 0.12 and
ffmpeg 9, where its own encoding step fails silently), have it write frames
and encode them yourself:

```bash
sed 's#^Output .*#Output "frames/"#' docs/demo/ipmg-compare.tape > /tmp/ipmg-compare.tape
vhs /tmp/ipmg-compare.tape
ffmpeg -y -framerate 50 -i frames/frame-text-%05d.png -framerate 50 -i frames/frame-cursor-%05d.png \
  -filter_complex "color=c=0x121212:s=1200x684:r=50[bg];[bg][0]overlay=shortest=1[t];[t][1]overlay,pad=1248:732:24:24:color=0x121212,fps=15,split[a][b];[a]palettegen=max_colors=256:stats_mode=full[p];[b][p]paletteuse=dither=none:diff_mode=rectangle" \
  docs/assets/ipmg-compare.gif
rm -rf frames
```

`1200x684` is the frame size VHS produces for the tape's `Width`, `Height`,
and `Padding`; check it with `file frames/frame-text-00001.png` if you
change those.

## IPMG Web screenshots

The screenshots use the seeded demo (`?demo=1`), the same one the website
serves, so they need no scan history. Playwright is installed into a
throwaway directory, not the repository:

```bash
TOOLS="$(mktemp -d)"
npm install --prefix "$TOOLS" playwright@1
"$TOOLS/node_modules/.bin/playwright" install chromium

python3 -m http.server 4173 --bind 127.0.0.1 -d src/ipmg/web/static &
NODE_PATH="$TOOLS/node_modules" node docs/demo/screenshots.cjs
kill %1
```

To change what the Changes view shows, edit the seeded history in
`src/ipmg/web/static/js/demo.js`. Keep it to changes real IPMG would report;
the rules are in `src/ipmg/core/diff.py`.
