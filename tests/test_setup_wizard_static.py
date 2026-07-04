from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SetupWizardStaticTests(unittest.TestCase):
    def test_setup_template_uses_quick_wizard_structure(self):
        template = (ROOT / "templates" / "setup.html").read_text(encoding="utf-8")

        self.assertIn('class="setup-progress"', template)
        self.assertIn('data-setup-step="controller"', template)
        self.assertIn('data-setup-step="outputs"', template)
        self.assertIn('data-setup-step="inputs"', template)
        self.assertIn('data-setup-step="review"', template)
        self.assertIn('data-action="setup-next"', template)
        self.assertIn('data-action="setup-back"', template)
        self.assertIn('id="setup-review-list"', template)
        self.assertNotIn('id="setup-test-output"', template)
        self.assertNotIn('id="setup-test-output-select"', template)

    def test_setup_javascript_manages_wizard_state(self):
        script = (ROOT / "static" / "js" / "main.js").read_text(encoding="utf-8")

        self.assertIn("setupWizardSteps", script)
        self.assertIn("setupWizardStep", script)
        self.assertIn("goToSetupStep", script)
        self.assertIn("updateSetupWizardNav", script)
        self.assertIn("renderSetupReview", script)
        self.assertIn('window.location.href = "/"', script)
        self.assertNotIn("#setup-test-output", script)
        self.assertNotIn("#setup-test-output-select", script)

    def test_setup_css_has_wizard_layout(self):
        stylesheet = (ROOT / "static" / "css" / "style.css").read_text(encoding="utf-8")

        self.assertIn(".setup-progress", stylesheet)
        self.assertIn(".setup-wizard-step", stylesheet)
        self.assertIn(".setup-wizard-step.active", stylesheet)
        self.assertIn(".setup-review-list", stylesheet)


if __name__ == "__main__":
    unittest.main()
