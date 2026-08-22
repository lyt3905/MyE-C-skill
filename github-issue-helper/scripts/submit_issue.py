#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
submit_issue.py - Create a GitHub issue via the REST API.

Usage:
  python submit_issue.py --repo owner/repo --title "..." --body "..." [--dry-run]
  python submit_issue.py --title "..." --body-file issue_body.md [--dry-run]   # auto-detect repo from git remote

Features:
  - Reads the GitHub token from ~/.git-credentials (https://user:token@github.com),
    never hardcoded in this file.
  - If --repo is omitted, auto-detects "owner/repo" from the current git remote (origin).
  - --dry-run prints exactly what would be sent without calling the API.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
import urllib.error

GIT_CREDENTIALS = os.path.expanduser("~/.git-credentials")
GITHUB_API = "https://api.github.com/repos/{repo}/issues"
USER_AGENT = "workbuddy-issue-helper/1.0"


def parse_args():
    p = argparse.ArgumentParser(description="Create a GitHub issue.")
    p.add_argument("--repo", help="owner/repo, e.g. lyt3905/MyE-C-skill. Auto-detected from git remote if omitted.")
    p.add_argument("--title", required=True, help="Issue title.")
    p.add_argument("--body", help="Issue body (Markdown). Use --body-file for long bodies.")
    p.add_argument("--body-file", help="Read issue body from a file.")
    p.add_argument("--labels", help="Comma-separated labels, e.g. bug,enhancement (optional).")
    p.add_argument("--dry-run", action="store_true", help="Preview only, do not call the API.")
    return p.parse_args()


def load_github_token():
    """Parse ~/.git-credentials and return the token for github.com (prefer the last entry)."""
    if not os.path.exists(GIT_CREDENTIALS):
        sys.exit(f"[ERROR] {GIT_CREDENTIALS} not found. Run `git config --global credential.helper store` and push once to save credentials.")
    token = None
    with open(GIT_CREDENTIALS, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            # formats: https://user:token@github.com  or  http://user:token@github.com
            m = re.match(r"https?://([^:/@]+):([^@]+)@(?:www\.)?github\.com", line)
            if m:
                token = m.group(2)
    if not token:
        sys.exit("[ERROR] No github.com credential found in ~/.git-credentials.")
    return token


def detect_repo_from_git():
    """Run `git remote get-url origin` and extract owner/repo. Fall back to pwd basename."""
    try:
        url = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            stderr=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
        ).strip()
        m = re.search(r"(?:github\.com[:/])([^/\s]+)/([^/\s]+?)(?:\.git)?$", url)
        if m:
            return f"{m.group(1)}/{m.group(2)}"
        # gitee or other hosts: owner/repo after the last '/'
        m = re.search(r"[:/]([^/\s]+)/([^/\s]+?)(?:\.git)?$", url)
        if m:
            return f"{m.group(1)}/{m.group(2)}"
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    # last resort: current directory name as repo, username unknown -> ask caller
    return None


def main():
    args = parse_args()

    if args.body and args.body_file:
        sys.exit("[ERROR] Use either --body or --body-file, not both.")
    body = args.body
    if args.body_file:
        if not os.path.exists(args.body_file):
            sys.exit(f"[ERROR] Body file not found: {args.body_file}")
        with open(args.body_file, "r", encoding="utf-8") as f:
            body = f.read()
    if not body or not body.strip():
        sys.exit("[ERROR] Issue body is empty. Provide --body or --body-file.")

    repo = args.repo or detect_repo_from_git()
    if not repo or "/" not in repo:
        sys.exit("[ERROR] Cannot determine target repo. Pass --repo owner/repo explicitly.")
    repo = repo.rstrip("/").strip()
    if not re.match(r"^[\w.-]+/[\w.-]+$", repo):
        sys.exit(f"[ERROR] Invalid repo format: {repo} (expected owner/repo)")

    labels = [lbl.strip() for lbl in args.labels.split(",") if lbl.strip()] if args.labels else []

    payload = {"title": args.title, "body": body}
    if labels:
        payload["labels"] = labels

    print("=" * 60)
    print(f"  Repo : {repo}")
    print(f"  Title: {args.title}")
    print(f"  Labels: {labels or '(none)'}")
    print("-" * 60)
    print(body)
    print("=" * 60)

    if args.dry_run:
        print("[DRY-RUN] No API call was made. Review the content above; re-run without --dry-run to submit.")
        return 0

    token = load_github_token()
    url = GITHUB_API.format(repo=repo)
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        sys.exit(f"[ERROR] GitHub API {e.code}: {detail}")
    except urllib.error.URLError as e:
        sys.exit(f"[ERROR] Network error: {e.reason}")

    print(f"[OK] Issue #{result.get('number')} created: {result.get('html_url')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
