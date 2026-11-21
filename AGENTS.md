# Agent Guidelines

## Home-SWE-Home Architecture & Invariants

- `home-swe-home` is a small coding agent on **anima** (micro-kernel) and
  **magitech-harness** (the hardened turn engine). `context.py` calls
  `create_harness()`, mounts the app services, registers the Gemini adapter and
  the 15 mth `ToolDefinition`s, and assembles the prompt from
  `ctx.system_prompt` sections. The turn loop is mth's `ReactLoopAgent`
  (`ctx.agents.create` → `agent.followup` → `agent.when_idle`); it calls the
  model, runs requested tools, and repeats. Architecture, invariants, tool
  wiring, runtime config, and the editable harness are specified in
  [DESIGN.md](DESIGN.md).
- Home-first resolution, the repo map, skill integration and the improvement
  loop are designed in [DESIGN.md](DESIGN.md) and ADRs under `docs/adr/`.

## Shared Development Guidance

Shared standards, workflow and quality gates:
[agents-home AGENTS](../agents-home/AGENTS.md) → `knowledge/engineering-standards/index.md` (in `../agents-home`),
`docs/WORKFLOWS.md`, `knowledge/coding-standards/index.md` (in `../agents-home`), and `scripts/check_all.py`.

### Local checks
Run `python3 ../agents-home/scripts/check_all.py --fast` before committing;
CI runs the full gate.

## Home-SWE-Home-Specific References

- Issue tracker: GitHub Issues via `gh` CLI (`magitech-ai` organization).
- PR body contract: `Agent review` requires `Trigger issue: #N` and
  `Author model: <id>` in every PR body (`.github/PULL_REQUEST_TEMPLATE.md`).
- Triage labels: [docs/agents/triage-labels.md](docs/agents/triage-labels.md).
- Domain docs: `DESIGN.md` + [docs/adr/](docs/adr/).
- Improvement loop: `hsh-improve` drives one measured Propose–Probe–Compose cycle;
  `HOME_SWE_HOME_PROPOSER_MODEL` must be set. See
  [DESIGN.md](DESIGN.md#measuring-improvement).
- Adding a tool: [DESIGN.md](DESIGN.md#tools-as-mth-components) and the tests
  under `tests/unit/`.
