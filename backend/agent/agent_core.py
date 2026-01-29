import uuid
import traceback
from typing import Dict, Any, List, AsyncGenerator
from datetime import datetime
from zoneinfo import ZoneInfo

from .models import ChatRequest, ChatResponse, AgentStep
from .memory import AgentMemory
from .planner import Planner
from services.finance_data import get_realtime_quote, compare_sector_trend
from services.akshare_tools import (
    get_cn_stock_history,
    get_hk_stock_history,
    get_us_stock_history,
)
from services.news_fetcher import fetch_mixed_finance_news, filter_news_by_keyword
from services.summarizer import summarize_news, translate_text
from openai import OpenAI
from config import OPENAI_API_KEY, OPENAI_MODEL_MAIN, OPENAI_BASE_URL
import json

class Agent:
    def __init__(self):
        self.memory = AgentMemory()
        self.planner = Planner()

    def _classify_query(self, query: str, language: str, context_brief: str) -> Dict[str, Any]:
        client = OpenAI(api_key=OPENAI_API_KEY or None, base_url=OPENAI_BASE_URL or None)
        system_prompt = """
            You are a strict JSON Intent Classifier for a financial assistant.
            Your task is to analyze the User Query and Context, then categorize the intent and extract parameters into a SINGLE valid JSON object.

            ### 1. Categories & Schemas
            Choose one of the following categories based on the user's intent:

            - **Category: 'news'** (Searching for news, rumors, or recent events)
            Schema: {"category": "news", "keyword": "string", "language": "zh|en"}

            - **Category: 'quote' or 'compare'** (Asking for price, stock performance, trends, or comparing assets)
            Schema: {"category": "quote" OR "compare", "symbols": ["string"], "market": ["string"], "days": int, "language": "zh|en"}

            - **Category: 'other'** (Chit-chat, greeting, or out of scope)
            Schema: {"category": "other", "content": "string", "language": "zh|en"}

            ### 2. Extraction Rules (CRITICAL)
            - **Sector Mapping:** If the user mentions a sector/industry (e.g., "AI", "新能源", "白酒"), YOU MUST convert it into 3-5 representative tickers.
            - "新能源/EV" -> ["105.TSLA", "106.NIO", "1211.HK"]
            - "AI/人工智能" -> ["105.NVDA", "105.MSFT", "105.GOOGL"]
            - "白酒" -> ["600519", "000858"]
            - "Banks/银行" -> ["106.JPM", "106.BAC", "601398"]
            - **Market Logic:** Identify the market for each symbol strictly:
            - 6 digits (e.g., 600519) -> "cn"
            - Ends with .HK (e.g., 0700.HK) -> "hk"
            - Otherwise (e.g., AAPL, TSLA, BTC) -> "us"
            - The 'market' array order must match the 'symbols' array.
            - **Days:** Default to 90 if not specified.
            - **Language:** Detect user language ('zh' for Chinese, 'en' for English).

            ### 3. Few-Shot Examples
            User: "看看英伟达和茅台的股价对比"
            JSON: {"category": "compare", "symbols": ["105.NVDA", "600519"], "market": ["us", "cn"], "days": 90, "language": "zh"}

            User: "最近半导体行业有什么大新闻？"
            JSON: {"category": "news", "keyword": "半导体", "language": "zh"}

            User: "Tell me about Tesla performance last week"
            JSON: {"category": "quote", "symbols": ["105.TSLA"], "market": ["us"], "days": 7, "language": "en"}

            User: "推荐几只电动车股票"
            JSON: {"category": "quote", "symbols": ["105.TSLA", "106.NIO", "1211.HK", "105.LI"], "market": ["us", "us", "hk", "us"], "days": 90, "language": "zh"}

            ### 4. Output Requirement
            Output ONLY the raw JSON string. Do not use Markdown blocks (```json). Do not explain.
        """
        user_prompt = (
            f"用户语言：{language}\n"
            f"用户问题：{query}\n"
            f"上下文：{context_brief}"
        )

        try:
            completion = client.chat.completions.create(
                model=OPENAI_MODEL_MAIN,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0,
            )
            content = completion.choices[0].message.content or ""
            parsed = json.loads(content)
            # 按用户要求：直接返回 LLM 的 JSON，不做字段转换
            return parsed
        except Exception:
            # Fallback: simple heuristic-based shaping per category
            lower_q = query.lower()
            if "新闻" in query or "news" in lower_q:
                cat = "news"
            elif "走势" in query or "compare" in lower_q or "对比" in lower_q:
                cat = "compare"
            elif "报价" in query or "price" in lower_q or "行情" in query:
                cat = "quote"
            else:
                cat = "other"

            lang = "zh" if any(x in query for x in ["新闻", "公司", "股票", "指数"]) else "en"

            # quick symbol extraction
            raw_tokens = [t.strip().upper() for t in query.replace("，", ",").replace(" ", ",").split(",") if t.strip()]
            symbols = []
            markets = []
            for tok in raw_tokens:
                digits = "".join(ch for ch in tok if ch.isdigit())
                if (len(tok) == 6 and tok.isdigit()) or tok.lower().startswith(("sh", "sz")):
                    symbols.append(tok)
                    markets.append("cn")
                elif tok.endswith(".HK") or (digits.isdigit() and 4 <= len(digits) <= 5):
                    symbols.append(tok)
                    markets.append("hk")
                elif tok and tok[0].isalnum():
                    symbols.append(tok)
                    markets.append("us")

            if cat == "news":
                return {"category": cat, "keyword": symbols[0] if symbols else None, "language": lang}
            elif cat in ("compare", "quote"):
                return {
                    "category": cat,
                    "symbols": symbols or ([query.strip().upper()] if query.strip() else []),
                    "market": markets or (["us"] if symbols else []),
                    "days": 90,
                    "language": lang,
                }
            else:
                return {"category": "other", "content": query, "language": lang}

    def _sse_json(self, payload: Dict[str, Any]) -> str:
    # SSE payload must be JSON-serializable.
    # Steps / structured_data may contain non-JSON types (e.g. datetime),
    # so we fall back to str() for unknown objects.
        return f"data: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"


    # ---- high level entry ----
    def handle_chat(self, req: ChatRequest) -> ChatResponse:
        session_id = req.session_id
        print("lang=", req.language)

        # 记录用户消息
        self.memory.append_message(session_id, "user", req.query)

        steps: List[AgentStep] = []
        structured: Dict[str, Any] = {}
        reply = ""

        try:
            # ========= 原有逻辑开始 =========

            # 规划步骤
            context_brief = self._build_context_brief(session_id)
            plan_step = self.planner.plan(req.query, context_brief)
            self.memory.add_step(session_id, plan_step)

            # LLM classify
            steps.append(plan_step)

            try:
                classification = self._classify_query(req.query, req.language, context_brief)
            except Exception:
                classification = {"category": "quote", "keyword": None, "language": req.language}

            cat = (classification.get("category") or "quote").lower()
            detected_kw = classification.get("keyword")
            user_lang = classification.get("language") or req.language
            print(f"[Agent] Classified query category: {cat}, keyword: {detected_kw}, language: {user_lang}")

            # 1. 今日市场新闻 & 解读
            if cat == "news":
                news_items = fetch_mixed_finance_news(limit=40, keyword=detected_kw)
                if detected_kw:
                    news_items = filter_news_by_keyword(news_items, detected_kw, limit=20)

                news_step = AgentStep(
                    id=str(uuid.uuid4()),
                    type="tool",
                    title="获取多源金融新闻",
                    detail=f"从新浪财经 + Yahoo Finance + Investing.com + NewsAPI + 极速API 获取了 {len(news_items)} 条相关新闻。",
                    # timestamp=datetime.utcnow(),
                    timestamp=datetime.now().isoformat(),
                    payload={"category": cat, "keyword": detected_kw, "news_count": len(news_items)},
                )
                steps.append(news_step)
                self.memory.add_step(session_id, news_step)

                structured["news_items"] = news_items

                # 如果真的一条都没有，给出清晰提示，而不是假装“生成了汇总”
                if not news_items:
                    reply = "暂时没有从新闻源获取到符合条件的新闻，请稍后再试，或更换关键词 / 时间范围。"

                    summary_step = AgentStep(
                        id=str(uuid.uuid4()),
                        type="summary",
                        title="新闻汇总与分析",
                        detail="由于新闻源为空，未生成分析，仅返回提示信息。",
                        # timestamp=datetime.utcnow(),
                        timestamp=datetime.now().isoformat(),
                    )
                    steps.append(summary_step)
                    self.memory.add_step(session_id, summary_step)
                else:
                    summary = summarize_news(news_items, req.query, language=user_lang)
                    reply = summary

                    summary_step = AgentStep(
                        id=str(uuid.uuid4()),
                        type="summary",
                        title="新闻汇总与分析",
                        detail="已生成新闻的综合解读。",
                        # timestamp=datetime.utcnow(),
                        timestamp=datetime.now().isoformat(),
                    )
                    steps.append(summary_step)
                    self.memory.add_step(session_id, summary_step)


            # 2. 对比最近几个月股价走势
            elif cat == "compare":
                symbols = classification.get("symbols") or []
                markets = classification.get("market") or []
                days = int(classification.get("days") or 90)

                series = {"days": days, "series": []}
                for idx, sym in enumerate(symbols):
                    mkt = markets[idx] if idx < len(markets) else "us"
                    if mkt == "cn":
                        hist = get_cn_stock_history(sym, days=days)
                    elif mkt == "hk":
                        hist = get_hk_stock_history(sym, days=days)
                    else:
                        hist = get_us_stock_history(sym, days=days)

                    pts = hist.get("points", [])
                    if not pts:
                        series["series"].append({"symbol": sym, "market": mkt, "points": []})
                        continue
                    base = pts[0]["close"] if pts and ("close" in pts[0]) else None
                    pct_points = []
                    if base is not None and base != 0:
                        for p in pts:
                            pct = (p["close"] / base - 1.0) * 100.0
                            pct_points.append({"date": p["date"], "pct_change": float(pct)})
                    series["series"].append({"symbol": sym, "market": mkt, "points": pct_points})

                structured["sector_trend"] = series

                tool_step = AgentStep(
                    id=str(uuid.uuid4()),
                    type="tool",
                    title="获取多只股票历史价格",
                    detail=f"已获取 {days} 天内 {len(symbols)} 只股票的价格走势。",
                    timestamp=datetime.now().isoformat(),
                    payload={"symbol": symbols, "market": markets, "days": days, "stock_count": len(symbols), "result_counts": [len(s["points"]) for s in series["series"]]},
                )
                steps.append(tool_step)
                self.memory.add_step(session_id, tool_step)

                client = OpenAI(api_key=OPENAI_API_KEY or None, base_url=OPENAI_BASE_URL or None)
                sp = (
                    "下面是任务规划详情：\n"
                    f"{plan_step.detail}\n\n"
                    f"下面是 {len(symbols)} 只股票在最近 {days} 天内的数据：\n"
                    f"{json.dumps(series, ensure_ascii=False)[:6000]}"
                    "请你根据用户原始请求组织回复内容，给出专业且简洁的分析与解读，"
                    f"回复使用{'中文' if user_lang == 'zh' else '英文'}，应尽量简洁并保持专业。"
                )
                up = (
                    f"当前时间：{datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"用户原始请求：{req.query}\n"
                    f"上下文摘要：{context_brief}"
                )

                completion = client.chat.completions.create(
                    model=OPENAI_MODEL_MAIN,
                    messages=[
                        {"role": "system", "content": sp},
                        {"role": "user", "content": up},
                    ],
                    temperature=0.2,
                )
                content = completion.choices[0].message.content or ""
                reply = content

                summary_step = AgentStep(
                    id=str(uuid.uuid4()),
                    type="summary",
                    title="价格走势分析",
                    detail="已根据历史数据生成趋势分析与对比。",
                    # timestamp=datetime.utcnow(),
                    timestamp=datetime.now().isoformat(),
                )
                steps.append(summary_step)
                self.memory.add_step(session_id, summary_step)

            # 3. 默认：简单实时行情 + 简要说明（比如用户输入一个股票代码）
            elif cat == "quote":
                symbols = classification.get("symbols") or []
                markets = classification.get("market") or []
                days = int(classification.get("days") or 90)
                token = symbols[0] if symbols else (req.query.strip().split()[0].upper())

                mkt = markets[0] if markets else None
                if mkt == "cn":
                    points_result = get_cn_stock_history(token, days=days)
                elif mkt == "hk":
                    points_result = get_hk_stock_history(token, days=days)
                else:
                    points_result = get_us_stock_history(token, days=days)

                normalized_history = {
                    "symbol": points_result.get("symbol", token),
                    "period": days,
                    "interval": "1d",
                    "history": points_result.get("points", []),
                    "source": points_result.get("source", "akshare"),
                }

                structured["history"] = normalized_history

                client = OpenAI(api_key=OPENAI_API_KEY or None, base_url=OPENAI_BASE_URL or None)
                sp = (
                    "下面是任务规划详情：\n"
                    f"{plan_step.detail}\n\n"
                    f"下面是股票 {token} 在最近 {days} 天内的数据：\n"
                    f"{json.dumps(normalized_history, ensure_ascii=False)[:6000]}"
                    "请你根据用户原始请求和任务规划详情组织回复内容，给出专业且简洁的分析与解读，"
                    f"回复使用{'中文' if user_lang in ('zh', 'auto') else '英文'}，应尽量简洁并保持专业。"
                )
                up = (
                    f"当前时间：{datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"用户原始请求：{req.query}\n"
                    f"上下文摘要：{context_brief}"
                )

                completion = client.chat.completions.create(
                    model=OPENAI_MODEL_MAIN,
                    messages=[
                        {"role": "system", "content": sp},
                        {"role": "user", "content": up},
                    ],
                    temperature=0.2,
                )
                content = completion.choices[0].message.content or ""
                reply = content

                tool_step = AgentStep(
                    id=str(uuid.uuid4()),
                    type="tool",
                    title="获取实时与历史行情",
                    detail=f"已为 {token} 获取最近 {days} 天日线数据和当前价格。",
                    # timestamp=datetime.utcnow(),
                    timestamp=datetime.now().isoformat(),
                    payload={"symbol": token, "market": mkt, "days": days, "result_count": len(normalized_history["history"])},
                )
                steps.append(tool_step)
                self.memory.add_step(session_id, tool_step)

            # ========= 原有逻辑结束 =========

            else:
                client = OpenAI(api_key=OPENAI_API_KEY or None, base_url=OPENAI_BASE_URL or None)
                sp = (
                    "下面是任务规划详情：\n"
                    f"{plan_step.detail}\n\n"
                    "你是一个金融助理。用户可能提出复杂或开放性的问题。"
                    "请直接以自然语言完整回答用户原始请求，必要时给出步骤、建议或参考来源，"
                    "如果无法获取外部数据则明确说明并给出可行的替代方案。"
                    f"回复应使用{'中文' if user_lang == 'zh' else '英文'}，应尽量简洁并保持专业。"
                )
                up = (
                    f"当前时间：{datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"用户原始请求：{req.query}\n"
                    f"上下文摘要：{context_brief}"
                )

                completion = client.chat.completions.create(
                    model=OPENAI_MODEL_MAIN,
                    messages=[
                        {"role": "system", "content": sp},
                        {"role": "user", "content": up},
                    ],
                    temperature=0.2,
                )
                content = completion.choices[0].message.content or ""
                reply = content

                llm_step = AgentStep(
                    id=str(uuid.uuid4()),
                    type="analysis",
                    title="由 LLM 原样处理用户请求",
                    detail="使用 LLM 对用户原始请求进行完整的自然语言处理并生成回复。",
                    timestamp=datetime.now().isoformat(),
                    payload={"model": OPENAI_MODEL_MAIN},
                )
                steps.append(llm_step)
                self.memory.add_step(session_id, llm_step)

                structured["llm_response"] = {"text": content}

        except Exception as e:
            # 捕获所有异常，避免直接 500
            err_text = "".join(traceback.format_exception(type(e), e, e.__traceback__))

            error_step = AgentStep(
                id=str(uuid.uuid4()),
                type="analysis",
                title="Agent 执行出错",
                detail=f"Agent 在处理请求时出现异常：\n{err_text}",
                # timestamp=datetime.utcnow(),
                timestamp=datetime.now().isoformat(),
            )
            steps.append(error_step)
            self.memory.add_step(session_id, error_step)

            reply = f"后端 Agent 执行出错：{e}\n\n详细堆栈已记录在服务器日志中。"
            structured = {}

        # 生成 Markdown 汇总报告（用于导出）
        markdown_report = None
        if req.export_markdown:
            markdown_report = self._generate_markdown_report(req, structured, steps)

        # 记录 assistant 回复到记忆
        self.memory.append_message(session_id, "assistant", reply)

        return ChatResponse(
            reply=reply,
            steps=steps,
            structured_data=structured,
            markdown_report=markdown_report,
        )


    # ---- streaming (SSE) ----
    def stream_chat(self, req: ChatRequest):
        """
        SSE 流式接口：同 handle_chat 逻辑，但最终回复用 OpenAI 流式返回。
        事件格式：
        - {"type":"chunk","content": "..."}
        - {"type":"done","reply": "...","steps": [...],"structured_data": {...}}
        - {"type":"error","message": "..."}
        """

        def serialize_steps(step_list: List[AgentStep]) -> List[Dict[str, Any]]:
            out = []
            for s in step_list:
                d = s.dict()
                ts = d.get("timestamp")
                if hasattr(ts, "isoformat"):
                    d["timestamp"] = ts.isoformat()
                out.append(d)
            return out

        def serialize_step(step: AgentStep) -> Dict[str, Any]:
            d = step.dict()
            ts = d.get("timestamp")
            if hasattr(ts, "isoformat"):
                d["timestamp"] = ts.isoformat()
            return d

        def yield_error(msg: str):
            return self._sse_json({"type": "error", "message": msg})

        def yield_step(step: AgentStep):
            return self._sse_json({"type": "step", "step": serialize_step(step)})

        session_id = req.session_id
        self.memory.append_message(session_id, "user", req.query)

        steps: List[AgentStep] = []
        structured: Dict[str, Any] = {}
        reply_text = ""

        try:
            context_brief = self._build_context_brief(session_id)
            plan_step = self.planner.plan(req.query, context_brief)
            self.memory.add_step(session_id, plan_step)
            steps.append(plan_step)
            yield yield_step(plan_step)

            try:
                classification = self._classify_query(req.query, req.language, context_brief)
            except Exception:
                classification = {"category": "quote", "keyword": None, "language": req.language}

            cat = (classification.get("category") or "quote").lower()
            detected_kw = classification.get("keyword")
            user_lang = classification.get("language") or req.language

            # ---- news ----
            if cat == "news":
                news_items = fetch_mixed_finance_news(limit=40, keyword=detected_kw)
                if detected_kw:
                    news_items = filter_news_by_keyword(news_items, detected_kw, limit=20)

                news_step = AgentStep(
                    id=str(uuid.uuid4()),
                    type="tool",
                    title="获取多源金融新闻",
                    detail=f"从新浪财经 + Yahoo Finance + Investing.com + NewsAPI + 极速API 获取了 {len(news_items)} 条相关新闻。",
                    timestamp=datetime.now().isoformat(),
                    payload={"category": cat, "keyword": detected_kw, "news_count": len(news_items)},
                )
                steps.append(news_step)
                self.memory.add_step(session_id, news_step)
                yield yield_step(news_step)
                structured["news_items"] = news_items

                if not news_items:
                    reply_text = "暂时没有从新闻源获取到符合条件的新闻，请稍后再试，或更换关键词 / 时间范围。"
                else:
                    # 构造摘要提示（与 summarize_news 逻辑类似，但流式输出）
                    lines = []
                    for i, it in enumerate(news_items[:12], start=1):
                        lines.append(f"{i}. [{it.get('source','?')}] {it.get('title','')} ({it.get('lang','unk')}) - {(it.get('summary') or '')[:200]}...")

                    if user_lang == "zh":
                        ask_lang = "请使用中文回答。"
                    elif user_lang == "en":
                        ask_lang = "Please answer in English."
                    else:
                        ask_lang = "如果用户问题是中文，用中文回答；否则用英文回答。"

                    system_prompt = (
                        "You are a bilingual financial analyst (Chinese & English). "
                        "Summarise and explain financial market news for non-expert investors. "
                        "Keep answers concise, structured and neutral, avoiding insider info."
                    )
                    user_prompt = (
                        f"用户问题：{req.query}\n\n"
                        f"以下是若干金融新闻条目（最多 20 条），请先筛选最相关的 10 条，再进行归纳：\n\n"
                        + "\n".join(lines)
                        + "\n\n"
                        + "要求：\n"
                        "- 先给出简短的市场整体概览；\n"
                        "- 列出要点清单；\n"
                        "- 简要说明可能的风险或不确定性；\n"
                        "- 给出一个适合普通投资者的总结。\n"
                        + ask_lang
                    )

                    reply_parts: List[str] = []
                    try:
                        client = OpenAI(api_key=OPENAI_API_KEY or None, base_url=OPENAI_BASE_URL or None)
                        stream = client.chat.completions.create(
                            model=OPENAI_MODEL_MAIN,
                            messages=[
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": user_prompt},
                            ],
                            temperature=0.5,
                            stream=True,
                        )
                        for chunk in stream:
                            delta = chunk.choices[0].delta.content if chunk.choices else None
                            if not delta:
                                continue
                            reply_parts.append(delta)
                            yield self._sse_json({"type": "chunk", "content": delta})
                    except Exception as e:
                        yield yield_error(str(e))
                        return
                    reply_text = "".join(reply_parts)

                summary_step = AgentStep(
                    id=str(uuid.uuid4()),
                    type="summary",
                    title="新闻汇总与分析",
                    detail="已生成新闻的综合解读。" if news_items else "由于新闻源为空，未生成分析，仅返回提示信息。",
                    timestamp=datetime.now().isoformat(),
                )
                steps.append(summary_step)
                self.memory.add_step(session_id, summary_step)
                yield yield_step(summary_step)

            # ---- compare ----
            elif cat == "compare":
                symbols = classification.get("symbols") or []
                markets = classification.get("market") or []
                days = int(classification.get("days") or 90)

                series = {"days": days, "series": []}
                for idx, sym in enumerate(symbols):
                    mkt = markets[idx] if idx < len(markets) else "us"
                    if mkt == "cn":
                        hist = get_cn_stock_history(sym, days=days)
                    elif mkt == "hk":
                        hist = get_hk_stock_history(sym, days=days)
                    else:
                        hist = get_us_stock_history(sym, days=days)

                    pts = hist.get("points", [])
                    if not pts:
                        series["series"].append({"symbol": sym, "market": mkt, "points": []})
                        continue
                    base = pts[0].get("close") if pts else None
                    pct_points = []
                    if base:
                        for p in pts:
                            pct = (p.get("close", 0) / base - 1.0) * 100.0
                            pct_points.append({"date": p.get("date"), "pct_change": float(pct)})
                    series["series"].append({"symbol": sym, "market": mkt, "points": pct_points})

                structured["sector_trend"] = series

                tool_step = AgentStep(
                    id=str(uuid.uuid4()),
                    type="tool",
                    title="获取多只股票历史价格",
                    detail=f"已获取 {days} 天内 {len(symbols)} 只股票的价格走势。",
                    timestamp=datetime.now().isoformat(),
                    payload={
                        "symbol": symbols,
                        "market": markets,
                        "days": days,
                        "stock_count": len(symbols),
                        "result_counts": [len(s["points"]) for s in series["series"]],
                    },
                )
                steps.append(tool_step)
                self.memory.add_step(session_id, tool_step)
                yield yield_step(tool_step)

                system_prompt = (
                    "你是一个金融助理，请基于给定的多只股票的历史走势数据做比较分析，"
                    "输出简明的结论和风险提示，语气保持专业与中性。"
                )
                user_prompt = (
                    f"当前时间：{datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"用户原始请求：{req.query}\n"
                    f"上下文摘要：{context_brief}\n\n"
                    f"下面是 {len(symbols)} 只股票在最近 {days} 天内的数据：\n"
                    f"{json.dumps(series, ensure_ascii=False)[:6000]}\n"
                    f"回复使用{'中文' if user_lang == 'zh' else '英文'}，尽量简洁并保持专业。"
                )

                reply_parts: List[str] = []
                try:
                    client = OpenAI(api_key=OPENAI_API_KEY or None, base_url=OPENAI_BASE_URL or None)
                    stream = client.chat.completions.create(
                        model=OPENAI_MODEL_MAIN,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        temperature=0.2,
                        stream=True,
                    )
                    for chunk in stream:
                        delta = chunk.choices[0].delta.content if chunk.choices else None
                        if not delta:
                            continue
                        reply_parts.append(delta)
                        yield self._sse_json({"type": "chunk", "content": delta})
                except Exception as e:
                    yield yield_error(str(e))
                    return
                reply_text = "".join(reply_parts)

                summary_step = AgentStep(
                    id=str(uuid.uuid4()),
                    type="summary",
                    title="价格走势分析",
                    detail="已根据历史数据生成趋势分析与对比。",
                    timestamp=datetime.now().isoformat(),
                )
                steps.append(summary_step)
                self.memory.add_step(session_id, summary_step)
                yield yield_step(summary_step)

            # ---- quote ----
            elif cat == "quote":
                symbols = classification.get("symbols") or []
                markets = classification.get("market") or []
                days = int(classification.get("days") or 90)
                token = symbols[0] if symbols else (req.query.strip().split()[0].upper())

                mkt = markets[0] if markets else None
                if mkt == "cn":
                    points_result = get_cn_stock_history(token, days=days)
                elif mkt == "hk":
                    points_result = get_hk_stock_history(token, days=days)
                else:
                    points_result = get_us_stock_history(token, days=days)

                normalized_history = {
                    "symbol": points_result.get("symbol", token),
                    "period": days,
                    "interval": "1d",
                    "history": points_result.get("points", []),
                    "source": points_result.get("source", "akshare"),
                }
                structured["history"] = normalized_history

                tool_step = AgentStep(
                    id=str(uuid.uuid4()),
                    type="tool",
                    title="获取实时与历史行情",
                    detail=f"已为 {token} 获取最近 {days} 天日线数据和当前价格。",
                    timestamp=datetime.now().isoformat(),
                    payload={"symbol": token, "market": mkt, "days": days, "result_count": len(normalized_history["history"])},
                )
                steps.append(tool_step)
                self.memory.add_step(session_id, tool_step)
                yield yield_step(tool_step)

                system_prompt = (
                    "你是一个金融助理，请根据给定的单只股票最近走势数据，"
                    "提供简明的走势解读、风险提示，以及需关注的下一步数据。"
                )
                user_prompt = (
                    f"当前时间：{datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"用户原始请求：{req.query}\n"
                    f"上下文摘要：{context_brief}\n\n"
                    f"下面是股票 {token} 在最近 {days} 天内的数据：\n"
                    f"{json.dumps(normalized_history, ensure_ascii=False)[:6000]}\n"
                    f"回复使用{'中文' if user_lang in ('zh', 'auto') else '英文'}，应尽量简洁并保持专业。"
                )

                reply_parts: List[str] = []
                try:
                    client = OpenAI(api_key=OPENAI_API_KEY or None, base_url=OPENAI_BASE_URL or None)
                    stream = client.chat.completions.create(
                        model=OPENAI_MODEL_MAIN,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        temperature=0.2,
                        stream=True,
                    )
                    for chunk in stream:
                        delta = chunk.choices[0].delta.content if chunk.choices else None
                        if not delta:
                            continue
                        reply_parts.append(delta)
                        yield self._sse_json({"type": "chunk", "content": delta})
                except Exception as e:
                    yield yield_error(str(e))
                    return
                reply_text = "".join(reply_parts)

                summary_step = AgentStep(
                    id=str(uuid.uuid4()),
                    type="summary",
                    title="股票走势解读",
                    detail="已根据历史数据生成走势解读和风险提示。",
                    timestamp=datetime.now().isoformat(),
                )
                steps.append(summary_step)
                self.memory.add_step(session_id, summary_step)
                yield yield_step(summary_step)

            # ---- other ----
            else:
                system_prompt = (
                    "你是一个金融助理。用户可能提出复杂或开放性的问题。"
                    "请直接以自然语言完整回答用户原始请求，必要时给出步骤、建议或参考来源，"
                    "如果无法获取外部数据则明确说明并给出可行的替代方案。"
                    f"回复应使用{'中文' if user_lang == 'zh' else '英文'}，应尽量简洁并保持专业。"
                )
                user_prompt = (
                    f"当前时间：{datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"用户原始请求：{req.query}\n"
                    f"上下文摘要：{context_brief}"
                )

                reply_parts: List[str] = []
                try:
                    client = OpenAI(api_key=OPENAI_API_KEY or None, base_url=OPENAI_BASE_URL or None)
                    stream = client.chat.completions.create(
                        model=OPENAI_MODEL_MAIN,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        temperature=0.2,
                        stream=True,
                    )
                    for chunk in stream:
                        delta = chunk.choices[0].delta.content if chunk.choices else None
                        if not delta:
                            continue
                        reply_parts.append(delta)
                        yield self._sse_json({"type": "chunk", "content": delta})
                except Exception as e:
                    yield yield_error(str(e))
                    return
                reply_text = "".join(reply_parts)

                llm_step = AgentStep(
                    id=str(uuid.uuid4()),
                    type="analysis",
                    title="由 LLM 原样处理用户请求",
                    detail="使用 LLM 对用户原始请求进行完整的自然语言处理并生成回复。",
                    timestamp=datetime.now().isoformat(),
                    payload={"model": OPENAI_MODEL_MAIN},
                )
                steps.append(llm_step)
                self.memory.add_step(session_id, llm_step)

        except Exception as e:
            yield yield_error(str(e))
            return

        # 汇总、记录、结束事件
        self.memory.append_message(session_id, "assistant", reply_text)
        done_payload = {
            "type": "done",
            "reply": reply_text,
            "steps": serialize_steps(steps),
            "structured_data": structured,
        }
        yield self._sse_json(done_payload)


    # ---- helpers ----
    def _build_context_brief(self, session_id: str) -> str:
        msgs = self.memory.get_session_messages(session_id)[-6:]
        if not msgs:
            return "这是该会话的第一次对话。"
        lines = [f"{m['role']}: {m['content']}" for m in msgs]
        return "\n".join(lines)

    def _generate_markdown_report(
        self,
        req: ChatRequest,
        structured: Dict[str, Any],
        steps: List[AgentStep],
    ) -> str:
        import json

        md_lines = [
            f"# 金融数据提取与消息汇总报告",
            "",
            f"- 会话 ID：`{req.session_id}`",
            f"- 用户问题：{req.query}",
            # f"- 导出时间：{datetime.utcnow().isoformat()}",
            f"- 导出时间：{datetime.now().isoformat()}",
            "",
            "## 任务规划与执行步骤",
            "",
        ]
        for s in steps:
            md_lines.append(f"### {s.title}")
            md_lines.append(f"- 类型：{s.type}")
            md_lines.append(f"- 时间：{s.timestamp.isoformat()}")
            md_lines.append("")
            md_lines.append(s.detail)
            md_lines.append("")

        md_lines.append("## 结构化数据概览")
        md_lines.append("")
        md_lines.append("```json")
        md_lines.append(json.dumps(structured, ensure_ascii=False, indent=2))
        md_lines.append("```")

        return "\n".join(md_lines)
