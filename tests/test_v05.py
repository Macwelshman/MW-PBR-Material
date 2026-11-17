"""Blender runtime checks for V0.5 per-material panel state."""

from __future__ import annotations

import sys
from pathlib import Path

import bpy


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import mw_pbr_material  # noqa: E402
from mw_pbr_material import ui  # noqa: E402


def run(*, reset=True):
    if reset:
        bpy.ops.wm.read_factory_settings(use_empty=True)
    mw_pbr_material.register()

    mesh = bpy.data.meshes.new("MW V0.5 Test Mesh")
    obj = bpy.data.objects.new("MW V0.5 Test Object", mesh)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    settings = bpy.context.scene.mw_pbr_material
    assert bpy.app.timers.is_registered(ui._material_poll_timer)

    settings.material_name = "Material A"
    assert bpy.ops.mw_pbr.create_material() == {"FINISHED"}
    material_a = obj.active_material
    image_a = bpy.data.images.new("Material A BaseColor", 4, 4)
    settings.base_color = image_a
    settings.texture_scale = 2.0
    settings.base_color_brightness = -0.25
    settings.displacement_amount = 2.0

    external = bpy.data.materials.new("Temporary Material Slot")
    obj.data.materials.append(external)
    obj.active_material_index = 1
    settings.material_name = "Material B"
    assert bpy.ops.mw_pbr.create_material() == {"FINISHED"}
    material_b = obj.active_material
    image_b = bpy.data.images.new("Material B BaseColor", 4, 4)
    settings.base_color = image_b
    settings.texture_scale = 0.5
    settings.base_color_brightness = 0.4
    settings.emissive = bpy.data.images.new("Material B Emissive", 4, 4)
    settings.emission_strength = 3.0
    settings.displacement_amount = 0.5

    obj.active_material_index = 0
    ui._material_poll_timer()
    assert settings.material_name == material_a.name
    assert settings.base_color == image_a
    assert settings.emissive is None
    assert settings.texture_scale == 2.0
    assert settings.base_color_brightness == -0.25
    assert settings.emission_strength == 0.0
    assert settings.displacement_amount == 2.0

    obj.active_material_index = 1
    ui._material_poll_timer()
    assert settings.material_name == material_b.name
    assert settings.base_color == image_b
    assert settings.emissive is not None
    assert settings.texture_scale == 0.5
    assert abs(settings.base_color_brightness - 0.4) < 1e-6
    assert settings.emission_strength == 3.0
    assert settings.displacement_amount == 0.5

    # Automatic changes preserve each material's own texture selections.
    assert material_b.node_tree.nodes["MW BaseColor Texture"].image == image_b
    assert material_a.node_tree.nodes["MW BaseColor Texture"].image == image_a

    # The permanent Create action makes a clean replacement material.
    settings.material_name = "Material C"
    assert bpy.ops.mw_pbr.create_material() == {"FINISHED"}
    material_c = obj.active_material
    assert material_c != material_b
    assert settings.base_color is None
    assert settings.emissive is None
    assert material_a.node_tree.nodes["MW BaseColor Texture"].image == image_a
    assert material_b.node_tree.nodes["MW BaseColor Texture"].image == image_b

    mw_pbr_material.unregister()
    assert not bpy.app.timers.is_registered(ui._material_poll_timer)
    print("MW_PBR_MATERIAL_V05_RUNTIME_OK")


if __name__ == "__main__":
    run()
