"""MW PBR Material add-on entry point."""

bl_info = {
    "name": "MW PBR Material",
    "author": "MacWelshman",
    "version": (0, 6, 6),
    "blender": (5, 0, 0),
    "location": "Properties > Material > MW PBR Material",
    "description": "Build clean Principled PBR materials from manually selected textures",
    "category": "Material",
}

from . import operators, properties, texture_detection, ui


_MODULES = (properties, operators, ui)


def register():
    for module in _MODULES:
        module.register()


def unregister():
    for module in reversed(_MODULES):
        module.unregister()


if __name__ == "__main__":
    register()
