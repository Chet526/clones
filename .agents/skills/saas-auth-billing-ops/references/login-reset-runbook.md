# Login and Password Reset Runbook

1. Verify auth config endpoint is enabled and points to correct project.
2. Confirm redirect URLs include account page and post-login route.
3. Trigger magic link/reset email and verify provider accepted send request.
4. Validate token/session creation and expiry settings.
5. If email template/provider fails, provide fallback support script and incident note.
6. Close with customer-safe instructions and expected timeline.
