import tempfile
import unittest
from pathlib import Path
from build_metadata import metadata

class BuildMetadataTests(unittest.TestCase):
    def test_detached_and_branch_refs(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);sha='a'*40
            (root/'HEAD').write_text(sha)
            self.assertEqual(metadata(root)['revision'],sha)
            (root/'HEAD').write_text('ref: refs/heads/main')
            (root/'refs/heads').mkdir(parents=True)
            (root/'refs/heads/main').write_text(sha)
            self.assertEqual(metadata(root)['revision'],sha)
            (root/'refs/heads/main').unlink()
            (root/'packed-refs').write_text(sha+' refs/heads/main\n')
            self.assertEqual(metadata(root)['revision'],sha)
