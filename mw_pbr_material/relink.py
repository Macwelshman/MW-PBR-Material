"""Read-only matching and material-local image replacement."""
from pathlib import Path

import bpy

from .material_builder import STATE_PREFIX, TEXTURE_NODE_NAMES, _set_color_space, owned_nodes
from .texture_detection import (
    SUPPORTED_IMAGE_EXTENSIONS, classify_texture_path, settings_update_guard,
    _normal_convention,
)

ROLES = {name: role for role, name in TEXTURE_NODE_NAMES.items()}


def missing_images(material):
    missing = []
    if material.node_tree:
        for node in material.node_tree.nodes:
            image = getattr(node, "image", None)
            if not image or image.source != "FILE" or image.packed_files or not image.filepath:
                continue
            path = Path(bpy.path.abspath(image.filepath, library=image.library))
            if not path.is_file():
                missing.append((node, image, path))
    return missing


def suggestions(material, directory):
    missing = missing_images(material)
    folders = {path.parent for _, _, path in missing}
    for value in (directory, material.get(STATE_PREFIX + "texture_folder", "")):
        if value:
            folders.add(Path(bpy.path.abspath(value)))
    files = set()
    for folder in folders:
        try:
            files.update(path.resolve() for path in folder.iterdir()
                         if path.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS
                         and path.is_file())
        except OSError:
            continue
    classified = {path: classify_texture_path(path) for path in files}
    rows = []
    roles = {node: ROLES.get(role) for role, node in owned_nodes(material).items()}
    for node, image, original in missing:
        expected = classify_texture_path(original)
        role = roles.get(node) or (expected.role if expected else None)
        ranked = {}
        for path, match in classified.items():
            if path.name.casefold() == original.name.casefold():
                ranked[path] = 2
            elif (expected and match and expected.set_key
                  and match.set_key == expected.set_key
                  and expected.role == match.role == role
                  and (role != "normal" or
                       _normal_convention(match) == _normal_convention(expected))):
                ranked[path] = 1
        best = max(ranked.values(), default=0)
        rows.append((node, image, original,
                     sorted(path for path, score in ranked.items() if score == best), best))
    return rows


def apply_relinks(settings, rows, material):
    """Load independently of other materials, then swap only reviewed references."""
    replacements = {}
    roles = {node: ROLES.get(role) for role, node in owned_nodes(material).items()}
    changed = []
    try:
        for node, image, _, candidates, _ in rows:
            if len(candidates) != 1:
                continue
            path = candidates[0]
            role = roles.get(node)
            key = (image, path, role)
            if key in replacements:
                continue
            replacement = bpy.data.images.load(str(path), check_existing=False)
            replacements[key] = replacement
            if not all(replacement.size):
                raise RuntimeError(f"Could not decode {path.name}")
            if role:
                _set_color_space(replacement, role)
            else:
                replacement.colorspace_settings.name = image.colorspace_settings.name
            replacement.alpha_mode = image.alpha_mode
        with settings_update_guard(settings):
            for node, image, _, candidates, _ in rows:
                if len(candidates) != 1:
                    continue
                role = roles.get(node)
                previous = getattr(settings, role) if role else None
                changed.append((node, image, role, previous))
                node.image = replacements[image, candidates[0], role]
                if role:
                    setattr(settings, role, node.image)
    except Exception:
        with settings_update_guard(settings):
            for node, image, role, previous in reversed(changed):
                node.image = image
                if role:
                    setattr(settings, role, previous)
        for replacement in replacements.values():
            bpy.data.images.remove(replacement)
        raise

    return len(changed)
