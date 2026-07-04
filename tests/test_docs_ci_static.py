from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DocsCiStaticTests(unittest.TestCase):
    def test_ci_workflow_exists_for_alpha_checks(self):
        workflow = ROOT / ".github" / "workflows" / "ci.yml"

        self.assertTrue(workflow.exists())
        content = workflow.read_text(encoding="utf-8")
        self.assertIn("python -m unittest discover -s tests", content)
        self.assertIn("node --check static/js/main.js", content)

    def test_readme_and_context_match_current_alpha(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        context = (ROOT / "context.md").read_text(encoding="utf-8")

        self.assertIn("v0.1.0-alpha", readme)
        self.assertIn("operator PIN", readme)
        self.assertIn("mobile operator dashboard", readme)
        self.assertIn("Quick Setup Wizard", context)
        self.assertNotIn("test output", context.lower())


if __name__ == "__main__":
    unittest.main()
