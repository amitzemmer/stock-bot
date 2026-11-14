"""
בוט שוק ההון - מושך נתונים, מנתח ובונה דף docs/index.html
מניות: S&P 500 + נאסד"ק 100
"""
import io
import os
import html
import datetime as dt

import numpy as np
import pandas as pd
import requests
import yfinance as yf

H = {"User-Agent": "Mozilla/5.0"}


# ---------- רשימת המניות ----------
def wiki_table(url, col):
    page = requests.get(url, headers=H, timeout=30).text
    for t in pd.read_html(io.StringIO(page)):
        if col in t.columns:
            return t
    raise RuntimeError(f"לא נמצאה טבלה ב-{url}")


def get_universe():
    names = {}
    sp = wiki_table("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", "Symbol")
    for s, n in zip(sp["Symbol"], sp["Security"]):
        names[str(s).replace(".", "-")] = n
    try:
        nq = wiki_table("https://en.wikipedia.org/wiki/Nasdaq-100", "Ticker")
        for s, n in zip(nq["Ticker"], nq["Company"]):
            names.setdefault(str(s).replace(".", "-"), n)
    except Exception as e:  # לא קריטי
        print("נאסד\"ק 100 לא נטען:", e)
    return names


# ---------- חישובים ----------
def rsi(close, n=14):
    d = close.diff()
    up = d.clip(lower=0).rolling(n).mean()
    dn = (-d.clip(upper=0)).rolling(n).mean()
    return float((100 - 100 / (1 + up / dn)).iloc[-1])


def score_stock(price, ma50, ma200, month, rsi14, vol_ratio, from_high):
    """ציון 0-100 + סיבות. זה כלי מיון לפי מומנטום, לא תחזית."""
    score, why = 0, []
    if price > ma50:
        score += 25
        why.append("מעל ממוצע 50 יום")
    if ma50 > ma200:
        score += 20
        why.append("מגמה עולה לטווח ארוך")
    score += round(min(max(month, 0) / 0.15, 1) * 20)
    if month > 0.03:
        why.append("מומנטום חודשי חיובי")
    if 50 <= rsi14 <= 70:
        score += 15
        why.append("RSI בריא")
    elif rsi14 > 75:
        why.append("חם מדי (RSI גבוה)")
    if vol_ratio > 1.2:
        score += 10
        why.append("נפח מסחר מוגבר")
    if from_high >= -0.10:
        score += 10
        why.append("קרוב לשיא שנתי")
    return score, why


def analyze(tk, df):
    close = df["Close"].dropna()
    vol = df["Volume"].dropna()
    if len(close) < 210 or len(vol) < 60:
        return None
    price = float(close.iloc[-1])
    avg_dollar_vol = price * float(vol.tail(50).mean())
    if price < 5 or avg_dollar_vol < 2e7:  # מסננים מניות קטנות/לא נזילות
        return None
    week = price / float(close.iloc[-6]) - 1
    month = price / float(close.iloc[-22]) - 1
    ma50 = float(close.tail(50).mean())
    ma200 = float(close.tail(200).mean())
    r = rsi(close)
    vol_ratio = float(vol.tail(5).mean() / vol.tail(50).mean())
    from_high = price / float(close.tail(252).max()) - 1
    s, why = score_stock(price, ma50, ma200, month, r, vol_ratio, from_high)
    return dict(ticker=tk, price=price, week=week, month=month, rsi=r,
                score=s, why=why)


def index_week(symbol):
    try:
        c = yf.download(symbol, period="1mo", auto_adjust=True, progress=False)["Close"].dropna()
        c = c.squeeze()
        return float(c.iloc[-1] / c.iloc[-6] - 1), float(c.iloc[-1])
    except Exception:
        return None, None


# ---------- בניית הדף ----------
def pct(x):
    cls = "pos" if x >= 0 else "neg"
    return f'<span class="{cls}" dir="ltr">{x * 100:+.1f}%</span>'


def table(rows, names, show_score=False):
    head = "<tr><th>סימול</th><th>חברה</th><th>מחיר</th><th>שבוע</th><th>חודש</th>"
    head += "<th>ציון</th><th>למה</th></tr>" if show_score else "</tr>"
    out = [head]
    for r in rows:
        tds = (
            f"<td><b>{html.escape(r['ticker'])}</b></td>"
            f"<td>{html.escape(str(names.get(r['ticker'], '')))}</td>"
            f"<td dir='ltr'>${r['price']:.2f}</td>"
            f"<td>{pct(r['week'])}</td><td>{pct(r['month'])}</td>"
        )
        if show_score:
            tds += f"<td><b>{r['score']}</b></td><td class='why'>{' · '.join(r['why'])}</td>"
        out.append(f"<tr>{tds}</tr>")
    return "<div class='scroll'><table>" + "".join(out) + "</table></div>"


