#!/usr/bin/env python3
"""Extract and chunk clinical guide documents for KB ingestion."""

import json
import os
import re
import subprocess
import sys
import tempfile
import shutil
import glob
from typing import List, Tuple
from zipfile import ZipFile
from xml.etree import ElementTree as ET

MAX_CHARS = 1200
MIN_CHARS = 180


def load_metadata() -> dict:
    raw = sys.stdin.read()
    if not raw.strip():
        raise SystemExit("Missing metadata input")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid metadata JSON: {exc}")


def clean_text(value: str) -> str:
    if not value:
        return ""
    text = value.replace("\r", "\n").replace("\t", " ")
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ ]{2,}", " ", text)
    text = re.sub(r"\n[ ]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", text)
    return text.strip()


def find_split(segment: str) -> int:
    tokens = ["\n\n", "\n", ". ", "; ", ": ", ", ", " "]
    for token in tokens:
        idx = segment.rfind(token, 0, MAX_CHARS)
        if idx >= MIN_CHARS:
            return idx + len(token)
    return MAX_CHARS


def chunk_pages(pages: List[str]) -> List[dict]:
    chunks: List[dict] = []
    chunk_index = 0
    carry = ""
    carry_page = None
    for page_number, raw_page in enumerate(pages, start=1):
        page_text = clean_text(raw_page)
        if not page_text:
            continue
        combined = page_text if not carry else f"{carry}\n\n{page_text}"
        page_for_chunk = carry_page if carry_page is not None else page_number
        carry = ""
        carry_page = None
        text = combined
        while text:
            if len(text) <= MAX_CHARS:
                carry = text
                carry_page = page_for_chunk
                break
            head = text[:MAX_CHARS]
            split_at = find_split(head)
            piece = text[:split_at].strip()
            text = text[split_at:].lstrip()
            if not piece:
                continue
            if len(piece) < MIN_CHARS and text:
                carry = piece
                if carry_page is None:
                    carry_page = page_for_chunk
                continue
            chunk_index += 1
            chunks.append({
                "chunk_index": chunk_index,
                "page_number": page_for_chunk,
                "content": piece,
                "status": "ok",
            })
            page_for_chunk = page_number
        if carry and len(carry) >= MAX_CHARS:
            chunk_index += 1
            chunks.append({
                "chunk_index": chunk_index,
                "page_number": carry_page if carry_page is not None else page_number,
                "content": carry.strip(),
                "status": "ok",
            })
            carry = ""
            carry_page = None
    if carry:
        carry_text = carry.strip()
        if carry_text:
            if chunks and len(carry_text) < MIN_CHARS:
                chunks[-1]["content"] = f"{chunks[-1]['content']}\n\n{carry_text}".strip()
            else:
                chunk_index += 1
                chunks.append({
                    "chunk_index": chunk_index,
                    "page_number": carry_page if carry_page is not None else (len(pages) or 1),
                    "content": carry_text,
                    "status": "ok",
                })
    return chunks

