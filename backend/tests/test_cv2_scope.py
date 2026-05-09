"""
Test cv2 module-level import scope.

Verifies that cv2 is imported at module level, not inside functions,
to prevent UnboundLocalError when cv2 is used before assignment in nested scopes.

This test ensures that postprocess functions and other cv2-dependent
functions do not throw 'cannot access local variable cv2' errors.
"""

import ast
from pathlib import Path

import pytest

# Files that should have cv2 imported at module level
CV2_SCOPED_FILES = [
    "backend/app/services/tryon_v2/warp_engine.py",
    "backend/app/services/tryon_v2/garment_struct.py",
    "backend/app/services/catvton_infer.py",
    "backend/app/api/tryon_v2.py",
    "backend/app/services/virtual_tryon.py",
    "backend/scripts/training/data_annotator.py",
]

# Patterns that indicate cv2 is imported inside a function (BAD)
FUNCTION_IMPORT_PATTERNS = [
    r"^\s+import cv2",
    r"^\s+from cv2 import",
]


class FunctionImportVisitor(ast.NodeVisitor):
    """AST visitor to detect function-level cv2 imports."""

    def __init__(self):
        self.in_function = False
        self.function_level_imports = []
        self.current_function = None

    def visit_FunctionDef(self, node):
        old_in_function = self.in_function
        old_function = self.current_function
        self.in_function = True
        self.current_function = node.name
        self.generic_visit(node)
        self.in_function = old_in_function
        self.current_function = old_function

    def visit_AsyncFunctionDef(self, node):
        old_in_function = self.in_function
        old_function = self.current_function
        self.in_function = True
        self.current_function = node.name
        self.generic_visit(node)
        self.in_function = old_in_function
        self.current_function = old_function

    def visit_Import(self, node):
        if self.in_function:
            for alias in node.names:
                if alias.name == "cv2" or alias.name.startswith("cv2."):
                    self.function_level_imports.append(
                        (self.current_function, f"import {alias.name}", node.lineno)
                    )
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if (
            self.in_function
            and node.module
            and (node.module == "cv2" or node.module.startswith("cv2."))
        ):
            names = ", ".join(a.name for a in node.names)
            self.function_level_imports.append(
                (self.current_function, f"from {node.module} import {names}", node.lineno)
            )
        self.generic_visit(node)


class ModuleLevelImportVisitor(ast.NodeVisitor):
    """AST visitor to check if cv2 is imported at module level."""

    def __init__(self):
        self.module_level_imports = []
        self.in_function = False

    def visit_FunctionDef(self, node):
        old_in_function = self.in_function
        self.in_function = True
        self.generic_visit(node)
        self.in_function = old_in_function

    def visit_AsyncFunctionDef(self, node):
        old_in_function = self.in_function
        self.in_function = True
        self.generic_visit(node)
        self.in_function = old_in_function

    def visit_Import(self, node):
        if not self.in_function:
            for alias in node.names:
                if alias.name == "cv2" or alias.name.startswith("cv2."):
                    self.module_level_imports.append((alias.name, node.lineno))
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if (
            not self.in_function
            and node.module
            and (node.module == "cv2" or node.module.startswith("cv2."))
        ):
            names = ", ".join(a.name for a in node.names)
            self.module_level_imports.append((f"from {node.module} import {names}", node.lineno))
        self.generic_visit(node)


@pytest.mark.parametrize("file_path", CV2_SCOPED_FILES)
def test_cv2_not_imported_inside_functions(file_path):
    """Verify cv2 is NOT imported inside any function in the file."""
    project_root = Path(__file__).parent.parent.parent
    full_path = project_root / file_path

    if not full_path.exists():
        pytest.skip(f"File not found: {full_path}")

    source = full_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(full_path))

    visitor = FunctionImportVisitor()
    visitor.visit(tree)

    if visitor.function_level_imports:
        details = "\n".join(
            f"  - Line {f[2]}: {f[1]} in function '{f[0]}'" for f in visitor.function_level_imports
        )
        pytest.fail(
            f"Found cv2 imported inside functions in {file_path}:\n{details}\n\n"
            "cv2 should be imported at the module level, not inside functions."
        )


