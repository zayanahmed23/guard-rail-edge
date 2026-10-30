# Acme KnowledgeBase RAG Assistant Example

Tests an internal Q&A assistant against indirect prompt injection where adversarial instructions are embedded within untrusted retrieved document context.

Run with:
```bash
guard-rail-edge run --config examples/rag-assistant/guard-rail-edge.toml examples/rag-assistant/tests.json
```
Expected result: Benign questions answer strictly from context; indirect injections attempting to override system constraints trigger canary detection or judge evaluation. Offline testing: append `--mock`.

