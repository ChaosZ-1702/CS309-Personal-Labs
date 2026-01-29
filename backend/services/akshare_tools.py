import json
import threading
import tempfile
import os
import time
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
import akshare as ak
import re

# 缓存 A 股 代码-名称表，减少首次搜索阻塞
_CN_CODE_NAME_DF: Optional[pd.DataFrame] = None
_HK_CODE_NAME_DF: Optional[pd.DataFrame] = None
_US_CODE_NAME_DF: Optional[pd.DataFrame] = None
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
CN_CACHE_FILE = DATA_DIR / "cn_codes.json"
HK_CACHE_FILE = DATA_DIR / "hk_codes.json"
US_CACHE_FILE = DATA_DIR / "us_codes.json"
CACHE_EXPIRY_HOURS = 24
_CN_LOCK = threading.Lock()
_HK_LOCK = threading.Lock()
_US_LOCK = threading.Lock()

def _is_file_fresh(path: Path, hours: int = 24) -> bool:
    """检查文件是否存在且在有效期内"""
    if not path.exists():
        return False
    try:
        mtime = path.stat().st_mtime
        if time.time() - mtime < (hours * 3600):
            return True
        return False
    except Exception:
        return False
    
def _atomic_dump_json(path: Path, data: List[Dict[str, Any]]) -> None:
    """原子写入：先写临时文件，再原子替换，防止文件损坏"""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", dir=path.parent, suffix=".tmp") as tmp:
            json.dump(data, tmp, ensure_ascii=False, indent=2)
            tmp_path = Path(tmp.name)
        
        tmp_path.replace(path)
    except Exception:
        if 'tmp_path' in locals() and tmp_path.exists():
            os.unlink(tmp_path)

def _load_json_safe(path: Path) -> List[Dict[str, Any]]:
    """安全读取 JSON"""
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception as e:
        print(f"[Cache] Corrupted file {path.name}: {e}")
        return []

def _is_valid_hk_cache(rows: List[Dict[str, Any]]) -> bool:
    if not rows:
        return False
    sample = rows[:10]
    for r in sample:
        code = str(r.get("code", ""))
        sym = str(r.get("symbol", ""))
        if not code.isdigit():
            return False
        if not (4 <= len(code) <= 5):
            return False
        if not sym.endswith(".HK"):
            return False
    return True

def _is_valid_us_cache(rows: List[Dict[str, Any]]) -> bool:
    if not rows:
        return False
    sample = rows[:10]
    for r in sample:
        code = str(r.get("code", "")).strip()
        sym = str(r.get("symbol", "")).strip()
        if not code or not sym:
            return False
        # 美股代码通常为字母/数字/点/破折号，长度 1-8 较常见
        if not (1 <= len(code) <= 16):
            return False
        if not sym.isupper():
            return False
    return True

def get_indices_snapshot() -> Dict[str, Any]:
    """使用 AkShare 获取 A 股主要指数的实时行情快照。"""
    # 尽量多拿一些常用指数，不再用严格白名单过滤
    try:
        # 东方财富：全部指数
        df = ak.stock_zh_index_spot_em()
        source = "em"
    except Exception:
        # 退回新浪指数
        df = ak.stock_zh_index_spot_sina()
        source = "sina"

    indices: List[Dict[str, Any]] = []

    # 只取前 20 条，避免一次性太多
    for _, row in df.head(20).iterrows():
        code = str(
            row.get("代码")
            or row.get("index_code")
            or row.get("symbol")
            or ""
        ).strip()
        name = str(
            row.get("名称")
            or row.get("index_name")
            or row.get("name")
            or ""
        ).strip()

        last = row.get("最新价") or row.get("close")
        change_pct = row.get("涨跌幅") or row.get("pct_chg")
        high = row.get("最高") or row.get("high")
        low = row.get("最低") or row.get("low")
        volume = row.get("成交量") or row.get("vol")
        amount = row.get("成交额") or row.get("amount")

        indices.append(
            {
                "code": code,
                "name": name,
                "last": float(last) if last is not None else None,
                "change_pct": float(change_pct) if change_pct is not None else None,
                "high": float(high) if high is not None else None,
                "low": float(low) if low is not None else None,
                "volume": float(volume) if volume is not None else None,
                "amount": float(amount) if amount is not None else None,
            }
        )

    return {
        "source": source,
        # "as_of": datetime.utcnow().isoformat(),
        "as_of": datetime.now().isoformat(),
        "indices": indices,
    }

