# pySimpleView

A focused, no-fuss capture app for USB microscopes and document cameras. Pick a
camera, watch the live stream, line up your shot with on-screen guides, and snap
pictures that are saved exactly as you see them. Add crop, calibrated
measurement, white balance, and optional AI identification of whatever is under
the lens.

Everything is configured in the GUI and remembered between runs — there are no
config files to hand-edit.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![Platform](https://img.shields.io/badge/platform-macOS-lightgrey.svg)

---

## Run

```sh
uv run python -m pysimpleview
```

The first launch resolves dependencies (PySide6, OpenCV, NumPy, anthropic,
keyring) into a local `uv` environment. On macOS you'll be prompted to grant
**Camera** access the first time a device is opened
(System Settings → Privacy & Security → Camera).

Press **Ctrl-C** in the terminal at any time for a clean shutdown — the live
capture is released and the app exits gracefully.

---

## Features

### Camera

- **Device picker with live preview** — *Change camera…* scans connected cameras
  and shows a live preview of the highlighted one, so you choose by sight rather
  than guessing index numbers.
- **Hot-plug detection** — the picker keeps scanning while it's open, so a camera
  you plug in after opening the dialog shows up on its own.
- **Resilient capture** — if a camera briefly drops off the bus (common with
  unpowered USB hubs or KVM switches), pySimpleView automatically tries to
  reconnect with backoff and resumes the stream. Only after repeated failures
  does it mark the camera "not responding" and leave it alone until you pick one
  again.

### Capturing

- **Capture** — the big button or the **Space** key. The saved image is exactly
  what's on screen: orientation, crop, and white balance are all applied.
- **Output directory** — save anywhere; you're prompted before overwriting an
  existing file.
- **Flexible naming**
  - *Single file name* (e.g. `capture`) — the extension is added automatically.
  - *Naming convention* with an auto-incrementing counter, e.g.
    `resistors-${%04d}.png` → `resistors-0001.png`, `resistors-0002.png`, …
    It resumes from the highest number already in the folder (after
    `resistors-0023.png` the next save is `resistors-0024.png`).
  - A *Follow naming convention* checkbox switches between the two modes, and a
    *Next file:* line always previews what the next save will be called.
- **Format** — PNG, JPG, BMP, or TIFF.

### Framing and image adjustments

- **Orientation** — flip horizontal/vertical and rotate 0 / 90 / 180 / 270°.
- **Overlays** — a centering crosshair and a rule-of-thirds grid to help you
  compose, with an option to *burn* the guides into the saved image (off by
  default, so your captures stay clean).
- **Crop to selection** — *Set crop region*, then drag a rectangle on the video;
  every capture is cropped to it. *Clear crop* returns to the full frame.
- **White balance** — *Set white balance*, then click/drag a patch you know is
  neutral grey/white; the colour gains are corrected live and applied to saves.
  *Clear* returns to the raw sensor colour.

### Measurement

- **Calibrate** — draw a line over a feature of known length and enter its real
  size (µm by default). pySimpleView stores the scale.
- **Measure** — draw a line and read its length in real units. Without
  calibration it simply reports pixels.
- A printable `calibration_target.svg` / `.pdf` is included to help you
  calibrate against a known scale.

### AI identification

Send the current frame to a vision model and get back a description — see the
[next section](#ai-integration) for setup and ideas.

---

## AI integration

pySimpleView can ask a vision-capable model "what am I looking at?" using the
frame currently on screen. It's optional — the app is fully usable without it —
but it's handy for reading component markings, identifying parts, and describing
specimens.

### How it works

Click **Identify** to send the current frame (JPEG-encoded) plus a text prompt
to your chosen provider and show the response in the panel. All providers are
driven through the Anthropic Messages API, so switching between them is just a
matter of base URL and model.

| Provider | Default model | Endpoint |
|----------|---------------|----------|
| **MiniMax M3** (default) | `MiniMax-M3` | `https://api.minimax.io/anthropic` |
| **Claude (Anthropic)** | `claude-opus-4-8` | default Anthropic endpoint |
| **Custom (Anthropic-compatible)** | you choose | you provide the base URL |

The *Custom* option lets you point at any Anthropic-API-compatible endpoint by
supplying your own base URL and model id.

### Setup

1. Open **AI settings…** in the panel.
2. Choose a **Provider** (and, if you like, override the **Model** / **Base
   URL** — leave them blank to use the provider's defaults).
3. Paste your **API key** and click **Save**.
4. Optionally edit the **Prompt** (see below).

**Your key never touches the settings file.** It's stored in the macOS Keychain
(service `pySimpleView`, account = provider). Alternatively, supply it via an
environment variable, which takes precedence over the keychain:

```sh
# PYSIMPLEVIEW_<PROVIDER>_API_KEY  (provider in UPPERCASE)
export PYSIMPLEVIEW_MINIMAX_API_KEY=...      # MiniMax M3
export PYSIMPLEVIEW_ANTHROPIC_API_KEY=...    # Claude
export PYSIMPLEVIEW_CUSTOM_API_KEY=...       # Custom endpoint
```

### The prompt — and what you can do with it

The prompt is fully editable, so you can repurpose Identify for whatever you put
under the lens. The default is geared toward electronics:

> Identify a small electronic component or object under a USB microscope. For a
> resistor, read the colour bands and state the resistance value and tolerance;
> for other components, give the type and any visible markings or part numbers.

Some ways people use it:

- **Resistor colour bands** → resistance value and tolerance, with the band
  colours called out.
- **Reading tiny markings** — part numbers, date codes, and logos on ICs, SMD
  components, and connectors that are hard to read with the naked eye.
- **PCB inspection** — describing a region of a board, spotting damaged traces or
  solder bridges.
- **Identifying unknown small parts** — screws, fasteners, crimps, SMD packages.
- **Natural-history / specimen work** — rewrite the prompt to describe insects,
  plant structures, fibres, minerals, or print/textile detail.
- **Coins, stamps, and collectibles** — surface a prompt that asks about
  mint marks, denominations, or condition cues.

Tip: the more specific the prompt ("you are a numismatist; describe the date and
mint mark"), the more useful the answer.

### Enhancing legibility

Tick **Enhance image(s) for AI** to boost local contrast (CLAHE) on the frame
before it's sent — this makes faint, low-contrast markings such as laser-etched
part numbers or date codes much easier for the model to read. The enhancement:

- is **colour-preserving** (it works on lightness only), so it won't throw off
  colour-critical reads like resistor bands;
- is **non-destructive** — it's applied only to the image sent to the AI, never
  to your saved captures;
- can be **previewed** any time with the **Preview enhanced** button, which shows
  the original next to the enhanced version side by side.

### Guided multi-angle capture

Some details only appear from the right angle or under raking light — embossed or
etched text being the classic example. **Guided…** opens a small wizard that:

1. shows a live preview and a cycling suggestion for each shot (straight-on, tilt
   left/right, raking light, rotate 90°, …);
2. lets you **capture several shots** of the same subject, building a thumbnail
   strip you can prune;
3. sends **all the shots together in a single request**, telling the model they
   are the same subject from different angles/lighting so it can reason across
   them.

This is often the most effective way to identify a tricky part: a marking that's
invisible flat-on frequently pops under side lighting, and the model fuses what
it sees across the set. Enhancement, if enabled, is applied to every shot.

---

## Settings

All settings are saved automatically to
`~/Library/Application Support/pySimpleView/settings.json`. API keys are **not**
stored there — they live in the macOS Keychain.

## Troubleshooting / logging

Diagnostic logging is off by default. Enable it with the `PYSIMPLEVIEW_LOG`
environment variable:

```sh
PYSIMPLEVIEW_LOG=1            uv run python -m pysimpleview   # debug → stderr
PYSIMPLEVIEW_LOG=info         uv run python -m pysimpleview   # info level
PYSIMPLEVIEW_LOG=/tmp/psv.log uv run python -m pysimpleview   # also write a file
```

The logs trace camera open/probe results, frame delivery, dropped-stream
reconnect attempts, and shutdown — useful for diagnosing flaky USB/KVM setups.
They never include image data or API keys.

---

## Project layout

| File | Purpose |
|------|---------|
| `pysimpleview/__main__.py` | App entry point + graceful Ctrl-C handling |
| `pysimpleview/main_window.py` | Controls panel and wiring |
| `pysimpleview/video_view.py` | Live view, overlays, crop / measure / white-balance interaction |
| `pysimpleview/device_dialog.py` | Camera picker with live preview and hot-plug scanning |
| `pysimpleview/camera.py` | Device enumeration + capture thread with auto-reconnect |
| `pysimpleview/transform.py` | Orientation, crop, and colour image ops |
| `pysimpleview/naming.py` | Filename convention / counter logic |
| `pysimpleview/config.py` | Persistent settings |
| `pysimpleview/ai_settings_dialog.py` | AI provider / model / key / prompt settings |
| `pysimpleview/ai_dialogs.py` | Enhancement preview + guided multi-angle capture |
| `pysimpleview/vision_worker.py` | Background thread for AI requests |
| `pysimpleview/vision/` | Pluggable vision providers (Anthropic / MiniMax / custom) |
| `pysimpleview/log.py` | Opt-in diagnostic logging |

## License

[MIT](LICENSE) © Tim Bolton
