"""Principled material construction for MW PBR Material."""

from __future__ import annotations

from array import array
from functools import lru_cache
import json

import bpy


SRGB_TEXTURES = {"base_color", "emissive"}
MW_PBR_MATERIAL_KEY = "mw_pbr_material"
NON_COLOR_TEXTURES = {
    "metallic",
    "normal",
    "roughness",
    "opacity",
    "height",
    "ambient_occlusion",
}

TEXTURE_ROLES = (
    "base_color",
    "metallic",
    "roughness",
    "normal",
    "opacity",
    "height",
    "ambient_occlusion",
    "emissive",
)

TEXTURE_NODE_NAMES = {
    "base_color": "MW BaseColor Texture",
    "metallic": "MW Metallic Texture",
    "roughness": "MW Roughness Texture",
    "normal": "MW Normal Texture",
    "opacity": "MW Opacity Texture",
    "height": "MW Height Texture",
    "ambient_occlusion": "MW Ambient Occlusion Texture",
    "emissive": "MW Emissive Texture",
}

STATE_PREFIX = "mw_pbr_state_"


@lru_cache(maxsize=2)
def _configured_color_space(is_color):
    """Resolve against Blender's active OCIO configuration, fixed at startup."""
    probe = bpy.data.images.new("MW PBR colour space probe", 1, 1)
    try:
        color = probe.colorspace_settings
        if not is_color:
            # Blender resolves this to the configured OCIO data role.
            color.is_data = True
            if color.is_data:
                return color.name
            raise RuntimeError("The active OpenColorIO configuration has no data colour space")

        names = color.bl_rna.properties["name"].enum_items.keys()
        candidates = ["sRGB"]
        if "sRGB" not in names:
            # Resolve OCIO aliases to their canonical RNA enum names.
            import PyOpenColorIO as ocio

            config = ocio.GetCurrentConfig()
            for alias in ("srgb_rec709_scene", "srgb_texture", "Utility - sRGB - Texture"):
                space = config.getColorSpace(alias)
                if space:
                    candidates.append(space.getName())
        for name in candidates:
            if name in names:
                color.name = name
                if not color.is_data:
                    return name
        # Blender 5.3 also exposes standardized interoperability identifiers.
        if hasattr(color, "interop_id"):
            for name in names:
                color.name = name
                if not color.is_data and color.interop_id == "srgb_rec709_scene":
                    return name
        raise RuntimeError("The active OpenColorIO configuration has no sRGB texture colour space")
    finally:
        bpy.data.images.remove(probe)


def _target_color_space(image, role):
    # Any existing space flagged as data is already suitable for a data map.
    if role not in SRGB_TEXTURES and image.colorspace_settings.is_data:
        return image.colorspace_settings.name
    return _configured_color_space(role in SRGB_TEXTURES)


def _set_color_space(image, texture_role):
    target = _target_color_space(image, texture_role)
    if image.colorspace_settings.name != target:
        image.colorspace_settings.name = target


def _image_node(nodes, links, image, texture_role, label, location, vector_output, resolve_image):
    image = resolve_image(image, texture_role)
    node = nodes.new("ShaderNodeTexImage")
    node.name = f"MW {label} Texture"
    node.label = label
    node.image = image
    node.location = location
    links.new(vector_output, node.inputs["Vector"])
    return node


def _build_texture_coordinates(nodes, links, texture_scale):
    texture_coordinate = nodes.new("ShaderNodeTexCoord")
    texture_coordinate.name = "MW Texture Coordinate"
    texture_coordinate.label = "Shared UV Coordinates"
    texture_coordinate.location = (-1500, 0)

    mapping = nodes.new("ShaderNodeMapping")
    mapping.name = "MW Texture Scale"
    mapping.label = f"Texture Size {texture_scale:.2f}"
    mapping.vector_type = "POINT"
    mapping.location = (-1250, 0)

    # Mapping nodes control UV frequency. The reciprocal makes the visible UI
    # intuitive: raising Texture Scale enlarges the texture instead of tiling it.
    uv_frequency = 1.0 / max(float(texture_scale), 0.0001)
    mapping.inputs["Scale"].default_value = (
        uv_frequency,
        uv_frequency,
        uv_frequency,
    )
    links.new(texture_coordinate.outputs["UV"], mapping.inputs["Vector"])
    return mapping.outputs["Vector"]


