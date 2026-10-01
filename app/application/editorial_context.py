from io import BytesIO

from pypdf import PdfReader, PdfWriter


def slice_pdf_pages_as_bytes(pdf_path: str, page_start: int, page_end: int, window_size: int = 10) -> bytes:
    if window_size < 1:
        raise ValueError("window_size must be positive")
    reader = PdfReader(pdf_path)
    total_pages = len(reader.pages)
    if total_pages == 0:
        raise ValueError("PDF contains no pages")
    center = (max(1, page_start) + max(1, page_end)) // 2
    start_idx = max(0, center - (window_size // 2) - 1)
    end_idx = min(total_pages, start_idx + window_size)
    if end_idx - start_idx < window_size:
        start_idx = max(0, end_idx - window_size)
    writer = PdfWriter()
    for index in range(start_idx, end_idx):
        writer.add_page(reader.pages[index])
    output = BytesIO()
    writer.write(output)
    return output.getvalue()
