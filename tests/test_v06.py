"""Blender runtime checks for V0.6 height displacement modes."""

from __future__ import annotations

import sys
from math import isclose
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


def _is_linked(material, target_node_name, target_socket_name):
    target = material.node_tree.nodes[target_node_name].inputs[target_socket_name]
    return any(link.to_socket == target for link in material.node_tree.links)


def run(*, reset=True):
    if reset:
        bpy.ops.wm.read_factory_settings(use_empty=True)
    mw_pbr_material.register()

    mesh = bpy.data.meshes.new("MW V0.6 Test Mesh")
    obj = bpy.data.objects.new("MW V0.6 Test Object", mesh)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)

    assert bpy.ops.mw_pbr.create_material() == {"FINISHED"}
    material = obj.active_material
    settings = bpy.context.scene.mw_pbr_material
    settings.normal = bpy.data.images.new("MW V0.6 Normal", 4, 4)
    settings.height = bpy.data.images.new("MW V0.6 Height", 4, 4)

    assert material.displacement_method == "BUMP"
    assert "MW Height Bump" in material.node_tree.nodes
    assert material.node_tree.nodes["MW Height Bump"].inputs[
        "Strength"
    ].default_value == 1.0
    assert "MW Height Displacement" not in material.node_tree.nodes
    assert not _is_linked(material, "MW Material Output", "Displacement")

    amount_property = settings.bl_rna.properties["displacement_amount"]
    assert amount_property.hard_min == 0.0
    assert amount_property.hard_max == 2.0

    settings.displacement_amount = 2.0
    assert material.node_tree.nodes["MW Height Bump"].inputs[
        "Strength"
    ].default_value == 2.0
    assert bpy.ops.mw_pbr.reset_slider(
        target="displacement_amount"
    ) == {"FINISHED"}
    assert settings.displacement_amount == 1.0

    assert bpy.ops.mw_pbr.set_displacement_method(
        method="DISPLACEMENT"
    ) == {"FINISHED"}
    assert material.displacement_method == "DISPLACEMENT"
    assert "MW Height Bump" not in material.node_tree.nodes
    assert "MW Height Displacement" in material.node_tree.nodes
    assert isclose(
        material.node_tree.nodes["MW Height Displacement"].inputs[
            "Scale"
        ].default_value,
        1.0,
        rel_tol=1e-6,
    )
    assert _linked_from(material, "MW Material Output", "Displacement").name == (
        "MW Height Displacement"
    )
    assert _linked_from(material, "MW Principled BSDF", "Normal").name == (
        "MW OpenGL Normal Map"
    )

    settings.displacement_amount = 2.0
    assert material.node_tree.nodes["MW Height Displacement"].inputs[
        "Scale"
    ].default_value == 2.0

    assert bpy.ops.mw_pbr.set_displacement_method(method="BOTH") == {"FINISHED"}
    assert material.displacement_method == "BOTH"
    assert "MW Height Bump" in material.node_tree.nodes
    assert "MW Height Displacement" in material.node_tree.nodes
    assert material.node_tree.nodes["MW Height Bump"].inputs[
        "Strength"
    ].default_value == 2.0
    assert _linked_from(material, "MW Principled BSDF", "Normal").name == (
        "MW Height Bump"
    )
    assert _linked_from(material, "MW Height Bump", "Normal").name == (
        "MW OpenGL Normal Map"
    )

    mw_pbr_material.unregister()
    print("MW_PBR_MATERIAL_V06_RUNTIME_OK")


if __name__ == "__main__":
    run()
