# 0005. Conformant skill loading with alias deduplication

Date: 2026-11-18
Status: accepted

## Context

The shared collection has 33 skills, all passing the agentskills.io hard rules
(`name` 1–64 lowercase/hyphens, matching the directory, `description` 1–1024
chars). The local validator also enforces `.agents` protocol `references/AGENTS.md`
indexes, which agentskills.io does **not** require, so "100% valid" is a
narrower claim than full conformance.

Two non-spec frontmatter keys are widespread: `disable-model-invocation` (17
skills) and `argument-hint` (2). Primary-source research shows both are Claude
Code keys, not Matt Pocock inventions: `disable-model-invocation` hides a skill
from the model's catalog and blocks model-driven invocation while preserving
human invocation, and agentskills.io's own client guide names it as the example
of catalog filtering; `argument-hint` is a pure autocomplete hint with no
effect on loading or parsing. One genuine spec drift exists: `skills/pr/SKILL.md`
has `metadata.credits` as a nested map, while the spec requires string→string.

On this machine `~/.agents/skills` has 69 entries: 36 symlinks (33 to
`agents-home/skills`, 3 to omarchy skills) and 33 real directories. Across all
discovery roots there are 114 records but only 69 unique names and 69 unique
`SKILL.md` hashes — no two different skills share a name. tiktoken
`o200k_base` measures 4,101 tokens for all name+description pairs and 7,209 for
the full catalog with absolute paths.

No primary-source client deduplicates by content hash. Claude Code collapses
symlinks by resolved target; the agentskills.io client guide sets project >
user precedence, allows first- or last-found within a scope, and says to warn
when a skill is shadowed. Slash-namespaced skills are an unadopted RFC.

## Decision

- Author format: the six spec fields. Honor `disable-model-invocation` as a
  catalog filter with explicit `/skill <name>` activation; parse and discard
  `argument-hint` leniently; do not hard-fail on unknown fields. Fix only the
  `pr` metadata type drift.
- Discovery roots: `agents-home/skills/` (native/client scope, authoritative),
  `~/.agents/skills/` (cross-client user scope), `<project>/.agents/skills/`
  (project-local). No `~/.magecode/skills`.
- Deduplicate in two passes: canonicalize by `Path.resolve()` to collapse
  aliases, then key by `name` with project > user and last-found within a
  scope. Emit a warning naming both the kept and shadowed absolute paths.
  Do not dedup by content hash and do not introduce namespacing.
- Genuine name collisions resolve by that precedence plus warning.
- Project-level skills are default-deny: load only after the user explicitly
  trusts that project, because skills can carry executable scripts.
- The catalog contains `name` + `description` only — no paths, no cap, no
  truncation. The ~4.1k-token cost for 69 skills is accepted; a later
  seeker-rune component will address smart selection. Session activations are
  deduplicated so one skill is never injected twice.

## Consequences

- The dominant local "duplication" is symlink aliasing and disappears at
  discovery; users are not asked to clean up a working setup.
- Shadow warnings are a differentiator: most clients do not emit them.
- Descriptions stay intact, preserving activation semantics; catalog cost
  grows linearly with installed skills and will be addressed by a separate
  component rather than by truncation.
- Default-deny for project skills adds a trust prompt when entering an
  untrusted checkout.
- Strict third-party validators that reject unknown frontmatter keys will
  still reject these skills; conformance here means author format plus client
  behavior, not passing those validators.
