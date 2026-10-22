#!/usr/bin/python
"""Actual GLX/X11 pixel tests; the Xephyr parent is offscreen on the host."""
import argparse
import json
import os
from pathlib import Path
import re
import signal
import subprocess as sp
import tempfile
import time

from PIL import ImageGrab

parser = argparse.ArgumentParser()
parser.add_argument('--picom', type=Path, required=True)
parser.add_argument('--dwm', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--geometry-only', action='store_true')
parser.add_argument('--electron', type=Path, help='Optional VS Code Electron executable, with an isolated profile')
args = parser.parse_args()
args.picom, args.dwm, args.output = args.picom.resolve(), args.dwm.resolve(), args.output.resolve()
args.output.mkdir(parents=True, exist_ok=True)
nord = Path(__file__).resolve().parent
hostenv = os.environ.copy()
env = hostenv.copy()
display = next(n for n in range(98, 115) if not Path(f'/tmp/.X11-unix/X{n}').exists())
env['DISPLAY'] = f':{display}'
processes, logs, results = [], [], []

def spawn(argv, label, childenv=env, pipe=False):
    log = open(args.output / (label + '.log'), 'w')
    logs.append(log)
    proc = sp.Popen([str(x) for x in argv], env=childenv, text=True, start_new_session=True,
                    stdout=sp.PIPE if pipe else log, stderr=log)
    processes.append(proc)
    return proc

def run(*argv):
    return sp.run([str(x) for x in argv], env=env, capture_output=True, text=True,
                  check=True, timeout=10).stdout.strip()

def until(fn, seconds=8):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        try:
            value = fn()
            if value:
                return value
        except (sp.CalledProcessError, OSError, IndexError, ValueError):
            pass
        time.sleep(.02)
    raise AssertionError('Timed out: ' + str(fn))

def passed(label):
    results.append(label)
    print('PASS', label, flush=True)

def geometry(window):
    values = dict(x.split('=', 1) for x in run('xdotool', 'getwindowgeometry', '--shell', window).splitlines())
    return tuple(int(values[k]) for k in ('X', 'Y', 'WIDTH', 'HEIGHT'))

def frame():
    return ImageGrab.grab(xdisplay=env['DISPLAY']).convert('RGB')

def close(window):
    run('xdotool', 'windowactivate', '--sync', window)
    run('xdotool', 'key', '--clearmodifiers', 'super+q')

with tempfile.TemporaryDirectory(prefix='picom-nord-test-') as temp:
    state = Path(temp)
    fixture = state / 'client'
    sp.run(['cc', '-O2', str(nord / 'test-client.c'), '-lX11', '-o', str(fixture)], check=True)
    # Lengthen only the test animations so intermediate pixel values are measurable
    # under software-rendered Xephyr. Production uses 140/120 ms.
    config = state / 'picom.conf'
    config.write_text((nord / 'picom.conf').read_text().replace('duration = 0.14', 'duration = 0.45').replace('duration = 0.12', 'duration = 0.35'))
    try:
        parent = spawn([fixture, 'parent'], 'parent', childenv=hostenv, pipe=True)
        parentid = parent.stdout.readline().strip()
        spawn(['Xephyr', env['DISPLAY'], '-screen', '1280x800', '-parent', parentid,
               '-ac', '-nolisten', 'tcp', '-no-host-grab'], 'xephyr', childenv=hostenv)
        until(lambda: run('xdotool', 'getdisplaygeometry') == '1280 800')
        run('xsetroot', '-solid', '#2e3440')
        dwm = spawn([args.dwm], 'dwm')
        until(lambda: run('xdotool', 'search', '--class', '^dwm$'))
        run('xdotool', 'key', '--clearmodifiers', 'super+0')
        picom = spawn([args.picom, '--config', config, '--log-level=debug'], 'picom')
        time.sleep(.4)
        assert picom.poll() is None, (args.output / 'picom.log').read_text()[-3000:]
        background = frame().getpixel((500, 280))

        proc = spawn([fixture, 'geometry-regression'], 'geometry-client', pipe=True)
        window = proc.stdout.readline().strip()
        until(lambda: ' = 1' in run('xprop', '-id', window, '_DWM_FLOATING'))
        time.sleep(.09)
        run('xdotool', 'windowmove', window, 160, 130)
        time.sleep(.05)
        shot = frame()
        center = shot.getpixel((400, 280))
        shot.save(args.output / 'open-after-configure.png')
        assert 15 < center[0] < 158, ('Open animation interrupted by geometry update', center)
        time.sleep(.5)
        steady = frame()
        assert steady.getpixel((400, 280)) == (163, 190, 140), steady.getpixel((400, 280))
        passed('Open animation survives immediate ConfigureNotify; final client pixels are exact')

        if not args.geometry_only:
            x, y, width, height = geometry(window)
            # Inner client origin excludes the X11 border; find its outer origin
            # by comparing straight-edge pixels before checking all four arcs.
            outer_x, outer_y = x - 2, y - 2
            if steady.getpixel((x, y + height // 2)) == (180, 142, 173):
                outer_x, outer_y = x, y
            border = (180, 142, 173)
            crop = steady.crop((outer_x, outer_y, outer_x + width + 4, outer_y + height + 4))
            crop.save(args.output / 'rounded-border.png')
            points = [(2, 2), (width + 1, 2), (2, height + 1), (width + 1, height + 1)]
            for point in points:
                color = crop.getpixel(point)
                assert max(abs(a-b) for a,b in zip(color, border)) < 24, (point, color, crop.size)
            passed('Nord purple border continues around all four antialiased corners')

            # Mouse-motion update must not start a position/size animation.
            for i in range(35):
                run('xdotool', 'windowmove', window, 180 + i * 5, 140)
            assert geometry(window)[:2] == (350, 140), geometry(window)
            log = (args.output / 'picom.log').read_text()
            assert not re.search(r'Starting animation (position|size)', log)
            assert picom.poll() is None
            passed('Repeated interactive position updates stay immediate without geometry animations')

            close(window)
            time.sleep(.07)
            color = frame().getpixel((500, 280))
            assert 15 < color[0] < 160, ('Missing close animation', color)
            time.sleep(.45)
            assert frame().getpixel((500, 280)) == background
            passed('Destroyed client remains visible during close animation, then releases its image')

            # Real ARGB Kitty, isolated shell config and no networked UI.
            kitty = spawn(['kitty', '--config', 'NONE', '--class', 'NordKittyTest',
                           '--title', 'nord-kitty-test', '-o', 'font_size=12',
                           '-o', 'background=#a3be8c', '-o', 'shell=/bin/sh',
                           '-o', 'shell_integration=disabled', '-o', 'confirm_os_window_close=0'], 'kitty')
            kw = until(lambda: run('xdotool', 'search', '--name', '^nord-kitty-test$').splitlines()[-1])
            time.sleep(.7)
            close(kw)
            until(lambda: kitty.poll() is not None)
            time.sleep(.4)
            log = (args.output / 'picom.log').read_text()
            assert re.search(r'Starting animation (open|show).*nord-kitty-test', log), 'No Kitty open animation'
            assert re.search(r'Starting animation (close|hide).*nord-kitty-test', log), 'No Kitty close animation'
            passed('Actual ARGB Kitty receives both opening and closing lifetime animations')

            if args.electron:
                profile = state / 'code-profile'
                (profile / 'User').mkdir(parents=True)
                (profile / 'User/settings.json').write_text(json.dumps({
                    'window.title': 'Nord Electron Test',
                    'workbench.startupEditor': 'none',
                    'telemetry.telemetryLevel': 'off',
                    'update.mode': 'none',
                    'workbench.enableExperiments': False,
                    'extensions.autoCheckUpdates': False,
                    'extensions.autoUpdate': False,
                }))
                electron_env = env.copy()
                for name in ('ELECTRON_RUN_AS_NODE', 'VSCODE_IPC_HOOK_CLI'):
                    electron_env.pop(name, None)
                electron = spawn([args.electron.resolve(), '--user-data-dir', profile,
                                  '--extensions-dir', state / 'extensions', '--new-window',
                                  '--disable-extensions', '--disable-workspace-trust',
                                  '--skip-welcome', '--skip-release-notes',
                                  '--ozone-platform=x11'], 'electron', childenv=electron_env)
                ew = until(lambda: run('xdotool', 'search', '--onlyvisible', '--name',
                                       '^Nord Electron Test$').splitlines()[-1], seconds=25)
                time.sleep(1)
                run('xdotool', 'windowsize', ew, 800, 600)
                for i in range(60):
                    run('xdotool', 'windowmove', ew, 100 + i * 4, 90)
                assert geometry(ew)[:2] == (336, 90), geometry(ew)
                assert not re.search(r'Starting animation (position|size)',
                                     (args.output / 'picom.log').read_text())
                assert picom.poll() is None
                close(ew)
                until(lambda: electron.poll() is not None)
                passed('Actual Electron window follows repeated moves without geometry easing or compositor failure')
        assert picom.poll() is None
    finally:
        for proc in reversed(processes):
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                continue
            if proc.poll() is None:
                try:
                    proc.wait(timeout=2)
                except sp.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
        for log in logs:
            log.close()
        (args.output / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