def _build_base_color_brightness(nodes, links, base_node, brightness):
    adjustment = nodes.new("ShaderNodeMixRGB")
    adjustment.name = "MW BaseColor Brightness"
    adjustment.label = f"BaseColor Brightness {brightness:+.2f}"
    adjustment.location = (-630, 320)

    if brightness >= 0.0:
        adjustment.blend_type = "MIX"
        adjustment.inputs[0].default_value = brightness
        adjustment.inputs[2].default_value = (1.0, 1.0, 1.0, 1.0)
    else:
        level = 1.0 + brightness
        adjustment.blend_type = "MULTIPLY"
        adjustment.inputs[0].default_value = 1.0
        adjustment.inputs[2].default_value = (level, level, level, 1.0)

    links.new(base_node.outputs["Color"], adjustment.inputs[1])
    return adjustment.outputs["Color"]


def _input(node, name):
    socket = node.inputs.get(name)
    if socket is None:
        raise RuntimeError(f"Blender's Principled BSDF has no {name!r} input")
    return socket


def _configure_opacity(material: bpy.types.Material) -> None:
    material.surface_render_method = "DITHERED"


def _connect_material_surface(material, nodes, links, principled, output):
    """Connect the surface, adding render-engine-independent backface hiding."""
    if not material.use_backface_culling:
        links.new(principled.outputs["BSDF"], output.inputs["Surface"])
        return

    geometry = nodes.new("ShaderNodeNewGeometry")
    geometry.name = "MW Backface Geometry"
    geometry.label = "Backfacing"
    geometry.location = (350, 260)

    transparent = nodes.new("ShaderNodeBsdfTransparent")
    transparent.name = "MW Backface Transparent"
    transparent.label = "Hidden Backfaces"
    transparent.location = (580, 220)

    mix = nodes.new("ShaderNodeMixShader")
    mix.name = "MW Backface Mix"
    mix.label = "Hide Backfaces in Renders"
    mix.location = (820, 0)

    links.new(geometry.outputs["Backfacing"], mix.inputs[0])
    links.new(principled.outputs["BSDF"], mix.inputs[1])
    links.new(transparent.outputs["BSDF"], mix.inputs[2])
    links.new(mix.outputs["Shader"], output.inputs["Surface"])
    _configure_opacity(material)


def _build_normal_chain(nodes, links, image_node, interpretation):
    normal_map = nodes.new("ShaderNodeNormalMap")
    normal_map.name = "MW OpenGL Normal Map"
    normal_map.label = "OpenGL Normal"
    normal_map.location = (120, -360)

    if interpretation != "DIRECTX":
        links.new(image_node.outputs["Color"], normal_map.inputs["Color"])
        return normal_map.outputs["Normal"]

    separate = nodes.new("ShaderNodeSeparateColor")
    separate.name = "MW Separate DirectX Normal"
    separate.label = "Separate DirectX RGB"
    separate.mode = "RGB"
    separate.location = (-520, -360)

    invert_green = nodes.new("ShaderNodeMath")
    invert_green.name = "MW Flip DirectX Green"
    invert_green.label = "DirectX to OpenGL: 1 - Green"
    invert_green.operation = "SUBTRACT"
    invert_green.inputs[0].default_value = 1.0
    invert_green.location = (-300, -440)

    combine = nodes.new("ShaderNodeCombineColor")
    combine.name = "MW Combine OpenGL Normal"
    combine.label = "Recombine OpenGL RGB"
    combine.mode = "RGB"
    combine.location = (-80, -360)

    links.new(image_node.outputs["Color"], separate.inputs["Color"])
    links.new(separate.outputs["Red"], combine.inputs["Red"])
    links.new(separate.outputs["Green"], invert_green.inputs[1])
    links.new(invert_green.outputs[0], combine.inputs["Green"])
    links.new(separate.outputs["Blue"], combine.inputs["Blue"])
    links.new(combine.outputs["Color"], normal_map.inputs["Color"])
    return normal_map.outputs["Normal"]


def is_mw_material(material) -> bool:
    return bool(material and material.get(MW_PBR_MATERIAL_KEY, False))


