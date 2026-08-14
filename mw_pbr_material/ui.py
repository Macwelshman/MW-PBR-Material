"""Material Properties UI for MW PBR Material."""

from pathlib import Path

import bpy
import bpy.utils.previews
from bpy.app.handlers import persistent

from .material_builder import is_mw_material, sync_settings_from_material


MATERIAL_CONTEXT_PANELS = (
    "EEVEE_MATERIAL_PT_context_material",
    "CYCLES_PT_context_material",
)

TEXTURE_SLOTS = (
    ("base_color", "BaseColor"),
    ("metallic", "Metallic"),
    ("roughness", "Roughness"),
    ("normal", "Normal"),
    ("opacity", "Opacity"),
    ("height", "Height"),
    ("ambient_occlusion", "Ambient Occlusion"),
    ("emissive", "Emissive"),
)

_ICON_PREVIEWS = None
_MSGBUS_OWNER = object()
_MATERIAL_SYNC_IN_PROGRESS = False
_LAST_ACTIVE_SELECTION = None


def _register_icons():
    global _ICON_PREVIEWS
    _unregister_icons()
    icon_path = Path(__file__).with_name("icons") / "green_check.png"
    if not icon_path.is_file():
        return
    previews = bpy.utils.previews.new()
    previews.load("green_check", str(icon_path), "IMAGE", force_reload=True)
    _ICON_PREVIEWS = previews


def _unregister_icons():
    global _ICON_PREVIEWS
    if _ICON_PREVIEWS is not None:
        try:
            bpy.utils.previews.remove(_ICON_PREVIEWS)
        except (ReferenceError, RuntimeError):
            pass
        _ICON_PREVIEWS = None


def _green_check_icon_id():
    if _ICON_PREVIEWS is None:
        return 0
    try:
        return _ICON_PREVIEWS["green_check"].icon_id
    except (KeyError, ReferenceError):
        return 0


def _effective_normal_convention(settings):
    if settings.normal_interpretation in {"OPENGL", "DIRECTX"}:
        return settings.normal_interpretation
    if settings.detected_normal_convention in {"OPENGL", "DIRECTX"}:
        return settings.detected_normal_convention
    return "OPENGL"


def _normal_convention_uncertain(settings):
    return (
        settings.normal_interpretation == "AUTO"
        and settings.detected_normal_convention == "UNKNOWN"
    )


def _draw_slider_with_reset(layout, settings, property_name, text):
    row = layout.row(align=True)
    row.prop(settings, property_name, text=text, slider=True)
    reset = row.operator("mw_pbr.reset_slider", text="", icon="LOOP_BACK")
    reset.target = property_name


def _redraw_properties_areas():
    window_manager = getattr(bpy.context, "window_manager", None)
    for window in getattr(window_manager, "windows", ()):
        screen = getattr(window, "screen", None)
        for area in getattr(screen, "areas", ()):
            if area.type == "PROPERTIES":
                area.tag_redraw()


def _active_material_changed():
    """Synchronize the UI as soon as the active object or material slot changes."""
    global _LAST_ACTIVE_SELECTION, _MATERIAL_SYNC_IN_PROGRESS
    if _MATERIAL_SYNC_IN_PROGRESS:
        return
    _MATERIAL_SYNC_IN_PROGRESS = True
    try:
        scene = getattr(bpy.context, "scene", None)
        obj = getattr(bpy.context, "object", None)
        settings = getattr(scene, "mw_pbr_material", None) if scene else None
        material = getattr(obj, "active_material", None) if obj else None
        selection = (
            obj.as_pointer() if obj else 0,
            material.as_pointer() if material else 0,
        )
        if selection == _LAST_ACTIVE_SELECTION:
            return
        _LAST_ACTIVE_SELECTION = selection
        if settings is not None and is_mw_material(material):
            sync_settings_from_material(settings, material)
        _redraw_properties_areas()
    finally:
        _MATERIAL_SYNC_IN_PROGRESS = False


@persistent
def _depsgraph_material_changed(_scene, _depsgraph):
    _active_material_changed()


def _material_poll_timer():
    if not hasattr(bpy.types.Scene, "mw_pbr_material"):
        return None
    _active_material_changed()
    return 0.1


def _remove_stale_material_handlers():
    handlers = bpy.app.handlers.depsgraph_update_post
    for handler in tuple(handlers):
        if (
            getattr(handler, "__name__", "") == "_depsgraph_material_changed"
            and getattr(handler, "__module__", "").endswith("mw_pbr_material.ui")
        ):
            handlers.remove(handler)


def _register_material_change_listener():
    global _LAST_ACTIVE_SELECTION
    _LAST_ACTIVE_SELECTION = None
    bpy.msgbus.clear_by_owner(_MSGBUS_OWNER)
    _remove_stale_material_handlers()
    bpy.app.handlers.depsgraph_update_post.append(_depsgraph_material_changed)
    keys = (
        (bpy.types.Object, "active_material_index"),
        (bpy.types.Object, "active_material"),
        (bpy.types.LayerObjects, "active"),
    )
    for key in keys:
        bpy.msgbus.subscribe_rna(
            key=key,
            owner=_MSGBUS_OWNER,
            args=(),
            notify=_active_material_changed,
            options={"PERSISTENT"},
        )
    if not bpy.app.timers.is_registered(_material_poll_timer):
        bpy.app.timers.register(
            _material_poll_timer,
            first_interval=0.1,
            persistent=True,
        )


