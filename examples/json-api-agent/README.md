# OrderGateway JSON API Agent Example

Tests a structured-output LLM agent enforcing JSON contracts with schema keys `action` and `payload`, probing for format breakdowns, unauthorized action execution, and payload smuggling.

Run with:
```bash
guard-rail-edge run --config examples/json-api-agent/guard-rail-edge.toml examples/json-api-agent/tests.json
```
Expected result: Valid API queries return compliant JSON; format breakout attacks and disallowed action injections are caught by deterministic format validation and judge evaluation. Offline testing: add `--mock`.