def _material_pointer_token(material):
    return str(material.as_pointer()) if material else ""


STATE_FIELDS = (
    "texture_folder", "scan_status", "auto_load_companions",
    "detected_normal_convention", "normal_interpretation", "texture_scale",
    "base_color_brightness", "emission_strength", "displacement_amount",
)


def store_material_state(material, settings):
    for key in STATE_FIELDS:
        material[STATE_PREFIX + key] = getattr(settings, key)
    settings.synced_material_pointer = _material_pointer_token(material)


def _image_from_material(material, role):
    node = owned_nodes(material).get(TEXTURE_NODE_NAMES[role])
    return getattr(node, "image", None) if node else None


def _legacy_texture_scale(material):
    node = owned_nodes(material).get("MW Texture Scale")
    if node is None:
        return 1.0
    frequency = float(node.inputs["Scale"].default_value[0])
    return 1.0 / frequency if frequency > 0.0 else 1.0


def _legacy_base_color_brightness(material):
    node = owned_nodes(material).get("MW BaseColor Brightness")
    if node is None:
        return 0.0
    if node.blend_type == "MULTIPLY":
        return float(node.inputs[2].default_value[0]) - 1.0
    return float(node.inputs[0].default_value)


def _legacy_emission_strength(material):
    node = owned_nodes(material).get("MW Principled BSDF")
    if node is None:
        return 0.0
    return float(_input(node, "Emission Strength").default_value)


def _legacy_displacement_amount(material):
    bump = owned_nodes(material).get("MW Height Bump")
    if bump is not None:
        return float(bump.inputs["Strength"].default_value)
    displacement = owned_nodes(material).get("MW Height Displacement")
    if displacement is not None:
        return float(displacement.inputs["Scale"].default_value)
    return 1.0


def sync_settings_from_material(settings, material, force=False):
    """Load the selected MW material's own sources and controls into the UI."""
    if not is_mw_material(material):
        return False
    token = _material_pointer_token(material)
    if not force and settings.synced_material_pointer == token:
        return False

    from .texture_detection import settings_update_guard

    images = {role: _image_from_material(material, role) for role in TEXTURE_ROLES}
    count = sum(image is not None for image in images.values())
    stored_folder = material.get(f"{STATE_PREFIX}texture_folder", "")
    if not stored_folder:
        first_image = next((image for image in images.values() if image), None)
        filepath = getattr(first_image, "filepath", "") if first_image else ""
        if filepath:
            from pathlib import Path

            stored_folder = str(Path(bpy.path.abspath(filepath)).parent)

    normal_interpretation = material.get(
        f"{STATE_PREFIX}normal_interpretation",
        "DIRECTX" if "MW Flip DirectX Green" in owned_nodes(material) else "AUTO",
    )
    if normal_interpretation not in {"AUTO", "OPENGL", "DIRECTX"}:
        normal_interpretation = "AUTO"
    detected = material.get(f"{STATE_PREFIX}detected_normal_convention", "UNKNOWN")
    if detected not in {"UNKNOWN", "OPENGL", "DIRECTX"}:
        detected = "UNKNOWN"

    with settings_update_guard(settings):
        settings.material_name = material.name
        settings.texture_folder = str(stored_folder)
        settings.auto_load_companions = bool(
            material.get(f"{STATE_PREFIX}auto_load_companions", True)
        )
        for role, image in images.items():
            setattr(settings, role, image)
        settings.detected_normal_convention = detected
        settings.normal_interpretation = normal_interpretation
        settings.texture_scale = float(
            material.get(
                f"{STATE_PREFIX}texture_scale",
                _legacy_texture_scale(material),
            )
        )
        settings.base_color_brightness = float(
            material.get(
                f"{STATE_PREFIX}base_color_brightness",
                _legacy_base_color_brightness(material),
            )
        )
        settings.emission_strength = float(
            material.get(
                f"{STATE_PREFIX}emission_strength",
                _legacy_emission_strength(material),
            )
        )
        settings.displacement_amount = float(
            material.get(
                f"{STATE_PREFIX}displacement_amount",
                _legacy_displacement_amount(material),
            )
        )
        settings.matched_texture_count = count
        settings.scan_status = material.get(
            f"{STATE_PREFIX}scan_status",
            f"Matched {count} of {len(TEXTURE_ROLES)} texture maps"
            if count
            else "No textures loaded",
        )
        settings.synced_material_pointer = token
    return True


