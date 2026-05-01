"""Local OCR and document conversion wrappers.

All functions:
- Raise FileNotFoundError if the input file does not exist
- Raise RuntimeError on tool failure with stderr captured in the message
- Respect the timeout parameter (seconds)
"""
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def _run(cmd: list[str], timeout: int) -> subprocess.CompletedProcess:
    """Run subprocess, raise RuntimeError on non-zero exit."""
    logger.debug("Running: %s", " ".join(cmd))
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed ({result.returncode}): {' '.join(cmd)}\n"
            f"stderr: {result.stderr[:500]}"
        )
    return result


def extract_text_from_image(image_path: str, timeout: int = 60) -> str:
    """Extract text from an image file using tesseract. Returns plain text."""
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")
    result = _run(
        ["tesseract", str(path), "stdout", "-l", "spa+eng", "--psm", "3"],
        timeout=timeout,
    )
    return result.stdout


def ocr_pdf(input_path: str, output_path: str, timeout: int = 120) -> None:
    """OCR a scanned PDF using ocrmypdf. Output is a searchable PDF."""
    if not Path(input_path).exists():
        raise FileNotFoundError(f"PDF not found: {input_path}")
    _run(
        [
            "ocrmypdf",
            "--language", "spa+eng",
            "--output-type", "pdf",
            "--skip-text",
            "--jobs", "2",
            input_path,
            output_path,
        ],
        timeout=timeout,
    )
    logger.info("ocrmypdf done: %s -> %s", input_path, output_path)


def convert_office_to_pdf(input_path: str, output_dir: str, timeout: int = 60) -> str:
    """Convert .docx/.pptx/.xlsx to PDF using LibreOffice headless.

    Returns the path to the generated PDF file.
    """
    if not Path(input_path).exists():
        raise FileNotFoundError(f"File not found: {input_path}")
    _run(
        [
            "soffice",
            "--headless",
            "--convert-to", "pdf",
            "--outdir", output_dir,
            input_path,
        ],
        timeout=timeout,
    )
    stem = Path(input_path).stem
    pdf_path = Path(output_dir) / f"{stem}.pdf"
    if not pdf_path.exists():
        raise RuntimeError(f"LibreOffice did not produce {pdf_path}")
    return str(pdf_path)
