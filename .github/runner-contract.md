# Public CI runner contract

The `ci` workflow selects group `akretic-public-ci` and labels
`[self-hosted, Linux, X64, akretic-public-ci]`. Admission requires a separate
public-only pool of fresh Ubuntu 24.04 x64 VMs reset after every job. Do not
admit these public repository jobs to a private or production runner group.
The pool must isolate untrusted branch/fork code from private networks,
production credentials and other jobs. This source change does not create,
enroll or qualify that pool.

Keep both `push` and `pull_request` coverage, including fork pull requests and
GitHub's existing contributor-approval rules. The workflow grants only
`contents: read`, does not persist checkout credentials, and limits each job
to 20 minutes. CI uses synthetic/local test fixtures and needs no production
or model-service credentials. It neither deploys the demo nor publishes assets.

The pool needs Python setup-action support, venv/pip prerequisites, Git and
public package-download access. CI keeps Python 3.11, the existing requirements
file and the full `pytest -q` gate. Playwright installs Chromium with
`python -m playwright install --with-deps chromium`; a fresh VM needs the
associated Ubuntu libraries and passwordless package-install capability.
Do not replace browser execution with skips when the pool is unavailable.

Runner enrollment and an actual final-revision CI run are separate acceptance
steps. A local test result or queued check does not establish Linux runner
admission, fork behavior or clean-VM reset.
