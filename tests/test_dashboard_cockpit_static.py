from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DashboardCockpitStaticTests(unittest.TestCase):
    def test_dashboard_template_uses_operator_cockpit_structure(self):
        template = (ROOT / "templates" / "dashboard.html").read_text(encoding="utf-8")

        self.assertIn('class="dashboard-cockpit"', template)
        self.assertIn('id="dashboard-controller-status"', template)
        self.assertIn('id="dashboard-mode-status"', template)
        self.assertIn('id="dashboard-scheduler-status"', template)
        self.assertIn('id="dashboard-active-count"', template)
        self.assertIn('id="dashboard-active-runs"', template)
        self.assertIn('id="dashboard-output-empty"', template)
        self.assertIn('class="dashboard-primary-action"', template)
        self.assertNotIn('class="dashboard-hero"', template)

    def test_dashboard_javascript_renders_cockpit_runtime_data(self):
        script = (ROOT / "static" / "js" / "main.js").read_text(encoding="utf-8")

        self.assertIn('page === "dashboard"', script)
        self.assertIn('apiGet("/api/scheduler")', script)
        self.assertIn("renderDashboardActiveRuns", script)
        self.assertIn("dashboardSchedulerText", script)
        self.assertIn("dashboardTileSummary", script)
        self.assertIn("pendingDashboardInputs", script)
        self.assertIn("dashboard-trigger-disabled", script)
        self.assertIn("dashboard-output-on", script)

    def test_dashboard_css_has_mobile_cockpit_layout(self):
        stylesheet = (ROOT / "static" / "css" / "style.css").read_text(encoding="utf-8")

        self.assertIn(".dashboard-cockpit", stylesheet)
        self.assertIn(".cockpit-card", stylesheet)
        self.assertIn(".active-run-card", stylesheet)
        self.assertIn(".dashboard-trigger-badges", stylesheet)
        self.assertIn(".dashboard-output-on", stylesheet)
        self.assertIn("body[data-page=\"dashboard\"] .content-shell", stylesheet)


if __name__ == "__main__":
    unittest.main()