def _generate(settings, material, resolve_image):
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()

    output = nodes.new("ShaderNodeOutputMaterial")
    output.name = "MW Material Output"
    output.location = (1100, 0)

    principled = nodes.new("ShaderNodeBsdfPrincipled")
    principled.name = "MW Principled BSDF"
    principled.location = (550, 0)
    # Blender 5 defaults the Principled emission colour to white. Keep emission
    # disabled unless an emissive texture is actually connected.
    _input(principled, "Emission Color").default_value = (0.0, 0.0, 0.0, 1.0)
    _input(principled, "Emission Strength").default_value = 0.0
    _connect_material_surface(material, nodes, links, principled, output)

    vector_output = None
    if any(getattr(settings, role) for role in TEXTURE_ROLES):
        vector_output = _build_texture_coordinates(
            nodes,
            links,
            settings.texture_scale,
        )

    base_node = None
    base_color_output = None
    if settings.base_color:
        base_node = _image_node(
            nodes,
            links,
            settings.base_color,
            "base_color",
            "BaseColor",
            (-900, 320),
            vector_output, resolve_image,
        )
        base_color_output = _build_base_color_brightness(
            nodes,
            links,
            base_node,
            settings.base_color_brightness,
        )

    if settings.ambient_occlusion:
        ao_node = _image_node(
            nodes,
            links,
            settings.ambient_occlusion,
            "ambient_occlusion",
            "Ambient Occlusion",
            (-900, 100),
            vector_output, resolve_image,
        )
        ao_multiply = nodes.new("ShaderNodeMixRGB")
        ao_multiply.name = "MW AO BaseColor Multiply"
        ao_multiply.label = "AO × BaseColor"
        ao_multiply.blend_type = "MULTIPLY"
        ao_multiply.inputs[0].default_value = 1.0
        ao_multiply.inputs[1].default_value = _input(
            principled, "Base Color"
        ).default_value
        ao_multiply.location = (-300, 260)
        if base_color_output:
            links.new(base_color_output, ao_multiply.inputs[1])
        links.new(ao_node.outputs["Color"], ao_multiply.inputs[2])
        links.new(ao_multiply.outputs["Color"], _input(principled, "Base Color"))
    elif base_color_output:
        links.new(base_color_output, _input(principled, "Base Color"))

    simple_maps = (
        ("metallic", "Metallic", "Metallic", (-900, -100)),
        ("roughness", "Roughness", "Roughness", (-900, -260)),
    )
    for role, label, socket_name, location in simple_maps:
        image = getattr(settings, role)
        if image:
            image_node = _image_node(
                nodes, links, image, role, label, location, vector_output, resolve_image
            )
            links.new(image_node.outputs["Color"], _input(principled, socket_name))

    normal_output = None
    if settings.normal:
        normal_node = _image_node(
            nodes,
            links,
            settings.normal,
            "normal",
            "Normal",
            (-900, -440),
            vector_output, resolve_image,
        )
        interpretation = (
            settings.detected_normal_convention
            if settings.normal_interpretation == "AUTO"
            else settings.normal_interpretation
        )
        if interpretation not in {"OPENGL", "DIRECTX"}:
            interpretation = "OPENGL"
        normal_output = _build_normal_chain(
            nodes, links, normal_node, interpretation
        )

    if settings.height:
        height_node = _image_node(
            nodes,
            links,
            settings.height,
            "height",
            "Height",
            (-900, -700),
            vector_output, resolve_image,
        )
        displacement_method = getattr(material, "displacement_method", "BUMP")
        if displacement_method in {"BUMP", "BOTH"}:
            bump = nodes.new("ShaderNodeBump")
            bump.name = "MW Height Bump"
            bump.label = "Height as Bump"
            bump.location = (320, -420)
            bump.inputs["Strength"].default_value = settings.displacement_amount
            links.new(height_node.outputs["Color"], bump.inputs["Height"])
            if normal_output:
                links.new(normal_output, bump.inputs["Normal"])
            links.new(bump.outputs["Normal"], _input(principled, "Normal"))
        elif normal_output:
            links.new(normal_output, _input(principled, "Normal"))

        if displacement_method in {"DISPLACEMENT", "BOTH"}:
            displacement = nodes.new("ShaderNodeDisplacement")
            displacement.name = "MW Height Displacement"
            displacement.label = "True Displacement"
            displacement.location = (800, -520)
            displacement.inputs["Midlevel"].default_value = 0.5
            displacement.inputs["Scale"].default_value = settings.displacement_amount
            links.new(height_node.outputs["Color"], displacement.inputs["Height"])
            links.new(
                displacement.outputs["Displacement"],
                output.inputs["Displacement"],
            )
    elif normal_output:
        links.new(normal_output, _input(principled, "Normal"))

    if settings.opacity:
        opacity_node = _image_node(
            nodes,
            links,
            settings.opacity,
            "opacity",
            "Opacity",
            (-900, -920),
            vector_output, resolve_image,
        )
        links.new(opacity_node.outputs["Color"], _input(principled, "Alpha"))
        _configure_opacity(material)

    if settings.emissive:
        emissive_node = _image_node(
            nodes,
            links,
            settings.emissive,
            "emissive",
            "Emissive",
            (-900, -1100),
            vector_output, resolve_image,
        )
        _input(principled, "Emission Strength").default_value = (
            settings.emission_strength
        )
        links.new(
            emissive_node.outputs["Color"], _input(principled, "Emission Color")
        )


