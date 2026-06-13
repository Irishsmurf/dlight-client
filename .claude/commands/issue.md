---
description: Fetch details of a GitHub issue, create a dedicated local branch, implement the changes, verify, and commit.
argument-hint: "<issue-number>  e.g. 42"
---

Work on a GitHub issue for dlight-client. The issue number to address is: **$ARGUMENTS**

Follow these steps exactly, stopping and reporting to the user if any step fails.

## 1. Validate inputs

- If no issue number was provided in `$ARGUMENTS`, stop and ask the user: "Please specify the issue number you want to work on, e.g., `/issue 42`."
- Ensure `$ARGUMENTS` is a valid number. If not, stop and inform the user.

## 2. Fetch issue details

Run the following command to retrieve the issue details:
```bash
gh issue view "$ARGUMENTS"
```

Read and analyze the output to understand:
- The problem statement.
- The proposed changes.
- The acceptance criteria.

If the command fails (e.g. because of network issues or if the issue does not exist), stop and report to the user.

## 3. Create a branch

Extract the title from the issue output and derive a slug:
- Lowercase, alphanumeric, and hyphens only.
- Format: `issue-$ARGUMENTS-<slug>` (max ~50 characters total).
- Example: Issue 42 "pre-commit config for ruff" → `issue-42-ruff-pre-commit`

Check out a new branch:
```bash
git checkout -b <branch-name>
```

## 4. Implement changes

Locate the target files in the repository. Implement the changes requested in the issue description, ensuring:
- You adhere to PEP 8 coding style and existing project conventions.
- You do not introduce unrelated modifications.
- If there are new public methods or parameters, you update the documentation in `docs/` as required by `CLAUDE.md`.

## 5. Verify the changes

Run the test suite and verify formatting/linting before committing:
```bash
# Run unit tests
python -m unittest discover tests/

# Run ruff check and format check
ruff check .
ruff format --check .
```

If any check fails, resolve the issues before moving forward.

## 6. Commit the changes

Stage only the modified and newly created files:
```bash
git add <modified-files>
```
Do not stage helper scripts or build artifacts.

Compose a conventional commit message that references and closes the issue:
- Format: `<type>(<scope>): <summary> (closes #$ARGUMENTS)`
- Example: `chore(ci): add pre-commit config for ruff (closes #42)`

Commit the staged changes:
```bash
git commit -m "<commit-message>"
```

## 7. Confirm

Tell the user:
- What issue was worked on (number and title).
- The name of the branch created.
- The list of files modified.
- The commit message and hash.
- Remind them that they can run `/commit` to push the branch and prepare a pull request.
