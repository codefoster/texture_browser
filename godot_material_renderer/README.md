# Texture Browser Material Renderer

Small Godot project for rendering a material preview sphere from texture paths.
The renderer is separate from the main Texture Browser UI while it is being
stabilized, but it is designed to become the GPU-backed material thumbnail
generator.

## Current features

- PBR sphere preview with albedo, normal, roughness, metallic, AO, packed map,
  and height/parallax inputs.
- Workflow presets for metal/rough, spec/gloss, ORM, MRO, RMA, and
  diffuse/normal.
- Packed map channel selectors with an explicit `Use packed channels` checkbox
  so combined maps can be ignored until needed.
- Roughness modes for original red, grayscale, inverted red, and inverted
  grayscale.
- Height/parallax preview with enable, invert, and strength controls.
- DirectX normal support through the `Flip normal green` toggle.
- HDRI lighting with internal Ice Lake HDRI assets, HDRI rotation, and HDRI
  brightness up to 12.
- Draggable key light that can light from above, below, or either side.
- AO strength, UV scale, sphere scale, background swatches, albedo-only
  diagnostic mode, export folder browsing, and image export.

## Notes

- Godot's height map support here is parallax height mapping, not true geometry
  displacement. It is intended for fast material thumbnail previews.
- Set the roughness slider to `1.0` to read roughness maps as authored. Lower
  values are artistic overrides and will make materials glossier.
- Keep generated render tests and runtime HDRI files under `temp_material/`;
  that folder is intentionally ignored by git.

Run it visibly from the repo root:

```powershell
godot --path godot_material_renderer -- `
  --basecolor "D:\3D_Library\Materials\MegaScans\soil_sandy_ve0hedi\ve0hedi_8K_Albedo.jpg" `
  --normal "D:\3D_Library\Materials\MegaScans\soil_sandy_ve0hedi\ve0hedi_8K_Normal.jpg" `
  --roughness "D:\3D_Library\Materials\MegaScans\soil_sandy_ve0hedi\ve0hedi_8K_Roughness.jpg" `
  --ao "D:\3D_Library\Materials\MegaScans\soil_sandy_ve0hedi\ve0hedi_8K_AO.jpg"
```

Render to a PNG:

```powershell
godot --path godot_material_renderer -- `
  --basecolor "D:\3D_Library\Materials\MegaScans\soil_sandy_ve0hedi\ve0hedi_8K_Albedo.jpg" `
  --normal "D:\3D_Library\Materials\MegaScans\soil_sandy_ve0hedi\ve0hedi_8K_Normal.jpg" `
  --roughness "D:\3D_Library\Materials\MegaScans\soil_sandy_ve0hedi\ve0hedi_8K_Roughness.jpg" `
  --ao "D:\3D_Library\Materials\MegaScans\soil_sandy_ve0hedi\ve0hedi_8K_AO.jpg" `
  --output "C:\tmp\soil_sandy_godot_preview.png"
```

This project is intentionally separate from Texture Browser until the renderer is stable.
