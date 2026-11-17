"""Calculate code quality metrics for Python files in a directory."""

import re
from pathlib import Path

from anima import Context, Service


class CodeMetricsService(Service):
    """Calculate code quality metrics for Python files in a directory.

    Returns lines of code, cyclomatic complexity estimates, and other metrics.
    Useful for tracking improvement over recursive turns.

    Args:
        path: Directory to analyze (defaults to '.').

    Returns:
        Summary statistics for all .py files found.
    """

    def __init__(self, ctx: Context):
        super().__init__(ctx, "code_metrics")

    def __call__(
        self,
        *,
        path: str = ".",
        read_files: set[str] | None = None,
    ) -> str:
        root = Path(path)
        py_files = list(root.rglob("*.py"))

        total_lines = 0
        blank_lines = 0
        comment_lines = 0
        function_count = 0
        class_count = 0
        file_count = 0
        complexity_total = 0

        complexity_keywords = {"if", "elif", "for", "while", "try", "except"}

        for py_file in py_files:
            file_count += 1
            try:
                text = py_file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            lines = text.splitlines()
            total_lines += len(lines)

            blank_lines += sum(1 for line in lines if line.strip() == "")
            comment_lines += sum(1 for line in lines if line.strip().startswith("#"))

            for line in lines:
                stripped = line.strip()
                if stripped.startswith("class "):
                    class_count += 1
                elif stripped.startswith("def ") and not line.startswith((" ", "\t")):
                    function_count += 1

            for keyword in complexity_keywords:
                complexity_total += len(re.findall(rf"\b{keyword}\b", text))

        metrics = {
            "file_count": file_count,
            "total_lines": total_lines,
            "blank_lines": blank_lines,
            "comment_lines": comment_lines,
            "net_lines": total_lines - blank_lines - comment_lines,
            "function_count": function_count,
            "class_count": class_count,
            "estimated_complexity": complexity_total,
        }

        return f"Code metrics for {path}:\n" + "\n".join(
            f"  {k}: {v}" for k, v in metrics.items()
        )