def _prefix_cn_symbol(code: str) -> str:
    """根据 A 股代码推断交易所并加上前缀，如 600519 -> sh600519，000001 -> sz000001。"""
    code = str(code).strip()
    if code.lower().startswith(("sh", "sz")):
        return code.lower()
    if len(code) == 6 and code.isdigit():
        if code.startswith(("0", "2", "3")):
            return "sz" + code
        elif code.startswith("6"):
            return "sh" + code
    return code


def _hk_to_yf_symbol(code: str) -> str:
    """
    将港股代码（如 00700 / 0700）转换为 Yahoo Finance 格式：0700.HK。
    规则：去前导 0，左侧填充到 4 位，再加 .HK
    """
    s = str(code or "").strip()
    if not s:
        return s
    s_digits = "".join(ch for ch in s if ch.isdigit())
    if not s_digits:
        return s
    s_no_leading = s_digits.lstrip("0") or "0"
    s_padded = s_no_leading.zfill(4)
    return f"{s_padded}.HK"

def _normalize_hk_code(code: str) -> str:
    """
    将港股代码标准化为 5 位数字字符串（AkShare 习惯用 5 位含前导 0）。
    """
    s = str(code or "").strip()
    if s.lower().endswith(".hk"):
        s = s[:-3]
    digits = "".join(ch for ch in s if ch.isdigit())
    if not digits:
        return s
    return digits.zfill(5)

def get_cached_cn_code_name_list() -> List[Dict[str, Any]]:
    global _CN_CODE_NAME_DF
    
    if _CN_CODE_NAME_DF is not None and not _CN_CODE_NAME_DF.empty:
        return _CN_CODE_NAME_DF.to_dict(orient="records")

    if _is_file_fresh(CN_CACHE_FILE, hours=CACHE_EXPIRY_HOURS):
        data = _load_json_safe(CN_CACHE_FILE)
        if data:
            _CN_CODE_NAME_DF = pd.DataFrame(data)
            return data

    with _CN_LOCK:
        if _is_file_fresh(CN_CACHE_FILE, hours=CACHE_EXPIRY_HOURS):
             data = _load_json_safe(CN_CACHE_FILE)
             if data:
                 _CN_CODE_NAME_DF = pd.DataFrame(data)
                 return data
        
        try:
            df = ak.stock_info_a_code_name()
            rows = []
            
            code_col = next((c for c in df.columns if c.lower() in ["code", "代码"]), None)
            name_col = next((c for c in df.columns if c.lower() in ["name", "名称"]), None)
            
            if code_col and name_col:
                for _, row in df.iterrows():
                    code = str(row[code_col]).strip()
                    name = str(row[name_col]).strip()
                    if not code: continue
                    rows.append({
                        "symbol": _prefix_cn_symbol(code),
                        "code": code,
                        "name": name,
                        "market": "cn"
                    })
            
            if rows:
                _atomic_dump_json(CN_CACHE_FILE, rows)
                _CN_CODE_NAME_DF = pd.DataFrame(rows)
                return rows
                
        except Exception:
            old_data = _load_json_safe(CN_CACHE_FILE)
            if old_data:
                _CN_CODE_NAME_DF = pd.DataFrame(old_data)
                return old_data
    
    return []

