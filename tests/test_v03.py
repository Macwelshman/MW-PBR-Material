"""Blender runtime checks for V0.3 shared texture scaling."""

from __future__ import annotations

import sys
import tempfile
from math import isclose
from pathlib import Path

import bpy


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import mw_pbr_material  # noqa: E402
from mw_pbr_material import ui  # noqa: E402


def _linked_from(material, target_node_name, target_socket_name):
    target = material.node_tree.nodes[target_node_name].inputs[target_socket_name]
    links = [link for link in material.node_tree.links if link.to_socket == target]
    assert len(links) == 1
    return links[0].from_node


def _mapping_scale(material):
    return tuple(
        material.node_tree.nodes["MW Texture Scale"].inputs["Scale"].default_value
    )


def _write_png(path):
    image = bpy.data.images.new("MW Reload Writer", width=4, height=4)
    image.filepath_raw = str(path)
    image.file_format = "PNG"
    image.save()
    bpy.data.images.remove(image)


def run():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    mw_pbr_material.register()
    assert ui._ICON_PREVIEWS is not None
    assert "green_check" in ui._ICON_PREVIEWS
    assert ui._green_check_icon_id() == ui._ICON_PREVIEWS["green_check"].icon_id

    mesh = bpy.data.meshes.new("MW V0.3 Test Mesh")
    obj = bpy.data.objects.new("MW V0.3 Test Object", mesh)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)

    settings = bpy.context.scene.mw_pbr_material
    assert settings.texture_scale == 1.0
    assert settings.emission_strength == 0.0
    scale_property = settings.bl_rna.properties["texture_scale"]
    assert isclose(scale_property.hard_min, 0.01, rel_tol=1e-6)
    assert isclose(scale_property.soft_min, 0.01, rel_tol=1e-6)
    assert bpy.ops.mw_pbr.create_material() == {"FINISHED"}
    material = obj.active_material

    settings.base_color = bpy.data.images.new("MW Scale BaseColor", 4, 4)
    settings.roughness = bpy.data.images.new("MW Scale Roughness", 4, 4)

    assert _mapping_scale(material) == (1.0, 1.0, 1.0)
    assert _linked_from(material, "MW Texture Scale", "Vector").name == (
        "MW Texture Coordinate"
    )
    assert _linked_from(material, "MW BaseColor Texture", "Vector").name == (
        "MW Texture Scale"
    )
    assert _linked_from(material, "MW Roughness Texture", "Vector").name == (
        "MW Texture Scale"
    )

    settings.texture_scale = 2.0
    assert _mapping_scale(material) == (0.5, 0.5, 0.5)
    settings.texture_scale = 0.5
    assert _mapping_scale(material) == (2.0, 2.0, 2.0)
    settings.texture_scale = 0.01
    assert _mapping_scale(material) == (100.0, 100.0, 100.0)
    assert bpy.ops.mw_pbr.reset_slider(target="texture_scale") == {"FINISHED"}
    assert settings.texture_scale == 1.0
    assert _mapping_scale(material) == (1.0, 1.0, 1.0)

    assert material.use_backface_culling is False
    assert bpy.ops.mw_pbr.toggle_backfaces() == {"FINISHED"}
    assert material.use_backface_culling is True
    assert "MW Backface Geometry" in material.node_tree.nodes
    assert "MW Backface Transparent" in material.node_tree.nodes
    assert "MW Backface Mix" in material.node_tree.nodes
    assert _linked_from(material, "MW Material Output", "Surface").name == (
        "MW Backface Mix"
    )
    assert bpy.ops.mw_pbr.toggle_backfaces() == {"FINISHED"}
    assert material.use_backface_culling is False
    assert "MW Backface Mix" not in material.node_tree.nodes
    assert _linked_from(material, "MW Material Output", "Surface").name == (
        "MW Principled BSDF"
    )
    material.use_backface_culling = True
    settings.texture_scale = 1.0
    assert material.use_backface_culling is True

    with tempfile.TemporaryDirectory(prefix="mw_pbr_reload_") as temp_dir:
        image_path = Path(temp_dir) / "Reload_BaseColor.png"
        _write_png(image_path)
        settings.base_color = bpy.data.images.load(str(image_path))
        assert bpy.ops.mw_pbr.reload_all_textures() == {"FINISHED"}
        assert settings.base_color.colorspace_settings.name == "sRGB"

    settings.emissive = bpy.data.images.new("MW Emissive Strength", 4, 4)
    settings.emission_strength = 2.5
    principled = material.node_tree.nodes["MW Principled BSDF"]
    assert principled.inputs["Emission Strength"].default_value == 2.5
    assert bpy.ops.mw_pbr.reset_slider(
        target="emission_strength"
    ) == {"FINISHED"}
    assert settings.emission_strength == 0.0

    external_material = bpy.data.materials.new("External V0.3 Material")
    obj.active_material = external_material
    assert bpy.ops.mw_pbr.create_material() == {"FINISHED"}
    assert settings.texture_scale == 1.0
    assert settings.emission_strength == 0.0
    assert "MW Texture Scale" not in obj.active_material.node_tree.nodes

    mw_pbr_material.unregister()
    print("MW_PBR_MATERIAL_V03_RUNTIME_OK")


if __name__ == "__main__":
    run()
