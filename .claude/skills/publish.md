---
name: publish
description: Bump version, commit, push tag to trigger GitHub Actions PyPI publish workflow, and verify release
---

Publish a new version of easy-tdx to PyPI via GitHub Actions trusted publisher.

## Prerequisites

- All code changes must already be committed and pushed to `main`.
- PyPI trusted publisher must be configured (owner: `handsomejustin`, repo: `easy_tdx`, workflow: `publish.yml`, environment: `release`).
- GitHub `release` environment must exist in repo settings.

## Steps

1. **Confirm working tree is clean on `main`**: Run `git status` and `git log --oneline -3`. All changes must be pushed.

2. **Determine new version**: Read current version from `pyproject.toml`. Ask user for target version if not obvious (patch/minor/major), defaulting to patch bump.

3. **Bump version**: Edit `version` in `pyproject.toml` to the new version.

4. **Commit and push**:
   ```bash
   git add pyproject.toml
   git commit -m "chore: bump version to X.Y.Z"
   git push origin main
   ```

5. **Create and push tag**:
   ```bash
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```

6. **Wait for GitHub Actions**: Run `gh run list --limit 1` to get the run ID, then `gh run watch <ID>` to monitor. Timeout after 120 seconds.

7. **Verify on PyPI**:
   ```bash
   curl -s https://pypi.org/pypi/easy-tdx/json | python -c "import sys,json; d=json.load(sys.stdin); print('latest:', d['info']['version'])"
   ```
   Confirm the version matches.

8. **Report result**: State the published version and PyPI URL.

## Rollback

If the publish fails:
- Do NOT delete the tag (it's already pushed).
- Fix the issue, bump to next patch version, and re-run.
- If PyPI shows the version but something is wrong, it cannot be yanked automatically — the user must do it manually via PyPI dashboard.

## Notes

- The workflow file is at `.github/workflows/publish.yml`.
- It triggers on `push tags: v*`.
- Uses OIDC trusted publishing — no API tokens needed.
- Build uses `python -m build` (hatchling backend).
