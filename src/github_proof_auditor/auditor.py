from __future__ import annotations

import base64
import json
import re
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


BLOCKED_PATTERNS = [
    ("local Windows path", re.compile(r"\b[A-Z]:\\", re.IGNORECASE)),
    ("visa/status wording", re.compile(r"\b(H-1B|H1B|F-1|OPT|STEM OPT|visa|sponsorship)\b", re.IGNORECASE)),
    ("overclaim: production ready", re.compile(r"\bproduction[- ]ready\b", re.IGNORECASE)),
    ("overclaim: fully production", re.compile(r"\bfully production\b", re.IGNORECASE)),
]

POSITIVE_README_SIGNALS = [
    ("ci", re.compile(r"\b(CI|GitHub Actions|workflow)\b", re.IGNORECASE)),
    ("tests", re.compile(r"\b(test|tests|pytest|smoke)\b", re.IGNORECASE)),
    ("limits", re.compile(r"\b(honest limits|known limits|limits|limitations|safety)\b", re.IGNORECASE)),
    ("demo", re.compile(r"\b(demo|pages|screenshot|walkthrough)\b", re.IGNORECASE)),
]


@dataclass
class Finding:
    severity: str
    message: str


@dataclass
class RepoAudit:
    repo: str
    url: str = ""
    description: str = ""
    homepage: str = ""
    default_branch: str = ""
    topics: list[str] = field(default_factory=list)
    latest_run: dict[str, Any] | None = None
    readme_chars: int = 0
    readme_signals: list[str] = field(default_factory=list)
    homepage_status: str = ""
    findings: list[Finding] = field(default_factory=list)

    @property
    def score(self) -> int:
        score = 100
        for finding in self.findings:
            if finding.severity == "fail":
                score -= 25
            elif finding.severity == "warn":
                score -= 10
            else:
                score -= 3
        return max(score, 0)

    @property
    def status(self) -> str:
        if any(f.severity == "fail" for f in self.findings):
            return "Needs fix"
        if any(f.severity == "warn" for f in self.findings):
            return "Watch"
        return "Good"


def is_profile_repo(owner_repo: str) -> bool:
    owner, _, name = owner_repo.partition("/")
    return bool(owner and name and owner.lower() == name.lower())


def add_finding(audit: RepoAudit, severity: str, message: str) -> None:
    audit.findings.append(Finding(severity=severity, message=message))


def detect_blocked_patterns(text: str) -> list[str]:
    return [label for label, pattern in BLOCKED_PATTERNS if pattern.search(text)]


def detect_positive_signals(readme: str) -> list[str]:
    return [label for label, pattern in POSITIVE_README_SIGNALS if pattern.search(readme)]


