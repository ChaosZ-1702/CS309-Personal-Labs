from typing import List, Dict, Any
from openai import OpenAI
import config
from config import OPENAI_API_KEY, OPENAI_BASE_URL
OPENAI_MODEL_MAIN = "gpt-4o-mini"
client = OpenAI(
    api_key=OPENAI_API_KEY or None,
    base_url=OPENAI_BASE_URL or None,
)


SYSTEM_ANALYST = """You are a bilingual financial analyst (Chinese & English).
Summarise and explain financial market data and news for non-expert investors.
Keep answers concise, structured and neutral, avoiding any illegal insider info.
"""


SYSTEM_REPORT_EXTRACTOR = """You are a strict financial-report information extractor.
You will receive text and tables extracted from a PDF statement (Chinese/English mixed).

Return ONE single JSON object (no code fences) that follows the schema requirements in the user prompt.
Rules:
- Output MUST be valid JSON. Do not add comments.
- Use numbers for numeric values (no commas, no currency symbols).
- If a field is unknown or missing, set it to null or an empty list.
"""


def _strip_code_fences(s: str) -> str:
    s = (s or "").strip()
    if s.startswith("```"):
        # remove ```json ... ```
        s = s.strip("`")
        # in case model returns language tag in first line
        lines = s.splitlines()
        if lines and lines[0].strip().lower() in {"json", "javascript"}:
            lines = lines[1:]
        s = "\n".join(lines)
    return s.strip()


def _safe_json_loads(text: str) -> Dict[str, Any]:
    import json

    raw = _strip_code_fences(text)
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        # try extracting the first JSON object inside the text
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(raw[start : end + 1])
            except Exception:
                return {"raw": text}
        return {"raw": text}


def _chunk_text(text: str, chunk_size: int = 9000, overlap: int = 300) -> List[str]:
    """Simple character-based chunker."""
    text = text or ""
    if len(text) <= chunk_size:
        return [text]
    chunks: List[str] = []
    i = 0
    while i < len(text):
        chunks.append(text[i : i + chunk_size])
        i += max(1, chunk_size - overlap)
    return chunks


def summarize_news(
    news_items: List[Dict[str, Any]],
    user_query: str,
    language: str = "auto",
) -> str:
    """
    把多条中英文新闻汇总成结构化分析。
    """
    if not news_items:
        return "未从新闻源中获取到相关资讯。"

    # 简要拼接
    lines = []
    for i, it in enumerate(news_items, start=1):
        lines.append(f"{i}. [{it['source']}] {it['title']} ({it.get('lang', 'unk')}) - {it['summary'][:200]}...")

    if language == "zh":
        ask_lang = "请使用中文回答。"
    elif language == "en":
        ask_lang = "Please answer in English."
    else:
        ask_lang = "如果用户问题是中文，用中文回答；否则用英文回答。"

    prompt = (
        f"用户问题：{user_query}\n\n"
        f"以下是若干金融新闻条目，请先筛选最相关的大约 10 条，再进行归纳：\n\n"
        + "\n".join(lines)
        + "\n\n"
        + "要求：\n"
        "- 先给出简短的市场整体概览；\n"
        "- 列出要点清单；\n"
        "- 简要说明可能的风险或不确定性；\n"
        "- 给出一个适合普通投资者的总结。\n"
        + ask_lang
    )

    completion = client.chat.completions.create(
        model=OPENAI_MODEL_MAIN,
        messages=[
            {"role": "system", "content": SYSTEM_ANALYST},
            {"role": "user", "content": prompt},
        ],
        temperature=0.5,
    )
    return completion.choices[0].message.content or ""


def translate_text(text: str, target_language: str) -> str:
    """
    target_language: 'zh' or 'en'
    """
    if target_language not in ("zh", "en"):
        return text

    inst = "Translate the following text into Simplified Chinese." if target_language == "zh" \
        else "Translate the following text into English."

    completion = client.chat.completions.create(
        model=OPENAI_MODEL_MAIN,
        messages=[
            {"role": "system", "content": inst},
            {"role": "user", "content": text},
        ],
        temperature=0,
    )
    return completion.choices[0].message.content or ""