def _unregister_material_change_listener():
    global _LAST_ACTIVE_SELECTION
    _LAST_ACTIVE_SELECTION = None
    bpy.msgbus.clear_by_owner(_MSGBUS_OWNER)
    _remove_stale_material_handlers()
    if bpy.app.timers.is_registered(_material_poll_timer):
        bpy.app.timers.unregister(_material_poll_timer)


def _remove_material_context_draw_callbacks(panel):
    """Remove callbacks left behind by this add-on, including stale reloads."""
    draw_functions = tuple(getattr(panel.draw, "_draw_funcs", ()))
    for callback in draw_functions:
        callback_module = getattr(callback, "__module__", "")
        if (
            getattr(callback, "__name__", "") == "_material_context_draw"
            and callback_module.endswith("mw_pbr_material.ui")
        ):
            try:
                panel.remove(callback)
            except ValueError:
                pass


def _draw_material_builder(layout, context):
    settings = context.scene.mw_pbr_material
    material = context.object.active_material
    sync_settings_from_material(settings, material)

    folder = layout.box()
    folder.label(text="Texture Folder")
    folder.prop(settings, "texture_folder", text="")
    folder.prop(settings, "auto_load_companions")

    layout.prop(settings, "material_name")

    scale = layout.box()
    scale.label(text="Texture Scale")
    _draw_slider_with_reset(scale, settings, "texture_scale", "Size")

    loaded = sum(
        bool(getattr(settings, prop_name)) for prop_name, _label in TEXTURE_SLOTS
    )
    summary = layout.box()
    summary.progress(
        factor=loaded / len(TEXTURE_SLOTS),
        text=f"{loaded} of {len(TEXTURE_SLOTS)} textures loaded",
    )
    actions = summary.row()
    actions.operator(
        "mw_pbr.toggle_backfaces",
        text="Backfaces",
        icon="NORMALS_FACE",
        depress=not material.use_backface_culling,
    )
    actions.operator(
        "mw_pbr.reload_all_textures",
        text="Reload",
        icon="FILE_REFRESH",
    )
    actions.operator(
        "mw_pbr.remove_all_textures",
        text="Remove",
        icon="TRASH",
    )

    for prop_name, label in TEXTURE_SLOTS:
        texture_box = layout.box()
        heading = texture_box.row(align=True)
        heading.alignment = "LEFT"
        heading.label(text=label)
        image = getattr(settings, prop_name)
        texture_row = texture_box.row(align=True)
        if image:
            icon_id = _green_check_icon_id()
            if icon_id:
                texture_row.label(text="", icon_value=icon_id)
            else:
                texture_row.label(text="", icon="CHECKMARK")
        texture_row.template_ID(settings, prop_name, open="image.open")

        if prop_name == "base_color" and image:
            _draw_slider_with_reset(
                texture_box,
                settings,
                "base_color_brightness",
                "Brightness",
            )

        if prop_name == "normal" and image:
            convention = texture_box.row(align=True)
            effective = _effective_normal_convention(settings)
            if _normal_convention_uncertain(settings):
                convention.operator(
                    "mw_pbr.normal_uncertainty_hint",
                    text="",
                    icon="QUESTION",
                    emboss=False,
                )
            open_gl = convention.operator(
                "mw_pbr.set_normal_convention",
                text="OpenGL",
                depress=effective == "OPENGL",
            )
            open_gl.convention = "OPENGL"
            direct_x = convention.operator(
                "mw_pbr.set_normal_convention",
                text="DirectX",
                depress=effective == "DIRECTX",
            )
            direct_x.convention = "DIRECTX"

        if prop_name == "height" and image:
            displacement = texture_box.row(align=True)
            current_method = material.displacement_method
            for method, label in (
                ("BUMP", "Bump"),
                ("DISPLACEMENT", "Displacement"),
                ("BOTH", "Both"),
            ):
                choice = displacement.operator(
                    "mw_pbr.set_displacement_method",
                    text=label,
                    depress=current_method == method,
                )
                choice.method = method
            _draw_slider_with_reset(
                texture_box,
                settings,
                "displacement_amount",
                "Amount",
            )

        if prop_name == "emissive" and image:
            _draw_slider_with_reset(
                texture_box,
                settings,
                "emission_strength",
                "Strength",
            )


def _material_context_draw(self, context):
    """Draw the create action and its dropdown as one adjacent interface."""
    obj = getattr(context, "object", None)
    if obj is None or getattr(getattr(obj, "data", None), "materials", None) is None:
        return

    self.layout.separator()
    material = getattr(obj, "active_material", None)
    owned_material = is_mw_material(material)
    self.layout.operator(
        "mw_pbr.create_material",
        text="Create PBR Material",
        icon="ADD",
    )

    if not owned_material:
        return

    header, body = self.layout.panel(
        "mw_pbr_material_builder",
        default_closed=False,
    )
    header.label(text="MW PBR Material", icon="MATERIAL")
    if body is not None:
        _draw_material_builder(body, context)


def _register_material_context_draw():
    for panel_name in MATERIAL_CONTEXT_PANELS:
        panel = getattr(bpy.types, panel_name, None)
        if panel is not None:
            _remove_material_context_draw_callbacks(panel)
            panel.append(_material_context_draw)


def register():
    _register_icons()
    _register_material_change_listener()
    _register_material_context_draw()


def unregister():
    _unregister_material_change_listener()
    for panel_name in reversed(MATERIAL_CONTEXT_PANELS):
        panel = getattr(bpy.types, panel_name, None)
        if panel is not None:
            _remove_material_context_draw_callbacks(panel)
    _unregister_icons()
