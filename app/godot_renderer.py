from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from app.texture_sets import TextureSet


def launch_material_renderer(texture_set: TextureSet) -> tuple[bool, str]:
    renderer_command = _renderer_command()
    if renderer_command is None:
        return (
            False,
            "Material renderer not found. Export the Godot renderer or install Godot 4.",
        )

    texture_args = _material_arguments(texture_set)
    if not texture_args:
        return False, "No supported material maps were detected."

    command, working_directory = renderer_command
    try:
        subprocess.Popen(
            [*command, "--", *texture_args],
            cwd=os.fspath(working_directory),
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )
    except OSError as exc:
        return False, f"Could not start the material renderer: {exc}"
    return True, f"Opened material renderer for {texture_set.title}"


def _material_arguments(texture_set: TextureSet) -> list[str]:
    roles = texture_set.roles
    arguments: list[str] = []

    def add_role(role: str, argument_name: str) -> None:
        items = roles.get(role, [])
        if items:
            arguments.extend([f"--{argument_name}", os.fspath(items[0].preview_path)])

    add_role("basecolor", "basecolor")
    add_role("normal", "normal")
    add_role("roughness", "roughness")
    add_role("metallic", "metallic")
    add_role("ao", "ao")
    add_role("height", "height")
    add_role("opacity", "opacity")

    if "roughness" not in roles and roles.get("gloss"):
        arguments.extend(["--roughness", os.fspath(roles["gloss"][0].preview_path)])
        arguments.extend(["--roughness_mode", "invert_grayscale"])

    packed_items = roles.get("packed", [])
    if packed_items:
        packed_path = packed_items[0].preview_path
        arguments.extend(["--packed", os.fspath(packed_path), "--use_packed", "true"])
        layout = _packed_layout(packed_path)
        if layout:
            arguments.extend(["--workflow", layout])

    if roles.get("height"):
        arguments.extend(["--use_displacement", "false"])
    if roles.get("opacity"):
        arguments.extend(["--use_opacity", "true"])
    return arguments


def _packed_layout(path: Path) -> str:
    stem = path.stem.lower()
    for layout in ("orm", "mro", "rma"):
        if layout in stem:
            return layout
    return ""


def _exported_renderer_names() -> list[str]:
    if sys.platform == "win32":
        return ["TextureBrowserMaterialRenderer.exe"]
    if sys.platform == "darwin":
        return [
            "TextureBrowserMaterialRenderer.app/Contents/MacOS/TextureBrowserMaterialRenderer",
            "TextureBrowserMaterialRenderer",
        ]
    return [
        "TextureBrowserMaterialRenderer.x86_64",
        "TextureBrowserMaterialRenderer",
    ]


def _renderer_command() -> tuple[list[str], Path] | None:
    bundle_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    project_path = bundle_root / "godot_material_renderer"
    exported_candidates = [
        base / name
        for name in _exported_renderer_names()
        for base in (project_path, project_path / "build", bundle_root)
    ]
    configured_renderer = os.environ.get("TEXTURE_BROWSER_RENDERER", "").strip()
    if configured_renderer:
        exported_candidates.insert(0, Path(configured_renderer))

    for candidate in exported_candidates:
        if candidate.is_file():
            return [os.fspath(candidate)], candidate.parent

    godot = _find_godot()
    if godot is None or not (project_path / "project.godot").is_file():
        return None
    return [os.fspath(godot), "--path", os.fspath(project_path)], project_path


def _find_godot() -> Path | None:
    configured = os.environ.get("GODOT_PATH", "").strip()
    if configured and Path(configured).is_file():
        return Path(configured)

    for executable_name in ("godot4", "godot"):
        executable = shutil.which(executable_name)
        if executable:
            return Path(executable)

    if os.name == "nt":
        local_app_data = Path(os.environ.get("LOCALAPPDATA", ""))
        packages = local_app_data / "Microsoft" / "WinGet" / "Packages"
        if packages.is_dir():
            matches = sorted(
                (
                    path
                    for path in packages.glob("GodotEngine.GodotEngine_*/*win64.exe")
                    if "_console" not in path.name.lower()
                ),
                reverse=True,
            )
            if matches:
                return matches[0]
    elif sys.platform == "darwin":
        for candidate in (
            Path("/Applications/Godot.app/Contents/MacOS/Godot"),
            Path.home() / "Applications" / "Godot.app" / "Contents" / "MacOS" / "Godot",
        ):
            if candidate.is_file():
                return candidate
    return None
