# Reviewer model

The default independent reviewer is **`gemini-3.8-flash`** on the Gemini
provider. It is used by `hsh-review` when no model is supplied and by the
`Agent review` workflow.

## Decision evidence

The full decision is recorded in `agents-home/docs/DECISIONS.md` D-017
([agents-home PR #41](https://github.com/magitech-ai/agents-home/pull/41)).
The summary:

- The previous default, `google/gemma-4-31b-it` on NVIDIA, was retired after
  the audit record showed 2 timeouts in 6 live reviews.
- 3.8 Flash was chosen on the user's direction from official benchmarks. On our
  own 28-case B2 suite it scored 20/20 defect detection, zero false APPROVEs,
  zero injection approvals, one false positive (12.5%, within the D-013 bar),
  and no timeouts across 29 calls.
- Measured tradeoffs: ~11.9 s average latency and 3,763 completion tokens on
  the suite, versus ~1 s and 2,418 tokens for `gemini-3.1-flash-lite`. The B2
  suite is saturated at 100% detection, so external benchmark evidence decided
  the model choice.
- The author model defaults to `gemini-4-hydrogen`. The two models are
  different, satisfying the independent-review requirement; same-vendor review
  is an accepted tradeoff. Gemma and flash-lite remain validated alternatives.
