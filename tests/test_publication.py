import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.check_publication import check, export, public_path
from tools.output_paths import new_output_directory


class PublicationTests(unittest.TestCase):
    def make_package(self, root):
        data = b'# Minimal public fixture\n'
        (root / 'README.md').write_bytes(data)
        (root / 'PUBLISH_MANIFEST.json').write_text(json.dumps({'files': {
            'README.md': {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
        }}), encoding='utf-8')

    def test_unlisted_file_cannot_be_exported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'source'; root.mkdir(); self.make_package(root)
            (root / 'private.env').write_text('private fixture', encoding='utf-8')
            self.assertFalse(check(root)['passed'])
            target = Path(tmp) / 'release'
            with self.assertRaises(ValueError): export(root, target)
            self.assertFalse(target.exists())

    def test_changed_content_rejected_and_clean_export_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'source'; root.mkdir(); self.make_package(root)
            target = Path(tmp) / 'release'
            export(root, target)
            self.assertTrue(check(target)['passed'])
            (root / 'README.md').write_text('changed', encoding='utf-8')
            self.assertFalse(check(root)['passed'])

    def test_paths_cannot_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            for path in ('../private.txt', '/private.txt', 'C:/private.txt', 'x\\y'):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    public_path(Path(tmp), path)

    def test_source_change_between_check_and_copy_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'source'; root.mkdir(); self.make_package(root)
            target = Path(tmp) / 'release'
            def change_after_check(path, manifest=None):
                report = check(path, manifest)
                (root / 'README.md').write_text('changed during export', encoding='utf-8')
                return report
            with patch('tools.check_publication.check', side_effect=change_after_check):
                with self.assertRaises(ValueError): export(root, target)
            self.assertFalse((target / 'PUBLISH_MANIFEST.json').exists())

    def test_outputs_cannot_overwrite_frozen_or_existing_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(ValueError):
                new_output_directory(root / 'samples' / 'new', roots=(root,))
            out = new_output_directory(root / 'generated' / 'new', roots=(root,))
            with self.assertRaises(ValueError):
                new_output_directory(out, roots=(root,))
