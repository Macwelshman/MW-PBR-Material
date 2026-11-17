"""Filename recognition and texture loading for MW PBR Material V0.2."""

from __future__ import annotations

import re
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import bpy


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

# Keep aliases centralized and ordered from most specific to least specific.
# Adding support for another library should only require extending this table.
TEXTURE_ALIASES = {
    "base_color": (
        "base_color",
        "basecolor",
        "albedo",
        "diffuse",
        "diff",
        "colour",
        "color",
    ),
    "metallic": ("metallic", "metalness", "metal"),
    "roughness": ("roughness", "rough"),
    "normal": (
        "normal_opengl",
        "normalopengl",
        "normal_gl",
        "normalgl",
        "nor_opengl",
        "nor_gl",
        "normal_directx",
        "normaldirectx",
        "normal_dx",
        "normaldx",
        "nor_directx",
        "nor_dx",
        "normal",
        "nor",
    ),
    "ambient_occlusion": (
        "ambient_occlusion",
        "ambientocclusion",
        "occlusion",
        "ao",
    ),
    "height": ("displacement", "displace", "height", "disp"),
    "opacity": ("opacity", "alpha"),
    "emissive": ("emissive", "emission"),
}

SUPPORTED_IMAGE_EXTENSIONS = {
    ".bmp",
    ".dds",
    ".exr",
    ".hdr",
    ".jpeg",
    ".jpg",
    ".png",
    ".tga",
    ".tif",
    ".tiff",
    ".webp",
}

TRAILING_DECORATORS = {
    "1k",
    "2k",
    "4k",
    "8k",
    "16k",
    "linear",
    "srgb",
}

DIRECTX_NORMAL_ALIASES = {
    "normal_directx",
    "normaldirectx",
    "normal_dx",
    "normaldx",
    "nor_directx",
    "nor_dx",
}
OPENGL_NORMAL_ALIASES = {
    "normal_opengl",
    "normalopengl",
    "normal_gl",
    "normalgl",
    "nor_opengl",
    "nor_gl",
}

_SCAN_GUARD = set()


@dataclass(frozen=True)
class TextureMatch:
    role: str
    path: Path
    alias: str
    set_key: str


@dataclass(frozen=True)
class ScanResult:
    folder: Path
    matches: dict[str, TextureMatch]
    normal_convention: str


def _settings_key(settings):
    return settings.as_pointer()


def scan_in_progress(settings) -> bool:
    return _settings_key(settings) in _SCAN_GUARD


@contextmanager
def settings_update_guard(settings):
    """Suspend property callbacks while several settings are synchronized."""
    key = _settings_key(settings)
    already_guarded = key in _SCAN_GUARD
    _SCAN_GUARD.add(key)
    try:
        yield
    finally:
        if not already_guarded:
            _SCAN_GUARD.discard(key)


def _normalise_stem(stem: str) -> str:
    normalised = re.sub(r"(?<=[a-z])(?=[A-Z])", "_", stem)
    normalised = re.sub(r"[^a-zA-Z0-9]+", "_", normalised)
    normalised = normalised.strip("_").lower()
    return normalised.replace("_direct_x", "_directx").replace(
        "_open_gl", "_opengl"
    )


def _alias_regex(alias: str):
    parts = tuple(part for part in alias.split("_") if part)
    body = "_?".join(re.escape(part) for part in parts)
    return re.compile(rf"(?:^|_)({body})(?=_|$)")


def _trailing_tokens_are_decorators(normalised_stem: str, match_end: int) -> bool:
    trailing = normalised_stem[match_end:].strip("_")
    if not trailing:
        return True
    return all(token in TRAILING_DECORATORS for token in trailing.split("_"))


def classify_texture_path(path: Path) -> TextureMatch | None:
    """Classify one image using an alias near the end of its filename."""
    path = Path(path)
    if path.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
        return None

    stem = _normalise_stem(path.stem)
    candidates = []
    for role, aliases in TEXTURE_ALIASES.items():
        for alias in aliases:
            for match in _alias_regex(alias).finditer(stem):
                if not _trailing_tokens_are_decorators(stem, match.end()):
                    continue
                candidates.append(
                    (match.end(), len(alias), role, alias, match.start())
                )

    if not candidates:
        return None

    _end, _length, role, alias, match_start = max(candidates)
    set_key = stem[:match_start].strip("_")
    return TextureMatch(role=role, path=path, alias=alias, set_key=set_key)


def _normal_convention(match: TextureMatch | None) -> str:
    if match is None:
        return "UNKNOWN"
    if match.alias in DIRECTX_NORMAL_ALIASES:
        return "DIRECTX"
    if match.alias in OPENGL_NORMAL_ALIASES:
        return "OPENGL"
    return "UNKNOWN"


def _alias_priority(match: TextureMatch) -> int:
    aliases = TEXTURE_ALIASES[match.role]
    try:
        return aliases.index(match.alias)
    except ValueError:
        return len(aliases)


