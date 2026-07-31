# Texture Browser

Current development version: 0.2.0-beta.1

A lightweight cross-platform (Windows/macOS/Linux) texture and media browser built with Python and PySide6. It scans folders in the background, groups image sequences, caches thumbnails on disk, and opens a simple internal viewer for images, sequences, and video items.

## Features

- Folder tree with a persistent favorites section.
- Recursive media scanning with background workers.
- Thumbnail grid with Tiny, Small, Medium, and Large sizing.
- Extension filter for narrowing results to types like `.fbx`, `.png`, or `.exr`.
- Default results show images and image sequences; videos and models appear when their extension is typed.
- Image sequence grouping for names like `smoke_0001.tga` and `wood_diffuse.1001.exr`.
- Debounced filename-only search with comma-separated alternatives.
- Disk-based thumbnail cache keyed by file path, size, modified time, and file size.
- Change-aware, bounded folder and Favorites indexes for fast revisits without unbounded RAM growth.
- Persistent image-dimension cache for fast repeat size filtering.
- Right-click material-renderer launch with automatic PBR map assignment.
- Naming convention presets for quickly switching associated-texture matching terms.
- Context menu actions for revealing files in Explorer/Finder/your file manager, copying the file path, and copying the folder path.
- Internal image viewer with fit-to-window zoom and frame stepping for sequences.
- Video double-click handoff to VLC, falling back to the OS default video player.
- FBX double-click handoff to the OS default app for `.fbx` (e.g. Blender if you associate it).
- (and more!)

## Project Layout

```text
texture_browser/
  main.py
  app/
    __init__.py
    associated_browser.py
    cache_worker.py
    channel_inspector.py
    favorites.py
    favorites_index.py
    folder_tree.py
    godot_renderer.py
    main_window.py
    media_dimensions.py
    models.py
    naming_presets.py
    platform_services.py
    scanner.py
    sequence_detector.py
    size_filter_worker.py
    tag_csv_exporter.py
    tag_store.py
    texture_sets.py
    thumbnail_grid.py
    thumbnailer.py
    utils.py
    validation_report.py
    viewer.py
    workflow_filter.py
  assets/
  godot_material_renderer/
  tests/
  TextureBrowser.spec
  VERSION
  requirements.txt
  README.md
```

## Install

From the repo root, create a virtual environment and install the base dependencies.

Windows (PowerShell):

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

macOS / Linux (bash):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Install optional dependencies if you want broader preview support:

```bash
pip install imageio psd-tools opencv-python-headless
```

## Run

```bash
python main.py
```

## External tools (optional)

- **VLC** for video playback: found via `PATH` on all platforms, plus the standard install locations (`Program Files` on Windows, `/Applications` on macOS, system paths/snap/flatpak on Linux). Without VLC, videos open in the OS default player.
- **FBX viewer**: `.fbx` files open with whatever app your OS associates with the extension (Blender works well once associated).
- On Linux, "Reveal in File Manager" uses the DBus `org.freedesktop.FileManager1` interface with an open-folder fallback.

## Packaging

A single PyInstaller spec builds a standalone app on each platform:

```bash
pip install pyinstaller
pyinstaller TextureBrowser.spec
```

On Windows this produces `dist/TextureBrowser.exe`, on macOS `dist/TextureBrowser.app`, and on Linux a `dist/TextureBrowser` binary.

## Format Support

Fully supported with the base install:

- `.png`
- `.jpg`, `.jpeg`
- `.bmp`
- `.gif`
- `.tif`, `.tiff` when Pillow can decode them

Supported when optional libraries are available:

- `.tga`, `.hdr`, `.exr`: usually through `imageio` and its backend support
- `.psd`: through `psd-tools`
- `.mp4`, `.mov`, `.avi`, `.mkv`, `.webm` thumbnail extraction: through `opencv-python-headless`
- `.fbx`: listed in the browser with a model placeholder; double-click opens the OS default `.fbx` app

Graceful fallback behavior:

- Unsupported or unreadable files still appear in the browser.
- If a preview cannot be generated, the app shows a placeholder tile with the file extension.
- Corrupt files should not crash the app; preview generation failures fall back to placeholders.

## Notes

- Favorites and UI preferences are stored with `QSettings` (registry on Windows, plist on macOS, `~/.config` on Linux).
- Thumbnail cache files are stored under the app data directory used by Qt for the current user.
- Video playback is not included in this first version. Videos open in the internal viewer with file information and preview imagery where thumbnail extraction succeeds.
- The scan cancel action is cooperative. Large directory walks stop on the next cancel checkpoint.


## Lightweight Verification

~~~powershell
python -m compileall -q app main.py
python -m unittest discover -s tests -v
~~~

The Godot renderer can be exported separately and is included automatically by
TextureBrowser.spec when its exported files exist under
godot_material_renderer/build/.
