const BACKEND_BASE_URL = "http://localhost:8000";

export async function searchStocks(q, limit = 10) {
  if (!q || !q.trim()) return [];

  const url = new URL(`${BACKEND_BASE_URL}/api/stocks/search`);
  url.searchParams.set("q", q.trim());
  url.searchParams.set("limit", String(limit));

  const res = await fetch(url.toString(), {
    headers: { Accept: "application/json" }
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`搜索接口错误 ${res.status}: ${text}`);
  }

  const data = await res.json();
  // 后端返回：{ items: [...] }
  return data.items || [];
}

export async function getStockHistory(symbol, days = 90) {
  const url = new URL(`${BACKEND_BASE_URL}/api/stocks/history`);
  url.searchParams.set("symbol", symbol);
  url.searchParams.set("days", String(days));

  const res = await fetch(url.toString(), {
    headers: { Accept: "application/json" }
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`历史行情接口错误 ${res.status}: ${text}`);
  }

  return await res.json();
}
