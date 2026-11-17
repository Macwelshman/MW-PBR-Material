# MW PBR Material V0.6.6

MW PBR Material identifies a texture set and creates a clean Blender Principled
BSDF material. Manual texture selection remains available for overrides.

Supported maps are BaseColor, Metallic, Roughness, Normal, Opacity, Height, Ambient
Occlusion, and Emissive maps. OpenGL normals are native. DirectX normals are
converted non-destructively in the shader by flipping the green channel.

Download `MW_PBR_Material_v0.6.6.zip` from the GitHub release and install it
through Blender's Extensions preferences using **Install from Disk**. The panel
appears under **Material Properties > MW PBR Material**.

Release packages are also published through the separate
[MW Blender Extensions](https://github.com/Macwelshman/MW-Blender-Extensions)
update repository. Local development builds are written to `dist/`, which is
not tracked in this source repository.

## V0.2 workflow

1. Select the target object and click **Create PBR Material**.
2. The MW PBR Material dropdown appears directly below the Create button.
3. Choose a texture folder, or select one recognised texture manually.
4. The add-on identifies and loads its companion texture maps automatically.
5. Review the matched filenames and normal convention in the boxed slots.
6. Override any texture or choose **OpenGL**/**DirectX** when necessary.

The texture interface is only shown while an MW-created material is active.
Texture changes update the MW nodes in place. **Update Material** refreshes the
generated shader while preserving artist nodes, custom links, and settings
outside the MW controls. **Rebuild Material** starts over from the current MW
settings and asks for confirmation before replacing the whole shader graph.
Both actions prepare the new graph before editing the current material. If
generation or application fails, the existing graph and material settings are
kept.
**Remove All** clears the MW texture slots without deleting images or source files.

BaseColor and Emissive use sRGB; the other maps use a data colour space. If a
shared image needs a different interpretation, MW uses an independent
datablock and reuses compatible copies of unchanged, unpacked file images.
Source files are never changed. With a custom OpenColorIO configuration, MW
uses the configured data role and recognises an sRGB texture space by its
name, supported alias, or Blender's interoperability identifier. If the
required space cannot be resolved, the build stops and reports the problem.

Each new **Create PBR Material** action starts with an empty texture folder and
empty source slots. Materials display through their complete shader in Blender's
**Material Preview** and **Rendered** viewport modes; Solid mode does not display
the full PBR texture setup.

V0.2.4 keeps Principled emission disabled when no Emissive map is loaded. This
prevents Blender 5's white default Emission Color from washing out ordinary PBR
materials in Material Preview. When an Emissive map is present, it is connected
with a strength of 1.0.

## V0.3 texture scale

The shared **Texture Scale** slider controls every loaded map together and
defaults to 1.0 for each new material and extends down to 0.01. Increasing the value makes texture
features appear larger; decreasing it makes them appear smaller. The shader
uses one shared UV Mapping node so BaseColor, Normal, Roughness, Height, and all
other maps remain aligned.

**Backfaces**, **Reload**, and **Remove** share one compact action row. The
Backfaces button is blue while backfaces are visible and uses Blender's native
material backface-culling setting. Reload refreshes every assigned image from
disk and preserves its PBR colour space.

V0.3.3 removes repeated filenames and visible helper sentences from the texture
panel. Guidance remains available through control tooltips. A green tick appears
at the start of each loaded texture selector.

V0.3.4 places Auto, OpenGL, and DirectX together directly beneath the loaded
Normal texture. Loading an Emissive map reveals an Emission Strength slider
directly beneath it; the neutral default strength is 0.0.

V0.3.5 uses a bundled green tick icon for loaded texture slots. Backface hiding
continues to use Blender's native material setting for Material Preview and now
also adds a non-destructive Backfacing/Transparent shader branch so hidden
backfaces remain hidden in Rendered mode, including Cycles.

V0.3.6 groups recognised filenames by their shared material-set name instead of
mixing the first alphabetical map of each type in a folder. Manually choosing a
texture anchors companion loading to that exact set. When both normal variants
exist, folder scanning prefers native OpenGL unless the selected file explicitly
chooses DirectX.

The exact image datablock you picked stays selected when companions load.
A filename that does not match the selected slot, or an image whose source file
is missing, remains a manual choice and does not trigger a companion scan.

## V0.4 BaseColor brightness

Loading a BaseColor map reveals a **Brightness** slider directly beneath it.
The neutral default is 0.0; negative values darken toward black and positive
values lighten toward white. The adjustment is non-destructive and occurs before
Ambient Occlusion is multiplied into BaseColor.

V0.4.1 adds a reset icon to Texture Scale, BaseColor Brightness, and Emission
Strength. Automatic normal detection is now implicit: only OpenGL and DirectX
are shown, with the effective convention highlighted. An icon-only question mark
indicates uncertain filenames and provides its explanation as a tooltip; no
status sentence is shown beneath the controls.

## V0.5 material-slot state

Every MW material now retains its own texture assignments, source folder,
Texture Scale, BaseColor Brightness, Emission Strength, and normal convention.
Selecting another material slot on the same object refreshes the panel to show
that material's information. Existing MW materials are migrated from their
named shader nodes the first time they are selected.

V0.5.1 listens for active-object and active-material-slot changes. The Material
Properties panel now synchronizes and redraws immediately when another material
is selected, without requiring a manual refresh.

V0.5.2 keeps **Create PBR Material** as a permanent create action. It always
creates a fresh material, while texture and control changes continue to update
the selected MW material automatically. The Rescan button and visible matching
status have been removed. The custom green loaded-texture tick has also been
restored with a true-colour RGBA asset.

## V0.6 height modes

Loading a Height/Displacement texture reveals **Bump**, **Displacement**, and
**Both** directly beneath the texture selector. Bump remains the default.
Displacement and Both connect a true Displacement node to Material Output and
set Blender's native material displacement method; true surface displacement
requires sufficient mesh subdivision.

V0.6.1 adds a resettable **Amount** slider beneath the height-mode buttons. It
defaults to 1.0 and controls the height effect in every mode. Setting Amount to
0 disables the height effect.

V0.6.2 makes Amount a direct 0–2 slider with 1.0 as its default midpoint. In
true displacement modes, the displayed Amount is now passed directly to the
Displacement node's Scale input.

V0.6.3 recognises the abbreviated suffixes `diff` for BaseColor, `rough` for
Roughness, `nor` for Normal, and `disp` for Height/Displacement. Abbreviated
`nor_gl` and `nor_dx` filenames retain automatic normal-convention detection.

V0.6.6 adds non-destructive material updates, an explicit rebuild confirmation,
and a preview for relinking missing textures. Shared images keep their original
colour space when another role needs a separate datablock.

V0.6.4 is a behavior-neutral release used to verify the MW Blender Extensions
update channel. Add-on functionality is unchanged from V0.6.3.

V0.6.5 is a second behavior-neutral release used to verify automatic updates
from V0.6.4 through the MW Blender Extensions repository.

Auto recognises explicit NormalGL, NormalOpenGL, NormalDX, and NormalDirectX
filename hints. DirectX maps are converted to the native OpenGL convention
inside the shader; the source image is not changed. An unmarked Normal map
defaults safely to OpenGL. Height is connected through a Bump node, and Ambient
Occlusion is multiplied with BaseColor.

V0.2 recognises the agreed aliases for BaseColor/Albedo/Diffuse/Color/Colour,
Metallic/Metalness, Roughness, Normal, Opacity/Alpha, Height/Displacement,
AO/Occlusion, and Emissive/Emission. Alias definitions are centralized in
`texture_detection.py` for later expansion.

## Project structure

- `mw_pbr_material/__init__.py` — registration and add-on metadata
- `mw_pbr_material/properties.py` — manual texture and normal settings
- `mw_pbr_material/ui.py` — Material Properties panel
- `mw_pbr_material/operators.py` — Create PBR Material action
- `mw_pbr_material/texture_detection.py` — folder scanning and filename aliases
- `mw_pbr_material/material_builder.py` — node graph construction
- `tests/test_v01.py` — Blender runtime contract test
- `tests/test_v02.py` — folder detection and companion-loading runtime test
- `tests/test_v03.py` — shared texture-scale runtime test
- `tests/test_v04.py` — BaseColor brightness runtime test
- `tests/test_v05.py` — per-material slot-state runtime test
- `tests/test_v06.py` — height displacement-mode runtime test
- `tests/test_relink.py` — missing-file matching and relink rollback
- `tests/test_safe_updates.py` — graph ownership, shared images, rollback, and save/reopen
- `tests/test_material_safety.py` — variant reuse, manual overrides, scene image references, and Undo/Redo

To run the suite on macOS with Flue installed:

```sh
python3 tests/run_flue.py "/Applications/Blender.app"
python3 tests/run_flue.py "/Applications/Blender.app" --custom-ocio
```

The runner tests a disposable Blender session. The custom configuration
renames the sRGB and data spaces while retaining their transforms and roles.

Workflow inference, Glossiness/Specular support, confidence scoring, ambiguity
warnings, and advanced controls remain reserved for later stages.

### Relink missing textures

If external image files have moved, select the MW material and click **Relink Texture Set** in Material Properties. Choose the replacement folder in the dialog. Relink searches that folder, the stored texture folder, and the original directories of the missing files. It does not search subfolders.

Review the original path and suggested replacement before confirming. A matching filename has high confidence; a matching material-set name and map type has medium confidence. Equal-confidence matches are shown and skipped, as are maps with no match. To resolve a tie, put the intended files in a separate folder and remove the competing files from the search locations, or restore the exact original file.

Relink changes the image references in the material’s own shader tree, including custom image nodes. It preserves node links, mapping and shader controls, including the existing OpenGL/DirectX setup. Packed images, generated images, UDIMs, sequences, movies and images inside node groups are outside this operation. Source files and image datablocks used by other materials are left alone.
