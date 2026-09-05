"""Connected native-file tests. Every fixture lives in a temporary case vault."""
import hashlib
import asyncio
import json
import logging
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "backend" / "dynamics"))

from fastapi import FastAPI, HTTPException
import httpx
import app.v20_router as router
logging.getLogger('httpx').setLevel(logging.WARNING)
from app.source_documents import resolve_document
from source_document_fixtures import build_fixture_case


class ApiClient:
    def __init__(self, app):
        self.app = app

    def get(self, url, **kwargs):
        async def request():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://testserver") as client:
                return await client.get(url, **kwargs)
        return asyncio.run(request())


class SourceDocumentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.fixture = build_fixture_case(self.root)
        self.previous = {key: getattr(router, key) for key in ("VAULT", "CASE_PIPELINE_ROOT", "PIPELINE_OUT")}
        router.VAULT = self.root / "vault"
        router.CASE_PIPELINE_ROOT = self.root / "cases"
        router.PIPELINE_OUT = self.root / "legacy"
        app = FastAPI()
        app.include_router(router.v20)
        self.client = ApiClient(app)

    def tearDown(self):
        for key, value in self.previous.items():
            setattr(router, key, value)
        self.temp.cleanup()

    def citation(self, filename):
        return next(item for item in self.fixture["citations"] if item["filename"] == filename)

    def descriptor(self, filename, **overrides):
        item = self.citation(filename)
        params = {"source_id": item["sourceId"], "source_version_id": item["sourceVersionId"],
                  "locator": item["locator"], "claim_id": item["claimId"], **overrides}
        return self.client.get("/api/v20/cases/CASE-1/source-document", params=params)

    def test_pdf_opens_exact_page_and_only_uniquely_matching_quote(self):
        result = self.descriptor("company.pdf")
        self.assertEqual(result.status_code, 200, result.text)
        data = result.json()
        self.assertEqual(data["position"]["page"], 2)
        self.assertEqual(data["position"]["status"], "LOCATED")
        view = self.client.get(data["view_url"])
        self.assertEqual(view.status_code, 200, view.text[:200])
        self.assertIn('alt="Original page 2"', view.text)
        self.assertIn("Cited passage highlighted", view.text)
        self.assertIn('id="selection" style="position:absolute;top:', view.text)
        self.assertIn("frame-ancestors 'self'", view.headers["content-security-policy"])
        self.assertEqual(self.descriptor("company.pdf", locator="p99").status_code, 422)
        no_claim = self.descriptor("company.pdf", claim_id="WRONG").json()
        self.assertIn("No exact passage highlight", self.client.get(no_claim["view_url"]).text)

    def test_workbook_locates_cells_and_keeps_formula_without_recalculation(self):
        result = self.descriptor("financing.xlsx")
        self.assertEqual(result.status_code, 200, result.text)
        data = result.json()
        self.assertEqual(data["position"]["bounds"], [2, 2, 3, 2])
        view = self.client.get(data["view_url"])
        self.assertIn('class="selected" aria-label="B2">5</td>', view.text)
        self.assertIn("=B2*2", view.text)
        self.assertIn("No cached value", view.text)
        for locator in ("Missing!B2", "Financing Plan!B900", "Financing Plan!C3:B2"):
            self.assertEqual(self.descriptor("financing.xlsx", locator=locator).status_code, 422)
        rows = self.descriptor("financing.xlsx", locator="financing.xlsx::Financing Plan!2:3").json()
        self.assertEqual(rows["position"]["bounds"], [1, 2, 3, 3])

    def test_text_and_transcript_preserve_passage_and_escape_source_markup(self):
        text = self.descriptor("customer.txt").json()
        view = self.client.get(text["view_url"])
        self.assertIn('class="text-line selected" id="selection"><span>2</span>', view.text)
        self.assertIn("&lt;script&gt;", view.text)
        self.assertNotIn("<script>", view.text)
        transcript = self.descriptor("call.srt").json()
        self.assertEqual(transcript["position"]["start"], 6)
        self.assertEqual(transcript["position"]["end"], 7)
        self.assertIn("Senior delivery hires", self.client.get(transcript["view_url"]).text)
        wrong_cue = self.descriptor("call.srt", locator="call.srt::cue:7:00:03:12.000-->00:03:29.000").json()
        self.assertEqual(wrong_cue["position"]["status"], "UNRESOLVED")
        wrong_end = self.descriptor("call.srt", locator="call.srt::cue:2:00:03:12.000-->00:03:40.000").json()
        self.assertEqual(wrong_end["position"]["status"], "UNRESOLVED")

    def test_word_uses_extractor_block_numbering(self):
        from tools.extract_v2_physical import parse_docx
        chunks = parse_docx(router.VAULT / "inbox" / "note.docx")
        self.assertIn("blocks:", chunks[0].locator)
        result = self.descriptor("note.docx")
        self.assertEqual(result.status_code, 200, result.text)
        view = self.client.get(result.json()["view_url"])
        self.assertEqual(view.status_code, 200, view.text[:100])
        self.assertIn("| Deployment | Confirmed |", view.text)
        self.assertIn('class="text-line selected" id="selection"><span>2</span>', view.text)

    def test_audio_seeks_original_bytes_and_supports_native_range_requests(self):
        data = self.descriptor("recording.wav").json()
        self.assertEqual(data["position"]["start"], 1)
        view = self.client.get(data["view_url"])
        self.assertIn("#t=1.0,2.0", view.text)
        original = (router.VAULT / "inbox" / "recording.wav").read_bytes()
        for header, expected in (("bytes=0-15", original[:16]), ("bytes=-12", original[-12:]), ("bytes=20-", original[20:])):
            response = self.client.get(data["download_url"], headers={"Range": header})
            self.assertEqual(response.status_code, 206)
            self.assertEqual(response.content, expected)
        for header in ("bytes=900000-", "bytes=-0", "bytes=4-1", "bytes=0-2,5-9"):
            self.assertEqual(self.client.get(data["download_url"], headers={"Range": header}).status_code, 416)
        self.assertEqual(self.descriptor("recording.wav", locator="00:00:02–00:00:01").status_code, 422)

    def test_download_is_byte_identical_and_version_changes_fail_closed(self):
        data = self.descriptor("company.pdf").json()
        result = self.client.get(data["download_url"])
        self.assertEqual(result.content, (router.VAULT / "inbox" / "company.pdf").read_bytes())
        self.assertEqual("sha256:" + hashlib.sha256(result.content).hexdigest(), data["source_version_id"])
        self.assertIn("attachment", result.headers["content-disposition"])
        self.assertIn("no-store", result.headers["cache-control"])
        (router.VAULT / "inbox" / "company.pdf").write_bytes(b"a newer file with the same name")
        self.assertEqual(self.descriptor("company.pdf").status_code, 409)
        self.assertEqual(self.client.get(data["download_url"]).status_code, 409)
        self.assertEqual(self.descriptor("company.pdf", source_version_id="sha256:" + "a" * 64).status_code, 404)
        self.assertEqual(self.descriptor("company.pdf", source_version_id="SV-LEGACY").status_code, 422)

    def test_no_cross_case_source_substitution_or_path_escape(self):
        self.assertEqual(self.descriptor("company.pdf", source_id="OTHER").status_code, 404)
        item = self.citation("customer.txt")
        with self.assertRaises(HTTPException) as error:
            resolve_document(router.VAULT, self.fixture["records"], "OTHER-CASE", item["sourceId"], item["sourceVersionId"])
        self.assertEqual(error.exception.status_code, 404)
        with self.assertRaises(HTTPException) as error:
            router._original_source_document("..", item["sourceId"], item["sourceVersionId"])
        self.assertEqual(error.exception.status_code, 400)
        path = router.VAULT / "inbox" / "customer.txt"
        outside = self.root / "outside.txt"
        path.rename(outside)
        path.symlink_to(outside)
        self.assertEqual(self.descriptor("customer.txt").status_code, 404)
        records = json.loads(json.dumps(self.fixture["records"]))
        record = next(row for row in records if row["source_envelope"]["source_id"] == item["sourceId"])
        record["source_envelope"]["stored_filename"] = "../../outside.txt"
        with self.assertRaises(HTTPException):
            resolve_document(router.VAULT, records, "CASE-1", item["sourceId"], item["sourceVersionId"])

    def test_missing_location_opens_original_with_explicit_limit(self):
        for filename in ("company.pdf", "financing.xlsx", "customer.txt", "recording.wav"):
            data = self.descriptor(filename, locator="").json()
            self.assertEqual(data["position"]["status"], "UNRESOLVED")
            self.assertIn("without a verified passage selection", self.client.get(data["view_url"]).text)

    def test_durable_claim_retains_cited_version_and_original_span(self):
        claim = {**self.fixture["claims"][0], "statement": "Synthetic statement", "known_at": "2026-09-05"}
        router._persist_claims_to_vault("CASE-1", [claim], "company.pdf")
        path = next((router.VAULT / "deals" / "CASE-1" / "claims").glob("*.md"))
        data = router._read_frontmatter(path)
        self.assertEqual(data["source-version-id"], claim["source_version_id"])
        self.assertEqual(data["source"]["source_version_id"], claim["source_version_id"])
        self.assertEqual(data["source"]["locator"], claim["locator"])
        self.assertEqual(data["verbatim-or-lossless-span"], claim["verbatim_or_lossless_span"])


if __name__ == "__main__":
    unittest.main()
