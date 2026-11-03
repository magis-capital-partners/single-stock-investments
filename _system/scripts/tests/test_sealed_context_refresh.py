"""Include the context producer's seal regressions in the central CI suite."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_theme_panel import (
    test_sealed_inline_context_is_moved_only_with_exact_builder_binding,
    test_sealed_model_context_refresh_does_not_edit_model,
    test_sealed_sidecar_context_remains_reportable_and_linted,
)

__all__ = [
    'test_sealed_inline_context_is_moved_only_with_exact_builder_binding',
    'test_sealed_model_context_refresh_does_not_edit_model',
    'test_sealed_sidecar_context_remains_reportable_and_linted',
]
