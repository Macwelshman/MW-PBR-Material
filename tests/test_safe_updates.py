"""Run through Flue in a disposable Blender session; saves and reopens a fixture."""
import tempfile
from pathlib import Path

import bpy

import mw_pbr_material
from mw_pbr_material import material_builder as builder
from mw_pbr_material.texture_detection import settings_update_guard


def graph_snapshot(material):
    tree = material.node_tree
    return (
        tuple((node.as_pointer(), node.name, node.select, tuple(node.items()))
              for node in tree.nodes),
        frozenset((link.from_socket, link.to_socket, link.is_muted) for link in tree.links),
        tree.nodes.active,
        tuple(node for node in tree.nodes if node.type == "OUTPUT_MATERIAL" and node.is_active_output),
        dict(material.items()),
    )


def run(*, reset=True, color="sRGB", data="Non-Color"):
    if reset:
        bpy.ops.wm.read_factory_settings(use_empty=True)
    mw_pbr_material.register()
    try:
        with tempfile.TemporaryDirectory() as directory:
            exercise(Path(directory) / "safe-updates.blend", color, data)
    finally:
        mw_pbr_material.unregister()
    print("MW_PBR_SAFE_UPDATES_RUNTIME_OK")


def exercise(blend, color, data):
    scene = bpy.context.scene
    mesh = bpy.data.meshes.new("Safe Updates")
    obj = bpy.data.objects.new("Safe Updates", mesh)
    scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    settings = scene.mw_pbr_material

    shared = bpy.data.images.new("Shared colour and normal", 2, 2)
    shared.pixels[:4] = (0.1, 0.2, 0.3, 1.0)
    other = bpy.data.materials.new("Other Material")
    mesh.materials.append(other)
    other.node_tree.nodes.new("ShaderNodeTexImage").image = shared
    other.use_fake_user = True
    with settings_update_guard(settings):
        settings.base_color = shared
        settings.normal = shared
        settings.normal_interpretation = "DIRECTX"
    material = builder.build_material(settings)
    mesh.materials[0] = material

    nodes, links = material.node_tree.nodes, material.node_tree.links
    base = nodes["MW BaseColor Texture"]
    normal = nodes["MW Normal Texture"]
    assert base.image == shared and shared.colorspace_settings.name == color
    assert normal.image != shared and normal.image.colorspace_settings.name == data
    assert other.node_tree.nodes.get("Image Texture").image == shared
    variant = normal.image
    assert tuple(variant.pixels[:4]) == tuple(shared.pixels[:4])
    assert variant.packed_file

    # Simulate a previous release, then verify migration without clearing the tree.
    del material[builder.GRAPH_LINKS]
    for node in nodes:
        del node[builder.NODE_ROLE]
    artist = nodes.new("ShaderNodeValue")
    artist.name = "Artist Control"
    artist.outputs[0].default_value = 0.35
    artist_output = nodes.new("ShaderNodeOutputMaterial")
    artist_output.name = "Artist Output"
    artist_output.is_active_output = True
    principled = nodes["MW Principled BSDF"]
    principled.inputs["IOR"].default_value = 1.7
    links.new(artist.outputs[0], principled.inputs["Roughness"])
    links.new(principled.outputs["BSDF"], artist_output.inputs["Surface"])
    settings.texture_scale = 1.75
    assert base[builder.NODE_ROLE] == "MW BaseColor Texture"
    base.name = "My renamed texture"
    base.interpolation = "Closest"
    fake = nodes.new("ShaderNodeTexImage")
    fake.name = "MW BaseColor Texture"
    # This artist link runs between two owned nodes, but isn't generated.
    links.new(base.outputs["Alpha"], principled.inputs["Coat Weight"])
    artist_links = [link for link in links if link.from_node == artist
                    or link.to_node == artist_output or link.to_socket == principled.inputs["Coat Weight"]]

    with settings_update_guard(settings):
        settings.roughness = shared
    image_count = len(bpy.data.images)
    assert bpy.ops.mw_pbr.update_material() == {"FINISHED"}
    assert len(bpy.data.images) == image_count + 1
    stable = graph_snapshot(material)
    for _ in range(3):
        assert bpy.ops.mw_pbr.update_material() == {"FINISHED"}
        assert graph_snapshot(material) == stable
    assert len(bpy.data.images) == image_count + 1
    assert all(link in tuple(links) for link in artist_links)
    assert normal.image == variant and base.interpolation == "Closest"
    assert abs(principled.inputs["IOR"].default_value - 1.7) < 1e-6
    assert artist_output.is_active_output
    assert builder.owned_nodes(material)["MW BaseColor Texture"] == base
    assert builder.NODE_ROLE not in fake

    # Fail after graph reconciliation has begun, including removal/addition
    # of the generated DirectX route and changes to managed socket defaults.
    class FailOnce:
        def as_pointer(self):
            return settings.as_pointer()

        def __getattr__(self, name):
            if name == "scan_status":
                raise RuntimeError("injected commit failure")
            return getattr(settings, name)

        def __setattr__(self, name, value):
            setattr(settings, name, value)

    with settings_update_guard(settings):
        settings.texture_scale = 2.5
        settings.normal_interpretation = "OPENGL"
    before_failure = graph_snapshot(material)
    for rebuild in (False, True):
        try:
            builder.build_material(FailOnce(), material, rebuild=rebuild)
        except RuntimeError as exc:
            assert str(exc) == "injected commit failure"
        else:
            raise AssertionError("Failure injection did not run")
        assert graph_snapshot(material) == before_failure
        assert len(bpy.data.images) == image_count + 1
        assert not any(m.name.startswith("MW PBR staging") for m in bpy.data.materials)
    builder.sync_settings_from_material(settings, material, force=True)
    assert settings.normal_interpretation == "DIRECTX"
    assert abs(settings.texture_scale - 1.75) < 1e-6

    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    bpy.ops.wm.open_mainfile(filepath=str(blend), load_ui=False)
    window = bpy.context.window_manager.windows[0]
    with bpy.context.temp_override(window=window):
        verify_reopened()


def verify_reopened():
    material = bpy.context.object.active_material
    settings = bpy.context.scene.mw_pbr_material
    assert bpy.ops.mw_pbr.update_material() == {"FINISHED"}
    assert builder.owned_nodes(material)["MW BaseColor Texture"].name == "My renamed texture"
    assert material.node_tree.nodes["Artist Output"].is_active_output
    assert settings.normal_interpretation == "DIRECTX"
    assert abs(settings.texture_scale - 1.75) < 1e-6
    assert abs(settings.normal.pixels[0] - 0.1) < 0.005

    assert bpy.ops.mw_pbr.rebuild_material() == {"FINISHED"}
    assert all(builder.NODE_ROLE in node for node in material.node_tree.nodes)
    assert material.node_tree.nodes["MW Material Output"].is_active_output
    assert "MW Flip DirectX Green" in material.node_tree.nodes
    assert settings.normal_interpretation == "DIRECTX"


if __name__ == "__main__":
    run()
