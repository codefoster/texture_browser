# Changelog

## 0.2.0-beta.1

### Stability

- Thumbnail workers now return QImage data and create QPixmap objects only on
  the GUI thread.
- Added focused regression tests for worker thumbnails, Favorites index
  invalidation, dimension caching, and renderer argument mapping.

### Performance

- Removed full manifest rewrites from individual thumbnail jobs; Cache Here
  rebuilds the manifest once after its bounded queue completes.
- Limited thumbnail memory to a 96 MB byte budget.
- Made worker counts adaptive and limited Cache Here to a small pending queue.
- Added bounded, modification-aware folder and Favorites caches.
- Added persistent SQLite image-dimension caching.
- Debounced search input and made visible thumbnail discovery proportional to
  the viewport rather than the whole library.
- Debounced Godot settings writes and displacement slider rebuilds.
- Switched the HDRI sky away from continuous realtime processing and indexed
  generated displacement meshes.
- Added source signatures to converted EXR cache files.

### Integration

- Added Open material renderer to the image context menu.
- Added automatic material-role arguments for the Godot renderer.
- Added a Windows Godot export preset and conditional PyInstaller packaging.
- Displayed the semantic version in the application title.

## 0.1.0-beta.1

- First tracked semantic-version checkpoint.
- Added multi-texture material-set drag and drop with automatic channel and
  packed-layout detection.
