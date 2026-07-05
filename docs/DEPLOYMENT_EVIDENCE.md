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

Because the launch channel is local-first, reverse-proxy auth is conditionally required only when an agency exposes `/api/*` to the internet.

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
