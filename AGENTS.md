# Agent Guidelines

## Home-SWE-Home Architecture & Invariants

- `home-swe-home` is a small coding agent on anima. Every capability is an anima
  `Service` mounted by `src/home_swe_home/context.py` (`AGENT_SERVICES`); the loop
  calls the model, runs requested tools, and repeats. Architecture, invariants,
  tool wiring, runtime config, and the editable harness are specified in
  [DESIGN.md](DESIGN.md).
- Home-first resolution, the repo map, skill integration and the improvement
  loop are designed in [DESIGN.md](DESIGN.md) and ADRs under `docs/adr/`.

## Shared Development Guidance

Shared standards, workflow and quality gates:
[agents-home AGENTS](../agents-home/AGENTS.md) → `docs/ENGINEERING.md`,
`docs/WORKFLOWS.md`, `CODING_STANDARDS.md`, and `scripts/check_all.py`.

### Local checks
Run `python3 ../agents-home/scripts/check_all.py --fast` before committing;
CI runs the full gate.

## Home-SWE-Home-Specific References

- Issue tracker: GitHub Issues via `gh` CLI (`magitech-ai` organization).
- Triage labels: [docs/agents/triage-labels.md](docs/agents/triage-labels.md).
- Domain docs: `DESIGN.md` + [docs/adr/](docs/adr/).
- Adding a tool: [DESIGN.md](DESIGN.md#tools-as-anima-components) and the tests
  under `tests/unit/`.
