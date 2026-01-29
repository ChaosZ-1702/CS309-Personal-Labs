// akshark API 占位封装，请根据实际文档修改 baseURL、路径和字段名

const AKSHARK_BASE_URL = "https://api.your-akshark-domain.com"; // ← TODO: 替换成真实地址
const AKSHARK_API_KEY = ""; // ← 如果需要鉴权，则填入或通过环境变量注入

export async function fetchAksharkNews({ page = 1, pageSize = 10 } = {}) {
  const url = new URL(`${AKSHARK_BASE_URL}/v1/finance/news`); // ← TODO: 根据实际接口调整路径
  url.searchParams.set("page", String(page));
  url.searchParams.set("page_size", String(pageSize));

  const res = await fetch(url.toString(), {
    headers: {
      "Content-Type": "application/json",
      ...(AKSHARK_API_KEY ? { Authorization: `Bearer ${AKSHARK_API_KEY}` } : {})
    }
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`akshark 请求失败 ${res.status}: ${text}`);
  }

  const data = await res.json();
  // 假设返回 { items: [...], total: number }，如不一致请按实际结构调整
  return data;
}
