# AGENTS.md

## Project Overview

Texture Browser is a Windows-oriented Python desktop app built with PySide6. It scans folders for texture/media files, groups numbered image sequences, shows a lazy-loaded thumbnail grid, and opens images/sequences in an internal viewer. Videos are handed off to VLC when available, and FBX files are handed off to the default FBX app.

## How To Run

Use PowerShell from the repo root:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

Optional preview support can be installed manually:

```powershell
pip install imageio psd-tools opencv-python-headless
```

## Build Notes

The repo includes PyInstaller spec files:

```powershell
pyinstaller TextureBrowser.spec
pyinstaller TextureBrowser_Fixes.spec
```

`build/` and `dist/` are generated artifacts and are ignored by git, though they may exist locally.

## Project Layout

- `main.py`: app entry point; imports and runs `app.main_window.run`.
- `app/main_window.py`: main PySide6 window, scanning lifecycle, thumbnail queues, filtering, favorites, drag/drop import, viewer launch, associated texture matching.
- `app/folder_tree.py`: filesystem tree and favorites list UI.
- `app/thumbnail_grid.py`: `QListWidget` thumbnail grid, filtering, lazy population, drag/drop, context menu.
- `app/thumbnailer.py`: thumbnail cache and image/video/PSD/HDR/EXR loading fallback logic.
- `app/scanner.py`: background recursive scan worker using `os.walk`.
- `app/sequence_detector.py`: image sequence grouping for names with 3-6 digit frame numbers.
- `app/viewer.py`: internal viewer for images and sequences, including frame stepping and zoom.
- `app/associated_browser.py`: dialog for related texture variants based on naming convention/search terms.
- `app/naming_presets.py`: dialog for saving, editing, deleting, and loading naming convention presets.
- `app/favorites.py`: QSettings persistence for favorites, last root, thumbnail size, and naming convention.
- `app/utils.py`: extension sets, cache paths, Explorer/VLC/default-app handoff helpers.
- `app/models.py`: dataclasses/enums shared across the app.
- `assets/`: application icons.

## Runtime Behavior

- The UI is Qt/PySide6 using the Fusion style.
- Favorites and preferences are stored with `QSettings("TextureBrowser", "TextureBrowser")`.
- Naming convention presets are stored with the same QSettings profile as a JSON string.
- Thumbnail cache files are stored under Qt's app data location in `thumb_cache`.
- Scanning is cooperative and cancelable; the scan worker checks cancellation during directory walking.
- Drive roots are intentionally not scanned directly; the UI asks the user to choose a folder under the drive.
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

- Keep the app Windows-friendly; many helpers intentionally use Explorer, VLC paths, `os.startfile`, and `.ico` assets.
- Prefer PySide6 idioms, signals, and background `QRunnable` workers over blocking UI work.
- Preserve lazy loading behavior in `ThumbnailGrid` and `ThumbnailWorker`; large texture folders are expected.
- Be careful with `QPixmap`/Qt object usage in worker threads. Existing code emits pixmaps back via signals; test UI changes interactively when possible.
- Avoid scanning broad drive roots or adding behavior that recursively walks huge locations without cancellation checkpoints.
- Keep media loading tolerant. Unsupported or corrupt files should show placeholders instead of crashing.
- Do not commit generated `build/`, `dist/`, caches, or virtual environments.

## Verification

There is no test suite in the repo currently. For changes, at minimum run:

```powershell
python -m compileall app main.py
```

For UI or media-loading work, also run the app manually:

```powershell
python main.py
```

Then check folder scanning, thumbnail loading, filtering, viewer launch, and any changed workflow.
