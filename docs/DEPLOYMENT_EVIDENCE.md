# Deployment Security Evidence

## Scope
This evidence file tracks deployment-only controls that cannot be fully verified by repository unit tests.

Scope boundary:
- This conditional control applies to internet-exposed self-host investigator-data APIs.
- It does not apply to Netlify storefront commerce/account endpoints.

## Launch Channel
- Launch channel type: local-first investigator install (not a shared internet-exposed hosted API).
- Customer install pin: `52b31ec530c2a81c6647da7b5bf7f99cd03a4475`.
- Release governance snapshot tag: `v0.3.0-launch-r2`.
- Release signoff anchor: governance snapshot commit `724e6459c5d1ff89d133b11e449892bc1112841d`.

Signoff rule:
- Launch go/no-go is anchored to the governance snapshot commit and its CI evidence in this file.
- Post-anchor docs-only commits may include a representative supplemental CI sample for audit continuity, but are not launch blockers and do not need to match latest HEAD.

Because the launch channel is local-first, reverse-proxy auth is conditionally required only when an agency exposes `/api/*` to the internet.

## CI Evidence (Launch Governance Commit)
- Workflow: `CI`
- Run ID: `28729808845`
- Run number: `6`
- URL: `https://github.com/Chet526/clones/actions/runs/28729808845`
- Head SHA: `724e6459c5d1ff89d133b11e449892bc1112841d`
- Status: `completed`
- Conclusion: `success`
- Started at (UTC): `2026-07-05T04:44:42Z`
- Updated at (UTC): `2026-07-05T04:45:23Z`

Command used:
```bash
gh api repos/Chet526/clones/actions/runs/28729808845 --jq '{run_id: .id, run_number: .run_number, workflow: .name, workflow_id: .workflow_id, head_sha: .head_sha, status: .status, conclusion: .conclusion, html_url: .html_url, run_started_at: .run_started_at, updated_at: .updated_at, created_at: .created_at}'
```

## Supplemental CI Evidence (Optional Historical Sample)
- Snapshot note: this is a representative post-anchor sample; it may lag current HEAD.
- Workflow: `CI`
- Run ID: `28730241026`
- Run number: `10`
- URL: `https://github.com/Chet526/clones/actions/runs/28730241026`
- Head SHA: `c1138bb7f48de21f630c3ecf2e571ec0ce9e4c3f`
- Status: `completed`
- Conclusion: `success`
- Started at (UTC): `2026-07-05T05:05:52Z`
- Updated at (UTC): `2026-07-05T05:06:35Z`

Command used:
```bash
gh api repos/Chet526/clones/actions/runs/28730241026 --jq '{run_id: .id, run_number: .run_number, workflow: .name, workflow_id: .workflow_id, head_sha: .head_sha, status: .status, conclusion: .conclusion, html_url: .html_url, run_started_at: .run_started_at, updated_at: .updated_at, created_at: .created_at}'
```

## Provenance Verification Execution (2026-07-05)

Command:
```bash
git show-ref --tags v0.3.0-launch-r2
```
Output:
```text
0f4e9d8e2fc7498d47f65fb9d24cc6c7c7084a46 refs/tags/v0.3.0-launch-r2
```

Command:
```bash
git rev-parse v0.3.0-launch-r2^{}
```
Output:
```text
724e6459c5d1ff89d133b11e449892bc1112841d
```

Command:
```bash
grep -H "52b31ec530c2a81c6647da7b5bf7f99cd03a4475" README.md site/public/index.html docs/LAUNCH_CHECKLIST.md
```
Output:
```text
README.md:python -m pip install "git+https://github.com/Chet526/clones.git@52b31ec530c2a81c6647da7b5bf7f99cd03a4475"
site/public/index.html:            <pre><code>python -m pip install "git+https://github.com/Chet526/clones.git@52b31ec530c2a81c6647da7b5bf7f99cd03a4475"  # Python 3.10+
docs/LAUNCH_CHECKLIST.md:  - [x] [BLOCKER] Source install from immutable Git commit (`52b31ec530c2a81c6647da7b5bf7f99cd03a4475`) (current launch channel).
docs/LAUNCH_CHECKLIST.md:- [x] [BLOCKER] Customer install references are pinned to immutable commit `52b31ec530c2a81c6647da7b5bf7f99cd03a4475` and documented in README/storefront.
```

## Conditional Control: Reverse-Proxy Auth for Internet-Exposed `/api/*`
Status: conditional blocker (required if deployment is internet-exposed).

Required deployment evidence before exposure:
1. Reverse-proxy configuration artifact attached (Nginx/Caddy/Traefik config file path).
2. Access-control policy documented (allowed principals/groups).
3. Verification commands captured:
   - unauthenticated request returns `401`/`403`
   - authenticated request succeeds for allowed principal
4. Approval sign-off by deployment owner and security reviewer.

## Example Verification Commands
```bash
curl -i https://<host>/api/plans
curl -i -H "Authorization: Bearer <proxy-issued-token>" https://<host>/api/plans
```

## Sign-Off (internet-exposed deployments only)
- Deployment owner: N/A for current local-first launch profile
- Security reviewer: N/A for current local-first launch profile
- Date: N/A for current local-first launch profile
