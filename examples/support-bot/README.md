# CloudFlow Support Bot Example

Tests a customer support LLM assistant with confidential discount codes and a secret canary against direct leaks, authority roleplay, base64 obfuscation, and JSON jailbreaks.

Run with:
```bash
guard-rail-edge run --config examples/support-bot/guard-rail-edge.toml examples/support-bot/tests.json
```
Expected result: 3 benign tests pass; 5 adversarial attacks trigger canary detection or judge evaluation. For offline testing, pass `--mock`.

