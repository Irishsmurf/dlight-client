---
description: Stage changes, update CHANGELOG [Unreleased], commit, and push to a new branch ready for a PR.
argument-hint: "[short description]  e.g. fix connection pool timeout"
---

Prepare and push a commit for dlight-client. The user's description (if provided): **$ARGUMENTS**

Follow these steps exactly, stopping and reporting to the user if any step fails.

## 1. Inspect the working tree

Run:
```bash
git status --short
git diff --stat HEAD
```

Collect the list of changed/untracked files. If the working tree is completely clean (no changes at all), stop and tell the user: "Nothing to commit — working tree is clean."

## 2. Determine a branch name

If the user provided a description in `$ARGUMENTS`, derive the branch name from it:
- Lowercase, words joined with hyphens
- Prefix with a type: `fix/`, `feat/`, `chore/`, `docs/`, `refactor/` — infer from the description or the nature of the changed files
- Max ~50 chars total
- Example: "fix connection pool timeout" → `fix/connection-pool-timeout`

If no description was given, read the diff (`git diff HEAD` and `git status`) and infer a branch name from the changed files and content.

Check that the branch name doesn't already exist locally or remotely:
```bash
git branch --list "<branch>"
git ls-remote --heads origin "<branch>"
```
If it exists, append `-2` (then `-3`, etc.) until the name is free.

## 3. Check and update CHANGELOG

Read `CHANGELOG.md`. Look at the `## [Unreleased]` section (everything between that heading and the next `## [` heading).

**Case A — [Unreleased] already has content:** Continue to step 4. No changes needed.

**Case B — [Unreleased] is empty:** You must add an entry before committing. 

Infer the change type and write a concise Keep-a-Changelog entry:
- Use the diff and file names to determine the right `### Added`, `### Fixed`, `### Changed`, `### Removed`, or `### Security` sub-heading
- Write one or two bullet points describing the user-visible change

Insert the new content into `CHANGELOG.md` immediately under `## [Unreleased]`, like:

```markdown
## [Unreleased]

### Fixed
- Brief description of what was fixed.
```

Show the user what you wrote and confirm it accurately reflects the change before continuing.

## 4. Stage files

Stage all tracked modifications plus any new files that are clearly part of this change:
```bash
git add -u
```
Then also stage any relevant untracked files individually (don't blindly `git add .` — skip build artefacts, `dist/`, `site/`, `*.egg-info/`, `__pycache__/`, `.coverage`, `coverage.xml`).

Always include `CHANGELOG.md` if it was modified in step 3.

Show the final staged set with `git diff --cached --stat` before committing.

## 5. Write the commit message

Compose a conventional commit message:
- Format: `<type>(<optional scope>): <short imperative summary>` — max 72 chars on the first line
- Types: `fix`, `feat`, `chore`, `docs`, `refactor`, `test`, `ci`
- If there's more than one logical change, add a short body (blank line after subject)
- Do **not** mention the branch name or PR number

## 6. Create branch and commit

```bash
git checkout -b <branch>
git commit -m "<message>"
```

## 7. Push

```bash
git push -u origin <branch>
```

## 8. Confirm

Tell the user:
- Branch `<branch>` pushed with commit: `<subject line>`
- CHANGELOG [Unreleased] updated: `<the bullet(s) added>` (or "already had content")
- Open a PR at: https://github.com/Irishsmurf/dlight-client/compare/<branch>
