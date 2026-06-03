# Releasing Qualis

Qualis releases are tag-driven. Pushing a tag matching `v*` triggers
`.github/workflows/release.yml`, which builds the sdist + wheel and
publishes to PyPI via trusted publishing (OIDC — no API tokens).

## Cutting a release

1. Make sure `main` is green: <https://github.com/ahmedashraffcih/qualis/actions>.
2. Bump the version in two places:
   - `pyproject.toml` → `version = "X.Y.Z"`
   - `src/qualis/__init__.py` → `__version__ = "X.Y.Z"`
3. Add a `CHANGELOG.md` entry at the top, under a new heading for the version.
4. Commit:
   ```bash
   git add pyproject.toml src/qualis/__init__.py CHANGELOG.md
   git commit -m "chore: vX.Y.Z release"
   git push origin main
   ```
5. Tag and push:
   ```bash
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```
6. Watch <https://github.com/ahmedashraffcih/qualis/actions>. The `Release`
   workflow will:
   - verify the tag matches the version in `pyproject.toml` (fails the
     release if they disagree),
   - build the sdist + wheel,
   - request a PyPI upload via OIDC trusted publishing.
7. If the deployment environment has manual approval enabled, approve
   the deployment in the workflow run UI.
8. Verify the release on PyPI: <https://pypi.org/project/qualis/>.

## Yanking a broken release

`pip install qualis==X.Y.Z` is permanent — once a version is published,
it cannot be replaced, only yanked. If you ship a broken release:

1. Go to <https://pypi.org/manage/project/qualis/release/X.Y.Z/>
2. Click "Yank" and provide a reason.
3. Cut a `X.Y.(Z+1)` patch release with the fix.

Never delete and re-publish — PyPI rejects re-uploads of the same version.
