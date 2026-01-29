from __future__ import annotations

from typing import Dict, Any
from io import BytesIO
import pandas as pd
import numpy as np
import datetime as dt
import json

from .summarizer import (
    extract_financial_metrics_from_tables,
    summarize_financial_report_from_structured,
)


def _append_metrics_chart_from_tables(metrics: Dict[str, Any], prefix: str = "excel") -> Dict[str, Any]:
    """生成图表，保持与 PDF 同一逻辑：
    1) 若存在 chart_specs，走 render_chart_specs；
    2) 否则用数值字段生成 fallback bar 图。
    """

    from .charting import render_chart_specs

    chart_specs = metrics.get("chart_specs") if isinstance(metrics, dict) else None
    if isinstance(chart_specs, list) and chart_specs:
        charts = render_chart_specs(chart_specs, prefix=prefix)
        if charts:
            metrics["_charts"] = charts
        return metrics

    def _collect_numeric_items(obj: Any, path: str = "") -> list[tuple[str, float]]:
        items: list[tuple[str, float]] = []
        if isinstance(obj, dict):
            skip_keys = {"_charts", "_extract_meta", "_llm_analysis", "chart_specs"}
            for k, v in obj.items():
                if k in skip_keys:
                    continue
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    items.append((f"{path}{k}", float(v)))
                else:
                    items.extend(_collect_numeric_items(v, path=f"{path}{k}/"))
        elif isinstance(obj, list):
            for i, it in enumerate(obj):
                items.extend(_collect_numeric_items(it, path=f"{path}{i}/"))
        return items

    numeric_items = _collect_numeric_items(metrics)
    if not numeric_items:
        return metrics

    seen = set()
    compact_items: list[tuple[str, float]] = []
    for label, val in numeric_items:
        if not label or label in seen:
            continue
        seen.add(label)
        compact_items.append((label, val))
        if len(compact_items) >= 6:
            break

    if not compact_items:
        return metrics

    fallback_spec = [
        {
            "type": "bar",
            "title": "关键财务指标（自动）",
            "categories": [k for k, _ in compact_items],
            "values": [v for _, v in compact_items],
        }
    ]

    charts = render_chart_specs(fallback_spec, prefix=prefix)
    if charts:
        metrics["_charts"] = charts
    return metrics


def _build_fallback_metrics_from_structured(structured: Dict[str, Any]) -> Dict[str, Any]:
    """Align with PDF parser: flatten key_metrics and keep other_key_metrics."""
    metrics: Dict[str, Any] = {}
    key_metrics = (structured or {}).get("key_metrics") or {}
    if isinstance(key_metrics, dict):
        metrics.update(key_metrics)
    other = structured.get("other_key_metrics") if isinstance(structured, dict) else None
    if other is not None:
        metrics["other_key_metrics"] = other
    return metrics


def _normalize_value(v):
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except Exception:
        pass
    if isinstance(v, pd.Timestamp):
        try:
            return v.isoformat()
        except Exception:
            return str(v)
    if isinstance(v, (dt.datetime, dt.date)):
        return v.isoformat()
    if isinstance(v, np.generic):
        try:
            return v.item()
        except Exception:
            return float(v) if isinstance(v, (np.floating,)) else int(v)
    return v


def _to_json_safe_df(df: pd.DataFrame) -> pd.DataFrame:
    try:
        df = df.map(_normalize_value)
    except Exception:
        df = df.copy()
        for c in df.columns:
            df[c] = df[c].map(_normalize_value)
    try:
        df = df.where(pd.notnull(df), None)
    except Exception:
        pass
    return df


def parse_financial_excel(
    file_bytes: bytes,
    filename: str,
    include_preview: bool = True,
    preview_chars: int = 2000,
) -> Dict[str, Any]:
    buf = BytesIO(file_bytes)
    xls = pd.ExcelFile(buf)
    sheets_data = {}
    for sheet in xls.sheet_names:
        df = xls.parse(sheet)
        df = _to_json_safe_df(df)
        sheets_data[sheet] = df.to_dict(orient="records")

    structured = extract_financial_metrics_from_tables(sheets_data) or {}
    metrics = _build_fallback_metrics_from_structured(structured)

    if isinstance(structured, dict) and structured.get("chart_specs"):
        metrics["chart_specs"] = structured.get("chart_specs")

    metrics = _append_metrics_chart_from_tables(metrics, prefix=filename)

    preview = ""
    if include_preview:
        try:
            rows_preview = {}
            for sheet, rows in sheets_data.items():
                if isinstance(rows, list) and rows:
                    rows_preview[sheet] = rows[:5]
            preview = json.dumps(rows_preview, ensure_ascii=False, default=str)[:preview_chars]
        except Exception:
            preview = ""

    try:
        total_rows = sum(len(rows) for rows in sheets_data.values())
    except Exception:
        total_rows = None

    metrics["_extract_meta"] = {
        "filename": filename,
        "sheets": len(xls.sheet_names),
        "rows": total_rows,
        "pages": None,
        "content_chars": len(preview) if isinstance(preview, str) else None,
        "has_tables": True,
    }

    metrics["_llm_structured"] = structured

    try:
        metrics["_llm_analysis"] = summarize_financial_report_from_structured(structured, language="zh")
    except Exception:
        pass

    return {
        "filename": filename,
        "metrics": metrics,
        "raw_preview": preview,
    }
