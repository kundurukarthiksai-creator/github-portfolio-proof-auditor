import unittest
import json

from github_proof_auditor.auditor import (
    RepoAudit,
    add_finding,
    audit_to_dict,
    detect_blocked_patterns,
    detect_positive_signals,
    is_profile_repo,
    render_json,
    render_markdown,
)
from github_proof_auditor.cli import load_config


class PatternTests(unittest.TestCase):
    def test_detects_blocked_public_terms(self) -> None:
        text = "See C:\\Users\\karthik\\secret and do not mention sponsorship."
        labels = detect_blocked_patterns(text)
        self.assertIn("local Windows path", labels)
        self.assertIn("visa/status wording", labels)

    def test_detects_positive_readme_signals(self) -> None:
        readme = "GitHub Actions CI runs smoke tests. Honest Limits. Live demo included."
        signals = detect_positive_signals(readme)
        self.assertEqual(signals, ["ci", "tests", "limits", "demo"])


class AuditModelTests(unittest.TestCase):
    def test_profile_repo_detection(self) -> None:
        self.assertTrue(is_profile_repo("octocat/octocat"))
        self.assertFalse(is_profile_repo("octocat/hello-world"))

    def test_score_and_status(self) -> None:
        audit = RepoAudit(repo="owner/repo")
        add_finding(audit, "warn", "Missing thing.")
        add_finding(audit, "info", "Polish thing.")
        self.assertEqual(audit.score, 87)
        self.assertEqual(audit.status, "Watch")

    def test_fail_status_wins(self) -> None:
        audit = RepoAudit(repo="owner/repo")
        add_finding(audit, "fail", "Bad thing.")
        add_finding(audit, "warn", "Missing thing.")
        self.assertEqual(audit.status, "Needs fix")


class RenderTests(unittest.TestCase):
    def test_render_markdown_includes_summary_and_findings(self) -> None:
        audit = RepoAudit(
            repo="owner/repo",
            url="https://github.com/owner/repo",
            description="A test repo",
            readme_chars=1200,
            readme_signals=["ci", "tests", "limits"],
        )
        add_finding(audit, "warn", "No demo.")
        report = render_markdown([audit])
        self.assertIn("GitHub Proof Auditor Report", report)
        self.assertIn("| [owner/repo](https://github.com/owner/repo) | 90 | Watch |", report)
        self.assertIn("[WARN] No demo.", report)

    def test_render_json_includes_summary_and_structured_findings(self) -> None:
        audit = RepoAudit(
            repo="owner/repo",
            url="https://github.com/owner/repo",
            description="A test repo",
            readme_chars=1200,
            readme_signals=["ci", "tests", "limits"],
        )
        add_finding(audit, "warn", "No demo.")
        payload = json.loads(render_json([audit]))
        self.assertEqual(payload["summary"]["repo_count"], 1)
        self.assertEqual(payload["summary"]["watch"], 1)
        self.assertEqual(payload["audits"][0]["repo"], "owner/repo")
        self.assertEqual(payload["audits"][0]["score"], 90)
        self.assertEqual(payload["audits"][0]["findings"][0]["message"], "No demo.")

    def test_audit_to_dict_keeps_latest_run_subset(self) -> None:
        audit = RepoAudit(
            repo="owner/repo",
            latest_run={
                "name": "CI",
                "status": "completed",
                "conclusion": "success",
                "html_url": "https://example.test/run",
                "extra": "not exported",
            },
        )
        data = audit_to_dict(audit)
        self.assertEqual(
            data["latest_run"],
            {
                "name": "CI",
                "status": "completed",
                "conclusion": "success",
                "url": "https://example.test/run",
            },
        )


class ConfigTests(unittest.TestCase):
    def test_load_config(self) -> None:
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text('{"repos": ["owner/repo"]}', encoding="utf-8")
            self.assertEqual(load_config(path), ["owner/repo"])

    def test_rejects_invalid_config(self) -> None:
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text('{"repos": "owner/repo"}', encoding="utf-8")
            with self.assertRaises(ValueError):
                load_config(path)


if __name__ == "__main__":
    unittest.main()
