#!/usr/bin/env python3

import sys
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


if __name__ == '__main__':
    unittest.main()
