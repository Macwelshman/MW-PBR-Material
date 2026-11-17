"""Flue runtime test: creates and removes only its own temporary datablocks."""
import struct
import tempfile
from pathlib import Path
from types import SimpleNamespace

import bpy

from mw_pbr_material.material_builder import GRAPH_LINKS, NODE_ROLE, TEXTURE_NODE_NAMES
from mw_pbr_material.relink import apply_relinks, missing_images, suggestions


def run():
    before_images = set(bpy.data.images)
    material = bpy.data.materials.new("Relink test")
    other = bpy.data.materials.new("Relink shared user")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            original = Path(tmp) / "old"
            original.mkdir()
            # 1x1, 24-bit BMP with a padded scanline.
            pixel = (b"BM" + struct.pack("<IHHI", 58, 0, 0, 54)
                     + struct.pack("<IiiHHIIiiII", 40, 1, 1, 1, 24, 0, 4, 0, 0, 0, 0)
                     + bytes(4))
            for name in ("Wall_BaseColor.bmp", "Wall_NormalDX.bmp", "Wall_Roughness.bmp",
                         "Wall_AO.bmp"):
                (original / name).write_bytes(pixel)
            material["mw_pbr_material"] = True
            material[GRAPH_LINKS] = "[]"
            nodes = material.node_tree.nodes
            settings = SimpleNamespace(as_pointer=lambda: id(settings))
            for role, suffix in (("base_color", "BaseColor"), ("normal", "NormalDX"),
                                 ("roughness", "Roughness"), ("ambient_occlusion", "AO")):
                node = nodes.new("ShaderNodeTexImage")
                node.name = TEXTURE_NODE_NAMES[role]
                node[NODE_ROLE] = TEXTURE_NODE_NAMES[role]
                node.image = bpy.data.images.load(str(original / f"Wall_{suffix}.bmp"))
                setattr(settings, role, node.image)
            base = nodes[TEXTURE_NODE_NAMES["base_color"]]
            base.name = "Renamed Base Texture"
            shared = base.image
            other.node_tree.nodes.new("ShaderNodeTexImage").image = shared
            settings.ambient_occlusion.pack()
            nodes.new("ShaderNodeTexImage").image = bpy.data.images.new("Relink generated", 1, 1)
            custom = nodes.new("ShaderNodeMath")
            custom.name = "MW Flip DirectX Green"
            custom.inputs[0].default_value = 0.37
            normal = nodes[TEXTURE_NODE_NAMES["normal"]]
            material.node_tree.links.new(normal.outputs["Color"], custom.inputs[1])
            links = tuple(material.node_tree.links)
            identities = tuple(nodes)
            renamed = original.rename(Path(tmp) / "renamed")
            (renamed / "Wall_Roughness.bmp").unlink()
            (renamed / "Wall_NormalDX.bmp").rename(renamed / "Wall_NormalDX_2k.bmp")
            (renamed / "Wall_NormalGL.bmp").write_bytes(pixel)
            assert len(missing_images(material)) == 3
            original.mkdir()
            alias = original / "Wall_NormalDX_4k.bmp"
            alias.write_bytes(pixel)
            rows = suggestions(material, str(renamed))
            by_name = {node.name: (paths, score) for node, _, _, paths, score in rows}
            assert len(by_name[normal.name][0]) == 2
            assert by_name[TEXTURE_NODE_NAMES["roughness"]][0] == []
            alias.unlink()
            corrupt = renamed / "Wall_Roughness.bmp"
            corrupt.write_bytes(b"not a BMP")
            image_count = len(bpy.data.images)
            try:
                apply_relinks(settings, suggestions(material, str(renamed)), material)
            except RuntimeError:
                pass
            else:
                raise AssertionError("Unreadable replacement should abort relinking")
            assert base.image == shared
            assert Path(normal.image.filepath).parent == original
            assert len(bpy.data.images) == image_count
            corrupt.unlink()
            rows = suggestions(material, str(renamed))
            assert apply_relinks(settings, rows, material) == 2
            assert tuple(nodes) == identities and tuple(material.node_tree.links) == links
            assert abs(custom.inputs[0].default_value - 0.37) < 1e-6
            assert base.image != shared and settings.base_color == base.image
            assert shared.filepath == str(original / "Wall_BaseColor.bmp")
            assert other.node_tree.nodes.get("Image Texture").image == shared
            assert Path(normal.image.filepath).name == "Wall_NormalDX_2k.bmp"
            assert len(missing_images(material)) == 1
    finally:
        bpy.data.materials.remove(material)
        bpy.data.materials.remove(other)
        for image in set(bpy.data.images) - before_images:
            bpy.data.images.remove(image)


if __name__ == "__main__":
    run()
    print("MW_PBR_RELINK_RUNTIME_OK")
