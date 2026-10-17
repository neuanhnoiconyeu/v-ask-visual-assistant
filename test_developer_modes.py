"""Focused tests for developer mode request construction."""
import unittest

from developer_modes import MODE_INSTRUCTIONS, build_developer_request


class DeveloperModeTests(unittest.TestCase):
    def test_all_requested_modes_have_independent_instructions(self):
        modes = ("Explain Code", "Debug Assistant", "Code Review", "Generate Tests")
        self.assertTrue(all(MODE_INSTRUCTIONS[mode] for mode in modes))
        self.assertEqual(len({MODE_INSTRUCTIONS[mode] for mode in modes}), len(modes))

    def test_request_includes_each_supplied_input(self):
        request = build_developer_request(
            "Find the bug", "print('hello')", "NameError: x", "Python 3.12"
        )
        self.assertIn("Find the bug", request)
        self.assertIn("```\nprint('hello')\n```", request)
        self.assertIn("NameError: x", request)
        self.assertIn("Python 3.12", request)

    def test_empty_fields_do_not_create_a_request(self):
        self.assertEqual(build_developer_request("  ", "\n", "", " "), "")


if __name__ == "__main__":
    unittest.main()