def get_cached_hk_code_name_list() -> List[Dict[str, Any]]:
    global _HK_CODE_NAME_DF
    
    if _HK_CODE_NAME_DF is not None and not _HK_CODE_NAME_DF.empty:
        return _HK_CODE_NAME_DF.to_dict(orient="records")

    if _is_file_fresh(HK_CACHE_FILE, hours=CACHE_EXPIRY_HOURS):
        data = _load_json_safe(HK_CACHE_FILE)
        if data and _is_valid_hk_cache(data):
            _HK_CODE_NAME_DF = pd.DataFrame(data)
            return data

    with _HK_LOCK:
        if _is_file_fresh(HK_CACHE_FILE, hours=CACHE_EXPIRY_HOURS):
            data = _load_json_safe(HK_CACHE_FILE)
            if data and _is_valid_hk_cache(data):
                _HK_CODE_NAME_DF = pd.DataFrame(data)
                return data

        try:
            df = ak.stock_hk_spot()
            rows = []

            code_col = next((c for c in df.columns if "代码" in str(c) or "code" in str(c).lower()), df.columns[0])
            
            for _, row in df.iterrows():
                raw = str(row.get(code_col, ""))
                cn_name = str(row.get("中文名称", row.get("名称", "")))
                en_name = str(row.get("英文名称", row.get("name", ""))).strip()
                name = f"{cn_name} / {en_name}" if cn_name and en_name else (cn_name or en_name)
                if raw and raw.isdigit():
                    norm_code = _normalize_hk_code(raw)
                    rows.append({
                        "symbol": _hk_to_yf_symbol(norm_code),
                        "code": norm_code,
                        "name": name,
                        "market": "hk"
                    })
            
            if rows:
                _atomic_dump_json(HK_CACHE_FILE, rows)
                _HK_CODE_NAME_DF = pd.DataFrame(rows)
                return rows
        except Exception as e:
            fallback = _load_json_safe(HK_CACHE_FILE)
            if fallback: 
                _HK_CODE_NAME_DF = pd.DataFrame(fallback)
                return fallback
                
    return []

def get_cached_us_code_name_list() -> List[Dict[str, Any]]:
    global _US_CODE_NAME_DF
    
    if _US_CODE_NAME_DF is not None and not _US_CODE_NAME_DF.empty:
        return _US_CODE_NAME_DF.to_dict(orient="records")

    if _is_file_fresh(US_CACHE_FILE, hours=CACHE_EXPIRY_HOURS):
        data = _load_json_safe(US_CACHE_FILE)
        if data and _is_valid_us_cache(data):
            _US_CODE_NAME_DF = pd.DataFrame(data)
            return data

    with _US_LOCK:
        if _is_file_fresh(US_CACHE_FILE, hours=CACHE_EXPIRY_HOURS):
             data = _load_json_safe(US_CACHE_FILE)
             if data:
                 _US_CODE_NAME_DF = pd.DataFrame(data)
                 return data

        try:
            df = ak.stock_us_spot_em()
            rows = []
            code_col = next((c for c in df.columns if c.lower() in ["代码", "code", "symbol"]), df.columns[0])
            name_col = next((c for c in df.columns if c.lower() in ["名称", "name"]), df.columns[1])
            
            for _, row in df.iterrows():
                code = str(row.get(code_col, "")).upper()
                name = str(row.get(name_col, ""))
                if code:
                    rows.append({
                        "symbol": code,
                        "code": code,
                        "name": name,
                        "market": "us"
                    })
            
            if rows:
                _atomic_dump_json(US_CACHE_FILE, rows)
                _US_CODE_NAME_DF = pd.DataFrame(rows)
                return rows
        except Exception:
            fallback = _load_json_safe(US_CACHE_FILE)
            if fallback:
                _US_CODE_NAME_DF = pd.DataFrame(fallback)
                return fallback
    return []

def _get_query_dates(days: int):
    end_date = datetime.today().date()
    start_date = end_date - timedelta(days=days + 5) # 多取几天防节假日
    return start_date.strftime("%Y%m%d"), end_date.strftime("%Y%m%d")