NODE_ROLE = "mw_pbr_node_role"
GRAPH_LINKS = "mw_pbr_generated_links"

_NODE_TYPES = {
    **dict.fromkeys(TEXTURE_NODE_NAMES.values(), "ShaderNodeTexImage"),
    "MW Material Output": "ShaderNodeOutputMaterial",
    "MW Principled BSDF": "ShaderNodeBsdfPrincipled",
    "MW Texture Coordinate": "ShaderNodeTexCoord",
    "MW Texture Scale": "ShaderNodeMapping",
    "MW BaseColor Brightness": "ShaderNodeMixRGB",
    "MW AO BaseColor Multiply": "ShaderNodeMixRGB",
    "MW Backface Geometry": "ShaderNodeNewGeometry",
    "MW Backface Transparent": "ShaderNodeBsdfTransparent",
    "MW Backface Mix": "ShaderNodeMixShader",
    "MW OpenGL Normal Map": "ShaderNodeNormalMap",
    "MW Separate DirectX Normal": "ShaderNodeSeparateColor",
    "MW Flip DirectX Green": "ShaderNodeMath",
    "MW Combine OpenGL Normal": "ShaderNodeCombineColor",
    "MW Height Bump": "ShaderNodeBump",
    "MW Height Displacement": "ShaderNodeDisplacement",
}


def owned_nodes(material):
    """Resolve persistent roles; recognize the original graph on legacy materials."""
    if not is_mw_material(material) or not material.node_tree:
        return {}
    modern = GRAPH_LINKS in material
    result = {}
    for node in material.node_tree.nodes:
        role = node.get(NODE_ROLE) if modern else node.name
        if _NODE_TYPES.get(role) == node.bl_idname:
            result.setdefault(role, node)
    return result


def _link_key(link, roles):
    return (roles.get(link.from_node), link.from_socket.identifier,
            roles.get(link.to_node), link.to_socket.identifier)


