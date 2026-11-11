"""No state may be hard-coded into application logic.

The platform covers all 36 states and the FCT; Adamawa was only the first validation area.
This scans the backend package and the web app for state names used as literal values
(not documentation): selecting, filtering or defaulting by a state name must come from data
or from the user.
"""

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

STATES = {
    "abia", "adamawa", "akwa ibom", "anambra", "bauchi", "bayelsa", "benue", "borno",
    "cross river", "delta", "ebonyi", "edo", "ekiti", "enugu", "gombe", "imo", "jigawa",
    "kaduna", "kano", "katsina", "kebbi", "kogi", "kwara", "lagos", "nasarawa", "niger",
    "ogun", "ondo", "osun", "oyo", "plateau", "rivers", "sokoto", "taraba", "yobe",
    "zamfara", "fct", "abuja", "federal capital territory", "abuja federal capital territory",
}  # fmt: skip


# Legitimate uses of a word that is also a state name.
ALLOWED = {
    ("backend/connectly/models/directory.py", "Edo"),  # the Edo language (ISO 639-3 "bin")
}


def _docstring_nodes(tree: ast.AST) -> set[int]:
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                ids.add(id(body[0].value))
    return ids


def test_backend_code_has_no_state_name_literals():
    found = []
    for path in sorted((REPO / "backend" / "connectly").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docs = _docstring_nodes(tree)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in docs
                and node.value.strip().lower() in STATES
                and (str(path.relative_to(REPO)), node.value) not in ALLOWED
            ):
                found.append(f"{path.relative_to(REPO)}:{node.lineno} {node.value!r}")
    assert found == []


def test_web_app_has_no_state_name_literals():
    pattern = re.compile(r"""(["'`])([A-Za-z ]+)\1""")
    found = []
    for path in sorted((REPO / "frontend" / "src").rglob("*.ts*")):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("//"):
                continue
            for m in pattern.finditer(line):
                if m.group(2).strip().lower() in STATES:
                    found.append(f"{path.relative_to(REPO)}:{n} {m.group(0)}")
    assert found == []
