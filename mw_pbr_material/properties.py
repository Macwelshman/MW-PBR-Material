"""User-editable state for MW PBR Material."""

import bpy
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)
from bpy.types import Image, PropertyGroup


def _texture_update(role):
    def update(settings, context):
        from .texture_detection import scan_companions_from_image

        obj = getattr(context, "object", None)
        material = getattr(obj, "active_material", None)
        scan_companions_from_image(
            settings,
            role,
            getattr(settings, role),
            material=material,
        )

    update.__name__ = f"_update_{role}"
    return update


def _folder_updated(settings, context):
    from .texture_detection import scan_in_progress, scan_settings_folder

    if not settings.texture_folder or scan_in_progress(settings):
        return
    try:
        obj = getattr(context, "object", None)
        scan_settings_folder(
            settings,
            material=getattr(obj, "active_material", None),
        )
    except (FileNotFoundError, RuntimeError) as exc:
        settings.scan_status = str(exc)


def _auto_load_companions_updated(settings, context):
    from .material_builder import is_mw_material, store_material_state
    from .texture_detection import scan_in_progress

    if scan_in_progress(settings):
        return
    obj = getattr(context, "object", None)
    material = getattr(obj, "active_material", None)
    if is_mw_material(material):
        store_material_state(material, settings)


def _normal_interpretation_updated(settings, context):
    from .material_builder import build_material, is_mw_material
    from .texture_detection import scan_in_progress

    if scan_in_progress(settings):
        return

    obj = getattr(context, "object", None)
    material = getattr(obj, "active_material", None)
    if is_mw_material(material):
        build_material(settings, material=material)


def _texture_scale_updated(settings, context):
    from .material_builder import build_material, is_mw_material
    from .texture_detection import scan_in_progress

    if scan_in_progress(settings):
        return

    obj = getattr(context, "object", None)
    material = getattr(obj, "active_material", None)
    if is_mw_material(material):
        build_material(settings, material=material)


def _emission_strength_updated(settings, context):
    from .material_builder import build_material, is_mw_material
    from .texture_detection import scan_in_progress

    if scan_in_progress(settings):
        return

    obj = getattr(context, "object", None)
    material = getattr(obj, "active_material", None)
    if is_mw_material(material):
        build_material(settings, material=material)


def _base_color_brightness_updated(settings, context):
    from .material_builder import build_material, is_mw_material
    from .texture_detection import scan_in_progress

    if scan_in_progress(settings):
        return

    obj = getattr(context, "object", None)
    material = getattr(obj, "active_material", None)
    if is_mw_material(material):
        build_material(settings, material=material)


def _displacement_amount_updated(settings, context):
    from .material_builder import build_material, is_mw_material
    from .texture_detection import scan_in_progress

    if scan_in_progress(settings):
        return
    obj = getattr(context, "object", None)
    material = getattr(obj, "active_material", None)
    if is_mw_material(material):
        build_material(settings, material=material)


class MWPBRMaterialProperties(PropertyGroup):
    synced_material_pointer: StringProperty(
        default="",
        options={"HIDDEN", "SKIP_SAVE"},
    )
    material_name: StringProperty(
        name="Material Name",
        description="Name for the material that will be created",
        default="PBR Material",
    )

    texture_folder: StringProperty(
        name="Texture Folder",
        description="Folder containing one material's texture maps",
        subtype="DIR_PATH",
        update=_folder_updated,
    )
    scan_status: StringProperty(default="Choose a material folder or texture")
    matched_texture_count: IntProperty(default=0, options={"HIDDEN", "SKIP_SAVE"})
    auto_load_companions: BoolProperty(
        name="Load Companion Textures",
        description="Scan the same folder when a recognised texture is selected",
        default=True,
        update=_auto_load_companions_updated,
    )
    texture_scale: FloatProperty(
        name="Texture Scale",
        description="Visual size of all textures; higher values make texture details larger",
        default=1.0,
        min=0.01,
        max=10.0,
        soft_min=0.01,
        soft_max=4.0,
        precision=2,
        update=_texture_scale_updated,
    )
    emission_strength: FloatProperty(
        name="Emission Strength",
        description="Strength of the loaded Emissive texture",
        default=0.0,
        min=0.0,
        max=100.0,
        soft_max=10.0,
        precision=2,
        update=_emission_strength_updated,
    )
    base_color_brightness: FloatProperty(
        name="BaseColor Brightness",
        description="Darken BaseColor to the left or lighten it to the right",
        default=0.0,
        min=-1.0,
        max=1.0,
        precision=2,
        update=_base_color_brightness_updated,
    )
    displacement_amount: FloatProperty(
        name="Displacement Amount",
        description="Amount of bump or true displacement produced by the Height texture",
        default=1.0,
        min=0.0,
        max=2.0,
        soft_max=2.0,
        precision=2,
        update=_displacement_amount_updated,
    )

    base_color: PointerProperty(
        name="BaseColor", type=Image, update=_texture_update("base_color")
    )
    metallic: PointerProperty(
        name="Metallic", type=Image, update=_texture_update("metallic")
    )
    normal: PointerProperty(
        name="Normal", type=Image, update=_texture_update("normal")
    )
    roughness: PointerProperty(
        name="Roughness", type=Image, update=_texture_update("roughness")
    )
    opacity: PointerProperty(
        name="Opacity", type=Image, update=_texture_update("opacity")
    )
    height: PointerProperty(
        name="Height", type=Image, update=_texture_update("height")
    )
    ambient_occlusion: PointerProperty(
        name="Ambient Occlusion",
        type=Image,
        update=_texture_update("ambient_occlusion"),
    )
    emissive: PointerProperty(
        name="Emissive", type=Image, update=_texture_update("emissive")
    )

    detected_normal_convention: EnumProperty(
        name="Detected Normal Convention",
        items=(
            ("UNKNOWN", "Not detected", "No explicit normal convention was detected"),
            ("OPENGL", "OpenGL", "Filename identifies an OpenGL normal"),
            ("DIRECTX", "DirectX", "Filename identifies a DirectX normal"),
        ),
        default="UNKNOWN",
        options={"HIDDEN", "SKIP_SAVE"},
    )

    normal_interpretation: EnumProperty(
        name="Normal Interpretation",
        description="How the selected normal map should be interpreted",
        items=(
            (
                "AUTO",
                "Auto",
                "Use filename hints when available; otherwise use OpenGL",
            ),
            ("OPENGL", "OpenGL", "Use the normal map without Y-channel conversion"),
            (
                "DIRECTX",
                "DirectX",
                "Convert to OpenGL non-destructively by inverting the green channel",
            ),
        ),
        default="AUTO",
        update=_normal_interpretation_updated,
    )


_CLASSES = (MWPBRMaterialProperties,)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.mw_pbr_material = PointerProperty(type=MWPBRMaterialProperties)


def unregister():
    del bpy.types.Scene.mw_pbr_material
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