def _legacy_generated(link, key, wanted):
    """Legacy files have no link manifest. Recognize the original shader routes."""
    if key in wanted:
        return True
    source, output_id, target, input_id = key
    routes = {
        ("MW Texture Coordinate", "MW Texture Scale", "Vector"),
        ("MW Principled BSDF", "MW Material Output", "Surface"),
        ("MW Backface Mix", "MW Material Output", "Surface"),
        ("MW Backface Geometry", "MW Backface Mix", "Fac"),
        ("MW BaseColor Brightness", "MW Principled BSDF", "Base Color"),
        ("MW AO BaseColor Multiply", "MW Principled BSDF", "Base Color"),
        ("MW Height Bump", "MW Principled BSDF", "Normal"),
        ("MW OpenGL Normal Map", "MW Principled BSDF", "Normal"),
        ("MW OpenGL Normal Map", "MW Height Bump", "Normal"),
        ("MW Height Displacement", "MW Material Output", "Displacement"),
        ("MW Flip DirectX Green", "MW Combine OpenGL Normal", "Green"),
        ("MW Combine OpenGL Normal", "MW OpenGL Normal Map", "Color"),
        ("MW BaseColor Brightness", "MW AO BaseColor Multiply", "Color1"),
    }
    texture_targets = {
        "base_color": {("MW BaseColor Brightness", "Color1")},
        "ambient_occlusion": {("MW AO BaseColor Multiply", "Color2")},
        "metallic": {("MW Principled BSDF", "Metallic")},
        "roughness": {("MW Principled BSDF", "Roughness")},
        "normal": {("MW Separate DirectX Normal", "Color"), ("MW OpenGL Normal Map", "Color")},
        "height": {("MW Height Bump", "Height"), ("MW Height Displacement", "Height")},
        "opacity": {("MW Principled BSDF", "Alpha")},
        "emissive": {("MW Principled BSDF", "Emission Color")},
    }
    # These legacy nodes have repeated socket names. Match the actual
    # generated sockets so an artist's alternate routing stays untouched.
    if target == "MW Backface Mix" and source in {"MW Backface Transparent", "MW Principled BSDF"}:
        return link.to_socket == link.to_node.inputs[2 if source == "MW Backface Transparent" else 1]
    if target == "MW Flip DirectX Green" and source == "MW Separate DirectX Normal":
        return output_id == "Green" and link.to_socket == link.to_node.inputs[1]
    if target == "MW Combine OpenGL Normal" and source == "MW Separate DirectX Normal":
        return output_id == input_id and input_id in {"Red", "Blue"}
    socket = link.to_socket.name
    if source == "MW Texture Scale" and target in TEXTURE_NODE_NAMES.values():
        return socket == "Vector"
    return (source, target, socket) in routes or any(
        source == TEXTURE_NODE_NAMES[role] and (target, socket) in targets
        for role, targets in texture_targets.items()
    )


# Only these values are driven by MW controls on an existing node.
_MANAGED_INPUTS = {
    "MW Texture Scale": ("Scale",),
    "MW BaseColor Brightness": (0, 2),
    "MW Principled BSDF": ("Emission Color", "Emission Strength"),
    "MW Height Bump": ("Strength",),
    "MW Height Displacement": ("Scale",),
}
_NODE_ATTRIBUTES = {
    "ShaderNodeTexImage": ("image",),
    "ShaderNodeMapping": ("vector_type",),
    "ShaderNodeMixRGB": ("blend_type",),
    "ShaderNodeSeparateColor": ("mode",),
    "ShaderNodeCombineColor": ("mode",),
    "ShaderNodeMath": ("operation",),
}

_VARIANT_SOURCE = "mw_pbr_variant_source"


def _file_identity(image):
    # Dirty and packed images can have different pixels despite the same path.
    if image.source == "FILE" and image.filepath and not image.is_dirty and not image.packed_files:
        return (bpy.path.abspath(image.filepath, library=image.library), image.alpha_mode,
                image.use_multiview)
    return None


def _image_has_other_users(image, users):
    """Exempt only MW's texture picker references, not other scene image users."""
    picker_users = 0
    for user in users:
        if not isinstance(user, bpy.types.Scene):
            return True
        picker = getattr(user, "mw_pbr_material", None)
        if picker is not None:
            picker_users += sum(getattr(picker, role) == image for role in TEXTURE_ROLES)
    return image.users > picker_users


