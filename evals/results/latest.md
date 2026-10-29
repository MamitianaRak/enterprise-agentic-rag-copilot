# Evaluation run 20261029-133908-45e3

20261029-133908 · 32 cases · dataset v1 · models: gemini:gemini-3.5-flash-lite, groq:openai/gpt-oss-20b

| Check | Score | Cases |
|---|---|---|
| Source chosen (KB, web, direct, refusal) | 96% | 27 |
| Expected document cited | 100% | 24 |
| Expected facts in the answer | 100% (mean) | 28 |
| No forbidden advice | 100% | 4 |
| Priority / severity | 100% | 7 |
| Cases passing every check | 97% | 32 |

Latency per question: median 22.8 s, max 67.6 s. LLM calls per question: 5.6 on average. Malformed structured outputs recovered by a fallback: 0.

| Case | Source | Severity | Facts | Result | Note |
|---|---|---|---|---|---|
| hr-annual-leave | private_kb |  | 100% | pass |  |
| hr-sick-leave | private_kb |  | 100% | pass |  |
| hr-remote-work | private_kb |  | 100% | pass |  |
| hr-working-hours | private_kb |  | 100% | pass |  |
| hr-payroll-dates | private_kb |  | 100% | pass |  |
| hr-benefits-change | private_kb |  | 100% | pass |  |
| hr-harassment | private_kb |  | 100% | pass |  |
| hr-payroll-priority | private_kb |  | 100% | pass |  |
| hr-bank-details | private_kb |  | 100% | pass |  |
| hr-paternity-not-in-kb | insufficient_evidence |  |  | pass |  |
| hr-greeting | insufficient_evidence |  |  | FAIL |  |
| it-password-length | private_kb | P4 | 100% | pass |  |
| it-mfa-methods | private_kb | P4 | 100% | pass |  |
| it-vpn-fails | private_kb | P3 | 100% | pass |  |
| it-firewall-shortcut | private_kb | P3 | 100% | pass |  |
| it-phishing-clicked | private_kb | P1 | 100% | pass |  |
| it-mfa-code-request | private_kb | none | 100% | pass |  |
| it-lost-laptop | private_kb | P1 | 100% | pass |  |
| it-wifi-only-me | private_kb | P3 | 100% | pass |  |
| it-print-job | private_kb | P3 | 100% | pass |  |
| it-unlisted-software | private_kb | P4 | 100% | pass |  |
| it-team-blocked | private_kb | P2 |  | pass |  |
| it-thanks | direct | none |  | pass |  |
| co-502-after-release | private_kb | SEV2 | 100% | pass |  |
| co-sev1-paging | private_kb | SEV1 | 100% | pass |  |
| co-sev2-error-rate | private_kb | SEV2 | 100% | pass |  |
| co-sev3-region | private_kb | SEV3 | 100% | pass |  |
| co-payments-cpu | private_kb | SEV2 | 100% | pass |  |
| co-rollback-checks | private_kb | SEV4 | 100% | pass |  |
| co-postmortem-deadline | private_kb | SEV2 | 100% | pass |  |
| co-redis-root-cause | private_kb | SEV2 | 100% | pass |  |
| co-sev1-updates | private_kb | SEV1 | 100% | pass |  |
