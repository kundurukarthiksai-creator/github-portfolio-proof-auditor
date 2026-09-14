from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .auditor import RepoAudit, add_finding, audit_repo, render_json, render_markdown


DEFAULT_REPOS = [
    "kundurukarthiksai-creator/mcp-tool-safety-lab",
    "kundurukarthiksai-creator/github-portfolio-proof-auditor",
    "kundurukarthiksai-creator/agent-reliability-tool-use-eval-lab",
    "kundurukarthiksai-creator/AI-LinkedIn-Post-Generator",
    "kundurukarthiksai-creator/OpportUnityHub-Smart-Opportunity-Tracker",
    "kundurukarthiksai-creator/GitHub-Dev-Card-Generator",
    "kundurukarthiksai-creator/cse540-smart-contract-project",
    "kundurukarthiksai-creator/kundurukarthiksai-creator",
]


def load_config(path: Path) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    repos = data.get("repos")
    if not isinstance(repos, list) or not all(isinstance(repo, str) for repo in repos):
        raise ValueError("Config must contain a string list at key 'repos'.")
    return repos


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit public GitHub repos for proof quality.")
    parser.add_argument("repos", nargs="*", help="owner/repo values to audit")
    parser.add_argument("--config", type=Path, help="JSON config path with a repos list")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown", help="Report output format")
    parser.add_argument("--output", type=Path, help="Report output path")
    parser.add_argument(
        "--check-readme-links",
        action="store_true",
        help="Check HTTP(S) links found in each README. This is slower and can be affected by network issues.",
    )
    return parser.parse_args(argv)


def resolve_repos(args: argparse.Namespace) -> list[str]:
    if args.repos:
        return args.repos
    if args.config:
        return load_config(args.config)
    return DEFAULT_REPOS


def collect_audits(args: argparse.Namespace) -> list[RepoAudit]:
    repos = resolve_repos(args)

    audits: list[RepoAudit] = []
    for repo in repos:
        try:
            audits.append(audit_repo(repo, check_readme_links=args.check_readme_links))
        except Exception as exc:  # noqa: BLE001 - keep auditing other repos.
            audit = RepoAudit(repo=repo)
            add_finding(audit, "fail", f"Audit crashed for this repo: {exc}")
            audits.append(audit)
    return audits


def render_report(audits: list[RepoAudit], output_format: str) -> str:
    if output_format == "json":
        return render_json(audits)
    return render_markdown(audits)


def run(argv: list[str] | None = None) -> str:
    args = parse_args(argv)
    return render_report(collect_audits(args), args.format)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = render_report(collect_audits(args), args.format)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
    else:
        sys.stdout.write(report)
    return 0
