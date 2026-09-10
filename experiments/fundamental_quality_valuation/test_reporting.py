from __future__ import annotations

import ast
from pathlib import Path


ORIGINAL_STAGE_A_TESTS = Path("tests/test_fundamental_stage_a.py")
ORIGINAL_STAGE_B_TESTS = Path("tests/test_fundamental_stage_b.py")
CORRECTION_TESTS = Path("tests/test_fundamental_final_review_correction.py")


def collected_test_count(path: Path) -> int:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    total = 0
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.name.startswith("test_"):
            continue
        cases = 1
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            function = decorator.func
            if not isinstance(function, ast.Attribute) or function.attr != "parametrize":
                continue
            if len(decorator.args) < 2:
                raise ValueError(f"Uncountable pytest parametrization in {path}:{node.lineno}")
            values = ast.literal_eval(decorator.args[1])
            cases *= len(values)
        total += cases
    return total


def targeted_test_reporting(root: Path) -> dict[str, int]:
    stage_a = collected_test_count(root / ORIGINAL_STAGE_A_TESTS)
    stage_b = collected_test_count(root / ORIGINAL_STAGE_B_TESTS)
    correction = collected_test_count(root / CORRECTION_TESTS)
    original = stage_a + stage_b
    return {
        "original_stage_a": stage_a,
        "original_stage_b": stage_b,
        "original_targeted_tests": original,
        "correction_regression_tests": correction,
        "current_total_targeted_tests": original + correction,
    }
