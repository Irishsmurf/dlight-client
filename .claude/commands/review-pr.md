---
description: Fetch inline review comments on a PR, triage them, apply valid fixes, and push.
argument-hint: "[PR number]  e.g. 44  (defaults to the current branch's open PR)"
---

Review and action PR comments. PR number (if provided): **$ARGUMENTS**

Follow these steps exactly, stopping and reporting to the user if any step fails.

## 1. Identify the PR

If a PR number was given in `$ARGUMENTS`, use it directly.

Otherwise, detect the open PR for the current branch:
```bash
gh pr view --json number,url,headRefName
```

If no PR is found, stop and tell the user.

## 2. Fetch all review comments

Fetch both top-level PR comments and inline review comments:

```bash
# Inline code comments (with file + line context)
gh api repos/Irishsmurf/dlight-client/pulls/<PR>/comments \
  --jq '.[] | {path: .path, line: .line, body: .body}'

# General PR-level comments
gh pr view <PR> --comments
```

If there are no comments, tell the user "No review comments found on PR #<N>." and stop.

## 3. Triage comments

Read each comment and classify it as:

- **Apply** — a clear correctness bug, anti-pattern, or direct improvement with a concrete suggestion. Apply these without asking.
- **Discuss** — a matter of taste, preference, or architectural opinion where the right answer isn't obvious. Present these to the user before acting.
- **Skip** — informational notes, praise, or already-resolved items. Note these briefly but take no action.

Present the triage summary to the user before making any changes:

```
### Triage summary — PR #<N>

**Apply (N):**
- file.py:123 — [brief description]

**Discuss (N):**
- file.py:456 — [brief description and why it needs discussion]

**Skip (N):**
- [reason]
```

If there are **Discuss** items, use AskUserQuestion to get direction before continuing.

## 4. Apply changes

For each **Apply** item, make the targeted fix using the Edit tool. Do not rewrite surrounding code.

After all edits, run the test suite and linter to confirm nothing broke:
```bash
python -m unittest discover tests/
flake8 dlightclient tests --count --max-line-length=120 --statistics
```

If tests or lint fail, diagnose and fix before continuing.

## 5. Commit and push

Stage only the files that were changed:
```bash
git add <changed files>
git commit -m "refactor: address PR #<N> review comments

<one bullet per applied change>

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
git push
```

## 6. Confirm

Tell the user:
- How many comments were applied, discussed, and skipped
- The commit pushed
- Any **Discuss** items still outstanding that need a decision
