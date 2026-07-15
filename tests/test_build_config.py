#!/usr/bin/env python3

import sys
import tempfile
import unittest
from pathlib import Path

import build as windows_build


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'ungoogled-chromium' / 'utils'))
import downloads  # pylint: disable=wrong-import-position
sys.path.pop(0)


class BundledUblockOriginTests(unittest.TestCase):

    def setUp(self):
        self.info = downloads.DownloadInfo([ROOT / 'downloads.ini'])
        self.ublock = self.info['ublock-origin']

    def test_official_web_store_crx_is_pinned(self):
        self.assertEqual('ublock-origin-1.72.2.crx',
                         self.ublock.download_filename)
        self.assertEqual(
            '6e02d8e6dce569eec721b531f9c7d28403e5426442417d5a855a17dd288b56f8',
            self.ublock.hashes['sha256'])
        self.assertIn('id%3Dcjpalhdlnbpafiamejdnhcphjbkeiagm%26uc',
                      self.ublock.url)

    def test_staging_constants_match_download(self):
        self.assertEqual(self.ublock.download_filename,
                         windows_build._UBLOCK_ORIGIN_DOWNLOAD)
        self.assertEqual(
            Path('chrome/browser/extensions/default_extensions/ublock_origin.crx'),
            windows_build._UBLOCK_ORIGIN_DESTINATION)

    def test_chromium_patch_uses_same_id_and_version(self):
        patch_path = (ROOT / 'ungoogled-chromium' / 'patches' / 'extra' /
                      'curve-browser' / 'bundle-ublock-origin.patch')
        patch_text = patch_path.read_text(encoding='utf-8')
        self.assertIn('cjpalhdlnbpafiamejdnhcphjbkeiagm', patch_text)
        self.assertIn(
            '"external_version": "{}"'.format(
                windows_build._UBLOCK_ORIGIN_VERSION), patch_text)


class WinuiBuildStagingTests(unittest.TestCase):

    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.shell_output = self.root / 'shell'
        self.build_outputs = self.root / 'chromium'
        self.shell_output.mkdir()

    def tearDown(self):
        self.temporary_directory.cleanup()

    def _write_payload(self, relative, content=b'payload'):
        path = self.shell_output / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def _write_manifest(self, text):
        (self.shell_output / windows_build._WINUI_PAYLOAD_MANIFEST).write_text(
            text, encoding='utf-8-sig')

    def test_stages_nested_self_contained_payload_and_manifest(self):
        self._write_payload('curve_browser_shell.dll')
        self._write_payload('en-US/Microsoft.ui.xaml.dll.mui')
        self._write_payload('Microsoft.UI.Xaml/Assets/map.html')
        self._write_manifest(
            'curve_browser_shell.dll\n'
            'en-US\\Microsoft.ui.xaml.dll.mui\n'
            'Microsoft.UI.Xaml\\Assets\\map.html\n')

        paths = windows_build._stage_winui_payload(
            self.shell_output, self.build_outputs)

        self.assertEqual(3, len(paths))
        self.assertEqual(
            b'payload',
            (self.build_outputs / 'en-US' /
             'Microsoft.ui.xaml.dll.mui').read_bytes())
        self.assertTrue(
            (self.build_outputs /
             windows_build._WINUI_PAYLOAD_MANIFEST).is_file())

    def test_rejects_unsafe_or_duplicate_manifest_entries(self):
        self._write_payload('curve_browser_shell.dll')
        for manifest in (
                '../curve_browser_shell.dll\n',
                'curve_browser_shell.dll\nCURVE_BROWSER_SHELL.DLL\n'):
            with self.subTest(manifest=manifest):
                self._write_manifest(manifest)
                with self.assertRaises(ValueError):
                    windows_build._winui_payload_paths(self.shell_output)

    def test_missing_payload_is_fatal(self):
        self._write_manifest('curve_browser_shell.dll\n')
        with self.assertRaises(FileNotFoundError):
            windows_build._stage_winui_payload(
                self.shell_output, self.build_outputs)


if __name__ == '__main__':
    unittest.main()