TEMPLATE = """<!doctype html>
<html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>בוט שוק ההון</title>
<style>
body{font-family:system-ui,Arial,sans-serif;background:#0f1419;color:#e6e9ee;margin:0;padding:16px;max-width:960px;margin-inline:auto}
h1{font-size:22px;margin:0 0 4px} h2{font-size:18px;margin:28px 0 8px}
.sub{color:#8b95a3;font-size:13px}
.cards{display:flex;gap:10px;margin:14px 0;flex-wrap:wrap}
.card{background:#1a2029;border-radius:10px;padding:12px 16px;flex:1;min-width:140px}
.card b{display:block;font-size:20px}
.scroll{overflow-x:auto}
table{width:100%;border-collapse:collapse;background:#1a2029;border-radius:10px;font-size:14px}
th,td{padding:8px 10px;text-align:right;border-bottom:1px solid #262e3a;white-space:nowrap}
td.why{white-space:normal;color:#aab3c0;font-size:12px;min-width:180px}
th{color:#8b95a3;font-weight:600}
.pos{color:#3ddc84}.neg{color:#ff6b6b}
.note{background:#1a2029;border-radius:10px;padding:12px;margin-top:28px;color:#aab3c0;font-size:13px;line-height:1.6}
</style></head><body>
<h1>📈 סיכום שוק ההון</h1>
<div class="sub">עודכן לאחרונה: __UPDATED__ · ניתוח של __COUNT__ מניות · שינויים = 5 ימי מסחר אחרונים</div>
<div class="cards">__CARDS__</div>
<h2>⭐ המניות המבטיחות ביותר</h2>
<div class="sub">דירוג לפי מומנטום, מגמה, נפח מסחר וקרבה לשיא. הציון מ-0 עד 100.</div>
__PROMISING__
<h2>🚀 העולות ביותר השבוע</h2>__GAINERS__
<h2>🔻 היורדות ביותר השבוע</h2>__LOSERS__
<div class="note">⚠️ הדף מבוסס על חישובים טכניים אוטומטיים בלבד ואינו ייעוץ השקעות או תחזית.
מניה עם ציון גבוה יכולה לרדת. הנתונים מ-Yahoo Finance ועשויים להיות מעוכבים או שגויים. בדוק תמיד לפני שמחליטים.</div>
</body></html>"""


def main():
    names = get_universe()
    tickers = sorted(names)
    print("מוריד נתונים עבור", len(tickers), "מניות...")
    data = yf.download(tickers, period="1y", auto_adjust=True, group_by="ticker",
                       threads=True, progress=False)

    rows = []
    for tk in tickers:
        try:
            res = analyze(tk, data[tk])
            if res:
                rows.append(res)
        except Exception:
            continue
    if not rows:
        raise SystemExit("לא התקבלו נתונים - לא מעדכן את הדף")

    df = pd.DataFrame(rows)
    gainers = df.sort_values("week", ascending=False).head(10).to_dict("records")
    losers = df.sort_values("week").head(10).to_dict("records")
    promising = (df.sort_values(["score", "month"], ascending=False)
                 .head(15).to_dict("records"))

    cards = []
    for label, sym in [("S&P 500", "^GSPC"), ("נאסד\"ק", "^IXIC")]:
        w, last = index_week(sym)
        if w is not None:
            cards.append(f"<div class='card'>{label}<b>{pct(w)}</b>"
                         f"<span class='sub'>{last:,.0f}</span></div>")
    breadth = (df["week"] > 0).mean()
    cards.append(f"<div class='card'>מניות שעלו השבוע<b>{breadth * 100:.0f}%</b></div>")

    now = dt.datetime.now(dt.timezone.utc).astimezone(
        dt.timezone(dt.timedelta(hours=2))).strftime("%d/%m/%Y %H:%M")
    page = (TEMPLATE.replace("__UPDATED__", now)
            .replace("__COUNT__", str(len(df)))
            .replace("__CARDS__", "".join(cards))
            .replace("__PROMISING__", table(promising, names, True))
            .replace("__GAINERS__", table(gainers, names))
            .replace("__LOSERS__", table(losers, names)))

    os.makedirs("docs", exist_ok=True)
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(page)
    print("docs/index.html נוצר")


if __name__ == "__main__":
    main()