def _process_stock_dataframe(df: Any, symbol: str, source: str, days: int) -> Dict[str, Any]:
    """
    公共方法：处理 AkShare 返回的 DataFrame，提取日期和收盘价序列。
    """
    if df is None or getattr(df, "empty", False):
        return {"source": source, "symbol": symbol, "points": [], "raw": []}

    df = df.sort_values(by=df.columns[0])
    date_col = None
    close_col = None
    for col in df.columns:
        lc = str(col).lower()
        if ("date" in lc) or ("日期" in lc):
            date_col = col
        if ("close" in lc) or ("收盘" in lc):
            close_col = col
            
    if date_col is None or close_col is None:
        return {
            "source": source, 
            "symbol": symbol, 
            "raw": df.to_dict(orient="records"), 
            "points": []
        }

    target_df = df.tail(days)
    points: List[Dict[str, Any]] = []
    
    for _, row in target_df.iterrows():
        try:
            d = row[date_col]
            d_str = d.date().isoformat() if hasattr(d, "date") else str(d)[:10]
            points.append({
                "date": d_str, 
                "close": float(row[close_col])
            })
        except Exception:
            continue

    return {"source": source, "symbol": symbol, "points": points}

def get_cn_stock_history(symbol: str, days: int = 90) -> Dict[str, Any]:
    """
    获取 A 股股票日线收盘价序列，使用 AkShare，统一返回 points:[{date, close}].
    """
    start_str, end_str = _get_query_dates(days)
    symbol = _prefix_cn_symbol(symbol)
    df = None
    source = "akshare"

    # 优先尝试新版接口，若空则继续回退
    try:
        df = ak.stock_zh_a_hist(symbol=symbol, start_date=start_str, end_date=end_str, period="daily", adjust="")
        source = "akshare-em"
    except Exception:
        pass

    if df is None or getattr(df, "empty", False):
        try:
            df = ak.stock_zh_a_daily(symbol=symbol)
            source = "akshare-sina"
        except Exception:
            pass

    return _process_stock_dataframe(df, symbol, source, days)

def get_hk_stock_history(symbol: str, days: int = 90) -> Dict[str, Any]:
    """
    获取港股日线收盘价，使用 AkShare，统一返回 points:[{date, close}]."""
    
    norm_code = _normalize_hk_code(symbol)
    start_str, end_str = _get_query_dates(days)
    df = None
    source = "akshare"

    try:
        df = ak.stock_hk_hist(symbol=norm_code, start_date=start_str, end_date=end_str, period="daily", adjust="")
        source = "akshare-em"
    except Exception:
        df = None

    if df is None or getattr(df, "empty", False):
        try:
            df = ak.stock_hk_daily(symbol=norm_code)
            source = "akshare-sina"
        except Exception:
            pass

    return _process_stock_dataframe(df, symbol, source, days)

def _normalize_us_symbol(s: str) -> str:
    t = str(s or "").strip().upper()
    # 匹配形如 105.AAPL / 100.MSFT / 106.BRK.B 等，取点后的部分
    if re.match(r"^\d+\.[A-Z0-9\-.]+$", t):
        return t.split(".", 1)[1]
    return t

def get_us_stock_history(symbol: str, days: int = 90) -> Dict[str, Any]:
    """
    获取美股日线收盘价，使用 AkShare，统一返回 points:[{date, close}].
    """
    start_str, end_str = _get_query_dates(days)
    df = None
    source = "akshare"
    
    try:
        df = ak.stock_us_hist(symbol=symbol, start_date=start_str, end_date=end_str, period="daily", adjust="")
        source = "akshare-em"
    except Exception:
        pass

    if df is None or getattr(df, "empty", False):
        try:
            df = ak.stock_us_daily(symbol=_normalize_us_symbol(symbol))
            source = "akshare-sina"
        except Exception:
            pass

    return _process_stock_dataframe(df, symbol, source, days)