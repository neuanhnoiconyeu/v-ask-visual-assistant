"""Filesystem safety and proposal lifecycle tests using isolated temporary projects."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from patch_applier import (
    MAX_PATCH_CHARS,
    ProposalState,
    apply_proposal,
    build_change_proposal,
    reject_proposal,
)
from workspace_reader import WorkspaceError, index_workspace, validate_workspace_target


class PatchApplierTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.root = Path(self.temp_dir.name) / "project"
        self.root.mkdir()
        self.source = self.root / "app.py"
        self.source.write_text(
            "def calculate(x):\n    return x\n\n# keep this unrelated code\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def _proposal(self, entries, *, explanation="Update the requested behavior.", allowed=None):
        response = json.dumps({
            "schema_version": 1,
            "explanation": explanation,
            "files": entries,
        })
        index = index_workspace(self.root)
        return build_change_proposal(
            index, "Update the code", response,
            set(allowed if allowed is not None else {"app.py"}),
        )

    @staticmethod
    def _entry(path="app.py", patch=None, reason="Apply the requested fix."):
        if patch is None:
            patch = (
                "@@ -1,3 +1,3 @@\n"
                " def calculate(x):\n"
                "-    return x\n"
                "+    return x + 1\n"
                " \n"
            )
        return {"path": path, "reason": reason, "patch": patch}

    def test_modifies_only_reviewed_lines_and_preserves_unrelated_content(self):
        proposal = self._proposal([self._entry()])
        result = apply_proposal(proposal, self.root)
        self.assertEqual(result[0]["status"], "Applied")
        self.assertEqual(
            self.source.read_text(encoding="utf-8"),
            "def calculate(x):\n    return x + 1\n\n# keep this unrelated code\n",
        )
        self.assertEqual(proposal.state, ProposalState.APPLIED)

    def test_creates_new_file_atomically(self):
        patch = "@@ -0,0 +1,2 @@\n+def helper():\n+    return True\n"
        (self.root / "tests").mkdir()
        proposal = self._proposal(
            [self._entry("tests/test_helper.py", patch)], allowed=set()
        )
        result = apply_proposal(proposal, self.root)
        created = self.root / "tests" / "test_helper.py"
        self.assertEqual(result[0]["status"], "Applied")
        self.assertEqual(created.read_text(encoding="utf-8"), "def helper():\n    return True\n")

    def test_rejects_paths_outside_workspace_and_forbidden_files(self):
        for path in ("../outside.py", str(self.root.parent / "outside.py"), ".env", "secrets/id_rsa"):
            with self.subTest(path=path), self.assertRaises((ValueError, WorkspaceError)):
                validate_workspace_target(self.root, path, allow_create=True)

    def test_rejects_symlink_target(self):
        outside = self.root.parent / "outside.py"
        outside.write_text("outside", encoding="utf-8")
        link = self.root / "linked.py"
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("This Windows environment does not permit creating test symlinks.")
        with self.assertRaises(WorkspaceError):
            validate_workspace_target(self.root, "linked.py", allow_create=True)

    def test_detects_change_after_proposal_generation(self):
        proposal = self._proposal([self._entry()])
        self.source.write_text("def calculate(x):\n    return x * 4\n", encoding="utf-8")
        result = apply_proposal(proposal, self.root)
        self.assertEqual(result[0]["status"], "Conflict")
        self.assertIn("changed", result[0]["detail"].casefold())
        self.assertIn("x * 4", self.source.read_text(encoding="utf-8"))
        self.assertEqual(proposal.state, ProposalState.CONFLICT)

    def test_rejects_malformed_oversized_and_duplicate_proposals(self):
        index = index_workspace(self.root)
        with self.assertRaisesRegex(ValueError, "invalid proposal JSON"):
            build_change_proposal(index, "fix", "not json", {"app.py"})
        with self.assertRaisesRegex(ValueError, "duplicate JSON fields"):
            build_change_proposal(
                index, "fix",
                '{"schema_version":1,"schema_version":1,"explanation":"x","files":[]}',
                {"app.py"},
            )
        with self.assertRaises(ValueError):
            self._proposal([self._entry(patch="x" * (MAX_PATCH_CHARS + 1))])
        entry = self._entry()
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self._proposal([entry, dict(entry)])
        too_many = [self._entry(f"new_{i}.py", "@@ -0,0 +1,1 @@\n+x\n") for i in range(6)]
        with self.assertRaisesRegex(ValueError, "between 1 and"):
            self._proposal(too_many, allowed=set())

    def test_rejection_does_not_change_any_file(self):
        before = self.source.read_bytes()
        proposal = self._proposal([self._entry()])
        reject_proposal(proposal)
        self.assertEqual(proposal.state, ProposalState.REJECTED)
        self.assertEqual(self.source.read_bytes(), before)

    def test_prevents_applying_a_proposal_twice(self):
        proposal = self._proposal([self._entry()])
        apply_proposal(proposal, self.root)
        with self.assertRaisesRegex(ValueError, "cannot be applied again"):
            apply_proposal(proposal, self.root)

    def test_generates_readable_unified_diff(self):
        proposal = self._proposal([self._entry()])
        diff = proposal.files[0].diff
        self.assertIn("--- a/app.py", diff)
        self.assertIn("+++ b/app.py", diff)
        self.assertIn("-    return x", diff)
        self.assertIn("+    return x + 1", diff)

    def test_reports_precise_partial_failure_for_multiple_files(self):
        second = self.root / "other.py"
        second.write_text("def other():\n    return 2\n", encoding="utf-8")
        index = index_workspace(self.root)
        response = json.dumps({
            "schema_version": 1,
            "explanation": "Two edits",
            "files": [
                self._entry("app.py"),
                self._entry(
                    "other.py",
                    "@@ -1,2 +1,2 @@\n def other():\n-    return 2\n+    return 3\n",
                ),
            ],
        })
        proposal = build_change_proposal(index, "Change both", response, {"app.py", "other.py"})
        second.write_text("def other():\n    return 99\n", encoding="utf-8")
        results = apply_proposal(proposal, self.root)
        self.assertEqual([entry["status"] for entry in results], ["Applied", "Conflict"])
        self.assertEqual(proposal.state, ProposalState.PARTIAL)
        self.assertIn("return x + 1", self.source.read_text(encoding="utf-8"))
        self.assertIn("return 99", second.read_text(encoding="utf-8"))

    def test_diff_patch_rejects_bad_ranges_and_nonmatching_context(self):
        with self.assertRaisesRegex(ValueError, "line counts"):
            self._proposal([self._entry(patch="@@ -1,3 +1,3 @@\n wrong\n")])
        with self.assertRaisesRegex(ValueError, "does not match"):
            self._proposal([self._entry(patch="@@ -1 +1 @@\n-wrong\n+fixed\n")])
        with self.assertRaisesRegex(ValueError, "new-file hunk ranges"):
            self._proposal([self._entry(patch=(
                "@@ -1 +99 @@\n-def calculate(x):\n+def calculate(y):\n"
            ))])

    def test_preserves_crlf_line_endings(self):
        self.source.write_bytes(
            b"def calculate(x):\r\n    return x\r\n\r\n# keep this unrelated code\r\n"
        )
        proposal = self._proposal([self._entry()])
        apply_proposal(proposal, self.root)
        self.assertIn(b"\r\n", self.source.read_bytes())
        self.assertNotIn(b"\n", self.source.read_bytes().replace(b"\r\n", b""))


if __name__ == "__main__":
    unittest.main()
