# 金融聚合 Agent

本项目包含：

- **前端**：Vue3（`frontend/`）
- **后端**：FastAPI（`backend/`）

本次更新重点优化了 **PDF 报表上传解析**：

1. 后端会尽可能把 PDF 的 **全文文字 + 表格** 全部抽取出来（按页拼接成一份 Markdown 文本）
2. 将抽取内容交给 LLM，要求其**严格按 JSON schema 输出**（包含 `key_metrics` 和 `chart_specs`）
3. 后端根据 `chart_specs` **自动绘图**并返回前端展示
4. 再将结构化 JSON 交给 LLM 做**第二次解读**（返回在 `metrics._llm_analysis`）

---

## 1. 后端启动

进入后端目录并安装依赖：

```bash
cd backend
conda create -n cs309 python=3.10 -y
conda activate cs309
pip install -r requirements.txt
```

在 .env 中配置您的 OpenAI Key 及模型。

启动：

```bash
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

上传接口：

- `POST /api/upload/pdf`（表单：`session_id`, `file`）
- `POST /api/upload/excel`（表单：`session_id`, `file`）

PDF 返回的核心字段：

- `metrics._llm_structured`：LLM 输出的结构化 JSON（含 `chart_specs`）
- `metrics._charts`：后端渲染好的 base64 PNG 图
- `metrics._llm_analysis`：LLM 二次解读文本
- `metrics._extract_meta`：抽取页数/字符数等

---

## 2. 前端启动

```bash
cd frontend
npm install
npm run dev
```

默认后端地址写在：`frontend/src/api/upload.js`（`http://localhost:8000`）。

---

## 3. 问题

### 3.1 扫描版 PDF（图片）抽不出文字

当前后端用 `pdfplumber` 做“文字/表格”抽取。若 PDF 是扫描件，需要 OCR 才能识别文字。
可以后续增加 OCR（例如 tesseract）作为 fallback。

### 3.2 为什么要两次调用 LLM？

第一次 **抽结构化 JSON**（让后端可以稳定绘图、存档、对比）；第二次 **基于结构化结果做解读**，更稳定也更可控。

