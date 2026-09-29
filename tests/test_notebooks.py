"""The committed notebooks must have been executed and contain no error output."""
import json
from pathlib import Path

import pytest

NOTEBOOKS = sorted((Path(__file__).resolve().parents[1] / "python" / "notebooks").glob("*.ipynb"))


def test_four_notebooks_exist():
    assert len(NOTEBOOKS) == 4


@pytest.mark.parametrize("path", NOTEBOOKS, ids=lambda p: p.name)
def test_notebook_was_executed_without_errors(path):
    nb = json.loads(path.read_text(encoding="utf-8"))
    code_cells = [c for c in nb["cells"] if c["cell_type"] == "code"]
    assert code_cells
    for cell in code_cells:
        assert cell.get("execution_count") is not None, f"{path.name}: a code cell was never executed"
        assert not [o for o in cell.get("outputs", []) if o.get("output_type") == "error"], f"{path.name}: error output"
