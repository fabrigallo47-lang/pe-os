"""Adapters from public benchmark records to the PANTA evaluation contract."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from evaluation.io import read_cases, read_records
from evaluation.schema import validate_case

from .base import (
    AdapterError,
    BenchmarkAdapter,
    infer_format,
    infer_family,
    make_case,
    make_input,
    safe_id,
)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _first(record: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if record.get(key) is not None:
            return record[key]
    return default


def _path_value(value: Any, fallback: str) -> str:
    if isinstance(value, Mapping):
        value = _first(value, "path", "file_name", "filename", "name", default=fallback)
    return str(value if value is not None else fallback)


def _poly_to_bbox(poly: Any) -> list[float] | None:
    if not isinstance(poly, list) or len(poly) < 4:
        return None
    if len(poly) == 4 and all(isinstance(value, (int, float)) for value in poly):
        return [float(value) for value in poly]
    if len(poly) >= 8 and all(isinstance(value, (int, float)) for value in poly):
        xs = [float(poly[index]) for index in range(0, len(poly), 2)]
        ys = [float(poly[index]) for index in range(1, len(poly), 2)]
        return [min(xs), min(ys), max(xs), max(ys)]
    return None


class NativeAdapter(BenchmarkAdapter):
    adapter_id = "native"

    def adapt(self, source: Path, **_: Any) -> list[dict[str, Any]]:
        cases = read_cases(source)
        for case in cases:
            validate_case(case)
        return cases


class OfficeComprehensionAdapter(BenchmarkAdapter):
    adapter_id = "office_comprehension"

    def adapt(self, source: Path, *, dataset_root: Path | None = None,
              split: str = "public_test", version: str = "2026",
              options: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
        options = options or {}
        name = source.name.lower()
        default_track = str(options.get("track") or (
            "file_fidelity" if "fidelity" in name else "domain_qa"
        ))
        cases = []
        for index, record in enumerate(read_records(source)):
            original_id = str(record.get("id", index))
            files = _as_list(_first(record, "filepath", "reference_files", "files"))
            if not files:
                raise AdapterError(f"OCB record {original_id} has no filepath")
            inputs = [
                make_input(
                    f"file-{number + 1}",
                    _path_value(filepath, f"reference-{number + 1}"),
                    root=dataset_root,
                )
                for number, filepath in enumerate(files)
            ]
            assertions = _as_list(_first(record, "gold", "expected_assertions", default=[]))
            weights = _as_list(record.get("weights"))
            if weights and len(weights) == len(assertions):
                assertions = [
                    item if isinstance(item, Mapping) else {
                        "id": f"assertion-{number + 1}",
                        "text": str(item),
                        "weight": max(float(weights[number]), 1e-9),
                    }
                    for number, item in enumerate(assertions)
                ]
            track = str(record.get("track") or default_track)
            gold: dict[str, Any] = {"assertions": assertions}
            cases.append(make_case(
                test_id=f"ocb:{original_id}", benchmark_id="office_comprehension_bench",
                benchmark_version=version, original_id=original_id, split=split,
                task="semantic_qa", inputs=inputs,
                query=_first(record, "query", "question"), gold=gold,
                metrics=["assertion_recall", "answer_f1"], track=track,
                source_uri="https://github.com/microsoft/OfficeComprehensionBench",
                tags=[
                    value for value in (
                        track, str(record.get("feature", "")).strip(),
                        str(record.get("app_type", "")).strip(),
                    ) if value
                ],
            ))
        return cases


class DocILEAdapter(BenchmarkAdapter):
    adapter_id = "docile"

    def adapt(self, source: Path, *, dataset_root: Path | None = None,
              split: str = "validation", version: str = "1.0",
              options: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
        options = options or {}
        raw = json.loads(source.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and "annotations" in raw:
            raw = raw["annotations"]
        if not isinstance(raw, dict):
            raise AdapterError("DocILE adapter expects a docid -> fields JSON mapping")
        track = str(options.get("track", "KILE")).upper()
        documents_dir = Path(str(options.get("documents_dir", "pdfs")))
        cases = []
        for docid, annotations in raw.items():
            if not isinstance(annotations, list):
                continue
            fields = []
            evidence = []
            for annotation in annotations:
                bbox = annotation.get("bbox")
                locator = {
                    "type": "page", "page": int(annotation.get("page", 0)),
                    "index_base": 0,
                }
                if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
                    locator["bbox"] = [float(value) for value in bbox]
                field = {
                    "field_type": str(annotation.get("fieldtype") or "unknown"),
                    "value": annotation.get("text"),
                    "text": annotation.get("text"),
                    "input_id": "document",
                    "locator": locator,
                }
                if annotation.get("line_item_id") is not None:
                    field["line_item_id"] = annotation["line_item_id"]
                fields.append(field)
                evidence.append({"input_id": "document", "locator": locator, "role": "answer"})
            cases.append(make_case(
                test_id=f"docile:{track.lower()}:{docid}", benchmark_id="docile",
                benchmark_version=version, original_id=str(docid), split=split,
                task="field_extraction",
                inputs=[make_input("document", documents_dir / f"{docid}.pdf", root=dataset_root)],
                gold={"fields": fields, "native": {"track": track}}, evidence=evidence,
                metrics=["field_precision", "field_recall", "field_f1", "evidence_f1"],
                track=track, source_uri="https://github.com/rossumai/docile",
                tags=["business_document", "invoice_or_order", track.lower()],
            ))
        return cases


class OmniDocBenchAdapter(BenchmarkAdapter):
    adapter_id = "omnidocbench"

    def adapt(self, source: Path, *, dataset_root: Path | None = None,
              split: str = "public_test", version: str = "1.7",
              options: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
        cases = []
        if source.is_dir():
            for md_path in sorted(source.rglob("*.md")):
                original_id = md_path.stem
                cases.append(make_case(
                    test_id=f"omnidocbench:{original_id}", benchmark_id="omnidocbench",
                    benchmark_version=version, original_id=original_id, split=split,
                    task="document_parsing",
                    inputs=[make_input("page", md_path.with_suffix(".jpg"), root=dataset_root,
                                       format_name="pdf_page", family="document", role="rendered_page")],
                    gold={"content": md_path.read_text(encoding="utf-8")},
                    metrics=["content_similarity"], track="md2md",
                    source_uri="https://github.com/opendatalab/OmniDocBench",
                    tags=["pdf", "rendered_page", "markdown"],
                ))
            return cases

        raw = json.loads(source.read_text(encoding="utf-8"))
        samples = raw.get("samples", raw) if isinstance(raw, dict) else raw
        if not isinstance(samples, list):
            raise AdapterError("OmniDocBench adapter expects a JSON array or markdown directory")
        for index, sample in enumerate(samples):
            page_info = sample.get("page_info", {})
            image_path = page_info.get("image_path") or sample.get("image_path") or f"page-{index}.jpg"
            original_id = str(page_info.get("page_id") or Path(str(image_path)).stem or index)
            elements = []
            evidence = []
            content_parts = []
            for order, item in enumerate(sample.get("layout_dets", [])):
                element_type = str(item.get("category_type") or item.get("category_name") or "unknown")
                text = _first(item, "text", "content", "latex", "html")
                bbox = _poly_to_bbox(item.get("poly") or item.get("bbox"))
                locator = {"type": "image_region", "image_id": original_id,
                           "bbox": bbox or [0.0, 0.0, 0.0, 0.0]}
                element: dict[str, Any] = {
                    "type": element_type, "text": str(text) if text is not None else None,
                    "order": order, "input_id": "page", "locator": locator,
                    "metadata": {key: item[key] for key in ("language", "attribute") if key in item},
                }
                for key in ("html", "latex"):
                    if item.get(key) is not None:
                        element[key] = str(item[key])
                elements.append(element)
                evidence.append({"input_id": "page", "locator": locator, "role": "answer"})
                if text is not None:
                    content_parts.append(str(text))
            tags = [str(value) for key, value in page_info.items()
                    if key in {"language", "layout", "data_source", "type"} and value]
            cases.append(make_case(
                test_id=f"omnidocbench:{original_id}", benchmark_id="omnidocbench",
                benchmark_version=version, original_id=original_id, split=split,
                task="document_parsing",
                inputs=[make_input("page", image_path, root=dataset_root, format_name="pdf_page",
                                   family="document", role="rendered_page")],
                gold={"content": "\n".join(content_parts), "elements": elements,
                      "native": {"page_info": page_info}}, evidence=evidence,
                metrics=["content_similarity", "element_f1", "evidence_f1"], track="end2end",
                source_uri="https://github.com/opendatalab/OmniDocBench", tags=["pdf"] + tags,
            ))
        return cases


class DocVQAAdapter(BenchmarkAdapter):
    adapter_id = "docvqa"

    def adapt(self, source: Path, *, dataset_root: Path | None = None,
              split: str = "validation", version: str = "2026",
              options: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
        raw = json.loads(source.read_text(encoding="utf-8"))
        records = raw.get("data", raw) if isinstance(raw, dict) else raw
        if not isinstance(records, list):
            raise AdapterError("DocVQA adapter expects a JSON array or {data: [...]} object")
        options = options or {}
        images_dir = Path(str(options.get("images_dir", "images")))
        cases = []

        def page_inputs(record: Mapping[str, Any], doc_id: str) -> list[dict[str, Any]]:
            raw_pages = _first(
                record, "page_paths", "images", "document", "image", "image_path", "file_name"
            )
            pages = _as_list(raw_pages)
            if not pages:
                pages = [images_dir / doc_id / "page-001.png"]
            inputs = []
            for page_index, raw_page in enumerate(pages, start=1):
                fallback = str(images_dir / doc_id / f"page-{page_index:03d}.png")
                page_path = _path_value(raw_page, fallback)
                inputs.append(make_input(
                    f"page-{page_index}", page_path, root=dataset_root,
                    family="image", role="primary" if page_index == 1 else "reference",
                ))
            return inputs

        def add_case(record: Mapping[str, Any], *, question_id: Any, question: Any,
                     answers: Any, doc_id: str, category: str | None) -> None:
            original_id = str(question_id)
            tags = ["document_image", "visual_qa"]
            if category:
                tags.append(category)
            cases.append(make_case(
                test_id=f"docvqa:{original_id}", benchmark_id="docvqa",
                benchmark_version=version, original_id=original_id, split=split,
                task="visual_qa", inputs=page_inputs(record, doc_id), query=str(question),
                gold={"answers": _as_list(answers), "native": {"doc_id": doc_id}},
                metrics=["answer_exact_match", "anls", "answer_f1"],
                source_uri="https://www.docvqa.org/", tags=tags,
            ))

        for index, record in enumerate(records):
            doc_id = str(_first(record, "doc_id", "document_id", "id", default=index))
            category = record.get("doc_category")
            questions = record.get("questions")
            answers_block = record.get("answers")
            if isinstance(questions, Mapping) and isinstance(questions.get("question"), list):
                question_texts = questions["question"]
                question_ids = _as_list(questions.get("question_id"))
                answer_by_id: dict[str, Any] = {}
                positional_answers: list[Any] = []
                if isinstance(answers_block, Mapping):
                    answer_ids = _as_list(answers_block.get("question_id"))
                    positional_answers = _as_list(answers_block.get("answer"))
                    answer_by_id = {
                        str(answer_id): positional_answers[position]
                        for position, answer_id in enumerate(answer_ids)
                        if position < len(positional_answers)
                    }
                for position, question in enumerate(question_texts):
                    question_id = (
                        question_ids[position]
                        if position < len(question_ids)
                        else f"{doc_id}-q{position + 1}"
                    )
                    answer = answer_by_id.get(
                        str(question_id),
                        positional_answers[position] if position < len(positional_answers) else [],
                    )
                    add_case(
                        record, question_id=question_id, question=question,
                        answers=answer, doc_id=doc_id,
                        category=str(category) if category else None,
                    )
                continue
            original_id = _first(record, "questionId", "question_id", "id", default=index)
            add_case(
                record, question_id=original_id, question=record.get("question", ""),
                answers=_first(record, "answers", "answer", default=[]), doc_id=doc_id,
                category=str(category) if category else None,
            )
        return cases


class SlideVQAAdapter(BenchmarkAdapter):
    adapter_id = "slidevqa"

    def adapt(self, source: Path, *, dataset_root: Path | None = None,
              split: str = "validation", version: str = "1.0",
              options: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
        records = read_records(source)
        cases = []
        for index, record in enumerate(records):
            original_id = str(record.get("qa_id", index))
            deck_name = str(record.get("deck_name") or original_id)
            deck_path = Path(str((options or {}).get("decks_dir", "decks"))) / deck_name
            evidence = [
                {"input_id": "deck", "locator": {"type": "slide", "slide": int(page)}, "role": "answer"}
                for page in _as_list(record.get("evidence_pages"))
            ]
            answer = record.get("answer")
            cases.append(make_case(
                test_id=f"slidevqa:{original_id}", benchmark_id="slidevqa",
                benchmark_version=version, original_id=original_id, split=split,
                task="visual_qa",
                inputs=[make_input("deck", deck_path, root=dataset_root, format_name="slide_images",
                                   family="presentation")],
                query=record.get("question"), gold={"answers": _as_list(answer), "native": {
                    "arithmetic_expression": record.get("arithmetic_expression")}},
                evidence=evidence, metrics=["answer_exact_match", "anls", "evidence_f1"],
                source_uri="https://github.com/nttmdlab-nlp/SlideVQA",
                tags=[str(value) for value in (record.get("reasoning_type"), record.get("answer_type")) if value],
            ))
        return cases


class SpreadsheetBenchAdapter(BenchmarkAdapter):
    adapter_id = "spreadsheetbench"
    benchmark_id = "spreadsheetbench"
    source_uri = "https://github.com/RUCKBReasoning/SpreadsheetBench"

    def adapt(self, source: Path, *, dataset_root: Path | None = None,
              split: str = "public_test", version: str = "1.0",
              options: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
        options = options or {}
        cases = []
        for index, record in enumerate(read_records(source)):
            original_id = str(_first(record, "id", "task_id", "question_id", default=index))
            workbook = str(_first(
                record, "input_file", "filepath", "spreadsheet_path", "file",
                default=f"{original_id}.xlsx",
            ))
            base = dataset_root or source.parent
            candidate = Path(workbook)
            resolved = candidate if candidate.is_absolute() else base / candidate
            if candidate.suffix.lower() in {".xlsx", ".xlsm"}:
                workbooks = [resolved]
            elif resolved.is_dir():
                workbooks = sorted(resolved.glob("*_input.xls*"))
                if not workbooks:
                    raise AdapterError(
                        f"SpreadsheetBench record {original_id} has no *_input.xlsx files"
                    )
            else:
                raise AdapterError(
                    f"SpreadsheetBench record {original_id} points to a workbook directory; "
                    "provide --dataset-root so its test cases can be expanded"
                )
            answer = _first(record, "answer", "expected_answer")
            explicit_output = _first(
                record, "output_file", "expected_output", "golden_response_path"
            )
            category = str(record.get("category") or record.get("instruction_type") or "")
            metric = (
                "native:visual_checklist"
                if category.casefold() == "visualization"
                else "native:online_judge"
            )
            for workbook_number, workbook_path in enumerate(workbooks, start=1):
                expected_output: str | None = None
                if explicit_output:
                    output_path = Path(str(explicit_output))
                    expected_output = str(
                        output_path if output_path.is_absolute() else base / output_path
                    )
                elif workbook_path.name.endswith("_input.xlsx"):
                    expected_output = str(workbook_path.with_name(
                        workbook_path.name.replace("_input.xlsx", "_answer.xlsx")
                    ))
                native = {
                    "answer_position": record.get("answer_position"),
                    "category": category or None,
                    "expected_output": expected_output,
                }
                gold: dict[str, Any] = {"native": native, "expected_status": "success"}
                metrics = [metric]
                if answer is not None:
                    gold["answer"] = answer
                    metrics.append("structured_accuracy")
                suffix = f":{workbook_number}" if len(workbooks) > 1 else ""
                cases.append(make_case(
                    test_id=f"{self.benchmark_id}:{original_id}{suffix}",
                    benchmark_id=self.benchmark_id, benchmark_version=version,
                    original_id=f"{original_id}{suffix}", split=split,
                    task="spreadsheet_manipulation",
                    inputs=[make_input(
                        "workbook", workbook_path,
                        format_name=workbook_path.suffix.lstrip("."),
                    )],
                    query=_first(record, "instruction", "question", "query"), gold=gold,
                    metrics=metrics, source_uri=self.source_uri,
                    tags=[
                        value for value in ("excel", "agentic", "manipulation", category)
                        if value
                    ],
                ))
        return cases


class SpreadsheetBench2Adapter(SpreadsheetBenchAdapter):
    adapter_id = "spreadsheetbench2"
    benchmark_id = "spreadsheetbench2"
    source_uri = "https://github.com/RUCKBReasoning/SpreadsheetBench-2"


class QAConvAdapter(BenchmarkAdapter):
    adapter_id = "qaconv"

    def adapt(self, source: Path, *, dataset_root: Path | None = None,
              split: str = "public_test", version: str = "1.1",
              options: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
        options = options or {}
        documents_path = Path(str(options.get("documents", "article_segment.json")))
        if dataset_root and not documents_path.is_absolute():
            documents_path = dataset_root / documents_path
        cases = []
        for index, record in enumerate(read_records(source)):
            original_id = str(record.get("id", index))
            segment_id = str(record.get("article_segment_id") or record.get("article_full_id") or original_id)
            answers = _as_list(record.get("answers"))
            if answers:
                gold: dict[str, Any] = {"answers": answers}
                metrics = ["answer_exact_match", "answer_f1"]
            else:
                gold = {"unanswerable": True, "expected_status": "abstained"}
                metrics = ["status_accuracy"]
            cases.append(make_case(
                test_id=f"qaconv:{original_id}", benchmark_id="qaconv",
                benchmark_version=version, original_id=original_id, split=split,
                task="semantic_qa",
                inputs=[make_input("thread", documents_path, format_name="email_thread", family="email",
                                   selector={"article_segment_id": segment_id})],
                query=record.get("question"), gold=gold, metrics=metrics,
                source_uri="https://github.com/salesforce/QAConv",
                tags=["business_email", "conversation", "unanswerable" if not record.get("answers") else "answerable"],
            ))
        return cases


class EmailSumAdapter(BenchmarkAdapter):
    adapter_id = "emailsum"

    def adapt(self, source: Path, *, dataset_root: Path | None = None,
              split: str = "public_test", version: str = "1.0",
              options: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
        cases = []
        for index, record in enumerate(read_records(source)):
            original_id = str(_first(record, "id", "thread_id", default=index))
            summary = _first(record, "summary", "long_summary", "short_summary")
            summaries = _as_list(_first(record, "summaries", default=summary))
            thread_path = str(_first(record, "path", "thread_path", default=f"threads/{original_id}.json"))
            cases.append(make_case(
                test_id=f"emailsum:{original_id}", benchmark_id="emailsum",
                benchmark_version=version, original_id=original_id, split=split,
                task="summarization",
                inputs=[make_input("thread", thread_path, root=dataset_root,
                                   format_name="email_thread", family="email")],
                query="Summarize the email thread.", gold={"answers": summaries},
                metrics=["rouge1", "rouge2", "rouge_l"],
                source_uri="https://github.com/ZhangShiyue/EmailSum",
                tags=["email", "thread", "summarization"],
            ))
        return cases


class TikaFixtureAdapter(BenchmarkAdapter):
    adapter_id = "tika_fixtures"

    def adapt(self, source: Path, *, dataset_root: Path | None = None,
              split: str = "smoke", version: str = "4.x",
              options: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
        cases = []
        for index, record in enumerate(read_records(source)):
            original_id = str(record.get("id", index))
            filepath = str(_first(record, "file", "filepath", default=original_id))
            fields = [
                {"name": str(name), "value": value}
                for name, value in (record.get("expected_metadata") or {}).items()
            ]
            gold: dict[str, Any] = {"expected_status": record.get("expected_status", "success")}
            metrics = ["status_accuracy"]
            if record.get("expected_text") is not None:
                gold["content"] = str(record["expected_text"])
                metrics.append("content_similarity")
            if fields:
                gold["fields"] = fields
                metrics += ["field_precision", "field_recall", "field_f1"]
            cases.append(make_case(
                test_id=f"tika:{original_id}", benchmark_id="apache_tika_fixtures",
                benchmark_version=version, original_id=original_id, split=split,
                task="parsing", inputs=[make_input("file", filepath, root=dataset_root)],
                gold=gold, metrics=metrics, source_uri="https://github.com/apache/tika",
                tags=["parser_regression", infer_format(filepath), infer_family(infer_format(filepath))],
            ))
        return cases
