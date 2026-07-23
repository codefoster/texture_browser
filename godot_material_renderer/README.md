# Texture Browser Material Renderer

Godot 4 PBR material previewer used by Texture Browser. Right-click an image in
Texture Browser and choose Open material renderer; the browser detects its
material set and supplies the recognized maps.

## Current Features

- Albedo, normal, roughness/gloss, metallic, AO, height, opacity, and packed
  ORM/MRO/RMA inputs.
- Multi-file drag and drop with automatic map-role detection.
- Metal/rough, spec/gloss, ORM, MRO, RMA, and diffuse/normal workflows.
- Solo-map inspection, map replacement, material health checks, and presets.
- HDRI and movable key/fill lighting, lighting presets, and background swatches.
- Parallax height plus optional real geometry displacement for dense planes and
  spheres.
- UV tiling shared by shading and displacement, normal green-channel flipping,
  opacity, custom objects, and PNG export.
- Debounced settings and displacement updates for lower CPU and disk usage.
- EXR fallback conversion through oiiotool when Godot cannot decode a file.

## Development Run

~~~powershell
godot --path godot_material_renderer -- --basecolor "D:\materials\stone_albedo.png" --normal "D:\materials\stone_normal.png" --roughness "D:\materials\stone_roughness.png"
~~~

## Windows Export

Install the matching Godot export templates, then run:

~~~powershell
godot --headless --path godot_material_renderer --export-release "Windows Desktop" "build\TextureBrowserMaterialRenderer.exe"
~~~

The export preset embeds the PCK. When the exported executable is present,
TextureBrowser.spec includes it in the packaged browser. Without an export, the
source build falls back to GODOT_PATH, a Godot executable on PATH, or a Godot
installation managed by WinGet.

temp_material/ contains runtime and render-test output and is excluded from the
exported project.
