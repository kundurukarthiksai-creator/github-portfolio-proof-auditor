# GitHub Portfolio Proof Auditor

CLI for auditing whether public GitHub portfolio repositories have recruiter-facing proof that is easy to trust.

It checks repo metadata, README proof signals, risky public wording, latest GitHub Actions status, and homepage health, then writes a Markdown report.

## Why This Exists

Portfolio repos drift. A README can keep claiming something after CI breaks, a repo card can overstate maturity, or a public profile can hide the strongest proof behind weaker pinned projects.

This tool is a lightweight surface audit. It does not replace a code review.

## What It Checks

- Repo description exists.
- Repo topics exist.
- README exists and has enough substance.
- README mentions proof signals like CI, tests, limits, or demo paths.
- Public text does not include blocked patterns such as local machine paths or sensitive career-status wording.
- Latest GitHub Actions run succeeded when Actions are expected.
- Homepage URL returns HTTP 200 when configured.

## What It Does Not Check

- It does not prove code quality.
- It is not a security scanner.
- It does not audit private repos by default.
- It does not store GitHub tokens.
- It does not submit changes to GitHub.

## Requirements

- Python 3.11+
- GitHub CLI (`gh`) installed and authenticated for API access

## Usage

Run with explicit repos:

```powershell
python -m github_proof_auditor --output reports/audit.md owner/repo another-owner/another-repo
```

Run with a config file:

```powershell
python -m github_proof_auditor --config configs/karthik-public-repos.json --output reports/karthik-public-repos.md
```

Config format:

```json
{
  "repos": [
    "owner/repo"
  ]
}
```

## Development

Run tests:

```powershell
python -m pip install -e .
python -m unittest discover -s tests
```

Run the packaged CLI from source:

```powershell
python -m github_proof_auditor --config configs/karthik-public-repos.json --output reports/karthik-public-repos.md
```

## Honest Limits

- GitHub API shape can vary by repo type.
- The score is a reviewer-surface heuristic, not an objective quality score.
- The default blocked-word list is intentionally conservative and may need repo-specific exceptions.
- Network checks can fail transiently.
