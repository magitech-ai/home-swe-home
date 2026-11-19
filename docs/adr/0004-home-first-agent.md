# 0004. Make home-swe-home the home-first agent

Date: 2026-11-18
Status: accepted

## Context

`agents-home/README.md:4` says "Start agent sessions here when a task may span
multiple repositories." Today that is a convention relying on OpenCode loading
the root `AGENTS.md` and personal skill links; the pattern repo explicitly
labels itself exploratory and non-normative
(`agents-home-pattern/README.md:3`).

home-swe-home was previously documented as a standalone agent runnable from any cwd.
Its `InstructionsService.agents_md()` reads only the current directory's
`AGENTS.md`, so "which instructions apply?" was answered by wherever the user
happened to launch it. The editable harness added in PR #8 lives inside the
installed package, which cannot be the authoritative copy for a shared agent.

Evidence from this machine: `/home` and `/mnt/storage` are different
filesystems; the `agents-home` checkout at
`/mnt/storage/projects/magitech/agents-home` is 952 MB. A hardcoded checkout
under `~/.agents/` would put a large working repo into a config directory on
the wrong disk. `gh auth status` already has `admin:org`, `gist`, `repo` and
`workflow` scopes, but `magitech-ai/agents-home` is private and the org has no
template repository.

## Decision

home-swe-home is the agent run *from* `agents-home`. The home repo is always its
starting point; standalone any-cwd use is no longer the target.

Home resolution order:

1. `~/.agents/home-swe-home/config.toml` with an absolute `home_path` and repo
   identity — authoritative.
2. `AGENTS_HOME_PATH` environment override.
3. Name-based walk-up from cwd for a directory named `agents-home` containing
   `AGENTS.md`, `skills/` and the `## Other Repos` map.

`HOME_SWE_HOME_HARNESS_DIR` keeps its separate meaning: a candidate harness tree for
an improvement rollout.

When no home is found, a wizard performs the human-only steps: `gh auth login`
if needed, choose a local path (offer `~/.agents/agents-home`, always confirm),
scaffold from templates packaged in home-swe-home, offer `gh repo create --private`
and an initial push with explicit consent, then write the config. An existing
checkout skips onboarding entirely. Tokens are never written to home-swe-home's
config.

The home repo supplies the authoritative harness tree, canonical skills, the
curated repo map, shared `AGENTS.md` and GitHub workflow conventions.
Multi-repo work is map-driven: GitHub links or local directories resolve
through the map, missing checkouts are cloned as siblings only on confirmation,
map changes go through a PR, each target repo's `AGENTS.md` is layered into the
session, and each affected repo's own checks must pass before "done". One
context is used initially; no sub-agents until evidence demands isolation.

## Consequences

- The packaged `src/home_swe_home/harness/` files remain, but as **bootstrap
  templates** only — at runtime the home tree wins. This reverses part of PR
  #8's framing, not its files.
- The config file is small and lives in the `.agents` global config layer;
  the large checkout may live anywhere, including another filesystem.
- Symlinks in `~/.agents/skills` must remain symlinks; copying would duplicate
  a ~1 GB tree across disks.
- Fresh users need a GitHub account and a token with repo-creation scope for
  remote provisioning; that step is opt-in and confirmed, never automatic.
- Layered instructions and per-repo verification increase session context and
  wall time; this is the price of correct cross-repo behavior.
- Implementation is staged: home-mode foundation, then skills, then the
  external improvement loop.
