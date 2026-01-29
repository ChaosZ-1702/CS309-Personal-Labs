const BACKEND_BASE_URL = "http://localhost:8000";

async function _readSSE(res) {
  if (!res.ok || !res.body) {
    const text = await res.text();
    throw new Error(`上传失败 ${res.status}: ${text}`);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let sep;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const packet = buffer.slice(0, sep).trim();
      buffer = buffer.slice(sep + 2);
      if (!packet.startsWith("data:")) continue;
      const jsonStr = packet.replace(/^data:\s*/, "");
      let payload;
      try {
        payload = JSON.parse(jsonStr);
      } catch {
        continue;
      }

      if (payload.type === "done") return payload;
      if (payload.type === "error") throw new Error(payload.message || "上传解析流式错误");
    }
  }
  throw new Error("上传解析流未返回完成事件");
}

export async function uploadPdf({ sessionId, file, store = true }) {
  const form = new FormData();
  form.append("session_id", sessionId);
  form.append("file", file);
  form.append("store", store ? "true" : "false");

  const res = await fetch(`${BACKEND_BASE_URL}/api/upload/pdf/stream`, {
    method: "POST",
    body: form
  });

  const payload = await _readSSE(res);
  return {
    session_id: payload.session_id,
    filename: payload.filename,
    metrics: payload.metrics,
    steps: payload.steps || [],
  };
}

export async function uploadExcel({ sessionId, file, store = true }) {
  const form = new FormData();
  form.append("session_id", sessionId);
  form.append("file", file);
  form.append("store", store ? "true" : "false");

  const res = await fetch(`${BACKEND_BASE_URL}/api/upload/excel/stream`, {
    method: "POST",
    body: form
  });

  const payload = await _readSSE(res);
  return {
    session_id: payload.session_id,
    filename: payload.filename,
    metrics: payload.metrics,
    steps: payload.steps || [],
  };
}
