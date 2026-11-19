# Review standard

This is the contract given to the independent Stage-A reviewer. It is
deliberately short and local so the reviewer does not depend on another
repository being checked out.

## Scope of judgement

Judge the change against the issue's acceptance criteria, this file, the repo's
`AGENTS.md`, and primary documentation for any external contract the change
touches. Do not judge style preferences that are not documented rules. Do not
assume any verification claim made by the author is true; CI is the authority
for tests.

## Non-negotiables

1. **Acceptance criteria are met.** Every "Done when" item in the issue is
   satisfied by the diff, with evidence.
2. **Contract fidelity.** Use the documented contract exactly at every
   boundary — field names, shapes, value domains, HTTP methods and upstream
   terminology. Invented or "close enough" shapes are blockers. This is the
   general rule recorded as D-009 in the agents-home decision log.
3. **Tests cover the behaviour change.** A change in behaviour has a matching
   test; the repo enforces 100% statement and branch coverage.
4. **Scope is respected.** Only the files the issue names are changed.
5. **Human merge is preserved.** The reviewer does not merge. A green light is
   a required check, not an autorisation to bypass branch protection.
6. **Different-model review.** A reviewer must never use the same model as the
   author; the CLI fails closed when they match.

## Verdict

`APPROVE` only when there are no findings. Any blocker or major finding is
`REQUEST_CHANGES`. Cite evidence for every finding (a file and line from the
diff, or a documented rule). If the material is insufficient to decide, request
changes and say what is missing.
