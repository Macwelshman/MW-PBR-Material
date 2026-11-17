"""Blender runtime checks for V0.4 BaseColor brightness."""

from __future__ import annotations

import sys
from pathlib import Path

import bpy


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import mw_pbr_material  # noqa: E402


def _linked_from(material, target_node_name, target_socket_name):
    target = material.node_tree.nodes[target_node_name].inputs[target_socket_name]
    links = [link for link in material.node_tree.links if link.to_socket == target]
    assert len(links) == 1
    return links[0].from_node


def run(*, reset=True):
    if reset:
        bpy.ops.wm.read_factory_settings(use_empty=True)
    mw_pbr_material.register()

    mesh = bpy.data.meshes.new("MW V0.4 Test Mesh")
    obj = bpy.data.objects.new("MW V0.4 Test Object", mesh)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)

    settings = bpy.context.scene.mw_pbr_material
    assert settings.base_color_brightness == 0.0
    assert bpy.ops.mw_pbr.create_material() == {"FINISHED"}
    material = obj.active_material
    settings.base_color = bpy.data.images.new("MW Brightness BaseColor", 4, 4)

    adjustment = material.node_tree.nodes["MW BaseColor Brightness"]
    assert adjustment.blend_type == "MIX"
    assert adjustment.inputs[0].default_value == 0.0
    assert _linked_from(material, "MW Principled BSDF", "Base Color").name == (
        "MW BaseColor Brightness"
    )

    settings.base_color_brightness = 0.75
    adjustment = material.node_tree.nodes["MW BaseColor Brightness"]
    assert adjustment.blend_type == "MIX"
    assert adjustment.inputs[0].default_value == 0.75

    settings.base_color_brightness = -0.5
    adjustment = material.node_tree.nodes["MW BaseColor Brightness"]
    assert adjustment.blend_type == "MULTIPLY"
    assert tuple(adjustment.inputs[2].default_value) == (0.5, 0.5, 0.5, 1.0)

    assert bpy.ops.mw_pbr.reset_slider(
        target="base_color_brightness"
    ) == {"FINISHED"}
    assert settings.base_color_brightness == 0.0
    adjustment = material.node_tree.nodes["MW BaseColor Brightness"]
    assert adjustment.blend_type == "MIX"
    assert adjustment.inputs[0].default_value == 0.0

    settings.ambient_occlusion = bpy.data.images.new("MW Brightness AO", 4, 4)
    assert _linked_from(
        material,
        "MW AO BaseColor Multiply",
        "Color1",
    ).name == "MW BaseColor Brightness"
    assert _linked_from(material, "MW Principled BSDF", "Base Color").name == (
        "MW AO BaseColor Multiply"
    )

    external_material = bpy.data.materials.new("External V0.4 Material")
    obj.active_material = external_material
    assert bpy.ops.mw_pbr.create_material() == {"FINISHED"}
    assert settings.base_color_brightness == 0.0

    mw_pbr_material.unregister()
    print("MW_PBR_MATERIAL_V04_RUNTIME_OK")


if __name__ == "__main__":
    run()
