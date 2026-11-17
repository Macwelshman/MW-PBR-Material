"""Run MW PBR Material tests in a disposable macOS Blender over Flue."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("blender", type=Path, help="Path to a Blender.app bundle")
    parser.add_argument("--custom-ocio", action="store_true",
                        help="Run with renamed sRGB and data spaces")
    args = parser.parse_args()
    adapter = Path(subprocess.check_output(["flue", "where"], text=True).splitlines()[0])
    adapter /= "adapters/blender_adapter"
    bridge = adapter / "blender_bridge.py"
    addon = adapter / "addon/creative_adapter_bridge.py"
    executable = args.blender / "Contents/MacOS/Blender"
    if not all(path.is_file() for path in (bridge, addon, executable)):
        parser.error("Blender executable or the installed Flue Blender adapter was not found")

    with tempfile.TemporaryDirectory(prefix="mw-pbr-flue-") as directory:
        work = Path(directory)
        env = dict(os.environ, BLENDER_USER_RESOURCES=str(work / "profile"), TMPDIR=str(work))
        env.pop("OCIO", None)
        if args.custom_ocio:
            resources = args.blender / "Contents/Resources"
            config, = resources.glob("*/datafiles/colormanagement/config.ocio")
            shutil.copytree(config.parent, work / "ocio")
            config = work / "ocio/config.ocio"
            # Keep the transforms, LUTs and OCIO roles, but hide both canonical
            # stock names. The sRGB texture alias still points to the same space.
            source = re.sub(r"(?<![\w-])sRGB(?![\w-])", "MW Encoded Texture", config.read_text())
            config.write_text(source.replace("Non-Color", "MW Raw Pixels"))
            env["OCIO"] = str(config)
        bootstrap = work / "bootstrap.py"
        bootstrap.write_text(f"""
import runpy
adapter = runpy.run_path({str(addon)!r})
adapter['register'].__globals__['_session_dir'] = lambda: {str(work)!r}
adapter['register']()
""")
        log = work / "blender.log"
        with log.open("w") as output:
            process = subprocess.Popen(
                [str(executable), "--factory-startup", "--python-exit-code", "1", "--python", str(bootstrap)],
                env=env, stdout=output, stderr=subprocess.STDOUT,
            )
            try:
                session = work / "blender.json"
                deadline = time.monotonic() + 30
                while not session.exists():
                    if process.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError(f"Private Flue bridge did not start:\n{log.read_text()[-3000:]}")
                    time.sleep(0.1)
                script = _runtime_script(process.pid, args.custom_ocio)
                result = subprocess.run(
                    [sys.executable, str(bridge), "--session-file", str(session), "--stdin"],
                    input=script, text=True, capture_output=True, timeout=55,
                )
                if result.returncode:
                    raise RuntimeError(result.stderr or result.stdout or log.read_text()[-3000:])
                report = json.loads(result.stdout)
                print(report["stdout"], end="")
                if report["stderr"]:
                    print(report["stderr"], file=sys.stderr, end="")
                return int(not report["ok"] or report["result"] != 0)
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()


def _runtime_script(pid, custom):
    return f"""
import os, runpy, sys, traceback
from pathlib import Path
assert os.getpid() == {pid} and not bpy.data.filepath
root = Path({str(ROOT)!r})
sys.path.insert(0, str(root))
custom = {custom!r}
color, data = ('MW Encoded Texture', 'MW Raw Pixels') if custom else ('sRGB', 'Non-Color')
jobs = [
    ('test_v01', (), {{'reset': False, 'color': color, 'data': data}}),
    ('test_v02', (), {{'reset': False}}),
    ('test_v03', (), {{'reset': False, 'color': color}}),
    ('test_v04', (), {{'reset': False}}),
    ('test_v05', (), {{'reset': False}}),
    ('test_v06', (), {{'reset': False}}),
    ('test_relink', (), {{}}),
    ('test_safe_updates', (), {{'reset': False, 'color': color, 'data': data}}),
]
jobs += [
    ('test_material_safety', (case, color, data), {{'reset': False}})
    for case in ('reuse', 'manual', 'scene', 'undo')
]
print(bpy.app.version_string, '(custom OCIO)' if custom else '(standard OCIO)')
failed = 0
for test, args, kwargs in jobs:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    window = bpy.context.window_manager.windows[0]
    area = next(a for a in window.screen.areas if a.type == 'VIEW_3D')
    try:
        with bpy.context.temp_override(window=window, area=area):
            runpy.run_path(str(root / 'tests' / (test + '.py')))['run'](*args, **kwargs)
        print('PASS', test, *args[:1])
    except Exception:
        failed += 1
        print('FAIL', test, *args[:1])
        traceback.print_exc()
print(f'{{len(jobs) - failed}}/{{len(jobs)}} runtime checks passed')
_result = failed
"""


if __name__ == "__main__":
    sys.exit(main())
