"""PANTA multimodal document-intelligence evaluation suite."""

from .evaluator import evaluate_case
from .runner import EvaluationRunner
from .schema import SchemaValidationError, validate_case, validate_prediction

__all__ = [
    "EvaluationRunner",
    "SchemaValidationError",
    "evaluate_case",
    "validate_case",
    "validate_prediction",
]

__version__ = "0.1.0"
