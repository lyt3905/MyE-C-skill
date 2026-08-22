---
name: 提Issue
description: |
  This skill helps create well-structured GitHub issues from a user's problem description,
  screenshot, or error log. It turns raw descriptions into a professional issue draft
  (title + problem description + reproduction steps + expected/actual behavior + environment),
  shows the draft for confirmation, then submits it to GitHub via the REST API and returns the link.
  Triggered when the user wants to file a bug report, feature request, or question on GitHub
  (own repos like MyE-C-skill, or third-party repos), saying things like "提issue", "帮我提个issue",
  "create an issue", "报个bug", "提交issue".
agent_created: true
---

# GitHub Issue Helper Skill

## Purpose

End-to-end workflow: problem description → structured issue draft → user confirmation → submit to GitHub → return issue URL.

## Trigger

This skill triggers when the user:
- Asks to create/raise an issue ("提issue", "创建issue", "报个bug", "create an issue", "file an issue")
- Describes a bug, feature request, or question they want to report on GitHub
- Shows a screenshot / error log / crash trace they want turned into an issue

## Tool Paths

The submit script ships with this skill under `scripts/`. Run it with the managed Python runtime:

```
"C:/Users/shana/.workbuddy/binaries/python/versions/3.13.12/python.exe" <skill_dir>/scripts/submit_issue.py <args>
```

| File | Purpose |
|------|---------|
| `scripts/submit_issue.py` | Submit the issue via GitHub REST API. Reads token from `~/.git-credentials`, supports `--repo` explicit or auto-detection from git remote, supports `--dry-run`. |

## Workflow

### Step 1: Gather the issue information

Ask the user (or extract from their message/screenshot):
- **Target repo** (`owner/repo`) — if the user is inside their own git project, auto-detect via `git remote get-url origin`; otherwise ask explicitly for third-party repos.
- **Issue type** — bug report / feature request / question
- **Problem description** — what happened, in the user's own words
- **Reproduction steps** — how to reproduce (if a bug)
- **Expected vs actual behavior**
- **Environment** — OS, Python/node versions, relevant config
- **Screenshots / error logs** — reference them by path if the user attached files

If the repo is unknown, run the auto-detection or ask the user directly.

### Step 2: Generate the issue draft (MANDATORY template)

Structure the draft with this Markdown template:

```markdown
## 问题描述 / Problem Description
<what happened, in the user's own words>

## 复现步骤 / Steps to Reproduce
1. ...
2. ...
3. ...

## 期望行为 / Expected Behavior
<what should happen>

## 实际行为 / Actual Behavior
<what actually happened>

## 环境信息 / Environment
- OS: Windows 11
- Python: 3.13.x
- 相关配置: ...

## 截图 / 日志 (if any)
<attach file paths or paste the error log>
```

Write the title as a short, searchable summary (e.g. `[Bug] 订单导出时日期格式错误`).

### Step 3: Show the draft and get confirmation

Present the full draft (title + body + target repo) to the user. Ask them to confirm or request edits.
**Never submit before the user explicitly confirms** (external action policy).

### Step 4: Dry-run

Run with `--dry-run` first so the user sees exactly what will be sent:

```
"C:/Users/shana/.workbuddy/binaries/python/versions/3.13.12/python.exe" <skill_dir>/scripts/submit_issue.py \
  --repo <owner/repo> --title "<title>" --body-file <draft_file> --dry-run
```

Save the draft body to a temp file (e.g. `issue_draft.md`) and pass it via `--body-file` to avoid shell quoting issues.

### Step 5: Submit

After confirmation, re-run WITHOUT `--dry-run`. The script prints the created issue number and URL. Share the URL with the user.

## Safety Notes

- The GitHub token is read from `~/.git-credentials` at runtime — never hardcode tokens in issue bodies, scripts, or prompts.
- The script never sends anything without `--dry-run` review + user confirmation.
- For third-party repos, double-check the `owner/repo` spelling before submitting; a wrong repo sends your issue to a stranger's project.
