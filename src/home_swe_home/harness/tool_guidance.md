# Tool guidance

# Optional per-tool additions to the model-facing tool descriptions. Add a
# `## <tool_name>` section whose body is the guidance for that tool, e.g.:
#
#   ## run_command
#   Prefer short commands and check the reported exit code.
#
# Sections are keyed by the tool's registered name (the name passed to
# `super().__init__` in its Service). Unknown names are ignored. With no
# sections, tool descriptions are exactly the Service docstrings.
