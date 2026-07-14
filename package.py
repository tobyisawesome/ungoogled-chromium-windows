#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright (c) 2018 The ungoogled-chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""
ungoogled-chromium packaging script for Microsoft Windows
"""

import sys
if sys.version_info.major < 3:
    raise RuntimeError('Python 3 is required for this script.')

import argparse
import os
import platform
from pathlib import Path
import shutil
import subprocess

sys.path.insert(0, str(Path(__file__).resolve().parent / 'ungoogled-chromium' / 'utils'))
import filescfg
from _common import ENCODING, get_chromium_version
sys.path.pop(0)

_ROOT_DIR = Path(__file__).resolve().parent


def _get_build_root(requested_root):
    requested_root = requested_root.expanduser()
    if not requested_root.is_absolute():
        requested_root = _ROOT_DIR / requested_root
    target = requested_root.resolve()
    if os.name != 'nt' or target.drive.casefold() == _ROOT_DIR.drive.casefold():
        return target

    alias = _ROOT_DIR / 'build'
    target.mkdir(parents=True, exist_ok=True)
    if alias.exists():
        if alias.resolve() != target:
            raise RuntimeError(
                'The local build alias already points somewhere else: {} -> {}'.format(
                    alias, alias.resolve()))
    else:
        subprocess.run(
            ('cmd.exe', '/d', '/c', 'mklink', '/J', str(alias), str(target)),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            encoding=ENCODING)
    return alias

def _get_release_revision():
    revision_path = Path(__file__).resolve().parent / 'ungoogled-chromium' / 'revision.txt'
    return revision_path.read_text(encoding=ENCODING).strip()

def _get_packaging_revision():
    revision_path = Path(__file__).resolve().parent / 'revision.txt'
    return revision_path.read_text(encoding=ENCODING).strip()

_cached_target_cpu = None

def _get_target_cpu(build_outputs):
    global _cached_target_cpu
    if not _cached_target_cpu:
        with open(build_outputs / 'args.gn', 'r') as f:
            args_gn_text = f.read()
            for cpu in ('x64', 'x86', 'arm64'):
                if f'target_cpu="{cpu}"' in args_gn_text:
                    _cached_target_cpu = cpu
                    break
    assert _cached_target_cpu
    return _cached_target_cpu

def main():
    """Entrypoint"""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--cpu-arch',
        metavar='ARCH',
        default=platform.architecture()[0],
        choices=('64bit', '32bit', 'arm'),
        help=('Filter build outputs by a target CPU. '
              'This is the same as the "arch" key in FILES.cfg. '
              'Default (from platform.architecture()): %(default)s'))
    parser.add_argument(
        '--build-root',
        type=Path,
        default=Path('build'),
        help=('Directory containing src/out/Default and receiving packages. '
              'Default: %(default)s'))
    args = parser.parse_args()

    build_root = _get_build_root(args.build_root)
    source_root = build_root / 'src'
    build_outputs = source_root / 'out' / 'Default'

    shutil.copyfile(
        build_outputs / 'mini_installer.exe',
        build_root / 'ungoogled-chromium_{}-{}.{}_installer_{}.exe'.format(
            get_chromium_version(), _get_release_revision(),
            _get_packaging_revision(), _get_target_cpu(build_outputs)))

    timestamp = None
    try:
        with open(source_root / 'build' / 'util' / 'LASTCHANGE.committime', 'r') as ct:
            timestamp = int(ct.read())
    except FileNotFoundError:
        pass

    output = build_root / 'ungoogled-chromium_{}-{}.{}_windows_{}.zip'.format(
        get_chromium_version(), _get_release_revision(),
        _get_packaging_revision(), _get_target_cpu(build_outputs))

    excluded_files = set([
        Path('mini_installer.exe'),
        Path('mini_installer_exe_version.rc'),
        Path('setup.exe'),
        Path('chrome.packed.7z'),
    ])
    files_generator = filescfg.filescfg_generator(
        source_root / 'chrome' / 'tools' / 'build' / 'win' / 'FILES.cfg',
        build_outputs, args.cpu_arch, excluded_files)
    filescfg.create_archive(
        files_generator, tuple(), build_outputs, output, timestamp)

if __name__ == '__main__':
    main()
