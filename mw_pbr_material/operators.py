"""User-facing operations for MW PBR Material."""

import bpy
from bpy.props import EnumProperty, StringProperty
from bpy.types import Operator

from .material_builder import (
    TEXTURE_ROLES,
    build_material,
    is_mw_material,
    sync_settings_from_material,
)
from .relink import apply_relinks, missing_images, suggestions
from .texture_detection import (
    clear_texture_settings,
    scan_settings_folder,
    settings_update_guard,
)


def _assign_to_active_object(context, material):
    obj = context.active_object
    if obj is None or not hasattr(obj.data, "materials"):
        return False

    materials = obj.data.materials
    if obj.active_material_index < len(materials):
        materials[obj.active_material_index] = material
    else:
        materials.append(material)
    return True


class MWPBR_OT_CreateMaterial(Operator):
    bl_idname = "mw_pbr.create_material"
    bl_label = "Create PBR Material"
    bl_description = "Create a Principled PBR material from the selected textures"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.mw_pbr_material
        try:
            with settings_update_guard(settings):
                clear_texture_settings(settings, clear_folder=True)
                settings.texture_scale = 1.0
                settings.emission_strength = 0.0
                settings.base_color_brightness = 0.0
                settings.displacement_amount = 1.0
                settings.normal_interpretation = "AUTO"
            material = build_material(settings)
            assigned = _assign_to_active_object(context, material)
        except (RuntimeError, TypeError, ValueError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

        if assigned:
            self.report({"INFO"}, f"Created and assigned {material.name}")
        else:
            self.report({"INFO"}, f"Created {material.name}")
        return {"FINISHED"}


class MWPBR_OT_ScanTextureFolder(Operator):
    bl_idname = "mw_pbr.scan_texture_folder"
    bl_label = "Scan Texture Folder"
    bl_description = "Identify and load supported texture maps from the selected folder"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.mw_pbr_material
        if not settings.texture_folder:
            self.report({"ERROR"}, "Choose a texture folder")
            return {"CANCELLED"}
        try:
            obj = context.active_object
            scan_settings_folder(
                settings,
                material=getattr(obj, "active_material", None),
            )
        except (FileNotFoundError, RuntimeError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

        self.report({"INFO"}, settings.scan_status)
        return {"FINISHED"}


class MWPBR_OT_RemoveAllTextures(Operator):
    bl_idname = "mw_pbr.remove_all_textures"
    bl_label = "Remove All"
    bl_description = "Remove every selected texture without deleting image data or files"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.mw_pbr_material
        obj = context.active_object
        try:
            clear_texture_settings(
                settings,
                material=getattr(obj, "active_material", None),
                clear_folder=False,
            )
        except (RuntimeError, TypeError, ValueError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, "Removed all textures")
        return {"FINISHED"}


class MWPBR_OT_ToggleBackfaces(Operator):
    bl_idname = "mw_pbr.toggle_backfaces"
    bl_label = "Toggle Backfaces"
    bl_description = "Show or hide material backfaces"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        material = getattr(context.active_object, "active_material", None)
        if not is_mw_material(material):
            self.report({"ERROR"}, "Select an MW PBR material")
            return {"CANCELLED"}

        previous = material.use_backface_culling
        material.use_backface_culling = not previous
        result = _refresh_material(self, context, rebuild=False)
        if result == {"CANCELLED"}:
            material.use_backface_culling = previous
            return result
        state = "hidden" if material.use_backface_culling else "visible"
        self.report({"INFO"}, f"Backfaces are {state}")
        return {"FINISHED"}


class MWPBR_OT_SetNormalConvention(Operator):
    bl_idname = "mw_pbr.set_normal_convention"
    bl_label = "Set Normal Convention"
    bl_description = "Override how the selected normal texture is interpreted"
    bl_options = {"REGISTER", "UNDO"}

    convention: EnumProperty(
        items=(
            ("OPENGL", "OpenGL", "Interpret the normal texture as OpenGL"),
            ("DIRECTX", "DirectX", "Interpret the normal texture as DirectX"),
        )
    )

    def execute(self, context):
        settings = context.scene.mw_pbr_material
        material = getattr(context.active_object, "active_material", None)
        with settings_update_guard(settings):
            if is_mw_material(material):
                sync_settings_from_material(settings, material)
            settings.normal_interpretation = self.convention
        if is_mw_material(material):
            return _refresh_material(self, context, rebuild=False)
        return {"FINISHED"}


class MWPBR_OT_SetDisplacementMethod(Operator):
    bl_idname = "mw_pbr.set_displacement_method"
    bl_label = "Set Displacement Method"
    bl_description = "Choose how the loaded Height texture affects the material"
    bl_options = {"REGISTER", "UNDO"}

    method: EnumProperty(
        items=(
            ("BUMP", "Bump", "Use the Height texture as shader bump mapping"),
            (
                "DISPLACEMENT",
                "Displacement",
                "Use true surface displacement; the mesh requires sufficient subdivision",
            ),
            (
                "BOTH",
                "Both",
                "Use true displacement together with bump mapping for fine detail",
            ),
        )
    )

    def execute(self, context):
        material = getattr(context.active_object, "active_material", None)
        if not is_mw_material(material):
            self.report({"ERROR"}, "Select an MW PBR material")
            return {"CANCELLED"}
        previous = material.displacement_method
        material.displacement_method = self.method
        result = _refresh_material(self, context, rebuild=False)
        if result == {"CANCELLED"}:
            material.displacement_method = previous
        return result


class MWPBR_OT_NormalUncertaintyHint(Operator):
    bl_idname = "mw_pbr.normal_uncertainty_hint"
    bl_label = "Normal Convention Uncertain"
    bl_description = "The filename does not identify a convention; OpenGL is used as the safe fallback"

    def execute(self, context):
        return {"FINISHED"}


class MWPBR_OT_ResetSlider(Operator):
    bl_idname = "mw_pbr.reset_slider"
    bl_label = "Reset Value"
    bl_description = "Reset this slider to its default value"
    bl_options = {"REGISTER", "UNDO"}

    target: EnumProperty(
        items=(
            ("texture_scale", "Texture Scale", "Reset Texture Scale to 1"),
            (
                "base_color_brightness",
                "BaseColor Brightness",
                "Reset BaseColor Brightness to 0",
            ),
            (
                "emission_strength",
                "Emission Strength",
                "Reset Emission Strength to 0",
            ),
            (
                "displacement_amount",
                "Displacement Amount",
                "Reset Displacement Amount to 1",
            ),
        )
    )

    def execute(self, context):
        defaults = {
            "texture_scale": 1.0,
            "base_color_brightness": 0.0,
            "emission_strength": 0.0,
            "displacement_amount": 1.0,
        }
        setattr(
            context.scene.mw_pbr_material,
            self.target,
            defaults[self.target],
        )
        return {"FINISHED"}


class MWPBR_OT_ReloadAllTextures(Operator):
    bl_idname = "mw_pbr.reload_all_textures"
    bl_label = "Reload All Textures"
    bl_description = "Reload every assigned texture from disk"
    bl_options = {"REGISTER"}

    def execute(self, context):
        settings = context.scene.mw_pbr_material
        reloaded = 0
        failures = []

        for role in TEXTURE_ROLES:
            image = getattr(settings, role)
            if image is None:
                continue
            try:
                image.reload()
                reloaded += 1
            except RuntimeError:
                failures.append(image.name)

        if failures:
            self.report(
                {"WARNING"},
                f"Reloaded {reloaded}; failed: {', '.join(failures)}",
            )
        else:
            self.report({"INFO"}, f"Reloaded {reloaded} texture(s)")
        return {"FINISHED"}


class MWPBR_OT_UpdateMaterial(Operator):
    bl_idname = "mw_pbr.update_material"
    bl_label = "Update Material"
    bl_description = "Refresh MW nodes while preserving custom nodes and links"
    bl_options = {"UNDO"}

    @classmethod
    def poll(cls, context):
        material = getattr(context.object, "active_material", None)
        return is_mw_material(material) and material.is_editable

    def execute(self, context):
        return _refresh_material(self, context, rebuild=False)


class MWPBR_OT_RebuildMaterial(Operator):
    bl_idname = "mw_pbr.rebuild_material"
    bl_label = "Rebuild Material"
    bl_description = "Replace the entire shader graph, including custom nodes and links"
    bl_options = {"UNDO"}

    @classmethod
    def poll(cls, context):
        return MWPBR_OT_UpdateMaterial.poll(context)

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(
            self, event, title="Rebuild Material?",
            message="Custom nodes, links and node settings will be lost.",
            confirm_text="Rebuild", icon="WARNING",
        )

    def execute(self, context):
        return _refresh_material(self, context, rebuild=True)


def _refresh_material(operator, context, *, rebuild):
    material = context.object.active_material
    settings = context.scene.mw_pbr_material
    sync_settings_from_material(settings, material)
    try:
        build_material(settings, material, rebuild=rebuild)
    except Exception as exc:
        sync_settings_from_material(settings, material, force=True)
        operator.report({"ERROR"}, f"Material was not changed: {exc}")
        return {"CANCELLED"}
    return {"FINISHED"}


class MWPBR_OT_RelinkTextureSet(Operator):
    bl_idname = "mw_pbr.relink_texture_set"
    bl_label = "Relink Texture Set"
    bl_description = "Review replacement files for missing textures in this material"
    bl_options = {"UNDO"}

    directory: StringProperty(name="Replacement Folder", subtype="DIR_PATH",
                              options={"SKIP_SAVE"})

    @classmethod
    def poll(cls, context):
        material = getattr(context.object, "active_material", None)
        return is_mw_material(material) and material.is_editable

    def invoke(self, context, event):
        self._material = context.object.active_material
        self._reviewed = None
        return context.window_manager.invoke_props_dialog(
            self, width=760, confirm_text="Relink Suggested Files"
        )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "directory")
        layout.label(text="Also searches the original texture folders.")
        rows = suggestions(self._material, self.directory)
        self._reviewed = (self.directory, rows)
        for node, _, original, candidates, score in rows:
            box = layout.box()
            if len(candidates) > 1:
                status = "Ambiguous — skipped"
            elif not candidates:
                status = "No match — skipped"
            else:
                status = "High: same filename" if score == 2 else "Medium: same set and map type"
            box.label(text=f"{node.label or node.name} · {status}")
            box.label(text=f"Original: {original}")
            for path in candidates:
                box.label(text=f"{'Candidate' if len(candidates) > 1 else 'Replacement'}: {path}")
        if not rows:
            layout.label(text="No missing external image files.")

    def execute(self, context):
        material = context.object.active_material
        if (getattr(self, "_material", None) != material
                or getattr(self, "_reviewed", None) is None):
            self.report({"WARNING"}, "Open the relink dialog to review replacements first")
            return {"CANCELLED"}
        rows = suggestions(material, self.directory)
        if self._reviewed != (self.directory, rows):
            self.report({"WARNING"}, "Texture matches changed. Open Relink again to review them")
            return {"CANCELLED"}
        try:
            settings = context.scene.mw_pbr_material
            sync_settings_from_material(settings, material)
            count = apply_relinks(settings, rows, material)
        except (OSError, RuntimeError, ValueError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        if not count:
            self.report({"WARNING"}, "No unambiguous replacements found")
            return {"CANCELLED"}
        remaining = len(missing_images(material))
        self.report({"INFO"}, f"Relinked {count} texture reference(s); {remaining} still missing")
        return {"FINISHED"}


_CLASSES = (
    MWPBR_OT_UpdateMaterial,
    MWPBR_OT_RebuildMaterial,
    MWPBR_OT_RelinkTextureSet,
    MWPBR_OT_CreateMaterial,
    MWPBR_OT_ScanTextureFolder,
    MWPBR_OT_ToggleBackfaces,
    MWPBR_OT_SetNormalConvention,
    MWPBR_OT_SetDisplacementMethod,
    MWPBR_OT_NormalUncertaintyHint,
    MWPBR_OT_ResetSlider,
    MWPBR_OT_ReloadAllTextures,
    MWPBR_OT_RemoveAllTextures,
)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
