"""Safety and hierarchy tests for managed uploaded-project imports."""
from __future__ import annotations

import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import project_importer
from project_importer import (
    ProjectImportError,
    import_project_folder,
    import_project_zip,
    list_imported_projects,
    remove_imported_project,
)
from workspace_reader import index_workspace


class ProjectImporterTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.data_dir = Path(self.temp_dir.name) / "data"
        self.data_patch = patch.object(project_importer, "DATA_DIR", self.data_dir)
        self.data_patch.start()

    def tearDown(self):
        self.data_patch.stop()
        self.temp_dir.cleanup()

    @staticmethod
    def _zip(entries: dict[str, bytes]) -> bytes:
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, content in entries.items():
                archive.writestr(name, content)
        return output.getvalue()

    def test_folder_import_preserves_nested_paths_without_duplicate_top_level(self):
        project = import_project_folder([
            ("my-project/src/main.py", b"def run():\n    return True\n"),
            ("my-project/tests/test_main.py", b"def test_run():\n    assert True\n"),
            ("my-project/README.md", b"# Project\n"),
        ], name="my-project")

        self.assertTrue((project.root / "src" / "main.py").is_file())
        self.assertFalse((project.root / "my-project").exists())
        indexed = index_workspace(project.root)
        self.assertEqual(
            {file.relative_path for file in indexed.files},
            {"src/main.py", "tests/test_main.py", "README.md"},
        )

    def test_zip_import_handles_archives_with_and_without_a_top_level_folder(self):
        nested = import_project_zip("nested.zip", self._zip({"repo/src/app.py": b"value = 1\n"}))
        flat = import_project_zip("flat.zip", self._zip({"src/app.py": b"value = 2\n"}))

        self.assertTrue((nested.root / "src" / "app.py").is_file())
        self.assertTrue((flat.root / "src" / "app.py").is_file())
        self.assertFalse((flat.root / "app.py").exists())

    def test_rejects_zip_path_traversal_and_malformed_archives(self):
        traversal = self._zip({"../outside.py": b"bad"})
        with self.assertRaises(ProjectImportError):
            import_project_zip("unsafe.zip", traversal)
        with self.assertRaises(ProjectImportError):
            import_project_zip("broken.zip", b"not a zip archive")
        self.assertEqual(list_imported_projects(), ())

    def test_import_limits_and_sensitive_generated_files_are_handled_safely(self):
        with patch.object(project_importer, "MAX_PROJECT_IMPORT_FILES", 1):
            with self.assertRaises(ProjectImportError):
                import_project_folder([("a.py", b"a = 1"), ("b.py", b"b = 2")])

        project = import_project_folder([
            ("repo/.git/config", b"ignored"),
            ("repo/.env", b"API_KEY=not-stored"),
            ("repo/node_modules/pkg/index.js", b"ignored"),
            ("repo/src/app.py", b"safe = True\n"),
        ])
        self.assertEqual(project.imported_files, 1)
        self.assertEqual(project.skipped_files, 3)
        self.assertTrue((project.root / "src" / "app.py").is_file())
        self.assertFalse((project.root / ".env").exists())

    def test_imported_projects_are_isolated_and_removable(self):
        first = import_project_folder([("first.py", b"first = 1\n")], name="first")
        second = import_project_folder([("second.py", b"second = 2\n")], name="second")

        self.assertNotEqual(first.root, second.root)
        self.assertEqual({item.project_id for item in list_imported_projects()}, {first.project_id, second.project_id})
        remove_imported_project(first.project_id)
        self.assertFalse(first.root.exists())
        self.assertTrue(second.root.exists())
        self.assertEqual([item.project_id for item in list_imported_projects()], [second.project_id])


if __name__ == "__main__":
    unittest.main()
