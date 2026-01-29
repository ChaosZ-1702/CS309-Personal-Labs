from __future__ import annotations

"""PDF financial report parsing.

Pipeline (as requested):
1) Extract *all* PDF content (text + simple tables) into a single string.
2) Send extracted content to LLM with a strict JSON schema prompt.
3) Render charts from the JSON (chart_specs).
4) Send the structured JSON to LLM again for narrative analysis.

The endpoint returns:
- metrics: key_metrics + extra fields like _charts, _llm_structured, _llm_analysis.
- raw_preview: a short preview (to avoid huge payloads).
"""

from typing import Any, Dict, List
from io import BytesIO

import pdfplumber

from .charting import render_chart_specs
from .summarizer import (
    extract_financial_report_structured_from_pdf_content,
    summarize_financial_report_from_structured,
)


def _cell_to_str(x: Any) -> str:
    if x is None:
        return ""
    return str(x).strip()


def _table_to_markdown(table: List[List[Any]], max_rows: int = 40, max_cols: int = 12) -> str:
    """Convert a pdfplumber table (list of rows) into a compact markdown table."""
    if not table:
        return ""

    # Trim
    rows = table[:max_rows]
    rows = [r[:max_cols] if isinstance(r, list) else [] for r in rows]
    rows = [[_cell_to_str(c) for c in r] for r in rows]

    # If first row looks like a header, keep; else create generic headers.
    header = rows[0]
    if not any(header):
        return ""

    ncol = len(header)
    if ncol == 0:
        return ""

    # Markdown table
    lines: List[str] = []
    lines.append("| " + " | ".join(header) + " |")
    lines.append("| " + " | ".join(["---"] * ncol) + " |")
    for r in rows[1:]:
        rr = (r + [""] * ncol)[:ncol]
        lines.append("| " + " | ".join(rr) + " |")
    return "\n".join(lines)


def _extract_pdf_content(file_bytes: bytes) -> Dict[str, Any]:
    """Extract text + tables from all pages.

    Returns:
      {
        'pages': [{'page': 1, 'text': '...', 'tables_md': ['...']}...],
        'full_markdown': '...'
      }
    """
    buf = BytesIO(file_bytes)
    pages_out: List[Dict[str, Any]] = []
    md_parts: List[str] = []

    with pdfplumber.open(buf) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            txt = ""
            try:
                txt = page.extract_text(layout=True) or page.extract_text() or ""
            except Exception:
                txt = ""

            tables_md: List[str] = []
            try:
                tables = page.extract_tables() or []
                for t in tables:
                    md = _table_to_markdown(t)
                    if md:
                        tables_md.append(md)
            except Exception:
                tables_md = []

            pages_out.append({"page": i, "text": txt, "tables_md": tables_md})

            md_parts.append(f"\n\n## Page {i}\n")
            if txt.strip():
                md_parts.append(txt.strip())
            else:
                md_parts.append("(No extractable text on this page. If this is a scanned PDF, OCR is needed.)")

            if tables_md:
                for j, tmd in enumerate(tables_md, start=1):
                    md_parts.append(f"\n\n### Table {i}-{j}\n")
                    md_parts.append(tmd)

    full_markdown = "\n".join(md_parts).strip()
    return {"pages": pages_out, "full_markdown": full_markdown}


def _build_fallback_metrics_from_structured(structured: Dict[str, Any]) -> Dict[str, Any]:
    """Map structured output to a legacy-ish flat metrics dict."""
    metrics: Dict[str, Any] = {}
    key_metrics = (structured or {}).get("key_metrics") or {}
    if isinstance(key_metrics, dict):
        metrics.update(key_metrics)

    other = structured.get("other_key_metrics") if isinstance(structured, dict) else None
    if other is not None:
        metrics["other_key_metrics"] = other
    return metrics


def parse_financial_pdf(
    file_bytes: bytes,
    filename: str,
    include_preview: bool = True,
    preview_chars: int = 2000,
) -> Dict[str, Any]:
    """Parse PDF -> LLM structured JSON -> charts -> LLM narrative."""

    extracted = _extract_pdf_content(file_bytes)
    full_content = extracted["full_markdown"]

    structured = extract_financial_report_structured_from_pdf_content(full_content, language="zh")

    metrics: Dict[str, Any] = _build_fallback_metrics_from_structured(structured)
    metrics["_llm_structured"] = structured
    metrics["_extract_meta"] = {
        "filename": filename,
        "pages": len(extracted.get("pages") or []),
        "content_chars": len(full_content),
        "has_tables": any((p.get("tables_md") for p in (extracted.get("pages") or []))),
    }

    chart_specs = []
    if isinstance(structured, dict):
        chart_specs = structured.get("chart_specs") or []
    if isinstance(chart_specs, list) and chart_specs:
        metrics["_charts"] = render_chart_specs(chart_specs, prefix=filename)
    else:
        numeric_keys = []
        for k, v in metrics.items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                numeric_keys.append((k, float(v)))
        if numeric_keys:
            numeric_keys = numeric_keys[:6]
            fallback_spec = [
                {
                    "type": "bar",
                    "title": "关键财务指标（自动）",
                    "unit": None,
                    "categories": [k for k, _ in numeric_keys],
                    "values": [v for _, v in numeric_keys],
                }
            ]
            metrics["_charts"] = render_chart_specs(fallback_spec, prefix=filename)

    metrics["_llm_analysis"] = summarize_financial_report_from_structured(structured, language="zh")

    preview = full_content[:preview_chars] if include_preview else ""
    return {
        "filename": filename,
        "metrics": metrics,
        "raw_preview": preview,
    }
