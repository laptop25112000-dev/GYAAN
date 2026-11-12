import base64
import io
import unittest
import zipfile
import zlib

from file_service import MAX_FILE_BYTES, build_file_context, normalize_attachments


def payload(name, content, mime_type="text/plain"):
    encoded = base64.b64encode(content).decode("ascii")
    return {"name": name, "type": mime_type, "data": f"data:{mime_type};base64,{encoded}"}


class FileServiceTest(unittest.TestCase):
    def test_text_file_becomes_context(self):
        attachments, errors = normalize_attachments([
            payload("notes.txt", b"Important project notes")
        ])

        self.assertEqual(errors, [])
        self.assertEqual(attachments[0]["kind"], "text")
        self.assertIn("Important project notes", build_file_context(attachments))

    def test_csv_file_has_readable_preview(self):
        attachments, errors = normalize_attachments([
            payload("data.csv", b"name,score\nDivyansh,99\n", "text/csv")
        ])

        self.assertEqual(errors, [])
        self.assertIn("Divyansh,99", attachments[0]["preview"])

    def test_zip_file_lists_contents(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("inside.txt", "hello")

        attachments, errors = normalize_attachments([
            payload("bundle.zip", buffer.getvalue(), "application/zip")
        ])

        self.assertEqual(errors, [])
        self.assertEqual(attachments[0]["kind"], "archive")
        self.assertIn("inside.txt", attachments[0]["preview"])

    def test_pdf_file_extracts_selectable_text(self):
        stream = b"BT /F1 12 Tf 72 720 Td (Best Eye Exercise Routine) Tj ET"
        encoded_stream = base64.a85encode(zlib.compress(stream), adobe=True)
        pdf = (
            b"%PDF-1.4\n"
            b"1 0 obj\n<< /Filter [ /ASCII85Decode /FlateDecode ] /Length "
            + str(len(encoded_stream)).encode("ascii")
            + b" >>\nstream\n"
            + encoded_stream
            + b"\nendstream\nendobj\n%%EOF"
        )

        attachments, errors = normalize_attachments([
            payload("routine.pdf", pdf, "application/pdf")
        ])

        self.assertEqual(errors, [])
        self.assertEqual(attachments[0]["kind"], "document")
        self.assertIn("Best Eye Exercise Routine", attachments[0]["preview"])

    def test_oversized_file_is_rejected(self):
        attachments, errors = normalize_attachments([
            payload("large.bin", b"x" * (MAX_FILE_BYTES + 1), "application/octet-stream")
        ])

        self.assertEqual(attachments, [])
        self.assertTrue(errors)

    def test_xlsx_file_extracts_sheets(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr(
                "xl/sharedStrings.xml",
                "<sst><si><t>Apple</t></si><si><t>Banana</t></si></sst>"
            )
            archive.writestr(
                "xl/worksheets/sheet1.xml",
                "<worksheet><sheetData>"
                "<row><c t=\"s\"><v>0</v></c><c><v>100</v></c></row>"
                "<row><c t=\"s\"><v>1</v></c><c><v>200</v></c></row>"
                "</sheetData></worksheet>"
            )

        attachments, errors = normalize_attachments([
            payload("data.xlsx", buffer.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        ])

        self.assertEqual(errors, [])
        self.assertEqual(attachments[0]["kind"], "archive")
        self.assertIn("Apple,100", attachments[0]["preview"])
        self.assertIn("Banana,200", attachments[0]["preview"])

    def test_pptx_file_extracts_slides(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr(
                "ppt/slides/slide1.xml",
                "<slide><a:p><a:t>Hello PowerPoint World</a:t></a:p></slide>"
            )

        attachments, errors = normalize_attachments([
            payload("presentation.pptx", buffer.getvalue(), "application/vnd.openxmlformats-officedocument.presentationml.presentation")
        ])

        self.assertEqual(errors, [])
        self.assertEqual(attachments[0]["kind"], "archive")
        self.assertIn("Hello PowerPoint World", attachments[0]["preview"])


if __name__ == "__main__":
    unittest.main()
