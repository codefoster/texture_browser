# AGENTS.md

## Project Overview

Texture Browser is a cross-platform (Windows/macOS/Linux) Python desktop app built with PySide6. It scans folders for texture/media files, groups numbered image sequences, shows a lazy-loaded thumbnail grid, and opens images/sequences in an internal viewer. Videos are handed off to VLC when available (falling back to the OS default player), and FBX files are handed off to the OS default app for `.fbx`.

## How To Run

From the repo root.

Windows (PowerShell):

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

macOS / Linux (bash):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

Optional preview support can be installed manually:

```bash
pip install imageio psd-tools opencv-python-headless
```

## Build Notes

One PyInstaller spec builds on every platform (per-OS icon and a macOS `.app` bundle are handled inside the spec):

```bash
pyinstaller TextureBrowser.spec
```

`build/` and `dist/` are generated artifacts and are ignored by git, though they may exist locally.

## Project Layout

- `main.py`: app entry point; imports and runs `app.main_window.run`.
- `app/main_window.py`: main PySide6 window, scanning lifecycle, thumbnail queues, filtering, favorites, drag/drop import, viewer launch, associated texture matching.
- `app/platform_services.py`: ALL platform-specific handoffs — file-manager reveal, open-with-default-app, VLC discovery/launch, per-platform hint strings. `sys.platform` dispatch, exception-safe.
- `app/folder_tree.py`: filesystem tree and favorites list UI.
- `app/thumbnail_grid.py`: `QListWidget` thumbnail grid, filtering, lazy population, drag/drop, context menu.
- `app/thumbnailer.py`: thumbnail cache and image/video/PSD/HDR/EXR loading fallback logic.
- `app/scanner.py`: background recursive scan worker using `os.walk`.
- `app/sequence_detector.py`: image sequence grouping for names with 3-6 digit frame numbers.
- `app/viewer.py`: internal viewer for images and sequences, including frame stepping and zoom.
- `app/associated_browser.py`: dialog for related texture variants based on naming convention/search terms.
- `app/naming_presets.py`: dialog for saving, editing, deleting, and loading naming convention presets.
- `app/favorites.py`: QSettings persistence for favorites, last root, thumbnail size, and naming convention.
- `app/tag_store.py`: SQLite tag database stored in the library's `.texturebrowser-cache`.
- `app/tag_csv_exporter.py`: tag-based material CSV export worker.
- `app/texture_sets.py`: texture-set grouping and validation logic.
- `app/favorites_index.py`: background index for favorites search.
- `app/cache_worker.py`: local library cache builder.
- `app/utils.py`: extension sets, cache paths, path-identity helpers (`is_drive_root`, `normalize_path_key`).
- `app/models.py`: dataclasses/enums shared across the app.
- `assets/`: application icons and splash.
- `scripts/smoke_test.py`: offscreen launch smoke test used by CI.

## Runtime Behavior

- The UI is Qt/PySide6 using the Fusion style on all platforms.
- Favorites and preferences are stored with `QSettings("TextureBrowser", "TextureBrowser")`.
- Naming convention presets are stored with the same QSettings profile as a JSON string.
- Thumbnail cache files are stored under Qt's app data location in `thumb_cache`.
- Scanning is cooperative and cancelable; the scan worker checks cancellation during directory walking.
- Volume roots (drive letters, `/`, `/Volumes/*`, `/mnt/*`, `/media/*`) are intentionally not scanned directly; the UI asks the user to choose a folder below them (`utils.is_drive_root`).
- The thumbnail grid populates in batches and requests thumbnails only for visible/prefetched items.
- Search terms are comma-separated and all terms must appear in `MediaItem.search_text`.
- The extension filter reveals only matching extensions; with the filter empty, videos and models are hidden by default.
- Associated texture matching is currently based on same folder, same extension, naming convention terms, and the current search terms.

## Media Support

Base dependencies:

- PySide6
- Pillow

Base image support includes `.png`, `.jpg`, `.jpeg`, `.bmp`, `.gif`, `.tif`, and `.tiff` where Pillow can decode them.

Optional support:

- `imageio`: `.tga`, `.hdr`, `.exr` and other formats depending on installed backends.
- `psd-tools`: `.psd`.
- `opencv-python-headless`: video thumbnail extraction.

Videos supported by extension: `.mp4`, `.mov`, `.avi`, `.mkv`, `.webm`.
Models supported by extension: `.fbx`.

## Development Guidance

- **Keep the app cross-platform (Windows/macOS/Linux).** All file-manager reveals, external-app handoffs, and shell-outs MUST go through `app/platform_services.py` — never call `explorer`, `os.startfile`, `open`, or `xdg-open` directly from UI code.
- Never lowercase filesystem paths for identity/dedupe keys except via `utils.normalize_path_key` (Linux filesystems are case-sensitive).
- `.ico` is Windows-only; use `assets/app_icon.png` on other platforms (see `app_icon()` in main_window.py).
- The QSettings identity (`"TextureBrowser", "TextureBrowser"`) and the QApplication org/app names are load-bearing for existing installs — do not rename or "unify" them.
- Prefer PySide6 idioms, signals, and background `QRunnable` workers over blocking UI work.
- Preserve lazy loading behavior in `ThumbnailGrid` and `ThumbnailWorker`; large texture folders are expected.
- Be careful with `QPixmap`/Qt object usage in worker threads. Existing code emits pixmaps back via signals; test UI changes interactively when possible.
- Avoid scanning volume roots or adding behavior that recursively walks huge locations without cancellation checkpoints.
- Keep media loading tolerant. Unsupported or corrupt files should show placeholders instead of crashing.
- Do not commit generated `build/`, `dist/`, caches, or virtual environments.

## Verification

For changes, at minimum run:

```bash
python -m compileall app main.py
python scripts/smoke_test.py
```

The smoke test launches the app offscreen (`QT_QPA_PLATFORM=offscreen`) and exercises the platform helpers; CI runs it on Windows, macOS, and Ubuntu.

For UI or media-loading work, also run the app manually:

```bash
python main.py
```

Then check folder scanning, thumbnail loading, filtering, viewer launch, and any changed workflow.
