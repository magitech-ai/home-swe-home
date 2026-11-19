# Verified action references

Primary-source verification for action versions used in this repository's
workflows. Recorded 2026-11-19 with the GitHub CLI.

## actions/checkout

- Command: `gh api repos/actions/checkout/git/ref/tags/v5 --jq .ref`
- Observed output: `refs/tags/v5`
- Command: `gh api repos/actions/checkout/tags --jq '.[].name'`
- Observed output includes: `v7.0.1`, `v7.0.0`, `v7`, `v6.1.0`, ..., `v5.1.0`,
  `v5.0.1`, `v5.0.0`, `v5`.
- Therefore `actions/checkout@v5` is a valid major-version reference. The
  current major release is `v7`; `v4` is older.

Existing evidence in the repository: `.github/workflows/agent-review.yml` uses
`actions/checkout@v5` in two steps, and its runs complete successfully.

## Review rule

When a finding claims an external reference does not exist, the citation must
be verified against the owning system. A stale model belief is not evidence.
