"""Run through Flue in a disposable Blender session."""
from pathlib import Path
from tempfile import TemporaryDirectory

import bpy

import mw_pbr_material
from mw_pbr_material import material_builder as builder
from mw_pbr_material.texture_detection import settings_update_guard


def texture(directory, name):
    path = directory / name
    image = bpy.data.images.new(name, 2, 2)
    image.filepath_raw = str(path)
    image.file_format = "PNG"
    image.save()
    bpy.data.images.remove(image)
    return path


def object_with_material():
    obj = bpy.data.objects.new("Subject", bpy.data.meshes.new("Subject"))
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    return obj


def test_reuse_variants(directory, color, data):
    path = texture(directory, "Set_BaseColor.png")
    original = bpy.data.images.load(str(path))
    original.colorspace_settings.name = color
    artist = bpy.data.materials.new("Artist Material")
    artist_node = artist.node_tree.nodes.new("ShaderNodeTexImage")
    artist_node.image = original
    settings = bpy.context.scene.mw_pbr_material
    with settings_update_guard(settings):
        settings.base_color = original
        settings.normal = original
    initial = path.read_bytes()
    first = builder.build_material(settings)
    variant = first.node_tree.nodes["MW Normal Texture"].image
    assert variant != original and variant.colorspace_settings.name == data
    assert first.node_tree.nodes["MW BaseColor Texture"].image == original
    assert artist_node.image == original and original.colorspace_settings.name == color
    count = len(bpy.data.images)
    with settings_update_guard(settings):
        settings.normal = original
    second = builder.build_material(settings)
    assert second.node_tree.nodes["MW Normal Texture"].image == variant, "created a redundant colour-space copy"
    assert len(bpy.data.images) == count
    assert path.read_bytes() == initial


def test_manual_anchor(directory, color):
    path = texture(directory, "Manual_BaseColor.png")
    texture(directory, "Manual_Roughness.png")
    first = bpy.data.images.load(str(path), check_existing=True)
    manual = bpy.data.images.load(str(path), check_existing=False)
    manual.colorspace_settings.name = color
    obj = object_with_material()
    assert bpy.ops.mw_pbr.create_material() == {"FINISHED"}
    settings = bpy.context.scene.mw_pbr_material
    settings.base_color = manual
    assert settings.base_color != first
    assert obj.active_material.node_tree.nodes["MW BaseColor Texture"].image == manual
    assert settings.roughness is not None
    # An unrecognised filename is still a valid manual choice and must not
    # replace the companions with a different set.
    unnamed = bpy.data.images.load(str(texture(directory, "Reference.png")))
    settings.base_color = unnamed
    assert obj.active_material.node_tree.nodes["MW BaseColor Texture"].image == unnamed
    assert settings.roughness is not None
    # Missing (but named correctly) manual picks should not trigger a rescan.
    manual.filepath = str(directory / "missing" / path.name)
    settings.base_color = manual
    assert obj.active_material.node_tree.nodes["MW BaseColor Texture"].image == manual
    assert settings.roughness is not None


def test_scene_image_user(color, data):
    image = bpy.data.images.new("Referenced by the scene", 2, 2)
    image.colorspace_settings.name = color
    scene = bpy.context.scene
    # A scene ID can contain image references other than MW's pickers.
    scene["artist_image"] = image
    settings = scene.mw_pbr_material
    with settings_update_guard(settings):
        settings.roughness = image
    material = builder.build_material(settings)
    interpreted = material.node_tree.nodes["MW Roughness Texture"].image
    assert interpreted != image and interpreted.colorspace_settings.name == data
    assert scene["artist_image"] == image and image.colorspace_settings.name == color


def test_undo_redo():
    obj = object_with_material()
    bpy.context.preferences.edit.use_global_undo = True
    assert bpy.ops.mw_pbr.create_material() == {"FINISHED"}
    settings = bpy.context.scene.mw_pbr_material
    settings.auto_load_companions = False
    settings.normal = bpy.data.images.new("Normal", 2, 2)
    assert bpy.ops.ed.undo_push(message="OpenGL fixture") == {"FINISHED"}
    assert bpy.ops.mw_pbr.set_normal_convention(convention="DIRECTX") == {"FINISHED"}
    # Python execution does not implicitly push operator undo from a bridge.
    assert bpy.ops.ed.undo_push(message="DirectX fixture") == {"FINISHED"}
    assert "MW Flip DirectX Green" in obj.active_material.node_tree.nodes
    assert bpy.ops.ed.undo() == {"FINISHED"}
    assert "MW Flip DirectX Green" not in bpy.context.object.active_material.node_tree.nodes
    assert bpy.context.scene.mw_pbr_material.normal_interpretation != "DIRECTX"
    assert bpy.ops.ed.redo() == {"FINISHED"}
    assert "MW Flip DirectX Green" in bpy.context.object.active_material.node_tree.nodes
    assert bpy.context.scene.mw_pbr_material.normal_interpretation == "DIRECTX"


def run(case, color="sRGB", data="Non-Color", *, reset=True):
    if reset:
        bpy.ops.wm.read_factory_settings(use_empty=True)
    mw_pbr_material.register()
    try:
        with TemporaryDirectory() as directory:
            if case == "reuse":
                test_reuse_variants(Path(directory), color, data)
            elif case == "manual":
                test_manual_anchor(Path(directory), color)
            elif case == "undo":
                test_undo_redo()
            elif case == "scene":
                test_scene_image_user(color, data)
            else:
                raise ValueError(f"Unknown test case {case!r}")
    finally:
        mw_pbr_material.unregister()
    print(f"MW_PBR_{case.upper()}_RUNTIME_OK")
