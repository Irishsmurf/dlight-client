---
description: Cut a dlight-client release — bumps version, promotes CHANGELOG, commits, tags, and pushes to trigger automated PyPI publish.
argument-hint: <version>  e.g. 1.7.0
---

Cut a release for dlight-client. The version to release is: **$ARGUMENTS**

Follow these steps exactly, stopping and reporting to the user if any step fails.

## 1. Validate inputs

- If no version was provided, stop and ask the user: "Which version are you releasing? e.g. `/release 1.7.0`"
- The version must match `\d+\.\d+\.\d+` (no leading `v`). If it doesn't, stop and say so.

## 2. Pre-flight checks

Run all of the following and stop on any failure:

```bash
# Must be on main
git rev-parse --abbrev-ref HEAD

# Working tree must be clean
git status --porcelain

# Tag must not already exist
git tag --list "v$VERSION"

# Tests must pass
python -m unittest discover tests/
```

If the working tree is dirty, list the uncommitted files and ask the user to commit or stash them first.
If the tag already exists, tell the user and stop.

## 3. Check CHANGELOG

Read `CHANGELOG.md`. The `[Unreleased]` section must contain at least one non-empty bullet or paragraph under a `###` sub-heading. If it's empty, warn the user: "The [Unreleased] section in CHANGELOG.md is empty. Add release notes before cutting a release." Then stop.

## 4. Update `dlightclient/__init__.py`

Replace the current `__version__ = "..."` line with:

```python
__version__ = "$VERSION"
```

The file is at `dlightclient/__init__.py`. Use the Edit tool — do not rewrite the whole file.

## 5. Update `CHANGELOG.md`

Make two edits:

**a)** Replace the `## [Unreleased]` heading line with two blocks:

```
## [Unreleased]

## [$VERSION] — $TODAY
```

Where `$TODAY` is today's date in `YYYY-MM-DD` format.

**b)** Verify the result looks correct before continuing.

## 6. Commit

Stage only these two files:

```bash
git add dlightclient/__init__.py CHANGELOG.md
git commit -m "chore: bump version to $VERSION"
```

## 7. Tag and push

```bash
git tag "v$VERSION"
git push origin main
git push origin "v$VERSION"
```

## 8. Confirm

Tell the user:

- Tag `v$VERSION` pushed — the `release.yml` workflow will create the GitHub Release automatically.
- Once the GitHub Release is published, `python-publish.yml` will upload to PyPI.
- Watch progress at: https://github.com/Irishsmurf/dlight-client/actions
