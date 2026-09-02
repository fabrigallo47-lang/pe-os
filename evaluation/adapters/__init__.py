"""Benchmark adapter registry."""

from __future__ import annotations

from .base import AdapterError, BenchmarkAdapter
from .public import (
    DocILEAdapter,
    DocVQAAdapter,
    EmailSumAdapter,
    NativeAdapter,
    OfficeComprehensionAdapter,
    OmniDocBenchAdapter,
    QAConvAdapter,
    SlideVQAAdapter,
    SpreadsheetBenchAdapter,
    SpreadsheetBench2Adapter,
    TikaFixtureAdapter,
)


_ADAPTER_TYPES: tuple[type[BenchmarkAdapter], ...] = (
    NativeAdapter,
    OfficeComprehensionAdapter,
    OmniDocBenchAdapter,
    DocILEAdapter,
    DocVQAAdapter,
    SlideVQAAdapter,
    SpreadsheetBenchAdapter,
    SpreadsheetBench2Adapter,
    QAConvAdapter,
    EmailSumAdapter,
    TikaFixtureAdapter,
)

ADAPTERS = {adapter_type.adapter_id: adapter_type() for adapter_type in _ADAPTER_TYPES}


def get_adapter(adapter_id: str) -> BenchmarkAdapter:
    try:
        return ADAPTERS[adapter_id]
    except KeyError as exc:
        raise AdapterError(
            f"Unknown adapter {adapter_id!r}; available: {', '.join(sorted(ADAPTERS))}"
        ) from exc


__all__ = ["ADAPTERS", "AdapterError", "BenchmarkAdapter", "get_adapter"]
