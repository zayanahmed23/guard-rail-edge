---
name: New Adversarial Attack Proposal
about: Propose a new prompt-injection or jailbreak attack technique for the attack library
title: '[ATTACK] '
labels: attack-library, security
assignees: ''
---

### 🛡️ Harmless-Goal Rule Notice
> **Adversarial prompts submitted to guard-rail-edge MUST NOT contain real-world malicious payloads, exploit code, malware, credentials, or PII.**
> All submissions must adhere to the **harmless-goal rule**: attacks must test prompt instruction leakage, format evasion, roleplay override, or boundary enforcement only. Submissions violating this rule will be closed immediately.

**Attack Summary**
- **Technique Name**:
- **Target Category**: (`system_prompt_leakage` / `roleplay_bypasses` / `format_breakout` / `obfuscation`)
- **Severity Level**: (`low` / `medium` / `high`)

**Adversarial Input Prompt**
```
(paste adversarial prompt template here)
```

**Mechanisms & Literature Reference**
Explain the cognitive or formatting mechanism that causes models to bypass system boundaries (e.g., citation to academic paper, arxiv link, or novel framing):

**Detection Signatures**
- **Suggested Success Markers**: Substrings indicating target leakage
- **Suggested Success Regex**: Pattern indicating failure
- **Expected Rubric Score on Unhardened Target**: (1 Suspicious or 2 Jailbroken)
