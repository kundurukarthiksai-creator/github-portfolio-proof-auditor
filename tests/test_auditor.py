import unittest
import json

from github_proof_auditor.auditor import (
    RepoAudit,
    add_finding,
    audit_to_dict,
    detect_blocked_patterns,
    detect_positive_signals,
    evaluate_readme_links,
    extract_http_links,
    is_profile_repo,
    render_json,
    render_markdown,
)
from github_proof_auditor.cli import DEFAULT_REPOS, load_config


class PatternTests(unittest.TestCase):
    def test_detects_blocked_public_terms(self) -> None:
        text = "See C:\\Users\\karthik\\secret and do not mention sponsorship."
        labels = detect_blocked_patterns(text)
        self.assertIn("local Windows path", labels)
        self.assertIn("visa/status wording", labels)

    def test_opt_in_does_not_trigger_work_authorization_acronym(self) -> None:
        self.assertNotIn("work authorization acronym", detect_blocked_patterns("README link checks are opt-in."))
        self.assertIn("work authorization acronym", detect_blocked_patterns("Do not publish OPT wording."))

    def test_detects_positive_readme_signals(self) -> None:
        readme = "GitHub Actions CI runs smoke tests. Honest Limits. Live demo included."
        signals = detect_positive_signals(readme)
        self.assertEqual(signals, ["ci", "tests", "limits", "demo"])

    def test_extract_http_links_ignores_relative_and_duplicate_links(self) -> None:
        readme = (
            "[Repo](https://github.com/owner/repo) "
            "![Badge](https://img.shields.io/badge/test-pass-green) "
            "[Relative](docs/setup.md) "
            "[Mail](mailto:test@example.com) "
            "[Repo again](https://github.com/owner/repo)"
        )
        self.assertEqual(
            extract_http_links(readme),
            [
                "https://github.com/owner/repo",
                "https://img.shields.io/badge/test-pass-green",
            ],
        )


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

    def test_audit_to_dict_includes_readme_link_checks(self) -> None:
        audit = RepoAudit(repo="owner/repo")
        evaluate_readme_links(audit, "[Good](https://example.test/good)", checker=lambda _url: "200")
        data = audit_to_dict(audit)
        self.assertEqual(
            data["readme_link_checks"],
            [{"url": "https://example.test/good", "status": "200"}],
        )

    def test_readme_link_checks_warn_on_non_200(self) -> None:
        audit = RepoAudit(repo="owner/repo")
        statuses = {
            "https://example.test/good": "200",
            "https://example.test/missing": "404",
        }
        readme = "[Good](https://example.test/good) [Missing](https://example.test/missing)"
        evaluate_readme_links(audit, readme, checker=lambda url: statuses[url])
        self.assertEqual(len(audit.readme_link_checks), 2)
        self.assertEqual(audit.readme_link_checks[0].status, "200")
        self.assertEqual(audit.readme_link_checks[1].status, "404")
        self.assertEqual(audit.findings[0].severity, "warn")
        self.assertIn("README link returned 404", audit.findings[0].message)


class ConfigTests(unittest.TestCase):
    def test_default_repos_include_public_proof_projects(self) -> None:
        self.assertIn("kundurukarthiksai-creator/mcp-tool-safety-lab", DEFAULT_REPOS)
        self.assertIn("kundurukarthiksai-creator/github-portfolio-proof-auditor", DEFAULT_REPOS)
        self.assertIn("kundurukarthiksai-creator/agent-reliability-tool-use-eval-lab", DEFAULT_REPOS)
        self.assertEqual(len(DEFAULT_REPOS), 8)

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
