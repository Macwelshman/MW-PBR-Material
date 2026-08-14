"""Blender runtime checks for V0.2 folder detection and companion loading."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import bpy


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import mw_pbr_material  # noqa: E402
from mw_pbr_material import ui  # noqa: E402
from mw_pbr_material.texture_detection import classify_texture_path  # noqa: E402


def _write_png(path):
    image = bpy.data.images.new(f"Writer {path.stem}", width=4, height=4)
    image.filepath_raw = str(path)
    image.file_format = "PNG"
    image.save()
    bpy.data.images.remove(image)


def _basename(image):
    return Path(bpy.path.abspath(image.filepath)).name


def _make_active_mesh():
    mesh = bpy.data.meshes.new("MW V0.2 Test Mesh")
    obj = bpy.data.objects.new("MW V0.2 Test Object", mesh)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    return obj


def run():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    mw_pbr_material.register()
    obj = _make_active_mesh()
    settings = bpy.context.scene.mw_pbr_material

    assert classify_texture_path(Path("Metal_Wall_AO_2K.png")).role == (
        "ambient_occlusion"
    )
    assert classify_texture_path(Path("Metal_Wall_2K.png")) is None
    assert classify_texture_path(Path("Stone_NormalOpenGL.png")).role == "normal"
    assert classify_texture_path(Path("Stone_NormalDirectX.png")).role == "normal"
    assert classify_texture_path(Path("PavingStones10_4K-PNG_Color.png")).role == (
        "base_color"
    )
    assert classify_texture_path(Path("PavingStones10_4K_Colour.png")).role == (
        "base_color"
    )
    assert classify_texture_path(Path("PavingStones10_4K_Colour.png")).set_key == (
        "paving_stones10_4k"
    )
    short_aliases = {
        "Brick_diff.png": "base_color",
        "Brick_rough.png": "roughness",
        "Brick_nor.png": "normal",
        "Brick_disp.png": "height",
    }
    for filename, role in short_aliases.items():
        match = classify_texture_path(Path(filename))
        assert match.role == role
        assert match.set_key == "brick"

    assert classify_texture_path(Path("Brick_nor_gl.png")).alias == "nor_gl"
    assert classify_texture_path(Path("Brick_nor_dx.png")).alias == "nor_dx"

    with tempfile.TemporaryDirectory(prefix="mw_pbr_v02_") as temp_dir:
        folder = Path(temp_dir)
        expected = {
            "base_color": "Stone_BaseColor.png",
            "metallic": "Stone_Metalness.png",
            "roughness": "Stone_Rough.png",
            "normal": "Stone_NormalDX.png",
            "opacity": "Stone_Alpha.png",
            "height": "Stone_Displacement.png",
            "ambient_occlusion": "Stone_AmbientOcclusion.png",
            "emissive": "Stone_Emission.png",
        }
        for filename in expected.values():
            _write_png(folder / filename)
        (folder / "notes.txt").write_text("not a texture", encoding="utf-8")

        # The Create action establishes the owned material and reveals the UI.
        settings.material_name = "MW V0.2 Auto DirectX Test"
        assert bpy.ops.mw_pbr.create_material() == {"FINISHED"}
        material = obj.active_material
        assert material["mw_pbr_material"] is True

        # Choosing a folder scans immediately and rebuilds that material in place.
        settings.texture_folder = str(folder)
        assert obj.active_material == material
        assert settings.matched_texture_count == 8
        assert settings.scan_status == "Matched 8 of 8 texture maps"
        assert settings.detected_normal_convention == "DIRECTX"
        assert ui._effective_normal_convention(settings) == "DIRECTX"
        assert not ui._normal_convention_uncertain(settings)
        for role, filename in expected.items():
            assert _basename(getattr(settings, role)) == filename
        assert bpy.ops.mw_pbr.scan_texture_folder() == {"FINISHED"}
        assert obj.active_material.name == "MW V0.2 Auto DirectX Test"
        assert "MW Flip DirectX Green" in obj.active_material.node_tree.nodes

        # A manual override must take precedence over filename detection.
        settings.normal_interpretation = "OPENGL"
        assert obj.active_material == material
        assert "MW Flip DirectX Green" not in obj.active_material.node_tree.nodes

        assert bpy.ops.mw_pbr.set_normal_convention(
            convention="DIRECTX"
        ) == {"FINISHED"}
        assert settings.normal_interpretation == "DIRECTX"
        assert "MW Flip DirectX Green" in obj.active_material.node_tree.nodes

        settings.normal_interpretation = "AUTO"
        settings.detected_normal_convention = "UNKNOWN"
        assert ui._effective_normal_convention(settings) == "OPENGL"
        assert ui._normal_convention_uncertain(settings)

        assert bpy.ops.mw_pbr.remove_all_textures() == {"FINISHED"}
        assert settings.matched_texture_count == 0
        assert all(
            getattr(settings, role) is None
            for role in (
                "base_color",
                "metallic",
                "roughness",
                "normal",
                "opacity",
                "height",
                "ambient_occlusion",
                "emissive",
            )
        )
        assert not any(
            node.bl_idname == "ShaderNodeTexImage"
            for node in material.node_tree.nodes
        )

        # Create always makes a fresh material with clean source settings.
        previous_material = material
        settings.material_name = "MW V0.2 Fresh Material"
        assert bpy.ops.mw_pbr.create_material() == {"FINISHED"}
        material = obj.active_material
        assert material != previous_material
        assert settings.texture_folder == ""
        assert settings.matched_texture_count == 0
        assert all(getattr(settings, role) is None for role in expected)

    with tempfile.TemporaryDirectory(prefix="mw_pbr_mixed_sets_") as temp_dir:
        folder = Path(temp_dir)
        for filename in (
            "Brick_Color.png",
            "Brick_Roughness.png",
            "Stone_Color.png",
            "Stone_Roughness.png",
            "Stone_NormalDX.png",
            "Stone_NormalGL.png",
        ):
            _write_png(folder / filename)

        # Folder scans choose one complete set and prefer native OpenGL normals.
        settings.texture_folder = str(folder)
        assert _basename(settings.base_color) == "Stone_Color.png"
        assert _basename(settings.roughness) == "Stone_Roughness.png"
        assert _basename(settings.normal) == "Stone_NormalGL.png"
        assert settings.detected_normal_convention == "OPENGL"

        # A manually selected map anchors companions to its own material name.
        selected = bpy.data.images.load(str(folder / "Brick_Color.png"))
        settings.base_color = selected
        assert _basename(settings.base_color) == "Brick_Color.png"
        assert _basename(settings.roughness) == "Brick_Roughness.png"
        assert settings.normal is None
        clean_principled = material.node_tree.nodes["MW Principled BSDF"]
        assert clean_principled.inputs["Emission Strength"].default_value == 0.0
        assert tuple(clean_principled.inputs["Emission Color"].default_value) == (
            0.0,
            0.0,
            0.0,
            1.0,
        )

    with tempfile.TemporaryDirectory(prefix="mw_pbr_short_aliases_") as temp_dir:
        folder = Path(temp_dir)
        short_set = {
            "base_color": "Brick_diff.png",
            "roughness": "Brick_rough.png",
            "normal": "Brick_nor_gl.png",
            "height": "Brick_disp.png",
        }
        for filename in short_set.values():
            _write_png(folder / filename)
        settings.texture_folder = str(folder)
        for role, filename in short_set.items():
            assert _basename(getattr(settings, role)) == filename
        assert settings.detected_normal_convention == "OPENGL"

    with tempfile.TemporaryDirectory(prefix="mw_pbr_companions_") as temp_dir:
        folder = Path(temp_dir)
        for filename in (
            "Brick_Albedo.png",
            "Brick_Roughness.png",
            "Brick_NormalGL.png",
        ):
            _write_png(folder / filename)

        # Selecting one recognised map loads the companions from its folder.
        selected = bpy.data.images.load(str(folder / "Brick_Albedo.png"))
        settings.base_color = selected
        detected_folder = Path(bpy.path.abspath(settings.texture_folder)).resolve()
        assert detected_folder == folder.resolve()
        assert settings.matched_texture_count == 3
        assert _basename(settings.base_color) == "Brick_Albedo.png"
        assert _basename(settings.roughness) == "Brick_Roughness.png"
        assert _basename(settings.normal) == "Brick_NormalGL.png"
        assert settings.detected_normal_convention == "OPENGL"
        assert settings.metallic is None

        # Disabling companion loading permits a single-slot manual override.
        previous_folder = settings.texture_folder
        settings.auto_load_companions = False
        override_folder = folder / "override"
        override_folder.mkdir()
        override_path = override_folder / "Override_Roughness.png"
        _write_png(override_path)
        settings.roughness = bpy.data.images.load(str(override_path))
        assert settings.texture_folder == previous_folder
        assert _basename(settings.roughness) == "Override_Roughness.png"

        # Every new material must start with no retained folder or textures.
        settings.material_name = "MW Clean Material Test"
        previous_material = obj.active_material
        external_material = bpy.data.materials.new("External Test Material")
        obj.active_material = external_material
        assert bpy.ops.mw_pbr.create_material() == {"FINISHED"}
        clean_material = obj.active_material
        assert clean_material != previous_material
        assert settings.texture_folder == ""
        assert settings.matched_texture_count == 0
        assert all(
            getattr(settings, role) is None
            for role in (
                "base_color",
                "metallic",
                "roughness",
                "normal",
                "opacity",
                "height",
                "ambient_occlusion",
                "emissive",
            )
        )
        assert not any(
            node.bl_idname == "ShaderNodeTexImage"
            for node in clean_material.node_tree.nodes
        )
        clean_principled = clean_material.node_tree.nodes["MW Principled BSDF"]
        assert clean_principled.inputs["Emission Strength"].default_value == 0.0
        assert tuple(clean_principled.inputs["Emission Color"].default_value) == (
            0.0,
            0.0,
            0.0,
            1.0,
        )

    mw_pbr_material.unregister()
    print("MW_PBR_MATERIAL_V02_RUNTIME_OK")


if __name__ == "__main__":
    run()
