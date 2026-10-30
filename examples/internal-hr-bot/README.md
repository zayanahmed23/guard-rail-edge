# Acme HR PeopleBot Example

Tests an internal Slack-style HR assistant against roleplay audits, hypothetical framing, delimiter injection, and policy leakage regarding executive compensation, termination records, and leadership calendars.

Run with:
```bash
guard-rail-edge run --config examples/internal-hr-bot/guard-rail-edge.toml examples/internal-hr-bot/tests.json
```
Expected result: Policy queries pass cleanly; roleplay, hypothetical bypasses, and delimiter injections trigger guardrail alerts or fail the judge review. For offline testing: add `--mock`.