def _select_material_set(matches, preferred_matches):
    """Select one coherent filename set instead of mixing folder contents."""
    if preferred_matches:
        return next(iter(preferred_matches.values())).set_key

    grouped = {}
    for match in matches:
        grouped.setdefault(match.set_key, []).append(match)
    if not grouped:
        return None

    def group_rank(item):
        set_key, group = item
        roles = {match.role for match in group}
        return (-len(roles), -("base_color" in roles), set_key.casefold())

    return sorted(grouped.items(), key=group_rank)[0][0]


def scan_texture_folder(folder, preferred=None) -> ScanResult:
    """Find one coherent and deterministic texture set in a folder."""
    folder = Path(folder).expanduser().resolve()
    if not folder.is_dir():
        raise FileNotFoundError(f"Texture folder does not exist: {folder}")

    all_matches = []
    for path in sorted(folder.iterdir(), key=lambda item: item.name.casefold()):
        if not path.is_file():
            continue
        match = classify_texture_path(path)
        if match is not None:
            all_matches.append(match)

    preferred_matches = {}
    for role, path in (preferred or {}).items():
        match = classify_texture_path(Path(path))
        if match is not None and match.role == role:
            preferred_matches[role] = match

    selected_key = _select_material_set(all_matches, preferred_matches)
    candidates = {}
    if selected_key is not None:
        selected_matches = [
            match for match in all_matches if match.set_key == selected_key
        ]
        selected_matches.sort(
            key=lambda match: (
                _alias_priority(match),
                match.path.name.casefold(),
            )
        )
        for match in selected_matches:
            candidates.setdefault(match.role, match)

    candidates.update(preferred_matches)

    normal_match = candidates.get("normal")
    return ScanResult(
        folder=folder,
        matches=candidates,
        normal_convention=_normal_convention(normal_match),
    )


def _load_match(match: TextureMatch):
    try:
        return bpy.data.images.load(str(match.path), check_existing=True)
    except RuntimeError as exc:
        raise RuntimeError(f"Could not load {match.path.name}: {exc}") from exc


def _rebuild_owned_material(settings, material):
    from .material_builder import build_material, is_mw_material, sync_settings_from_material

    if is_mw_material(material):
        try:
            build_material(settings, material=material)
        except Exception:
            sync_settings_from_material(settings, material, force=True)
            raise


def apply_scan_result(settings, result: ScanResult, material=None, *, anchor=None) -> ScanResult:
    """Replace the detected slots while leaving every source file untouched."""
    loaded_images = {}
    for role, match in result.matches.items():
        loaded_images[role] = anchor[1] if anchor and role == anchor[0] else _load_match(match)
    with settings_update_guard(settings):
        settings.texture_folder = str(result.folder)
        for role in TEXTURE_ROLES:
            setattr(settings, role, loaded_images.get(role))
        settings.detected_normal_convention = result.normal_convention
        settings.normal_interpretation = "AUTO"
        count = len(result.matches)
        settings.matched_texture_count = count
        settings.scan_status = f"Matched {count} of {len(TEXTURE_ROLES)} texture maps"
    _rebuild_owned_material(settings, material)
    return result


def scan_settings_folder(settings, material=None) -> ScanResult:
    folder = bpy.path.abspath(settings.texture_folder)
    return apply_scan_result(
        settings,
        scan_texture_folder(folder),
        material=material,
    )


def scan_companions_from_image(settings, role: str, image, material=None):
    """Load companions when a recognised texture is selected manually."""
    if scan_in_progress(settings):
        return None
    if image is None:
        _rebuild_owned_material(settings, material)
        return None

    filepath = getattr(image, "filepath", "")
    if not filepath:
        if role == "normal":
            settings.detected_normal_convention = "UNKNOWN"
        _rebuild_owned_material(settings, material)
        return None
    path = Path(bpy.path.abspath(filepath, library=image.library))
    selected_match = classify_texture_path(path)
    if role == "normal":
        settings.detected_normal_convention = _normal_convention(selected_match)
        settings.normal_interpretation = "AUTO"
    if (
        selected_match is None
        or selected_match.role != role
        or not settings.auto_load_companions
        or not path.is_file()
    ):
        _rebuild_owned_material(settings, material)
        return None

    result = scan_texture_folder(path.parent, preferred={role: path})
    return apply_scan_result(settings, result, material=material, anchor=(role, image))


def clear_texture_settings(settings, material=None, clear_folder=False):
    """Clear every source slot without removing any image or source file."""
    with settings_update_guard(settings):
        for role in TEXTURE_ROLES:
            setattr(settings, role, None)
        if clear_folder:
            settings.texture_folder = ""
        settings.detected_normal_convention = "UNKNOWN"
        settings.matched_texture_count = 0
        settings.scan_status = "No textures loaded"
    _rebuild_owned_material(settings, material)