def run_json(args: list[str]) -> Any:
    result = subprocess.run(args, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return json.loads(result.stdout)


def gh_json(*args: str) -> Any:
    return run_json(["gh", *args])


def get_repo(owner_repo: str) -> dict[str, Any]:
    return gh_json(
        "repo",
        "view",
        owner_repo,
        "--json",
        "name,description,homepageUrl,isArchived,isFork,pushedAt,url,repositoryTopics,defaultBranchRef",
    )


def get_readme(owner_repo: str) -> str:
    data = gh_json("api", f"repos/{owner_repo}/readme")
    content = data.get("content", "")
    if not content:
        return ""
    return base64.b64decode(content).decode("utf-8", errors="replace")


def get_latest_run(owner_repo: str) -> dict[str, Any] | None:
    data = gh_json("api", f"repos/{owner_repo}/actions/runs?per_page=1")
    runs = data.get("workflow_runs", [])
    return runs[0] if runs else None


def check_url(url: str) -> str:
    if not url:
        return ""
    request = urllib.request.Request(url, method="GET", headers={"User-Agent": "github-proof-auditor"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return str(response.status)
    except urllib.error.HTTPError as exc:
        return str(exc.code)
    except Exception as exc:  # noqa: BLE001 - report diagnostics, do not crash audit.
        return f"error: {exc.__class__.__name__}"


def evaluate_repo_metadata(audit: RepoAudit, repo: dict[str, Any], profile_repo: bool) -> None:
    if repo.get("isArchived"):
        add_finding(audit, "fail", "Repository is archived.")
    if repo.get("isFork"):
        add_finding(audit, "warn", "Repository is a fork; only promote if contribution/story is clear.")
    if not audit.description.strip():
        add_finding(audit, "warn", "Missing repo description.")
    if len(audit.description) > 160:
        add_finding(audit, "info", "Description is long; repo cards scan better under 160 characters.")
    if len(audit.topics) < 3 and not profile_repo:
        add_finding(audit, "warn", "Fewer than 3 topics.")


def evaluate_readme(audit: RepoAudit, readme: str) -> None:
    audit.readme_chars = len(readme)
    if audit.readme_chars < 800:
        add_finding(audit, "warn", "README is short; may not give reviewers enough proof.")

    combined_public_text = f"{audit.description}\n{readme}"
    for label in detect_blocked_patterns(combined_public_text):
        add_finding(audit, "fail", f"Blocked public-surface pattern found: {label}.")

    audit.readme_signals = detect_positive_signals(readme)
    if "ci" not in audit.readme_signals:
        add_finding(audit, "warn", "README does not clearly mention CI/GitHub Actions.")
    if "tests" not in audit.readme_signals:
        add_finding(audit, "warn", "README does not clearly mention tests or smoke checks.")
    if "limits" not in audit.readme_signals:
        add_finding(audit, "warn", "README does not clearly mention limits/safety/honest scope.")


def audit_repo(owner_repo: str) -> RepoAudit:
    profile_repo = is_profile_repo(owner_repo)
    audit = RepoAudit(repo=owner_repo)

    repo = get_repo(owner_repo)
    audit.url = repo.get("url", "")
    audit.description = repo.get("description") or ""
    audit.homepage = repo.get("homepageUrl") or ""
    audit.default_branch = (repo.get("defaultBranchRef") or {}).get("name", "")
    audit.topics = [topic["name"] for topic in (repo.get("repositoryTopics") or []) if topic.get("name")]

    evaluate_repo_metadata(audit, repo, profile_repo)

    try:
        readme = get_readme(owner_repo)
    except RuntimeError as exc:
        readme = ""
        add_finding(audit, "fail", f"README could not be read: {exc}")

    evaluate_readme(audit, readme)

    try:
        audit.latest_run = get_latest_run(owner_repo)
    except RuntimeError as exc:
        audit.latest_run = None
        add_finding(audit, "warn", f"Could not read latest Actions run: {exc}")

    if audit.latest_run:
        conclusion = audit.latest_run.get("conclusion")
        status = audit.latest_run.get("status")
        if conclusion != "success":
            add_finding(audit, "warn", f"Latest Actions run is status={status}, conclusion={conclusion}.")
    elif not profile_repo:
        add_finding(audit, "warn", "No GitHub Actions runs found.")

    audit.homepage_status = check_url(audit.homepage)
    if audit.homepage and audit.homepage_status != "200":
        add_finding(audit, "warn", f"Homepage returned {audit.homepage_status}.")

    return audit


def render_markdown(audits: list[RepoAudit]) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines = [
        f"# GitHub Proof Auditor Report - {now}",
        "",
        "Purpose: check whether public repos have recruiter-facing proof that is easy to trust.",
        "",
        "This report is a surface audit, not a full code review.",
        "",
        "## Summary",
        "",
        "| Repo | Score | Status | Latest Actions | Homepage | Signals |",
        "| --- | ---: | --- | --- | --- | --- |",
    ]

    for audit in audits:
        if audit.latest_run:
            run_text = f"{audit.latest_run.get('status')}/{audit.latest_run.get('conclusion')}"
        else:
            run_text = "none"
        homepage = audit.homepage_status or "none"
        signals = ", ".join(audit.readme_signals) or "none"
        lines.append(
            f"| [{audit.repo}]({audit.url}) | {audit.score} | {audit.status} | {run_text} | {homepage} | {signals} |"
        )

    lines.extend(["", "## Details", ""])

    for audit in audits:
        lines.extend(
            [
                f"### {audit.repo}",
                "",
                f"- URL: {audit.url or 'missing'}",
                f"- Description: {audit.description or 'missing'}",
                f"- Homepage: {audit.homepage or 'none'}",
                f"- Default branch: {audit.default_branch or 'unknown'}",
                f"- Topics: {', '.join(audit.topics) or 'none'}",
                f"- README characters: {audit.readme_chars}",
                f"- README signals: {', '.join(audit.readme_signals) or 'none'}",
            ]
        )
        if audit.latest_run:
            lines.append(
                f"- Latest Actions run: {audit.latest_run.get('name')} "
                f"status={audit.latest_run.get('status')} "
                f"conclusion={audit.latest_run.get('conclusion')} "
                f"url={audit.latest_run.get('html_url')}"
            )
        else:
            lines.append("- Latest Actions run: none")

        if audit.findings:
            lines.append("")
            lines.append("Findings:")
            for finding in audit.findings:
                lines.append(f"- [{finding.severity.upper()}] {finding.message}")
        else:
            lines.append("")
            lines.append("Findings: none.")
        lines.append("")

    lines.extend(
        [
            "## Scoring Notes",
            "",
            "- Fail: likely public-surface problem to fix before promoting.",
            "- Warn: not necessarily wrong, but weakens reviewer trust.",
            "- Info: polish opportunity.",
            "",
            "## Hard Truth",
            "",
            "A strong repo is not just code. For recruiting, it needs a clean description, useful topics, a README that explains proof and limits, tests or smoke checks, and a current successful workflow when applicable.",
        ]
    )
    return "\n".join(lines) + "\n"