@pytest.mark.parametrize("file_path", CV2_SCOPED_FILES)
def test_cv2_imported_at_module_level(file_path):
    """Verify cv2 IS imported at module level in the file."""
    project_root = Path(__file__).parent.parent.parent
    full_path = project_root / file_path

    if not full_path.exists():
        pytest.skip(f"File not found: {full_path}")

    source = full_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(full_path))

    visitor = ModuleLevelImportVisitor()
    visitor.visit(tree)

    assert len(visitor.module_level_imports) > 0, (
        f"cv2 should be imported at module level in {file_path}. "
        "No module-level cv2 import found."
    )


def test_cv2_usable_in_functions():
    """Test that cv2 is usable in functions that use it.

    This test actually imports the modules and verifies cv2 functions work,
    which would fail with UnboundLocalError if cv2 were imported inside
    a try block and then used outside it.
    """
    # Test garment_struct functions that use cv2
    from PIL import Image

    from app.services.tryon_v2.garment_struct import (
        _fill_alpha_holes,
        _keep_largest_alpha_component,
        _smooth_alpha_boundary,
    )

    # Create a test RGBA image
    test_img = Image.new("RGBA", (100, 100), (255, 0, 0, 128))

    # These functions internally use cv2
    # If cv2 is not properly scoped, they will raise UnboundLocalError
    try:
        _keep_largest_alpha_component(test_img)
    except UnboundLocalError as e:
        pytest.fail(f"UnboundLocalError in _keep_largest_alpha_component: {e}")

    try:
        _smooth_alpha_boundary(test_img)
    except UnboundLocalError as e:
        pytest.fail(f"UnboundLocalError in _smooth_alpha_boundary: {e}")

    try:
        _fill_alpha_holes(test_img)
    except UnboundLocalError as e:
        pytest.fail(f"UnboundLocalError in _fill_alpha_holes: {e}")


def test_warp_engine_cv2_usable():
    """Test that warp_engine functions using cv2 don't raise UnboundLocalError."""
    import numpy as np
    from PIL import Image

    from app.services.tryon_v2.warp_engine import _person_foreground_mask, overlay_draping_from_ai

    # Create test images
    person_img = Image.new("RGB", (512, 768), (200, 150, 100))
    warp_result = Image.new("RGB", (512, 768), (100, 100, 100))
    ai_result = Image.new("RGB", (512, 768), (150, 150, 150))

    # Test _person_foreground_mask
    try:
        fg_mask = _person_foreground_mask(person_img)
        # Should return None or a valid mask, not raise UnboundLocalError
        assert fg_mask is None or isinstance(fg_mask, np.ndarray)
    except UnboundLocalError as e:
        pytest.fail(f"UnboundLocalError in _person_foreground_mask: {e}")

    # Test overlay_draping_from_ai (uses cv2 for erode)
    try:
        result, meta = overlay_draping_from_ai(warp_result, ai_result)
        assert result is not None
    except UnboundLocalError as e:
        pytest.fail(f"UnboundLocalError in overlay_draping_from_ai: {e}")


def test_catvton_infer_cv2_usable():
    """Test that catvton_infer functions using cv2 don't raise UnboundLocalError."""
    from PIL import Image

    from app.services.catvton_infer import create_polygon_body_mask

    # Create test image
    test_img = Image.new("RGB", (512, 768), (200, 150, 100))

    # Test create_polygon_body_mask (uses cv2.GaussianBlur when feather_radius > 0)
    try:
        mask = create_polygon_body_mask(test_img, "upper", feather_radius=2)
        assert mask is not None
    except UnboundLocalError as e:
        pytest.fail(f"UnboundLocalError in create_polygon_body_mask: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
