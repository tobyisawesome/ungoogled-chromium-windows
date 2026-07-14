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
from itertools import chain
import os
import platform
from pathlib import Path, PurePosixPath, PureWindowsPath
import shutil
import subprocess

sys.path.insert(0, str(Path(__file__).resolve().parent / 'ungoogled-chromium' / 'utils'))
import filescfg
from _common import ENCODING, get_chromium_version
sys.path.pop(0)

_ROOT_DIR = Path(__file__).resolve().parent
_PRODUCT_NAME = 'curve-browser'
_WINUI_PAYLOAD_MANIFEST = Path('windows_chromium_payload_manifest.txt')
_PORTABLE_CONFIGURATION = _ROOT_DIR / 'portable.ini'


def _artifact_filename(kind, version, release_revision, packaging_revision, target_cpu):
    """Return a branded package filename while retaining the upstream layout."""
    if kind == 'installer':
        package_kind = 'installer'
        extension = 'exe'
    elif kind == 'archive':
        package_kind = 'windows'
        extension = 'zip'
    else:
        raise ValueError('Unknown package kind: {}'.format(kind))
    return '{}_{}-{}.{}_{}_{}.{}'.format(
        _PRODUCT_NAME, version, release_revision, packaging_revision,
        package_kind, target_cpu, extension)


def _manifest_error(manifest_path, line_number, message):
    return ValueError('{}:{}: {}'.format(manifest_path, line_number, message))


def _winui_payload_paths(build_outputs):
    """Return archive-relative WinUI payload paths from the generated manifest.

    The manifest lives in the Chromium output root and contains one relative
    Windows or POSIX path per non-comment line. The manifest itself is retained
    in the portable archive so a packaged build remains auditable.
    """
    manifest_path = build_outputs / _WINUI_PAYLOAD_MANIFEST
    if not os.path.lexists(manifest_path):
        print(
            'WinUI payload manifest not found at {}; packaging the pristine '
            'Chromium baseline without a WinUI payload.'.format(manifest_path),
            file=sys.stderr)
        return tuple()
    if not manifest_path.is_file():
        raise ValueError('{} must be a regular UTF-8 text file'.format(manifest_path))

    root = build_outputs.resolve()
    payload_paths = []
    seen = set()
    try:
        manifest_lines = manifest_path.read_text(encoding=ENCODING).splitlines()
    except UnicodeDecodeError as exc:
        raise ValueError(
            '{} must be valid UTF-8: {}'.format(manifest_path, exc)) from exc

    for line_number, raw_line in enumerate(manifest_lines, 1):
        entry = raw_line.strip()
        if not entry or entry.startswith('#'):
            continue

        windows_path = PureWindowsPath(entry)
        posix_path = PurePosixPath(entry)
        if (windows_path.is_absolute() or windows_path.drive or windows_path.root or
                posix_path.is_absolute() or ':' in entry):
            raise _manifest_error(
                manifest_path, line_number,
                'payload path must be relative and drive-free: {!r}'.format(entry))

        normalized = PurePosixPath(entry.replace('\\', '/'))
        if '..' in normalized.parts:
            raise _manifest_error(
                manifest_path, line_number,
                'payload path may not contain "..": {!r}'.format(entry))

        relative_path = Path(*normalized.parts)
        if relative_path == _WINUI_PAYLOAD_MANIFEST:
            raise _manifest_error(
                manifest_path, line_number,
                'the payload manifest is included automatically')

        archive_key = relative_path.as_posix().casefold()
        if archive_key in seen:
            raise _manifest_error(
                manifest_path, line_number,
                'duplicate payload path: {!r}'.format(entry))
        seen.add(archive_key)

        candidate = (build_outputs / relative_path).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise _manifest_error(
                manifest_path, line_number,
                'payload path escapes the Chromium output root: {!r}'.format(entry)) from exc
        if not candidate.is_file():
            raise FileNotFoundError(
                '{}:{}: listed payload file does not exist: {}'.format(
                    manifest_path, line_number, candidate))
        payload_paths.append(relative_path)

    if not payload_paths:
        raise ValueError('{} does not list any payload files'.format(manifest_path))
    return (_WINUI_PAYLOAD_MANIFEST, *payload_paths)


def _merge_archive_paths(primary_paths, supplemental_paths):
    """Yield archive paths once, using Windows case-insensitive semantics."""
    seen = set()
    for relative_path in chain(primary_paths, supplemental_paths):
        archive_key = relative_path.as_posix().casefold()
        if archive_key in seen:
            continue
        seen.add(archive_key)
        yield relative_path


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

    version = get_chromium_version()
    release_revision = _get_release_revision()
    packaging_revision = _get_packaging_revision()
    target_cpu = _get_target_cpu(build_outputs)

    shutil.copyfile(
        build_outputs / 'mini_installer.exe',
        build_root / _artifact_filename(
            'installer', version, release_revision, packaging_revision, target_cpu))

    timestamp = None
    try:
        with open(source_root / 'build' / 'util' / 'LASTCHANGE.committime', 'r') as ct:
            timestamp = int(ct.read())
    except FileNotFoundError:
        pass

    output = build_root / _artifact_filename(
        'archive', version, release_revision, packaging_revision, target_cpu)

    excluded_files = set([
        Path('mini_installer.exe'),
        Path('mini_installer_exe_version.rc'),
        Path('setup.exe'),
        Path('chrome.packed.7z'),
    ])
    files_generator = filescfg.filescfg_generator(
        source_root / 'chrome' / 'tools' / 'build' / 'win' / 'FILES.cfg',
        build_outputs, args.cpu_arch, excluded_files)
    winui_payload_paths = _winui_payload_paths(build_outputs)
    archive_paths = _merge_archive_paths(files_generator, winui_payload_paths)
    filescfg.create_archive(
        archive_paths, (_PORTABLE_CONFIGURATION,), build_outputs, output, timestamp)

if __name__ == '__main__':
    main()
