from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .auditor import RepoAudit, add_finding, audit_repo, render_markdown


DEFAULT_REPOS = [
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
    parser.add_argument("--output", type=Path, help="Markdown output path")
    return parser.parse_args(argv)


def resolve_repos(args: argparse.Namespace) -> list[str]:
    if args.repos:
        return args.repos
    if args.config:
        return load_config(args.config)
    return DEFAULT_REPOS


def run(argv: list[str] | None = None) -> str:
    args = parse_args(argv)
    repos = resolve_repos(args)

    audits: list[RepoAudit] = []
    for repo in repos:
        try:
            audits.append(audit_repo(repo))
        except Exception as exc:  # noqa: BLE001 - keep auditing other repos.
            audit = RepoAudit(repo=repo)
            add_finding(audit, "fail", f"Audit crashed for this repo: {exc}")
            audits.append(audit)

    return render_markdown(audits)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = run(argv)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
    else:
        sys.stdout.write(report)
    return 0
