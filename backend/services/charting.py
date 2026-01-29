"""Chart rendering helpers.

The frontend expects charts in this shape:

    {
      "name": "...",
      "type": "bar|line|pie",
      "image_base64": "..."
    }

This module converts an LLM-produced chart spec into base64 PNG images.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import base64
import io

import matplotlib


matplotlib.use("Agg")
import matplotlib.pyplot as plt


def _setup_font() -> None:
    """Best-effort CJK font fallback.

    Don't hardcode a single platform font (e.g., STHeiti) because it is
    unavailable on many machines.
    """

    try:
        plt.rcParams["font.sans-serif"] = [
            "SimHei",
            "Noto Sans CJK SC",
            "Microsoft YaHei",
            "Arial Unicode MS",
            "DejaVu Sans",
        ]
        plt.rcParams["axes.unicode_minus"] = False
    except Exception:
        # matplotlib may be in a restricted env; ignore.
        pass


def _b64_png(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")


def render_chart_specs(
    chart_specs: List[Dict[str, Any]],
    prefix: str = "report",
    limit: int = 8,
) -> List[Dict[str, Any]]:
    """Render up to `limit` charts.

    Supported spec formats:
    - bar: {type:'bar', title/name, categories/x/labels, values/y, unit}
    - pie: {type:'pie', title/name, labels, values, unit}
    - line: {type:'line', title/name, x, series:[{name, y}] , unit}
    """

    _setup_font()

    charts: List[Dict[str, Any]] = []
    for idx, spec in enumerate(chart_specs[:limit]):
        ctype = (spec.get("type") or "").lower().strip()
        title = spec.get("title") or spec.get("name") or f"{prefix}-{idx+1}"
        unit = spec.get("unit")

        try:
            if ctype == "bar":
                cats = spec.get("categories") or spec.get("x") or spec.get("labels") or []
                vals = spec.get("values") or spec.get("y") or []
                if not cats or not vals:
                    continue
                # keep lengths aligned
                n = min(len(cats), len(vals))
                cats = [str(x) for x in cats[:n]]
                vals = [float(x) for x in vals[:n]]

                fig, ax = plt.subplots(figsize=(7, 4))
                ax.bar(cats, vals)
                ax.set_title(title)
                ax.set_ylabel(unit or "数值")
                plt.xticks(rotation=30, ha="right")
                b64 = _b64_png(fig)
                charts.append({"name": title, "type": "bar", "image_base64": b64})

            elif ctype == "pie":
                labels = spec.get("labels") or spec.get("categories") or []
                vals = spec.get("values") or []
                if not labels or not vals:
                    continue
                n = min(len(labels), len(vals))
                labels = [str(x) for x in labels[:n]]
                vals = [float(x) for x in vals[:n]]
                fig, ax = plt.subplots(figsize=(7, 4))
                ax.pie(vals, labels=labels, autopct="%1.1f%%")
                ax.set_title(title)
                b64 = _b64_png(fig)
                charts.append({"name": title, "type": "pie", "image_base64": b64})

            elif ctype == "line":
                x = spec.get("x") or []
                series = spec.get("series") or []
                if not x or not series:
                    continue

                fig, ax = plt.subplots(figsize=(7, 4))
                x = [str(v) for v in x]
                for s in series:
                    name = s.get("name") or "series"
                    y = s.get("y") or []
                    n = min(len(x), len(y))
                    if n <= 1:
                        continue
                    yy = [float(v) for v in y[:n]]
                    ax.plot(x[:n], yy, marker="o", label=str(name))
                ax.set_title(title)
                ax.set_ylabel(unit or "数值")
                plt.xticks(rotation=30, ha="right")
                ax.legend(loc="best")
                b64 = _b64_png(fig)
                charts.append({"name": title, "type": "line", "image_base64": b64})
            else:
                # Unsupported chart type
                continue
        except Exception:
            # Never fail the whole PDF parsing due to a single chart.
            continue

    return charts


def merge_charts_into_metrics(metrics: Dict[str, Any], charts: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not charts:
        return metrics
    existing = metrics.get("_charts") or []
    metrics["_charts"] = existing + charts
    return metrics
