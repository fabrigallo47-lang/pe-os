"""PAN-104 -- strip quoted reply history and signatures before chunking.

parse_email previously chunked the full message body including quoted
prior messages in a reply thread. In a real .mbox export, each later
reply's body contains the entire earlier message inline -- without
stripping, that earlier statement gets re-extracted once per reply, each
time attributed to the later reply's own known_at instead of the message
that actually made it. Verified here against a real multi-message mbox
thread built the way the mailbox stdlib module itself would produce one,
not a hand-rolled minimal fixture.
"""

import mailbox
import sys
import tempfile
import unittest
from email.message import EmailMessage
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.extract_v2 import parse_email  # noqa: E402


class PAN104EmailQuoteStrippingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temporary.cleanup()

    def _mbox_path(self, *messages: EmailMessage) -> Path:
        path = Path(self.temporary.name) / "thread.mbox"
        box = mailbox.mbox(str(path), create=True)
        try:
            box.lock()
            for message in messages:
                box.add(mailbox.mboxMessage(message))
            box.flush()
        finally:
            box.close()
        return path

    def test_later_reply_does_not_resurface_the_original_message_as_a_new_chunk(self):
        original = EmailMessage()
        original["From"] = "seller@keystone.example"
        original["To"] = "deal@example.com"
        original["Date"] = "Tue, 1 Sep 2026 09:00:00 +0000"
        original["Subject"] = "Q2 revenue"
        original.set_content("Revenue was EUR 20m in FY2025A.")

        reply = EmailMessage()
        reply["From"] = "deal@example.com"
        reply["To"] = "seller@keystone.example"
        reply["Date"] = "Tue, 1 Sep 2026 10:30:00 +0000"
        reply["Subject"] = "Re: Q2 revenue"
        reply.set_content(
            "Confirmed, thanks.\n\n"
            "On Tue, Sep 1, 2026 at 9:00 AM, seller@keystone.example wrote:\n"
            "> Revenue was EUR 20m in FY2025A.\n"
        )

        path = self._mbox_path(original, reply)
        chunks = parse_email(path)
        self.assertEqual(len(chunks), 2)

        original_chunk, reply_chunk = chunks
        self.assertIn("Revenue was EUR 20m in FY2025A.", original_chunk.body)
        self.assertTrue(original_chunk.period_context["document_date"].startswith("2026-09-01T09"))

        self.assertIn("Confirmed, thanks.", reply_chunk.body)
        self.assertNotIn("Revenue was EUR 20m", reply_chunk.body)
        self.assertTrue(reply_chunk.period_context["document_date"].startswith("2026-09-01T10"))
        self.assertTrue(reply_chunk.provenance["quoted_reply_history_stripped"])
        self.assertFalse(original_chunk.provenance["quoted_reply_history_stripped"])

    def test_plain_email_with_no_quoted_history_is_left_untouched(self):
        message = EmailMessage()
        message["From"] = "ceo@example.com"
        message["Date"] = "Tue, 1 Sep 2026 09:30:00 +0000"
        message["Subject"] = "Trading update"
        message.set_content("August revenue was EUR 2m.")

        path = self._mbox_path(message)
        chunks = parse_email(path)
        self.assertEqual(len(chunks), 1)
        self.assertIn("August revenue was EUR 2m.", chunks[0].body)
        self.assertFalse(chunks[0].provenance["quoted_reply_history_stripped"])

    def test_pure_forward_with_no_new_commentary_is_not_emptied_out(self):
        message = EmailMessage()
        message["From"] = "analyst@example.com"
        message["Date"] = "Tue, 1 Sep 2026 09:30:00 +0000"
        message["Subject"] = "Fwd: model"
        message.set_content(
            "---------- Forwarded message ---------\n"
            "From: seller@keystone.example\n"
            "Date: Mon, 31 Aug 2026 08:00:00 +0000\n\n"
            "EBITDA margin is 13.8%.\n"
        )

        path = self._mbox_path(message)
        chunks = parse_email(path)
        self.assertEqual(len(chunks), 1)
        self.assertIn("13.8%", chunks[0].body)


if __name__ == "__main__":
    unittest.main()