def extract_pdf_text(path: str) -> Tuple[str, str, str]:
    try:
        proc = subprocess.run(
            ['pdftotext', '-enc', 'UTF-8', '-layout', path, '-'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            text=True,
        )
        return proc.stdout or '', None, ''
    except FileNotFoundError:
        return '', 'pdftotext_not_found', ''
    except subprocess.CalledProcessError as exc:
        return exc.stdout or '', 'pdftotext_failed', (exc.stderr or '').strip()


def extract_pdf_ocr(path: str) -> Tuple[List[str], str, str]:
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            prefix = os.path.join(tmpdir, 'page')
            subprocess.run(
                ['pdftoppm', '-png', path, prefix],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                text=True,
            )
            images = sorted(glob.glob(f'{prefix}-*.png'))
            if not images:
                return [], 'pdftoppm_empty', 'pdftoppm produced no images'
            pages: List[str] = []
            for image_path in images:
                try:
                    tess = subprocess.run(
                        ['tesseract', image_path, 'stdout', '-l', 'spa+eng'],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        check=True,
                        text=True,
                    )
                    pages.append(tess.stdout or '')
                except FileNotFoundError:
                    return [], 'tesseract_not_found', ''
                except subprocess.CalledProcessError as exc:
                    return [], 'tesseract_failed', (exc.stderr or '').strip()
            return pages, None, ''
    except FileNotFoundError as exc:
        missing = os.path.basename(getattr(exc, 'filename', '') or '') or 'pdftoppm'
        return [], f'{missing}_not_found', ''
    except subprocess.CalledProcessError as exc:
        return [], 'pdftoppm_failed', (exc.stderr or '').strip()


def extract_docx_pages(path: str) -> Tuple[List[str], str]:
    try:
        with ZipFile(path) as zf:
            xml = zf.read('word/document.xml')
    except FileNotFoundError:
        return [], 'docx_not_found'
    except KeyError:
        return [], 'document_xml_missing'
    except Exception as exc:
        return [], f'docx_read_error: {exc}'
    try:
        root = ET.fromstring(xml)
    except Exception as exc:
        return [], f'docx_parse_error: {exc}'
    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    t_tag = '{%s}t' % ns['w']
    br_tag = '{%s}br' % ns['w']
    type_attr = '{%s}type' % ns['w']
    pages: List[str] = []
    current: List[str] = []
    for para in root.findall('.//w:p', ns):
        texts: List[str] = []
        page_break = False
        for node in para.iter():
            if node.tag == t_tag and node.text:
                texts.append(node.text)
            elif node.tag == br_tag and node.attrib.get(type_attr) == 'page':
                page_break = True
        paragraph = ' '.join(texts).strip()
        if paragraph:
            current.append(paragraph)
        if page_break:
            combined = '\n'.join(current).strip()
            if combined:
                pages.append(combined)
            current = []
    remaining = '\n'.join(current).strip()
    if remaining:
        pages.append(remaining)
    if not pages:
        all_paragraphs = []
        for para in root.findall('.//w:p', ns):
            texts = [node.text for node in para.findall('.//w:t', ns) if node.text]
            if texts:
                all_paragraphs.append(' '.join(texts))
        joined = '\n'.join(all_paragraphs).strip()
        if joined:
            pages.append(joined)
    return pages, None

def process_document(meta: dict) -> dict:
    source_id = int(meta.get('source_id') or -1)
    if source_id < 0:
        source_id = -1
    result = {
        "source_id": source_id,
        "source_name": (meta.get('source_name') or '').strip() or 'documento',
        "file_name": meta.get('file_name') or 'documento',
        "file_path": meta.get('file_path'),
        "dest_path": meta.get('dest_path'),
        "source_path": meta.get('source_path') or meta.get('dest_path'),
        "extension": (meta.get('extension') or '').lower(),
    }
    path = result['file_path']
    if not path or not os.path.exists(path):
        result.update({
            "chunks": [{
                "chunk_index": 1,
                "page_number": 1,
                "content": "[ERROR] No se encontró el archivo de origen para procesar.",
                "status": "error",
            }],
            "page_count": 0,
            "text_length": 0,
            "extraction": {
                "method": None,
                "used_ocr": False,
                "errors": {"file": "missing"},
            },
        })
        return result
    extension = result['extension']
    pages: List[str] = []
    extraction_method = None
    ocr_used = False
    errors = {}
    if extension == 'pdf':
        text, pdf_error, pdf_detail = extract_pdf_text(path)
        if pdf_error:
            errors['pdftotext'] = pdf_error
            if pdf_detail:
                errors['pdftotext_detail'] = pdf_detail
        if text and text.strip():
            pages = [page for page in text.split('\f') if page and page.strip()]
            extraction_method = 'pdftotext'
        else:
            pages, ocr_error, ocr_detail = extract_pdf_ocr(path)
            if ocr_error:
                errors['ocr'] = ocr_error
                if ocr_detail:
                    errors['ocr_detail'] = ocr_detail
            if pages:
                extraction_method = 'tesseract'
                ocr_used = True
    elif extension == 'docx':
        pages, docx_error = extract_docx_pages(path)
        if docx_error:
            errors['docx'] = docx_error
        extraction_method = 'docx'
    elif extension in {'doc', 'rtf'}:
        errors['unsupported'] = f'Formato no soportado: {extension}'
    else:
        errors['unsupported'] = f'Formato no soportado: {extension or "desconocido"}'
    page_count = len(pages)
    chunks = chunk_pages(pages) if pages else []
    if not chunks:
        if errors.get('unsupported'):
            message = errors['unsupported']
        elif extension == 'pdf':
            if errors.get('ocr'):
                message = f"[ERROR] OCR falló: {errors['ocr']}"
            elif errors.get('pdftotext'):
                message = f"[ERROR] pdftotext falló: {errors['pdftotext']}"
            else:
                message = 'No se encontró texto legible en el PDF.'
        elif extension == 'docx':
            message = f"No se pudo interpretar el DOCX: {errors.get('docx', 'desconocido')}"
        else:
            message = 'No se pudo extraer texto del documento.'
        chunks = [{
            "chunk_index": 1,
            "page_number": 1,
            "content": message,
            "status": "error",
        }]
    text_length = sum(len(chunk.get('content') or '') for chunk in chunks if chunk.get('status') == 'ok')
    result.update({
        "chunks": chunks,
        "page_count": page_count,
        "text_length": text_length,
        "extraction": {
            "method": extraction_method,
            "used_ocr": ocr_used,
            "errors": errors,
        },
    })
    return result

def main() -> None:
    meta = load_metadata()
    result = process_document(meta)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
