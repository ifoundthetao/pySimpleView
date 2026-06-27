# pySimpleView

A simple USB microscope capture app: pick a camera, watch the live stream, and
snap pictures. Optional centering guides, crop-to-selection, and calibrated
on-screen measurement. All configuration lives in the GUI and is saved between
runs.

## Run

```sh
uv run python -m pysimpleview
```

The first launch downloads dependencies (PySide6, OpenCV, NumPy) into a local
`uv` environment. On macOS you may be prompted to grant the terminal **Camera**
access the first time it opens a device (System Settings → Privacy & Security →
Camera).

## Features

- **Device picker with live preview** — *Change camera…* scans connected
  cameras and shows a live preview of the highlighted one so you pick by sight.
- **Capture** — big button or the **Space** key. Saves the image exactly as
  shown (orientation + crop applied).
- **Naming**
  - *Single file name* (e.g. `capture`) — extension added automatically.
  - *Naming convention* with an auto-incrementing counter, e.g.
    `resistors-${%04d}.png` → `resistors-0001.png`, `0002`, … It resumes from
    the highest number already in the output folder (after `resistors-0023.png`
    the next is `resistors-0024.png`).
  - *Follow naming convention* checkbox switches between the two.
  - *Next file:* preview always shows what the next save will be called.
- **Output directory** — pick any folder; you're prompted before overwriting.
- **Orientation** — flip horizontal/vertical and rotate 0/90/180/270°.
- **Overlays (optional)** — centering crosshair and rule-of-thirds grid, plus an
  option to burn the guides into the saved image.
- **Crop to selection** — *Set crop region*, then drag a rectangle on the video.
  *Clear crop* returns to the full frame.
- **Measurement** — *Calibrate…* by drawing a line over a known length and
  entering its real size (µm by default); then *Measure* shows live length in
  real units. Without calibration it reports pixels.

## Settings

Saved automatically to
`~/Library/Application Support/pySimpleView/settings.json`.

## Layout

| File | Purpose |
|------|---------|
| `pysimpleview/__main__.py` | App entry point |
| `pysimpleview/main_window.py` | Controls panel + wiring |
| `pysimpleview/video_view.py` | Live view, overlays, crop/measure interaction |
| `pysimpleview/device_dialog.py` | Camera picker with live preview |
| `pysimpleview/camera.py` | Device enumeration + capture thread |
| `pysimpleview/transform.py` | Orientation & crop image ops |
| `pysimpleview/naming.py` | Filename convention logic |
| `pysimpleview/config.py` | Persistent settings |
