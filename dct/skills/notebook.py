"""
dct.skills.notebook
Jupyter Notebook manipulation skill.
Read and edit .ipynb files.
"""

from __future__ import annotations
import json
import os
from dataclasses import dataclass


@dataclass
class NotebookResult:
    ok: bool
    message: str


def edit_notebook_cell(
    notebook_path: str, cell_index: int, new_source: str, edit_mode: str = "replace"
) -> NotebookResult:
    if not os.path.exists(notebook_path):
        return NotebookResult(False, f"Notebook {notebook_path} not found.")

    try:
        with open(notebook_path, "r", encoding="utf-8") as f:
            nb = json.load(f)

        cells = nb.get("cells", [])

        if edit_mode == "replace":
            if cell_index < 0 or cell_index >= len(cells):
                return NotebookResult(
                    False,
                    f"Cell index {cell_index} out of bounds (0-{len(cells) - 1}).",
                )
            cells[cell_index]["source"] = [
                line + "\n" for line in new_source.split("\n")
            ]
            cells[cell_index]["source"][-1] = cells[cell_index]["source"][-1].rstrip(
                "\n"
            )  # fixing last newline

        elif edit_mode == "insert":
            new_cell = {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": [line + "\n" for line in new_source.split("\n")],
            }
            if new_cell["source"]:
                new_cell["source"][-1] = new_cell["source"][-1].rstrip("\n")
            if cell_index < 0:
                cells.insert(0, new_cell)
            else:
                cells.insert(cell_index + 1, new_cell)

        elif edit_mode == "delete":
            if cell_index < 0 or cell_index >= len(cells):
                return NotebookResult(False, f"Cell index {cell_index} out of bounds.")
            cells.pop(cell_index)

        else:
            return NotebookResult(False, f"Invalid edit mode: {edit_mode}")

        nb["cells"] = cells
        with open(notebook_path, "w", encoding="utf-8") as f:
            json.dump(nb, f, indent=1)

        return NotebookResult(True, "Notebook updated successfully.")

    except Exception as e:
        return NotebookResult(False, f"Failed to edit notebook: {e}")
