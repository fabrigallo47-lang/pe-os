"""PAN-104 — email replies expose only the statement made by each message."""
from __future__ import annotations

import mailbox
import sys
import tempfile
import unittest
from email.message import EmailMessage
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from tools.extract_v2 import parse_source  # noqa: E402


def _message(*, sender: str, date: str, subject: str, body: str) -> EmailMessage:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = "deal@example.com"
    message["Date"] = date
    message["Subject"] = subject
    message.set_content(body)
    return message


class PAN104EmailReplyStrippingTests(unittest.TestCase):
    def test_eml_strips_quoted_reply_and_signature_before_chunking(self):
        message = _message(
            sender="Alice <alice@example.com>",
            date="Wed, 2 Sep 2026 10:00:00 +0000",
            subject="Re: Trading update",
            body=(
                "September revenue was EUR 3m.\n\n"
                "--\nAlice\n\n"
                "On Tue, 1 Sep 2026 at 09:00, Bob <bob@example.com> wrote:\n"
                "> August revenue was EUR 2m.\n"
            ),
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "reply.eml"
            path.write_bytes(message.as_bytes())
            chunks = parse_source(path)

        self.assertEqual([chunk.body for chunk in chunks], ["September revenue was EUR 3m."])
        self.assertNotIn("August revenue", chunks[0].body)
        self.assertNotIn("Alice", chunks[0].body)

    def test_mbox_keeps_each_statement_with_its_own_message_date(self):
        original = _message(
            sender="Bob <bob@example.com>",
            date="Tue, 1 Sep 2026 09:00:00 +0000",
            subject="Trading update",
            body="August revenue was EUR 2m.\n",
        )
        reply = _message(
            sender="Alice <alice@example.com>",
            date="Wed, 2 Sep 2026 10:00:00 +0000",
            subject="Re: Trading update",
            body=(
                "September revenue was EUR 3m.\n\n"
                "On Tue, 1 Sep 2026 at 09:00, Bob <bob@example.com> wrote:\n"
                "> August revenue was EUR 2m.\n"
            ),
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "thread.mbox"
            box = mailbox.mbox(path, create=True)
            try:
                box.add(original)
                box.add(reply)
                box.flush()
            finally:
                box.close()
            chunks = parse_source(path)

        self.assertEqual(
            [chunk.body for chunk in chunks],
            ["August revenue was EUR 2m.", "September revenue was EUR 3m."],
        )
        self.assertTrue(chunks[0].period_context["document_date"].startswith("2026-09-01"))
        self.assertTrue(chunks[1].period_context["document_date"].startswith("2026-09-02"))
        self.assertTrue(chunks[0].source_record["known_at"].startswith("2026-09-01"))
        self.assertTrue(chunks[1].source_record["known_at"].startswith("2026-09-02"))
        self.assertEqual(chunks[0].provenance["message_sender"], "Bob <bob@example.com>")
        self.assertEqual(chunks[1].provenance["message_sender"], "Alice <alice@example.com>")

    def test_html_only_reply_is_cleaned_after_visible_text_normalization(self):
        message = EmailMessage()
        message["From"] = "Alice <alice@example.com>"
        message["To"] = "deal@example.com"
        message["Date"] = "Wed, 2 Sep 2026 10:00:00 +0000"
        message["Subject"] = "Re: Trading update"
        message.set_content(
            """<html><body>
            <p>September revenue was EUR 3m.</p>
            <p>--<br>Alice</p>
            <blockquote>
              <p>On Tue, 1 Sep 2026 at 09:00, Bob &lt;bob@example.com&gt; wrote:</p>
              <p>August revenue was EUR 2m.</p>
            </blockquote>
            </body></html>""",
            subtype="html",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "reply.eml"
            path.write_bytes(message.as_bytes())
            chunks = parse_source(path)

        self.assertEqual([chunk.body for chunk in chunks], ["September revenue was EUR 3m."])


if __name__ == "__main__":
    unittest.main()
