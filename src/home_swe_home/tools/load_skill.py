"""Load a skill's full instructions on demand."""

from anima import Context, Service


class LoadSkillService(Service):
    """Mounted as ``ctx.load_skill`` and exposed as a model tool."""

    def __init__(self, ctx: Context):
        super().__init__(ctx, "load_skill")

    def __call__(self, *, name: str) -> str:
        """Load the named skill's full instructions into context.

        Args:
            name: Name of an available skill.
        """
        return str(self.ctx.skills.load(name))  # type: ignore[attr-defined]
