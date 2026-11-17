"""Blender runtime checks for the MW PBR Material V0.1 contract."""

from __future__ import annotations

import sys
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
    assert len(links) == 1, (target_node_name, target_socket_name, len(links))
    return links[0].from_node


def _new_image(name):
    return bpy.data.images.new(name, width=4, height=4)


def _matching_material_callbacks(panel):
    return [
        callback
        for callback in tuple(getattr(panel.draw, "_draw_funcs", ()))
        if getattr(callback, "__name__", "") == "_material_context_draw"
        and getattr(callback, "__module__", "").endswith("mw_pbr_material.ui")
    ]


def run(*, reset=True, color="sRGB", data="Non-Color"):
    if reset:
        bpy.ops.wm.read_factory_settings(use_empty=True)
    mw_pbr_material.register()

    mesh = bpy.data.meshes.new("MW Test Mesh")
    obj = bpy.data.objects.new("MW Test Object", mesh)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)

    for panel_name in ui.MATERIAL_CONTEXT_PANELS:
        panel = getattr(bpy.types, panel_name, None)
        if panel is not None:
            assert len(_matching_material_callbacks(panel)) == 1

    ui._register_material_context_draw()
    for panel_name in ui.MATERIAL_CONTEXT_PANELS:
        panel = getattr(bpy.types, panel_name, None)
        if panel is not None:
            assert len(_matching_material_callbacks(panel)) == 1

    class TestLayout:
        def __init__(self, events=None):
            self.events = events if events is not None else []
            self.operator_call = None

        def separator(self):
            self.events.append("separator")

        def operator(self, operator_id, **kwargs):
            self.events.append("operator")
            self.operator_call = (operator_id, kwargs)
            return type("TestOperatorProperties", (), {})()

        def panel(self, panel_id, **kwargs):
            self.events.append("panel")
            assert panel_id == "mw_pbr_material_builder"
            assert kwargs == {"default_closed": False}
            return TestLayout(), TestLayout()

        def label(self, **_kwargs):
            pass

        def prop(self, *_args, **_kwargs):
            pass

        def column(self, **_kwargs):
            return self

        def template_ID(self, *_args, **_kwargs):
            pass

        def box(self):
            return self

        def progress(self, **_kwargs):
            pass

        def row(self, **_kwargs):
            return self

    test_panel = type("TestPanel", (), {"layout": TestLayout()})()
    ui._material_context_draw(test_panel, bpy.context)
    assert test_panel.layout.operator_call == (
        "mw_pbr.create_material",
        {"text": "Create PBR Material", "icon": "ADD"},
    )
    assert test_panel.layout.events == ["separator", "operator"]

    settings = bpy.context.scene.mw_pbr_material
    settings.material_name = "MW V0.1 Runtime Test"

    result = bpy.ops.mw_pbr.create_material()
    assert result == {"FINISHED"}, result
    material = obj.active_material
    settings.normal_interpretation = "DIRECTX"

    roles = {
        "base_color": "BaseColor",
        "metallic": "Metallic",
        "roughness": "Roughness",
        "normal": "Normal",
        "opacity": "Opacity",
        "height": "Height",
        "ambient_occlusion": "Ambient Occlusion",
        "emissive": "Emissive",
    }
    images = {}
    for property_name, label in roles.items():
        images[property_name] = _new_image(f"MW Test {label}")
        setattr(settings, property_name, images[property_name])

    assert material is not None
    assert material.name == "MW V0.1 Runtime Test"
    assert material["mw_pbr_material"] is True
    assert material.node_tree is not None
    assert material.surface_render_method == "DITHERED"

    for role in ("base_color", "emissive"):
        assert images[role].colorspace_settings.name == color
    for role in (
        "metallic",
        "roughness",
        "normal",
        "opacity",
        "height",
        "ambient_occlusion",
    ):
        assert images[role].colorspace_settings.name == data, (
            role,
            images[role].colorspace_settings.name,
        )

    nodes = material.node_tree.nodes
    assert "MW AO BaseColor Multiply" in nodes
    assert _linked_from(material, "MW Principled BSDF", "Base Color").name == (
        "MW AO BaseColor Multiply"
    )
    assert _linked_from(material, "MW Principled BSDF", "Metallic").name == (
        "MW Metallic Texture"
    )
    assert _linked_from(material, "MW Principled BSDF", "Roughness").name == (
        "MW Roughness Texture"
    )
    assert _linked_from(material, "MW Principled BSDF", "Alpha").name == (
        "MW Opacity Texture"
    )
    assert _linked_from(material, "MW Principled BSDF", "Normal").name == (
        "MW Height Bump"
    )
    assert _linked_from(material, "MW Height Bump", "Normal").name == (
        "MW OpenGL Normal Map"
    )
    assert _linked_from(material, "MW Principled BSDF", "Emission Color").name == (
        "MW Emissive Texture"
    )
    assert nodes["MW Principled BSDF"].inputs["Emission Strength"].default_value == 0.0

    flip = nodes["MW Flip DirectX Green"]
    assert flip.operation == "SUBTRACT"
    assert flip.inputs[0].default_value == 1.0

    visible_panel = type("TestPanel", (), {"layout": TestLayout()})()
    ui._material_context_draw(visible_panel, bpy.context)
    assert visible_panel.layout.events == ["separator", "operator", "panel"]
    assert visible_panel.layout.operator_call == (
        "mw_pbr.create_material",
        {"text": "Create PBR Material", "icon": "ADD"},
    )

    settings.material_name = "MW Auto Normal Test"
    settings.normal_interpretation = "AUTO"
    result = bpy.ops.mw_pbr.create_material()
    assert result == {"FINISHED"}, result
    auto_material = obj.active_material
    settings.normal = images["normal"]
    assert "MW OpenGL Normal Map" in auto_material.node_tree.nodes
    assert "MW Flip DirectX Green" not in auto_material.node_tree.nodes

    mw_pbr_material.unregister()
    for panel_name in ui.MATERIAL_CONTEXT_PANELS:
        panel = getattr(bpy.types, panel_name, None)
        if panel is not None:
            assert not _matching_material_callbacks(panel)
    print("MW_PBR_MATERIAL_V01_RUNTIME_OK")


if __name__ == "__main__":
    run()