def extract_financial_metrics_from_text(full_text: str) -> Dict[str, Any]:
    """
    从 PDF 的纯文本中抽取资产、负债、仓位等信息。
    """
    schema_hint = (
        "请以 JSON 格式返回，字段包括："
        "total_assets, total_liabilities, net_assets, cash, stock_positions(列表), "
        "fund_positions(列表), other_key_metrics(列表)。不要包含代码块标记。"
    )
    completion = client.chat.completions.create(
        model=OPENAI_MODEL_MAIN,
        messages=[
            {"role": "system", "content": SYSTEM_ANALYST},
            {
                "role": "user",
                "content": f"下面是用户的个人或机构财务报表文本，请抽取关键财务指标。\n\n{schema_hint}\n\n原文：\n{full_text[:8000]}",
            },
        ],
        temperature=0,
    )
    import json

    try:
        return json.loads(completion.choices[0].message.content or "{}")
    except Exception:
        return {"raw": completion.choices[0].message.content}


def extract_financial_report_structured_from_pdf_content(
    full_content: str,
    language: str = "zh",
) -> Dict[str, Any]:
    """Extract a normalized, chart-friendly JSON from full PDF content.

    This is designed for: "extract full PDF -> LLM returns strict JSON -> we plot using JSON".

    The LLM is asked to provide BOTH:
    - key_metrics: key numbers we can display quickly
    - chart_specs: chart definitions that the backend can render
    """

    ask_lang = "中文" if language in ("zh", "auto", None) else "English"

    schema = (
        "请严格返回一个 JSON 对象（不要代码块），字段如下：\n"
        "{\n"
        "  \"doc\": {\"document_type\": string|null, \"currency\": string|null, \"period\": string|null},\n"
        "  \"key_metrics\": {\n"
        "     \"total_assets\": number|null,\n"
        "     \"total_liabilities\": number|null,\n"
        "     \"net_assets\": number|null,\n"
        "     \"cash\": number|null\n"
        "  },\n"
        "  \"breakdowns\": {\n"
        "     \"assets\": [{\"name\": string, \"value\": number, \"unit\": string|null}]|[],\n"
        "     \"liabilities\": [{\"name\": string, \"value\": number, \"unit\": string|null}]|[],\n"
        "     \"positions\": [{\"name\": string, \"type\": string|null, \"value\": number|null, \"weight\": number|null, \"unit\": string|null}]|[]\n"
        "  },\n"
        "  \"chart_specs\": [\n"
        "     {\"type\": \"bar\"|\"pie\"|\"line\", \"title\": string, \"unit\": string|null, \"categories\": string[]|null, \"values\": number[]|null, \"x\": string[]|null, \"series\": [{\"name\": string, \"y\": number[]}]|null }\n"
        "  ],\n"
        "  \"other_key_metrics\": string[]\n"
        "}\n"
        "规则：\n"
        "- 数字字段必须是 number（不要带逗号/货币符号）。\n"
        "- 没找到就填 null 或空数组。\n"
        "- chart_specs 最多 6 张：优先给出（1）资产/负债/净资产（bar），（2）资产结构（pie），（3）若有时间序列则给净资产/现金/收益（line）。\n"
    )

    # If the PDF is long, do chunking + a final merge call.
    chunks = _chunk_text(full_content, chunk_size=12000, overlap=400)
    # Avoid unbounded LLM calls on very long PDFs. If a PDF is extremely long,
    # keep the head+tail to preserve totals + latest summaries.
    if len(chunks) > 20:
        chunks = chunks[:10] + chunks[-10:]
    partials: List[Dict[str, Any]] = []

    for i, ck in enumerate(chunks, start=1):
        prompt = (
            f"你将收到一段从 PDF 报表抽取的文本（第 {i}/{len(chunks)} 段）。\n"
            f"请从该段中尽可能抽取结构化信息，并按下面 schema 输出严格 JSON。\n\n"
            f"{schema}\n\n"
            f"回答语言：{ask_lang}（但 JSON 内的值可中英文混合，字段名必须按 schema）。\n\n"
            f"PDF 内容片段：\n{ck}"
        )
        try:
            completion = client.chat.completions.create(
                model=OPENAI_MODEL_MAIN,
                messages=[
                    {"role": "system", "content": SYSTEM_REPORT_EXTRACTOR},
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
            )
            partials.append(_safe_json_loads(completion.choices[0].message.content or "{}"))
        except Exception as e:
            partials.append({"error": f"llm_call_failed: {type(e).__name__}"})

    # Single chunk -> done
    if len(partials) == 1:
        return partials[0]

    # Merge multiple partial JSONs into one final JSON.
    import json

    merge_prompt = (
        "下面是同一份 PDF 报表的多段抽取结果（JSON 列表）。\n"
        "请合并为一个最终 JSON，要求：\n"
        "1) 严格符合 schema 字段；\n"
        "2) 数值冲突时，以更完整/更像总计的值为准；\n"
        "3) 合并 breakdowns/assets/liabilities/positions 去重；\n"
        "4) chart_specs 最多保留 6 个，优先保留信息量最大的。\n\n"
        f"{schema}\n\n"
        "待合并 JSON 列表：\n"
        + json.dumps(partials, ensure_ascii=False)[:12000]
    )

    try:
        completion = client.chat.completions.create(
            model=OPENAI_MODEL_MAIN,
            messages=[
                {"role": "system", "content": SYSTEM_REPORT_EXTRACTOR},
                {"role": "user", "content": merge_prompt},
            ],
            temperature=0,
        )
        return _safe_json_loads(completion.choices[0].message.content or "{}")
    except Exception as e:
        # Fallback: return partials for debugging
        return {"partials": partials, "error": f"llm_merge_failed: {type(e).__name__}"}


def summarize_financial_report_from_structured(
    structured: Dict[str, Any],
    language: str = "zh",
) -> str:
    """Second-pass LLM analysis based on the structured JSON."""

    if not structured:
        return "未能从报表中抽取到可分析的结构化内容。"

    import json

    lang = language or "auto"
    if lang not in ("zh", "en", "auto"):
        lang = "auto"

    ask_lang = "请使用中文回答。" if lang in ("zh", "auto") else "Please answer in English."

    prompt = (
        "下面是一份从 PDF 财务报表中抽取的结构化 JSON（包含关键指标、资产/负债/持仓拆分、以及用于画图的 chart_specs）。\n"
        "请基于这些数据做一个面向普通用户的结构化解读，包含：\n"
        "1）一句话总览；\n"
        "2）关键指标解读（总资产/总负债/净资产/现金）与可能含义；\n"
        "3）资产结构/负债结构/持仓结构的亮点与风险点（如集中度、杠杆、流动性）；\n"
        "4）不确定性与缺失信息说明；\n"
        "5）给 3-6 个下一步建议（例如需要补充哪些字段、如何做跟踪）。\n"
        "强调：这不是投资建议。\n\n"
        f"{ask_lang}\n\n"
        "结构化 JSON：\n"
        + json.dumps(structured, ensure_ascii=False)[:12000]
    )

    try:
        completion = client.chat.completions.create(
            model=OPENAI_MODEL_MAIN,
            messages=[
                {"role": "system", "content": SYSTEM_ANALYST},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )
        return completion.choices[0].message.content or ""
    except Exception as e:
        return f"LLM 分析失败：{type(e).__name__}"


def extract_financial_metrics_from_tables(
    tables: Dict[str, Any],
) -> Dict[str, Any]:
    """
    从 Excel 多个 sheet 的字典结构中提取与 PDF 同 schema 的结构化 JSON：
    {
      "doc": {"document_type": str|null, "currency": str|null, "period": str|null},
      "key_metrics": {"total_assets": number|null, "total_liabilities": number|null, "net_assets": number|null, "cash": number|null},
      "breakdowns": {
         "assets": [{"name": str, "value": number, "unit": str|null}]|[],
         "liabilities": [{"name": str, "value": number, "unit": str|null}]|[],
         "positions": [{"name": str, "type": str|null, "value": number|null, "weight": number|null, "unit": str|null}]|[]
      },
      "chart_specs": [
         {"type": "bar|pie|line", "title": str, "unit": str|null, "categories": string[]|null, "values": number[]|null, "x": string[]|null, "series": [{"name": str, "y": number[]}]|null }
      ],
      "other_key_metrics": string[]
    }
    """
    import json

    schema = (
        "请严格返回一个 JSON 对象（不要代码块），字段如下：\n"
        "{\n"
        "  \"doc\": {\"document_type\": string|null, \"currency\": string|null, \"period\": string|null},\n"
        "  \"key_metrics\": {\n"
        "     \"total_assets\": number|null,\n"
        "     \"total_liabilities\": number|null,\n"
        "     \"net_assets\": number|null,\n"
        "     \"cash\": number|null\n"
        "  },\n"
        "  \"breakdowns\": {\n"
        "     \"assets\": [{\"name\": string, \"value\": number, \"unit\": string|null}]|[],\n"
        "     \"liabilities\": [{\"name\": string, \"value\": number, \"unit\": string|null}]|[],\n"
        "     \"positions\": [{\"name\": string, \"type\": string|null, \"value\": number|null, \"weight\": number|null, \"unit\": string|null}]|[]\n"
        "  },\n"
        "  \"chart_specs\": [\n"
        "     {\"type\": \"bar|pie|line\", \"title\": string, \"unit\": string|null, \"categories\": string[]|null, \"values\": number[]|null, \"x\": string[]|null, \"series\": [{\"name\": string, \"y\": number[]}]|null }\n"
        "  ],\n"
        "  \"other_key_metrics\": string[]\n"
        "}\n"
        "规则：\n"
        "- 数字字段必须是 number（不要带逗号/货币符号）。\n"
        "- 没找到就填 null 或空数组。\n"
        "- chart_specs 最多 6 张，优先资产/负债/净资产/现金以及结构拆分。\n"
    )

    prompt = (
        "下面是从多个 Excel 工作表解析出来的数据（JSON），请按同一 schema 返回结构化 JSON，便于画图和解读：\n\n"
        + schema
        + "\n\nExcel 数据：\n"
        + json.dumps(tables, ensure_ascii=False, default=str)[:8000]
    )

    completion = client.chat.completions.create(
        model=OPENAI_MODEL_MAIN,
        messages=[
            {"role": "system", "content": SYSTEM_ANALYST},
            {"role": "user", "content": prompt},
        ],
        temperature=0,
    )
    try:
        return _safe_json_loads(completion.choices[0].message.content or "{}")
    except Exception:
        return {"raw": completion.choices[0].message.content}


def analyze_index_snapshot(snapshot: Dict[str, Any], language: str = "zh") -> str:
    """使用大模型对 AkShare 指数快照数据做整体解读。"""
    import json

    lang = language or "zh"
    if lang not in ("zh", "en", "auto"):
        lang = "en"

    user_lang = "中文" if lang in ("zh", "auto") else "English"
    payload = json.dumps(snapshot, ensure_ascii=False)[:6000]

    prompt = (
        f"下面是通过 AkShare 获取的一组中国主要股票指数实时行情快照，请用{user_lang}面向普通投资者做一个结构化分析，"
        f"包括：\n"
        f"1）今天整体市场涨跌情况；\n"
        f"2）哪些指数表现最好、哪些较弱，并给出可能原因（可以引用行业或宏观背景，但不要编造具体新闻）；\n"
        f"3）给出 2-3 点中性、不过度确定的观察提醒，强调这不是投资建议。\n"
        f"数据 JSON 如下：\n{payload}"
    )

    completion = client.chat.completions.create(
        model=OPENAI_MODEL_MAIN,
        messages=[
            {"role": "system", "content": SYSTEM_ANALYST},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
    )
    return completion.choices[0].message.content or ""


from typing import List

def analyze_financial_reports(reports: List[Dict[str, Any]], language: str = "zh") -> str:
    """
    对多份已经抽取出 metrics 的财报/报表做综合分析。
    仅基于已有的结构化字段，不重新从原始 PDF/Excel 解析。
    """
    if not reports:
        return "当前会话中还没有可供分析的 PDF/Excel 财报，可以先在右侧上传文件。"

    import json

    lang = language or "auto"
    if lang == "zh":
        ask_lang = "请使用中文回答。"
    elif lang == "en":
        ask_lang = "Please answer in English."
    else:
        ask_lang = "如果用户问题是中文，用中文回答；否则用英文回答。"

    payload = json.dumps(reports, ensure_ascii=False)[:8000]

    prompt = (
        "下面是一组已经抽取出关键财务指标的报表数据，请做一个多报表的对比与综合分析：\n"
        "1）先说明这些报表大致对应的主体和期间（可从文件名中简单识别，例如年份/季度）；\n"
        "2）比较收入、盈利、现金、资产负债等方面的相对强弱；\n"
        "3）指出任何显著的变化或风险点，例如利润率变化、负债率较高等；\n"
        "4）最后给出 3-5 点中性的观察结论，避免给出具体的买卖建议。\n\n"
        f"{ask_lang}\n\n"
        f"报表结构化 JSON 如下：\n{payload}"
    )

    completion = client.chat.completions.create(
        model=OPENAI_MODEL_MAIN,
        messages=[
            {"role": "system", "content": SYSTEM_ANALYST},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
    )
    return completion.choices[0].message.content or ""
