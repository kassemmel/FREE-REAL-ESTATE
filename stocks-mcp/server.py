import yfinance as yf
from fastmcp import FastMCP

mcp = FastMCP("stocks")


@mcp.tool
def get_quote(symbol: str) -> dict:
    """Latest price and day stats for a ticker symbol."""
    fi = yf.Ticker(symbol).fast_info
    return {
        "symbol": symbol.upper(),
        "last_price": fi.last_price,
        "previous_close": fi.previous_close,
        "day_high": fi.day_high,
        "day_low": fi.day_low,
        "currency": fi.currency,
    }


@mcp.tool
def get_history(symbol: str, period: str = "1mo", interval: str = "1d") -> list[dict]:
    """Historical OHLCV. period: 1d,5d,1mo,3mo,1y,max. interval: 1d,1h,5m."""
    df = yf.Ticker(symbol).history(period=period, interval=interval)
    return [
        {
            "date": str(i.date()),
            "open": r.Open,
            "high": r.High,
            "low": r.Low,
            "close": r.Close,
            "volume": int(r.Volume),
        }
        for i, r in df.iterrows()
    ]


if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8000)  # serves /mcp