def build_material(settings, material=None, *, rebuild=False):
    """Stage generation, then apply a journaled graph update to the same material."""
    creating = material is None
    if not creating and (not is_mw_material(material) or not material.is_editable):
        raise ValueError("Select an editable MW PBR material")
    from .texture_detection import settings_update_guard

    stage = bpy.data.materials.new("MW PBR staging")
    created_images = []
    color_changes = []
    variants = {}
    undo = []

    def resolve_image(image, role):
        target = _target_color_space(image, role)
        original_space = image.colorspace_settings.name
        if original_space == target:
            return image
        key = (image, target)
        if key not in variants:
            identity = _file_identity(image)
            root = image.get(_VARIANT_SOURCE) if identity else None
            root = root if isinstance(root, bpy.types.Image) and _file_identity(root) == identity else image
            user_map = bpy.data.user_map(subset={image, root})
            if identity:
                # Only reuse a copy we created from this very datablock. An
                # unrelated import of the same path can have different settings.
                for candidate in (root, *user_map.get(root, ())):
                    if (isinstance(candidate, bpy.types.Image)
                            and (candidate == root or candidate.get(_VARIANT_SOURCE) == root)
                            and _file_identity(candidate) == identity
                            and candidate.colorspace_settings.name == target):
                        variants[key] = candidate
                        return candidate
            if (not image.is_editable or image.is_dirty
                    or _image_has_other_users(image, user_map.get(image, ()))
                    or any(source == image and _target_color_space(source, slot) == original_space
                           for slot, source in requested.items())):
                source = image
                image = image.copy()
                created_images.append(image)
                image.use_fake_user = False
                if _VARIANT_SOURCE in image:
                    del image[_VARIANT_SOURCE]
                if source.library and source.filepath.startswith("//"):
                    image.filepath = bpy.path.abspath(source.filepath, library=source.library)
                image.colorspace_settings.name = target
                if identity:
                    image[_VARIANT_SOURCE] = root
                if source.is_dirty:
                    # Blender's Image.copy does not copy unsaved image buffers.
                    if (source.source not in {"FILE", "GENERATED"}
                            or source.type not in {"IMAGE", "UV_TEST"}):
                        raise RuntimeError(f"Save {source.name!r} before using it in another colour space")
                    pixels = array("f", [0.0]) * len(source.pixels)
                    source.pixels.foreach_get(pixels)
                    if not pixels or len(image.pixels) != len(pixels):
                        raise RuntimeError(f"Could not copy the unsaved pixels of {source.name!r}")
                    image.pixels.foreach_set(pixels)
                    image.update()
                    image.pack()
            else:
                color_changes.append((image, original_space))
                image.colorspace_settings.name = target
            variants[key] = image
        return variants[key]

    def assign(obj, attr, value):
        previous = getattr(obj, attr)
        if hasattr(previous, "to_tuple"):
            previous = previous.to_tuple()
        elif hasattr(previous, "__len__") and not isinstance(previous, (str, bpy.types.ID)):
            previous = tuple(previous)
        if previous != value:
            undo.append(lambda: setattr(obj, attr, previous))
            setattr(obj, attr, value)

    def prop(obj, key, value):
        existed = key in obj
        previous = obj.get(key)
        def restore():
            if existed:
                obj[key] = previous
            elif key in obj:
                del obj[key]
        undo.append(restore)
        obj[key] = value

    try:
        requested = {role: getattr(settings, role) for role in TEXTURE_ROLES}
        if material:
            stage.use_backface_culling = material.use_backface_culling
            stage.displacement_method = material.displacement_method
        _generate(settings, stage, resolve_image)
        desired = {node.name: node for node in stage.node_tree.nodes}
        desired_roles = {node: role for role, node in desired.items()}
        desired_links = [_link_key(link, desired_roles) for link in stage.node_tree.links]
        if creating:
            material = stage
            material.name = settings.material_name.strip() or "PBR Material"
            for role, node in desired.items():
                node[NODE_ROLE] = role
            actual = desired
            installed_links = desired_links
        else:
            tree = material.node_tree
            nodes, links = tree.nodes, tree.links
            original = list(nodes)
            active = nodes.active
            active_outputs = [n for n in nodes if n.type == "OUTPUT_MATERIAL" and n.is_active_output]
            selected = [(n, n.select) for n in original]
            def restore_editor_state():
                for n, value in selected:
                    n.select = value
                nodes.active = active
                for n in active_outputs:
                    n.is_active_output = True
            undo.append(restore_editor_state)

            old = owned_nodes(material) if not rebuild else {}
            old_roles = {node: role for role, node in old.items()}
            previous_links = {tuple(key) for key in json.loads(material.get(GRAPH_LINKS, "[]"))}
            wanted = set(desired_links)
            obsolete = set(original if rebuild else (n for role, n in old.items() if role not in desired))
            managed = {}
            protected_inputs = set()
            protected_nodes = set()
            if not rebuild:
                for link in links:
                    key = _link_key(link, old_roles)
                    if (key in previous_links if GRAPH_LINKS in material
                            else _legacy_generated(link, key, wanted)):
                        managed[key] = link
                    else:
                        protected_inputs.add(link.to_socket)
                        protected_nodes.update((link.from_node, link.to_node))
                # A custom link or a custom frame can still use a retired MW node.
                for node in obsolete & (protected_nodes | {n for n in obsolete if n.parent}):
                    if NODE_ROLE in node:
                        previous = node[NODE_ROLE]
                        undo.append(lambda n=node, value=previous: n.__setitem__(NODE_ROLE, value))
                        del node[NODE_ROLE]
                    obsolete.remove(node)

            actual = {}
            for role, template in desired.items():
                node = old.get(role)
                new = node is None
                if new:
                    node = nodes.new(template.bl_idname)
                    undo.append(lambda n=node: nodes.remove(n))
                    node.name = "MW PBR pending" if rebuild else role
                    node.label = template.label
                    node.location = template.location
                    node.select = False
                actual[role] = node
                prop(node, NODE_ROLE, role)
                for attr in _NODE_ATTRIBUTES.get(template.bl_idname, ()):
                    if new or attr == "image" or role == "MW BaseColor Brightness":
                        assign(node, attr, getattr(template, attr))
                inputs = _MANAGED_INPUTS.get(role, ())
                if role == "MW Principled BSDF" and not (
                        settings.emissive or TEXTURE_NODE_NAMES["emissive"] in old):
                    inputs = ()
                if new:
                    inputs = [i for i, socket in enumerate(template.inputs)
                              if hasattr(socket, "default_value")]
                for i in inputs:
                    socket = node.inputs[i]
                    if socket not in protected_inputs:
                        assign(socket, "default_value", template.inputs[i].default_value)

            for key, link in managed.items():
                if key not in wanted:
                    src, dst, muted = link.from_socket, link.to_socket, link.is_muted
                    def restore_link(s=src, d=dst, m=muted):
                        links.new(s, d, verify_limits=False).is_muted = m
                    undo.append(restore_link)
                    links.remove(link)
            installed_links = []
            for key in desired_links:
                source, i, target, j = key
                src = next(s for s in actual[source].outputs if s.identifier == i)
                dst = next(s for s in actual[target].inputs if s.identifier == j)
                if dst in protected_inputs:
                    continue
                if key not in managed:
                    link = links.new(src, dst, verify_limits=False)
                    undo.append(lambda edge=link: links.remove(edge))
                installed_links.append(key)

            if rebuild or not active_outputs:
                actual["MW Material Output"].is_active_output = True
            else:
                restore_editor_state()
            if rebuild:
                for role in actual:
                    previous = nodes.get(role)
                    if previous in obsolete:
                        assign(previous, "name", "MW PBR retired")
                for role, node in actual.items():
                    assign(node, "name", role)

        prop(material, MW_PBR_MATERIAL_KEY, True)
        prop(material, GRAPH_LINKS, json.dumps(installed_links))
        if settings.opacity or stage.use_backface_culling:
            assign(material, "surface_render_method", stage.surface_render_method)
        with settings_update_guard(settings):
            for role, name in TEXTURE_NODE_NAMES.items():
                if name in actual:
                    assign(settings, role, actual[name].image)
            for key in STATE_FIELDS:
                prop(material, STATE_PREFIX + key, getattr(settings, key))
            assign(settings, "synced_material_pointer", _material_pointer_token(material))
        if not creating:
            # All fallible generation and assignments precede removal. These
            # are valid nodes in a verified editable local node tree.
            for node in obsolete:
                nodes.remove(node)
        return material
    except Exception as exc:
        with settings_update_guard(settings):
            for restore in reversed(undo):
                try:
                    restore()
                except Exception as rollback_error:
                    exc.add_note(f"Could not restore a material value: {rollback_error}")
        for image, color_space in reversed(color_changes):
            try:
                image.colorspace_settings.name = color_space
            except Exception as rollback_error:
                exc.add_note(f"Could not restore {image.name!r}: {rollback_error}")
        raise
    finally:
        if not creating or material != stage or not is_mw_material(stage):
            bpy.data.materials.remove(stage)
        for image in created_images:
            if not image.users:
                bpy.data.images.remove(image)
