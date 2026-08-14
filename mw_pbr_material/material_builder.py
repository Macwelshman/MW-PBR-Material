"""Principled material construction for MW PBR Material."""

from __future__ import annotations

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


def _set_color_space(image: bpy.types.Image, texture_role: str) -> None:
    """Set the Blender image datablock to the correct role-specific colour space."""
    target = "sRGB" if texture_role in SRGB_TEXTURES else "Non-Color"
    try:
        image.colorspace_settings.name = target
    except TypeError as exc:
        raise RuntimeError(
            f"{image.name!r} cannot use the required {target!r} colour space"
        ) from exc


def _image_node(nodes, links, image, texture_role, label, location, vector_output):
    _set_color_space(image, texture_role)
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
    """Use Blender's current transparent-surface setting with a legacy fallback."""
    if hasattr(material, "surface_render_method"):
        material.surface_render_method = "DITHERED"
    elif hasattr(material, "blend_method"):
        material.blend_method = "HASHED"


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


def store_material_state(material, settings):
    material[f"{STATE_PREFIX}texture_folder"] = settings.texture_folder
    material[f"{STATE_PREFIX}scan_status"] = settings.scan_status
    material[f"{STATE_PREFIX}auto_load_companions"] = bool(
        settings.auto_load_companions
    )
    material[f"{STATE_PREFIX}detected_normal_convention"] = (
        settings.detected_normal_convention
    )
    material[f"{STATE_PREFIX}normal_interpretation"] = (
        settings.normal_interpretation
    )
    material[f"{STATE_PREFIX}texture_scale"] = float(settings.texture_scale)
    material[f"{STATE_PREFIX}base_color_brightness"] = float(
        settings.base_color_brightness
    )
    material[f"{STATE_PREFIX}emission_strength"] = float(
        settings.emission_strength
    )
    material[f"{STATE_PREFIX}displacement_amount"] = float(
        settings.displacement_amount
    )
    settings.synced_material_pointer = _material_pointer_token(material)


def _image_from_material(material, role):
    node = material.node_tree.nodes.get(TEXTURE_NODE_NAMES[role])
    return getattr(node, "image", None) if node else None


def _legacy_texture_scale(material):
    node = material.node_tree.nodes.get("MW Texture Scale")
    if node is None:
        return 1.0
    frequency = float(node.inputs["Scale"].default_value[0])
    return 1.0 / frequency if frequency > 0.0 else 1.0


def _legacy_base_color_brightness(material):
    node = material.node_tree.nodes.get("MW BaseColor Brightness")
    if node is None:
        return 0.0
    if node.blend_type == "MULTIPLY":
        return float(node.inputs[2].default_value[0]) - 1.0
    return float(node.inputs[0].default_value)


def _legacy_emission_strength(material):
    node = material.node_tree.nodes.get("MW Principled BSDF")
    if node is None:
        return 0.0
    return float(_input(node, "Emission Strength").default_value)


def _legacy_displacement_amount(material):
    bump = material.node_tree.nodes.get("MW Height Bump")
    if bump is not None:
        return float(bump.inputs["Strength"].default_value)
    displacement = material.node_tree.nodes.get("MW Height Displacement")
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
        "DIRECTX" if "MW Flip DirectX Green" in material.node_tree.nodes else "AUTO",
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


def build_material(settings, material=None) -> bpy.types.Material:
    """Create or rebuild a material from the current texture settings."""
    material_name = settings.material_name.strip() or "PBR Material"
    if material is None:
        material = bpy.data.materials.new(name=material_name)
    elif not is_mw_material(material):
        raise ValueError("The active material was not created by MW PBR Material")

    material[MW_PBR_MATERIAL_KEY] = True
    material.use_nodes = True

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
            vector_output,
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
            vector_output,
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
                nodes, links, image, role, label, location, vector_output
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
            vector_output,
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
            vector_output,
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
            vector_output,
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
            vector_output,
        )
        _input(principled, "Emission Strength").default_value = (
            settings.emission_strength
        )
        links.new(
            emissive_node.outputs["Color"], _input(principled, "Emission Color")
        )

    store_material_state(material, settings)
    return material
