from typing import Dict, Any
import pandas as pd
from datetime import datetime, timedelta, date
import requests
import yfinance as yf

try:
    import akshare as ak
except Exception:
    ak = None


def get_realtime_quote(symbol: str) -> Dict[str, Any]:
    ticker = yf.Ticker(symbol)
    info = ticker.fast_info
    return {
        "symbol": symbol,
        "last_price": float(info.last_price) if info.last_price is not None else None,
        "currency": info.currency,
        "exchange": info.exchange,
        "regular_market_time": (
            info.last_price_time.isoformat() if getattr(info, "last_price_time", None) else None
        ),
    }   


def compare_sector_trend(
    symbols: Dict[str, str],
    months: int = 3,
) -> Dict[str, Any]:
    # symbols: {symbol: display_name}
    end = datetime.utcnow()
    start = end - timedelta(days=30 * months)
    result = {"start": start.isoformat(), "end": end.isoformat(), "series": []}
    for sym, name in symbols.items():
        df = yf.download(sym, start=start, end=end, interval="1d", progress=False)
        if df.empty:
            continue
        df = df.reset_index()
        base = df["Close"].iloc[0]
        df["pct_change"] = (df["Close"] / base - 1.0) * 100
        points = []
        for _, row in df.iterrows():
            points.append(
                {
                    "date": row["Date"].isoformat() if isinstance(row["Date"], (datetime,)) else str(row["Date"]),
                    "pct_change": float(row["pct_change"]),
                }
            )
        result["series"].append({"symbol": sym, "name": name, "points": points})
    return result
