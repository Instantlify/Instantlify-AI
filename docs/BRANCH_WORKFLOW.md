# Branch workflow

`feature/*` → pull request → `staging` → pull request → `main`.

- `staging` represents the staging release; `main` represents production.
- Both branches require a PR and the GitHub Actions checks `source-branch`,
  `backend`, `frontend`, and `integration`.
- Direct pushes, force pushes, and branch deletion are blocked, including for
  administrators. Repository administrators can still edit repository settings.
- Source branches must belong to this repository. Fork PRs are rejected.
- No reviewer approval is required initially, so a solo maintainer can merge.
- Feature branches are named `feature/<description>` and start from `staging`.
- Promote staging into main with a merge commit. Keep staging after release.
- Do not enable strict "branch must be up to date" protection on main: merging
  main back into staging would conflict with the feature-only source rule.
  CI still tests the proposed merge through the existing pull_request workflow.
- Tag production releases, for example `v1.0.0`, and record image digests.

## Initial setup

1. Review and merge the branch-policy workflow into `main` before enabling its
   required check. This one-time bootstrap is needed because main does not yet
   contain the trusted workflow. Do not commit unrelated local work or secrets.
2. Create `staging` from that updated `main`, or if staging already exists,
   review its history and bring the workflow in through a feature PR.
3. Verify GitHub Actions permits the metadata-only `pull_request_target` event.
   Public repositories may have an Actions event policy that blocks it. This
   workflow has read-only permissions, uses no secrets, and never checks out code.
   Do not replace it with a workflow that executes PR code in the target context.
4. Inspect existing classic protections and repository/organization rulesets.
   The setup script refuses to overwrite protected branches. If either branch
   is already protected, update its existing rules manually, preserving stronger
   requirements. For a private repository, verify the GitHub plan supports branch
   protection before setup.
5. With GitHub CLI installed and authenticated as a repository administrator, run:

   ```powershell
   ./scripts/protect-branches.ps1
   ```

   Both branches and both workflow files must already exist. The script performs
   read-only preflight checks before updating and verifying protections. A failure
   after the first update can leave that branch protected; inspect and finish the
   remaining branch manually rather than removing the protection to rerun.
6. Open an allowed feature PR into staging and verify all four checks appear.
   Verify a non-feature PR into staging fails `source-branch`, a feature PR into
   main fails it, and staging into main passes it. Close test PRs without merging.
   Confirm an ordinary direct push is rejected, without bypassing protections.

## Daily use

Start from a clean working tree:

```sh
git switch staging
git pull --ff-only origin staging
git switch -c feature/your-change
# Commit only the intended files, then:
git push -u origin feature/your-change
```

Open a PR to staging. Once merged and tested, open a staging-to-main release PR.
Urgent fixes follow the same route. Avoid squash/rebase merging the release PR;
use a merge commit to retain the shared branch history.

The current `boosend-parity` work must move through a `feature/*` branch before
entering staging after protections are enabled. Preserve uncommitted work first.

## Deployment scope

These files enforce the Git workflow once installed and configured on GitHub.
They do not provision servers, deploy containers, or configure databases/secrets.
Automatic staging deployment and production deployment need separate workflows
and environment-specific infrastructure configuration.
