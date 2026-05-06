"""Parse Word (.docx) resumes into plain text."""
from pathlib import Path
from docx import Document


def parse_docx(filepath: str | Path) -> str:
    """Extract all text from a .docx file, including tables."""
    doc = Document(str(filepath))
    parts: list[str] = []

    for para in doc.paragraphs:
        text = para.text.strip()
        if text:
            parts.append(text)

    for table in doc.tables:
        for row in table.rows:
            row_cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if row_cells:
                parts.append(" | ".join(row_cells))

    return "\n".join(parts)
