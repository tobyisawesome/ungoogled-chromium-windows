#!/usr/bin/env python3

import io
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
import zipfile

import package as windows_package


class ArtifactFilenameTests(unittest.TestCase):

    def test_curve_browser_artifact_names_retain_upstream_shape(self):
        values = ('150.0.7871.114', '1', '3', 'x64')
        self.assertEqual(
            'curve-browser_150.0.7871.114-1.3_installer_x64.exe',
            windows_package._artifact_filename('installer', *values))
        self.assertEqual(
            'curve-browser_150.0.7871.114-1.3_windows_x64.zip',
            windows_package._artifact_filename('archive', *values))


class WinuiPayloadManifestTests(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.outputs = Path(self.temp_dir.name)
        (self.outputs / 'chrome.exe').touch()
        self.manifest = self.outputs / windows_package._WINUI_PAYLOAD_MANIFEST

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write_payload(self, relative_path):
        payload_path = self.outputs / Path(*_native_manifest_path(relative_path).parts)
        payload_path.parent.mkdir(parents=True, exist_ok=True)
        payload_path.touch()

    def test_missing_manifest_is_a_clear_pristine_baseline_fallback(self):
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = windows_package._winui_payload_paths(self.outputs)
        self.assertEqual(tuple(), result)
        self.assertIn('pristine Chromium baseline', stderr.getvalue())

    def test_manifest_and_listed_payload_are_archived(self):
        self._write_payload('curve_browser_shell.dll')
        self._write_payload('WinUI/Microsoft.UI.Xaml.dll')
        self.manifest.write_text(
            '# WinUI self-contained payload\n'
            'curve_browser_shell.dll\n'
            'WinUI\\Microsoft.UI.Xaml.dll\n',
            encoding='utf-8')

        self.assertEqual(
            (
                Path('curve_browser_payload_manifest.txt'),
                Path('curve_browser_shell.dll'),
                Path('WinUI/Microsoft.UI.Xaml.dll'),
            ),
            windows_package._winui_payload_paths(self.outputs))

    def test_msbuild_utf8_bom_is_accepted(self):
        self._write_payload('curve_browser_shell.dll')
        self.manifest.write_text(
            'curve_browser_shell.dll\n', encoding='utf-8-sig')
        self.assertEqual(
            (
                Path('curve_browser_payload_manifest.txt'),
                Path('curve_browser_shell.dll'),
            ),
            windows_package._winui_payload_paths(self.outputs))

    def test_unsafe_paths_are_rejected(self):
        for entry in ('C:\\payload.dll', '/payload.dll', '..\\payload.dll',
                      'WinUI/../payload.dll'):
            with self.subTest(entry=entry):
                self.manifest.write_text(entry + '\n', encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'relative|drive-free|may not contain'):
                    windows_package._winui_payload_paths(self.outputs)

    def test_duplicate_paths_are_rejected_case_insensitively(self):
        self._write_payload('WinUI/Microsoft.UI.Xaml.dll')
        self.manifest.write_text(
            'WinUI/Microsoft.UI.Xaml.dll\n'
            'winui\\microsoft.ui.xaml.dll\n',
            encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'duplicate payload path'):
            windows_package._winui_payload_paths(self.outputs)

    def test_missing_listed_file_is_fatal(self):
        self.manifest.write_text('missing.dll\n', encoding='utf-8')
        with self.assertRaisesRegex(FileNotFoundError, 'listed payload file does not exist'):
            windows_package._winui_payload_paths(self.outputs)

    def test_empty_manifest_is_fatal(self):
        self.manifest.write_text('# no payload\n\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'does not list any payload files'):
            windows_package._winui_payload_paths(self.outputs)

    def test_manifest_path_must_be_a_regular_file(self):
        self.manifest.mkdir()
        with self.assertRaisesRegex(ValueError, 'regular UTF-8 text file'):
            windows_package._winui_payload_paths(self.outputs)

    def test_payload_manifest_and_portable_marker_land_in_zip_root(self):
        self._write_payload('curve_browser_shell.dll')
        self.manifest.write_text('curve_browser_shell.dll\n', encoding='utf-8')
        archive_path = self.outputs / 'curve-browser_test.zip'
        archive_paths = windows_package._merge_archive_paths(
            (Path('chrome.exe'),), windows_package._winui_payload_paths(self.outputs))

        windows_package.filescfg.create_archive(
            archive_paths, (windows_package._PORTABLE_CONFIGURATION,),
            self.outputs, archive_path)

        with zipfile.ZipFile(archive_path) as archive:
            self.assertEqual(
                {
                    'curve-browser_test/chrome.exe',
                    'curve-browser_test/curve_browser_payload_manifest.txt',
                    'curve-browser_test/curve_browser_shell.dll',
                    'curve-browser_test/portable.ini',
                },
                set(archive.namelist()))
            portable_config = archive.read(
                'curve-browser_test/portable.ini').decode('utf-8')
        self.assertIn('UserDataDirectory=User Data', portable_config)


class ArchivePathTests(unittest.TestCase):

    def test_supplemental_paths_do_not_duplicate_files_cfg_entries(self):
        result = tuple(windows_package._merge_archive_paths(
            (Path('chrome.exe'), Path('WinUI/Microsoft.UI.Xaml.dll')),
            (Path('winui/microsoft.ui.xaml.dll'), Path('curve_browser_shell.dll'))))
        self.assertEqual(
            (Path('chrome.exe'), Path('WinUI/Microsoft.UI.Xaml.dll'),
             Path('curve_browser_shell.dll')),
            result)


def _native_manifest_path(value):
    """Convert either manifest separator style into a native test path."""
    return Path(value.replace('\\', '/'))


if __name__ == '__main__':
    unittest.main()
