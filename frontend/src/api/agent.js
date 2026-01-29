const BACKEND_BASE_URL = "http://localhost:8000";

export async function sendChat({ sessionId, query, language = "zh", exportMarkdown = true }) {
  const res = await fetch(`${BACKEND_BASE_URL}/api/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json"
    },
    body: JSON.stringify({
      session_id: sessionId,
      query,
      language,
      export_markdown: exportMarkdown,
      export_pdf: false
    })
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`后端返回错误 ${res.status}: ${text}`);
  }

  return await res.json();
}
