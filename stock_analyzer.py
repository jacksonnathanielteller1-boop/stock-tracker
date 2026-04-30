"""
Stock Analyzer — fundamental analysis via yfinance + SEC EDGAR 10-K
58-question framework across 5 categories.
"""

import sys
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

import re
import time
import statistics
import datetime
import os
import json
import io
import contextlib
from dataclasses import dataclass
from typing import Optional

try:
    import yfinance as yf
except ImportError:
    print("Missing dependency. Run: pip install yfinance")
    sys.exit(1)

try:
    import requests
except ImportError:
    print("Missing dependency. Run: pip install requests")
    sys.exit(1)

# ─────────────────────────────────────────────
# SEC EDGAR configuration
# Replace with your name and email — required by SEC fair-access policy.
# ─────────────────────────────────────────────
SEC_USER_AGENT = "StockAnalyzer user@example.com"   # <-- edit this


# ─────────────────────────────────────────────
# Core helpers
# ─────────────────────────────────────────────

@dataclass
class Answer:
    question: str
    result: str          # "Yes", "No", "Manual Review Needed"
    detail: str = ""
    excerpt: str = ""    # 10-K snippet (empty when not used)


def safe(fn, default=None):
    try:
        v = fn()
        return default if v is None else v
    except Exception:
        return default


def pct(v):
    return f"{v*100:.1f}%" if v is not None else "N/A"


def fmt(v, decimals=2):
    return f"{v:.{decimals}f}" if v is not None else "N/A"


def yesno(condition: Optional[bool], detail: str) -> tuple[str, str]:
    if condition is None:
        return "Manual Review Needed", detail
    return ("Yes" if condition else "No"), detail


def mr(detail: str) -> tuple[str, str]:
    return "Manual Review Needed", detail


# ─────────────────────────────────────────────
# yfinance data helpers
# ─────────────────────────────────────────────

def fetch_yf(ticker: str):
    t = yf.Ticker(ticker)
    info       = safe(lambda: t.info, {})
    financials = safe(lambda: t.financials)
    balance    = safe(lambda: t.balance_sheet)
    cashflow   = safe(lambda: t.cashflow)
    return t, info, financials, balance, cashflow


def row(df, *keys):
    """First matching row from DataFrame as list (recent->old), or []."""
    if df is None:
        return []
    for k in keys:
        for idx in df.index:
            if k.lower() in str(idx).lower():
                return [v for v in df.loc[idx] if v is not None and str(v) != "nan"]
    return []


def avg(lst):
    clean = [x for x in lst if x is not None]
    return statistics.mean(clean) if clean else None


def cagr(values: list, years: int):
    """values[0] = most recent, values[-1] = oldest."""
    clean = [v for v in values if v is not None and v != 0]
    if len(clean) < 2 or years <= 0:
        return None
    start, end = clean[-1], clean[0]
    if start <= 0 or end <= 0:
        return None
    return (end / start) ** (1 / years) - 1


def stable(values: list, threshold=0.2) -> bool:
    """True if no value deviates more than threshold from the mean."""
    clean = [v for v in values if v is not None]
    if len(clean) < 2:
        return False
    m = statistics.mean(clean)
    if m == 0:
        return False
    return all(abs(v - m) / abs(m) <= threshold for v in clean)


# ─────────────────────────────────────────────
# SEC EDGAR — filing fetch
# ─────────────────────────────────────────────

_SEC_DELAY = 0.6   # seconds between requests (be polite)
_SEC_HDR   = {"User-Agent": SEC_USER_AGENT, "Accept-Encoding": "gzip, deflate"}


def _sec_get(url: str, timeout: int = 20) -> Optional[requests.Response]:
    try:
        time.sleep(_SEC_DELAY)
        r = requests.get(url, headers=_SEC_HDR, timeout=timeout)
        r.raise_for_status()
        return r
    except Exception:
        return None


def _get_cik(ticker: str) -> Optional[str]:
    """Return zero-padded 10-digit CIK for ticker, or None."""
    r = _sec_get("https://www.sec.gov/files/company_tickers.json")
    if not r:
        return None
    for entry in r.json().values():
        if entry.get("ticker", "").upper() == ticker.upper():
            return str(entry["cik_str"]).zfill(10)
    return None


def _get_latest_10k(cik: str) -> Optional[tuple[str, str, str]]:
    """
    Return (accession_nodash, filing_date, primary_doc_filename) for the
    most recent 10-K, or None.  The submissions JSON already includes the
    primary document name, so no separate index fetch is needed.
    """
    r = _sec_get(f"https://data.sec.gov/submissions/CIK{cik}.json")
    if not r:
        return None
    recent = r.json().get("filings", {}).get("recent", {})
    forms    = recent.get("form", [])
    accs     = recent.get("accessionNumber", [])
    dates    = recent.get("filingDate", [])
    pri_docs = recent.get("primaryDocument", [])
    for form, acc, date, doc in zip(forms, accs, dates, pri_docs):
        if form == "10-K":
            return acc.replace("-", ""), date, doc
    return None


def _strip_html(html: str) -> str:
    """Strip HTML tags and decode common entities."""
    text = re.sub(r"<[^>]{0,2000}?>", " ", html, flags=re.DOTALL)
    for ent, ch in [("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"),
                    ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'")]:
        text = text.replace(ent, ch)
    return re.sub(r"\s+", " ", text)


def fetch_10k_text(ticker: str) -> tuple[Optional[str], str]:
    """
    Download and return (plain_text, status_message) for the most recent
    10-K from SEC EDGAR. Returns (None, reason) on failure.
    """
    print("  Fetching SEC EDGAR data...")
    cik = _get_cik(ticker)
    if not cik:
        return None, "CIK not found for ticker"

    result = _get_latest_10k(cik)
    if not result:
        return None, "No 10-K filing found in EDGAR"
    acc, date, doc = result
    print(f"  CIK={cik} | 10-K filed {date} | doc={doc}")

    if not doc:
        return None, "primaryDocument field missing from EDGAR submissions"

    cik_int = int(cik)
    url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc}/{doc}"
    print(f"  Downloading 10-K...")
    r = _sec_get(url, timeout=90)
    if not r:
        return None, f"Failed to download {url}"

    text = _strip_html(r.text)
    print(f"  10-K loaded ({len(text):,} chars).")
    return text, f"10-K filed {date}"


# ─────────────────────────────────────────────
# 10-K text search helpers
# ─────────────────────────────────────────────

def _snippets(text: str, keywords: list[str], context: int = 280,
              max_hits: int = 2) -> list[tuple[str, str]]:
    """
    Find up to max_hits occurrences of any keyword.
    Returns list of (matched_keyword, surrounding_snippet).
    """
    if not text:
        return []
    tl = text.lower()
    results: list[tuple[str, str]] = []
    seen: list[int] = []
    for kw in keywords:
        kwl = kw.lower()
        pos = 0
        while len(results) < max_hits:
            idx = tl.find(kwl, pos)
            if idx == -1:
                break
            if not any(abs(idx - s) < 150 for s in seen):
                s = max(0, idx - context)
                e = min(len(text), idx + len(kw) + context)
                snip = text[s:e].strip()
                if s > 0:
                    snip = "..." + snip
                if e < len(text):
                    snip = snip + "..."
                results.append((kw, snip))
                seen.append(idx)
            pos = idx + 1
    return results


def _pcts_near(snippet: str) -> list[float]:
    """Extract all percentage numbers mentioned in a snippet."""
    return [float(m) for m in re.findall(r"(\d+(?:\.\d+)?)\s*%", snippet)]


def _contains_any(text: str, phrases: list[str]) -> bool:
    tl = text.lower()
    return any(p.lower() in tl for p in phrases)


def _first_snippet_str(hits: list[tuple[str, str]]) -> str:
    if not hits:
        return ""
    kw, snip = hits[0]
    return f'[matched: "{kw}"] {snip}'


# ─────────────────────────────────────────────
# Peer comparison helper (Q8)
# ─────────────────────────────────────────────

SECTOR_PEERS: dict[str, list[str]] = {
    "Technology":             ["MSFT", "GOOGL", "META", "ORCL"],
    "Consumer Cyclical":      ["AMZN", "NKE",   "HD",   "TGT"],
    "Consumer Defensive":     ["PG",   "KO",    "PEP",  "WMT"],
    "Healthcare":             ["JNJ",  "ABT",   "MDT",  "BMY"],
    "Financial Services":     ["JPM",  "BAC",   "GS",   "MS"],
    "Industrials":            ["HON",  "GE",    "MMM",  "CAT"],
    "Energy":                 ["XOM",  "CVX",   "COP",  "SLB"],
    "Basic Materials":        ["LIN",  "APD",   "ECL",  "NEM"],
    "Utilities":              ["NEE",  "DUK",   "SO",   "AEP"],
    "Real Estate":            ["AMT",  "PLD",   "CCI",  "EQIX"],
    "Communication Services": ["GOOGL","META",  "DIS",  "NFLX"],
}


def fetch_peer_metrics(ticker: str, sector: str) -> tuple[Optional[float], Optional[float], list[str]]:
    """
    Fetch average SG&A% and COGS% of revenue for 3-4 sector peers,
    excluding the company being analyzed.
    Returns (peer_avg_sga_pct, peer_avg_cogs_pct, peer_tickers_used).
    """
    peers = [p for p in SECTOR_PEERS.get(sector, []) if p.upper() != ticker.upper()][:4]
    if not peers:
        return None, None, []

    print(f"  Fetching peer data ({', '.join(peers)})...")
    sga_vals, cogs_vals, used = [], [], []
    for p in peers:
        try:
            pt = yf.Ticker(p)
            pfin = safe(lambda: pt.financials)  # noqa: B023
            prev = row(pfin, "Total Revenue")
            psga = row(pfin, "Selling General Administrative",
                             "Selling General And Administrative")
            pcog = row(pfin, "Cost Of Revenue", "Cost of Goods Sold")
            rev1 = prev[0] if prev else None
            sga1 = psga[0] if psga else None
            cog1 = pcog[0] if pcog else None
            if rev1 and rev1 != 0:
                if sga1 is not None:
                    sga_vals.append(sga1 / rev1)
                if cog1 is not None:
                    cogs_vals.append(abs(cog1) / rev1)
                used.append(p)
        except Exception:
            pass
        time.sleep(0.3)

    peer_sga  = avg(sga_vals)  if sga_vals  else None
    peer_cogs = avg(cogs_vals) if cogs_vals else None
    return peer_sga, peer_cogs, used


# ─────────────────────────────────────────────
# WACC via CAPM helper (Q46)
# ─────────────────────────────────────────────

def estimate_wacc(beta: Optional[float], int_exp: Optional[float],
                  total_debt: Optional[float], cash: Optional[float],
                  market_cap: Optional[float], tax_rate: Optional[float]
                  ) -> tuple[Optional[float], str]:
    """
    WACC = Ke * We + Kd_after_tax * Wd
    Ke   = Rf + Beta * ERP   (ERP = 5%)
    Rf   = current 10-yr US Treasury yield from ^TNX
    Kd   = interest expense / total debt
    """
    # Risk-free rate from ^TNX
    try:
        tnx = yf.Ticker("^TNX")
        rf_raw = tnx.info.get("regularMarketPrice") or tnx.info.get("previousClose")
        rf = float(rf_raw) / 100 if rf_raw else 0.045
    except Exception:
        rf = 0.045   # fallback: 4.5%

    ERP  = 0.05
    b    = beta if beta is not None else 1.0
    ke   = rf + b * ERP

    # Cost of debt (after tax)
    if int_exp and total_debt and total_debt > 0:
        kd      = int_exp / total_debt
        kd_at   = kd * (1 - (tax_rate or 0.21))
    else:
        kd      = 0.0
        kd_at   = 0.0

    # Capital weights
    net_debt = max(0.0, (total_debt or 0) - (cash or 0))
    if market_cap and market_cap > 0:
        tc  = market_cap + net_debt
        we  = market_cap / tc
        wd  = net_debt   / tc
    else:
        we, wd = 1.0, 0.0

    wacc = ke * we + kd_at * wd
    detail = (f"Rf={pct(rf)}, Beta={fmt(b)}, ERP=5.0% => Ke={pct(ke)} | "
              f"Kd(pre-tax)={pct(kd)}, Kd(after-tax)={pct(kd_at)} | "
              f"We={pct(we)}, Wd={pct(wd)} => WACC={pct(wacc)}")
    return wacc, detail


# ─────────────────────────────────────────────
# Per-question SEC analysis functions
# ─────────────────────────────────────────────

def sec_q6_retention(text: Optional[str]) -> tuple[str, str, str]:
    """Q6: Customer retention/repeat-purchase > 80%."""
    if not text:
        return *mr("10-K not available; check investor presentations"), ""
    hits = _snippets(text, ["retention rate", "renewal rate", "repeat purchase",
                             "churn rate", "customer retention", "repurchase rate",
                             "retained approximately", "renewed at a rate"])
    if not hits:
        return *mr("No retention/churn keywords found in 10-K"), ""
    for kw, snip in hits:
        for p in _pcts_near(snip):
            if p >= 80:
                return "Yes", f'Retention-related % found: {p}% near "{kw}"', snip
    return *mr(f'Keywords found but no clear >=80% rate; review snippet'), _first_snippet_str(hits)


def sec_q7_patents(text: Optional[str]) -> tuple[str, str, str]:
    """Q7: Patents/trademarks/brand enabling premium pricing."""
    if not text:
        return *mr("10-K not available"), ""
    hits = _snippets(text, ["patent", "trademark", "intellectual property",
                             "proprietary license", "brand recognition", "trade secret"])
    if hits:
        return "Yes", f'IP/brand language found in 10-K ({len(hits)} match(es))', _first_snippet_str(hits)
    return *mr("No patent/trademark/IP language found in 10-K"), ""


def sec_q8_cost_advantage(text: Optional[str], sga_pct: Optional[float],
                           cogs_pct: Optional[float], sector: str,
                           peer_sga: Optional[float], peer_cogs: Optional[float],
                           peer_names: list[str]) -> tuple[str, str, str]:
    """Q8: Cost advantage vs sector peers (SG&A% or COGS%)."""
    parts = []
    if sga_pct  is not None: parts.append(f"SG&A%={pct(sga_pct)}")
    if cogs_pct is not None: parts.append(f"COGS%={pct(cogs_pct)}")
    if peer_sga  is not None: parts.append(f"Peer SG&A%={pct(peer_sga)}")
    if peer_cogs is not None: parts.append(f"Peer COGS%={pct(peer_cogs)}")
    if peer_names: parts.append(f"Peers: {', '.join(peer_names)}")
    parts.append(f"Sector: {sector}")
    data_str = " | ".join(parts)

    excerpt = ""
    if text:
        hits = _snippets(text, ["cost advantage", "lower cost structure", "cost efficiency",
                                 "economies of scale", "operating leverage", "cost leadership"])
        if hits:
            excerpt = _first_snippet_str(hits)

    below_sga  = sga_pct  is not None and peer_sga  is not None and sga_pct  < peer_sga
    below_cogs = cogs_pct is not None and peer_cogs is not None and cogs_pct < peer_cogs

    if below_sga or below_cogs:
        which = []
        if below_sga:  which.append(f"SG&A% {pct(sga_pct)} < peer {pct(peer_sga)}")
        if below_cogs: which.append(f"COGS% {pct(cogs_pct)} < peer {pct(peer_cogs)}")
        return "Yes", f"Below peer avg on {' and '.join(which)} | {data_str}", excerpt

    if peer_sga is None and peer_cogs is None:
        # No peer data: fall back to absolute threshold
        if sga_pct is not None and sga_pct < 0.10:
            return "Yes", f"SG&A%={pct(sga_pct)} < 10% (lean overhead; no peer data) | {data_str}", excerpt
        return *mr(f"No peer data available; {data_str}"), excerpt

    return "No", f"At or above peer avg on both metrics | {data_str}", excerpt


def sec_q9_switching(text: Optional[str]) -> tuple[str, str, str]:
    """Q9: Switching costs evident."""
    if not text:
        return *mr("10-K not available"), ""
    hits = _snippets(text, ["switching cost", "lock-in", "locked-in", "recurring revenue",
                             "subscription", "renewal rate", "high retention", "sticky"])
    if not hits:
        return *mr("No switching-cost or recurring-revenue language found"), ""
    explicit = [h for h in hits if "switching cost" in h[0].lower() or "lock" in h[0].lower()]
    if explicit:
        return "Yes", f'Explicit switching-cost language found: "{explicit[0][0]}"', _first_snippet_str(explicit)
    return "Yes", f'Recurring/subscription model language found: "{hits[0][0]}"', _first_snippet_str(hits)


def sec_q10_business_text(text: Optional[str]) -> tuple[str, str, str]:
    """Q10: Pull first paragraph of Business section for manual review."""
    if not text:
        return *mr("10-K not available; read business description manually"), ""
    tl = text.lower()
    markers = ["item 1. business", "item 1 . business", "item 1business",
               "item\u00a01.\u00a0business", "overview of our business", "business overview"]
    start = -1
    for m in markers:
        idx = tl.find(m)
        if idx != -1:
            start = idx + len(m)
            break
    if start == -1:
        return *mr("Could not locate Business section; read 10-K manually"), ""
    # Skip leading whitespace / short tokens to get to real prose
    segment = text[start:start + 800].lstrip(" \t\n\r:")
    # Trim to first two sentence-ending boundaries for readability
    for end_ch in [". ", ".\n"]:
        second = segment.find(end_ch, segment.find(end_ch) + 1)
        if second != -1 and second > 80:
            segment = segment[:second + 1]
            break
    return *mr("Review business description below — judge if explainable in two sentences"), segment.strip()


def sec_q19_capital_allocation(text: Optional[str]) -> tuple[str, str, str]:
    """Q19: Capital allocation policy clearly stated."""
    if not text:
        return *mr("10-K not available"), ""
    hits = _snippets(text, ["capital allocation", "capital return program",
                             "return of capital", "shareholder return",
                             "return to shareholders", "repurchase program",
                             "dividend policy", "capital deployment"])
    if not hits:
        return *mr("No capital-allocation policy language found in 10-K"), ""
    # Stronger signal: explicit policy statement
    policy_hits = [h for h in hits if any(
        kw in h[1].lower() for kw in ["policy", "framework", "program", "strategy",
                                       "committed", "intend to", "will return"])]
    if policy_hits:
        return "Yes", "Capital-allocation policy explicitly stated in 10-K", _first_snippet_str(policy_hits)
    return "Yes", "Capital-return language found in 10-K", _first_snippet_str(hits)


def sec_q16_stock_acquisitions(text: Optional[str]) -> tuple[str, str, str]:
    """Q16: Management avoided large stock-financed acquisitions."""
    if not text:
        return *mr("10-K not available"), ""
    hits = _snippets(text, ["stock consideration", "share consideration",
                             "shares of common stock issued in connection with acquisition",
                             "stock-for-stock", "shares issued for acquisition",
                             "common stock as consideration"])
    if not hits:
        return "Yes", "No stock-financed acquisition language found in 10-K", ""
    return *mr("Potential stock-financed acquisition language found; review snippet"), _first_snippet_str(hits)


def sec_q17_related_party(text: Optional[str]) -> tuple[str, str, str]:
    """Q17: Related-party transactions minimal or fully disclosed."""
    if not text:
        return *mr("10-K not available"), ""
    hits = _snippets(text, ["related party", "related-party"])
    if not hits:
        return "Yes", "No related-party language found in 10-K", ""
    # Check for 'not material' or 'immaterial' nearby
    for kw, snip in hits:
        if any(p in snip.lower() for p in ["not material", "immaterial", "not significant",
                                             "arm's length", "arms length"]):
            return "Yes", "Related-party transactions described as immaterial/arm's-length", snip
    return *mr("Related-party transactions mentioned; assess materiality from snippet"), _first_snippet_str(hits)


def sec_q49_concentration(text: Optional[str]) -> tuple[str, str, str]:
    """Q49: Revenue not dependent on single customer > 10%."""
    if not text:
        return *mr("10-K not available"), ""
    # Explicit no-concentration statements -> Yes
    no_conc = _snippets(text, ["no single customer accounted for more than 10",
                                "no customer accounted for more than 10",
                                "no customer represented more than 10",
                                "no customer exceeded 10", "no individual customer accounted",
                                "no single customer exceeded 10", "no customer individually exceeded"])
    if no_conc:
        return "Yes", "10-K explicitly states no single customer >= 10% of revenue", _first_snippet_str(no_conc)
    # Negative signals: concentration exists
    conc_hits = _snippets(text, ["10% of revenue", "10% of net revenue",
                                  "accounted for more than 10%", "represented more than 10%",
                                  "one customer accounted", "largest customer",
                                  "significant customer", "major customer",
                                  "concentration of credit risk", "concentration of revenue"])
    if conc_hits:
        for kw, snip in conc_hits:
            pcts = _pcts_near(snip)
            if any(p >= 10 for p in pcts):
                return "No", "Customer concentration >= 10% indicated in 10-K", snip
        return *mr("Concentration language found but percentage unclear; verify"), _first_snippet_str(conc_hits)
    # No concentration language found at all -> treat as Yes
    return "Yes", "No customer concentration language found in 10-K", ""


def sec_q50_commodity(text: Optional[str]) -> tuple[str, str, str]:
    """Q50: Revenue not heavily exposed to commodity prices."""
    if not text:
        return *mr("10-K not available"), ""
    hits = _snippets(text, ["commodity price", "raw material cost", "input cost",
                             "commodity risk", "price of raw materials", "commodity fluctuation"])
    if not hits:
        return "Yes", "No commodity-price-risk language found in 10-K", ""
    # Check if they hedge or if it's just disclosure boilerplate
    for kw, snip in hits:
        if any(p in snip.lower() for p in ["not material", "do not believe", "hedg", "minimal impact"]):
            return "Yes", f"Commodity risk mentioned but characterized as hedged/minimal", snip
    return *mr("Commodity/raw-material exposure mentioned; assess significance from snippet"), _first_snippet_str(hits)


def sec_q51_secular(text: Optional[str]) -> tuple[str, str, str]:
    """Q51: Favorable secular industry trends."""
    if not text:
        return *mr("10-K not available"), ""
    hits = _snippets(text, ["secular growth", "secular trend", "secular tailwind",
                             "tailwind", "growing market", "market growth",
                             "total addressable market", "addressable market",
                             "expanding market", "rapid growth", "strong demand",
                             "favorable trends", "long-term growth"])
    if not hits:
        return *mr("No secular growth or TAM language found in 10-K"), ""
    # Negative qualifiers near the hit?
    positive_hits = [h for h in hits if not any(
        neg in h[1].lower() for neg in ["headwind", "decline", "shrink", "contraction",
                                         "challenging", "difficult", "unfavorable"])]
    if positive_hits:
        return "Yes", f'Positive secular/TAM language found: "{positive_hits[0][0]}"', _first_snippet_str(positive_hits)
    return *mr("Market language found but may contain headwinds; review snippet"), _first_snippet_str(hits)


def sec_q52_litigation(text: Optional[str]) -> tuple[str, str, str]:
    """Q52: No material pending litigations."""
    if not text:
        return *mr("10-K not available"), ""
    # Explicit no-material-proceedings statements -> Yes
    no_lit = _snippets(text, ["no pending legal proceedings", "no material legal proceedings",
                               "not a party to any material legal", "no material pending legal",
                               "no material litigation", "not party to any pending",
                               "not currently a party to any material"])
    if no_lit:
        return "Yes", "10-K states no material pending legal proceedings", _first_snippet_str(no_lit)
    # Hard negative signals: material liability + specific dollar amounts near litigation
    hard_neg = _snippets(text, ["material adverse", "significant liability", "material judgment",
                                 "substantial liability", "criminal indictment",
                                 "criminal investigation", "government enforcement action"])
    if hard_neg:
        for kw, snip in hard_neg:
            # Look for dollar amounts (e.g. $100 million, $1 billion)
            if re.search(r'\$\s*\d+[\d,.]*\s*(million|billion|M\b|B\b)', snip, re.IGNORECASE):
                return "No", f"Material litigation with dollar exposure found in 10-K", snip
        return *mr("Material litigation language found; verify dollar exposure"), _first_snippet_str(hard_neg)
    # Boilerplate litigation language (class action etc.) without materiality qualifiers
    boilerplate = _snippets(text, ["class action", "filed suit against", "alleged violations",
                                    "settlement agreement", "government investigation"])
    if boilerplate:
        for kw, snip in boilerplate:
            if any(m in snip.lower() for m in ["material", "significant liability", "substantial"]):
                return *mr("Potentially material litigation found; review snippet"), snip
        # Boilerplate only — treat as Yes
        return "Yes", "Boilerplate litigation disclosures only; no material liability indicated", _first_snippet_str(boilerplate)
    return "Yes", "No active litigation language found in 10-K", ""


def sec_q53_restatements(text: Optional[str]) -> tuple[str, str, str]:
    """Q53: No restatements or auditor qualifications."""
    if not text:
        return *mr("10-K not available"), ""
    # "restatement" alone appears in cover-page boilerplate checkboxes — require more context
    hits = _snippets(text, ["we restated", "has been restated", "restatement of",
                             "material weakness in internal control",
                             "significant deficiency in internal control",
                             "going concern doubt", "auditor expressed doubt"])
    if not hits:
        return "Yes", "No restatement or material weakness language found in 10-K", ""
    return "No", "Restatement or material weakness language found in 10-K", _first_snippet_str(hits)


def sec_q54_proprietary(text: Optional[str],
                         gross_margin: Optional[float] = None) -> tuple[str, str, str]:
    """Q54: High % revenue from proprietary products."""
    excerpt = ""
    # GM > 50% is a strong proxy for proprietary pricing power
    if gross_margin is not None and gross_margin > 0.50:
        gm_detail = f"Gross margin = {pct(gross_margin)} (>50% proxy for proprietary pricing power)"
        if text:
            hits = _snippets(text, ["proprietary", "patented", "owned brand", "our brands",
                                     "in-house", "first-party", "exclusive", "branded"])
            if hits:
                excerpt = _first_snippet_str(hits)
        return "Yes", gm_detail, excerpt

    if not text:
        if gross_margin is not None:
            return *mr(f"10-K unavailable; gross margin={pct(gross_margin)} (<50%)"), ""
        return *mr("10-K not available"), ""

    hits = _snippets(text, ["proprietary product", "proprietary technology", "patented product",
                             "exclusive product", "owned brand", "our brands", "branded product",
                             "in-house developed", "first-party", "proprietary software",
                             "proprietary platform", "proprietary solution"])
    if hits:
        return "Yes", "Proprietary/branded product language found in 10-K", _first_snippet_str(hits)

    # Broader fallback
    broad = _snippets(text, ["proprietary", "patented", "exclusive"])
    if broad:
        return "Yes", f'General proprietary language found: "{broad[0][0]}"', _first_snippet_str(broad)

    gm_str = f" | Gross margin = {pct(gross_margin)}" if gross_margin is not None else ""
    return *mr(f"No proprietary product language found{gm_str}"), ""


def sec_q56_obs(text: Optional[str]) -> tuple[str, str, str]:
    """Q56: No significant off-balance-sheet liabilities."""
    if not text:
        return *mr("10-K not available"), ""
    # Explicit no-OBS statements
    no_obs = _snippets(text, ["no off-balance-sheet arrangements", "no material off-balance",
                               "we do not have any off-balance", "no significant off-balance",
                               "not have any off-balance-sheet"])
    if no_obs:
        return "Yes", "10-K explicitly states no material off-balance-sheet arrangements", _first_snippet_str(no_obs)
    # OBS items detected
    obs_hits = _snippets(text, ["off-balance-sheet", "off balance sheet",
                                 "variable interest entity", "VIE", "unconsolidated entity",
                                 "special purpose entity", "synthetic lease"])
    if obs_hits:
        # Check whether the OBS items are described as immaterial
        for kw, snip in obs_hits:
            if any(p in snip.lower() for p in ["not material", "immaterial", "not significant",
                                                 "did not have a material", "no material impact"]):
                return "Yes", "OBS items mentioned but described as immaterial in 10-K", snip
        return *mr("Off-balance-sheet language found; assess materiality"), _first_snippet_str(obs_hits)
    # Nothing found -> treat as Yes
    return "Yes", "No off-balance-sheet language found in 10-K", ""


def sec_q58_accounting_changes(text: Optional[str]) -> tuple[str, str, str]:
    """Q58: No frequent accounting policy changes."""
    if not text:
        return *mr("10-K not available"), ""
    hits = _snippets(text, ["adoption of asu", "change in accounting policy",
                             "new accounting standard", "accounting standard update",
                             "recently adopted accounting", "change in accounting principle",
                             "retrospective adjustment", "cumulative effect of accounting"])
    if not hits:
        return "Yes", "No accounting policy change language found in 10-K", ""
    # Hard negative: material impact or restatement adjacent to change language
    for kw, snip in hits:
        sl = snip.lower()
        if any(p in sl for p in ["material impact", "material effect", "restatement",
                                   "restated", "significant impact on our financial"]):
            return "No", "Accounting change with material impact or restatement found in 10-K", snip
    # Only routine ASU adoptions -> Yes
    routine = [h for h in hits
               if any(p in h[1].lower() for p in ["no material impact", "no significant impact",
                                                    "did not have a material", "not material",
                                                    "no impact", "immaterial"])]
    if routine:
        return "Yes", f"Only routine ASU adoptions with no material impact ({len(hits)} adoption(s))", _first_snippet_str(routine)
    # Changes present but no materiality qualifier found — flag for review
    return *mr(f"Accounting standard changes found ({len(hits)} hit(s)); verify impact"), _first_snippet_str(hits)


# ─────────────────────────────────────────────
# Dividend history fix
# ─────────────────────────────────────────────

def annual_dividends_completed(t) -> list[float]:
    """
    Return list of annual dividend totals for fully-completed calendar years only,
    most recent first. Excludes the current in-progress year.
    """
    try:
        divs = t.dividends
        if divs is None or len(divs) == 0:
            return []
        current_year = datetime.date.today().year
        # Sum per calendar year, exclude current (incomplete) year
        divs.index = divs.index.tz_localize(None) if divs.index.tzinfo else divs.index
        by_year = divs.groupby(divs.index.year).sum()
        by_year = by_year[by_year.index < current_year]
        by_year = by_year[by_year > 0]
        return list(by_year.iloc[::-1])   # most recent first
    except Exception:
        return []


# ─────────────────────────────────────────────
# Phil Town Rule #1 Valuation
# ─────────────────────────────────────────────

_GROWTH_CAP      = 0.15   # max growth rate fed into projection
_TERMINAL_G      = 0.03   # long-term GDP+inflation rate (decay target at yr 10)
_PE_CAP          = 25.0   # absolute ceiling on Future P/E
_EPS_CAP         = 500.0  # max projected Future EPS before sanity reduction
_MKTCAP_MULT_CAP = 100.0  # max Future Price as multiple of current market cap


def _eps_with_decay(eps: float, g_hi: float, terminal_g: float = _TERMINAL_G) -> float:
    """Compound EPS over 10 years: g_hi for yrs 1-5, linear decay to terminal_g for yrs 6-10."""
    val = eps
    for yr in range(1, 11):
        if yr <= 5:
            g = g_hi
        else:
            step = yr - 5          # 1 … 5
            g = g_hi + (terminal_g - g_hi) * (step / 5)
        val *= (1 + g)
    return val


def _find_growth_for_eps_target(eps: float, target: float,
                                 terminal_g: float = _TERMINAL_G) -> float:
    """Binary-search for the highest g_hi that keeps _eps_with_decay ≤ target."""
    lo, hi = 0.001, _GROWTH_CAP
    for _ in range(60):
        mid = (lo + hi) / 2
        if _eps_with_decay(eps, mid, terminal_g) <= target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def _find_growth_for_price_target(eps: float, future_pe: float, target_price: float,
                                   terminal_g: float = _TERMINAL_G) -> float:
    """Binary-search for the highest g_hi that keeps future_price ≤ target_price."""
    lo, hi = 0.001, _GROWTH_CAP
    for _ in range(60):
        mid = (lo + hi) / 2
        fe = _eps_with_decay(eps, mid, terminal_g)
        if fe * future_pe <= target_price:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def calc_rule1(info: dict, net_income_r: list, shares_out: Optional[float],
               price: Optional[float], fin=None,
               total_rev_r: list = None, op_income_r: list = None) -> dict:
    """
    Compute Phil Town Rule #1 valuation inputs (original + sanity-adjusted).
    Returns a dict with all intermediate values for display.
    """
    r: dict = {}
    total_rev_r = total_rev_r or []
    op_income_r = op_income_r or []

    # ── Current EPS — try multiple sources, pick first valid positive ──
    eps_ttm = None
    eps_series: list = []   # most-recent-first, positive values only (for 3yr avg)

    # 1) yfinance trailing EPS fields
    for key in ("trailingEps", "epsTrailingTwelveMonths"):
        v = info.get(key)
        if v is not None and v > 0:
            eps_ttm = v
            break
    # 2) net income / shares outstanding
    if eps_ttm is None and net_income_r and shares_out and shares_out > 0:
        v = net_income_r[0] / shares_out
        if v > 0:
            eps_ttm = v
    # 3) diluted / basic EPS from income statement
    if eps_ttm is None and fin is not None:
        for label in ("Diluted EPS", "Basic EPS", "Diluted Eps", "BasicEPS"):
            eps_row = row(fin, label)
            if eps_row:
                v = eps_row[0]
                if v is not None and v > 0:
                    eps_ttm = v
                    break
    r["eps_ttm"] = eps_ttm

    # ── Build EPS history series (for hist CAGR and 3yr avg) ──
    if fin is not None:
        for label in ("Diluted EPS", "Basic EPS", "Diluted Eps", "BasicEPS"):
            eps_row = row(fin, label)
            if eps_row:
                eps_series = [v for v in eps_row[:6] if v is not None and v > 0]
                if eps_series:
                    break
    if not eps_series and net_income_r and shares_out and shares_out > 0:
        eps_series = [ni / shares_out for ni in net_income_r[:6]
                      if ni is not None and shares_out > 0 and ni / shares_out > 0]

    # 3yr average EPS for secondary intrinsic value check
    eps_3yr = [v for v in eps_series[:3] if v is not None]
    r["eps_3yr_avg"] = sum(eps_3yr) / len(eps_3yr) if eps_3yr else None

    # ── Historical EPS growth — try multiple methods ──
    hist_cagr: Optional[float] = None
    if len(eps_series) >= 2:
        hist_cagr = cagr(eps_series, min(len(eps_series) - 1, 5))
    if hist_cagr is None:
        ni5 = [v for v in net_income_r[:6] if v is not None]
        if len(ni5) >= 2:
            hist_cagr = cagr(ni5, min(len(ni5) - 1, 5))
    if hist_cagr is None:
        rev5 = [v for v in total_rev_r[:6] if v is not None]
        if len(rev5) >= 2:
            hist_cagr = cagr(rev5, min(len(rev5) - 1, 5))
    if hist_cagr is None:
        oi5 = [v for v in op_income_r[:6] if v is not None]
        if len(oi5) >= 2:
            hist_cagr = cagr(oi5, min(len(oi5) - 1, 5))
    r["hist_cagr"] = hist_cagr

    # ── Analyst forward growth estimate — try multiple sources ──
    analyst_growth: Optional[float] = None
    for key in ("earningsGrowth", "revenueGrowth", "earningsQuarterlyGrowth"):
        v = info.get(key)
        if v is not None:
            analyst_growth = v
            break
    if analyst_growth is None:
        fwd_eps = info.get("forwardEps")
        if fwd_eps and eps_ttm and eps_ttm > 0:
            analyst_growth = (fwd_eps - eps_ttm) / abs(eps_ttm)
    r["analyst_growth"] = analyst_growth

    # ── Conservative growth rate: lower of available estimates ──
    candidates = {k: v for k, v in
                  {"historical": hist_cagr, "analyst": analyst_growth}.items()
                  if v is not None}
    if candidates:
        chosen_label = min(candidates, key=candidates.get)
        growth_used  = candidates[chosen_label]
        others = ", ".join(f"{lbl} {pct(v)}" for lbl, v in candidates.items())
        r["growth_used"]   = growth_used
        r["growth_source"] = f"{chosen_label} (lower of: {others})"
    else:
        r["growth_used"]   = None
        r["growth_source"] = "N/A — no growth rate available"

    # ════════════════════════════════════════════
    # ORIGINAL MODEL (unadjusted Rule #1)
    # ════════════════════════════════════════════
    g = r["growth_used"]
    orig_pe = (2 * g * 100) if g is not None else None
    r["future_pe"]    = orig_pe if (orig_pe is not None and orig_pe > 0) else None
    r["future_eps"]   = (eps_ttm * (1 + g) ** 10
                         if eps_ttm is not None and g is not None and r["future_pe"] is not None
                         else None)
    r["future_price"] = (r["future_eps"] * r["future_pe"]
                         if r["future_eps"] is not None and r["future_pe"] is not None
                         else None)
    r["sticker"]      = (r["future_price"] / (1.15 ** 10)
                         if r["future_price"] is not None else None)
    r["mos"]          = r["sticker"] / 2 if r["sticker"] is not None else None

    # ════════════════════════════════════════════
    # ADJUSTED MODEL (capped growth + decay + sanity checks)
    # ════════════════════════════════════════════
    adj_notes: list[str] = []
    adj_g = None   # the growth rate that will be fed into the decay model

    if g is not None and g > 0 and eps_ttm is not None:
        adj_g = min(g, _GROWTH_CAP)
        if g > _GROWTH_CAP:
            adj_notes.append(f"growth capped {pct(g)} → {pct(adj_g)}")

        # Future P/E: 2 × capped rate, ceiling 25x
        adj_pe_raw = 2 * adj_g * 100
        adj_pe = min(adj_pe_raw, _PE_CAP)
        if adj_pe < adj_pe_raw:
            adj_notes.append(f"Future P/E capped {adj_pe_raw:.1f}x → {adj_pe:.1f}x")

        # Future EPS via decay model (yrs 1-5 at adj_g, yrs 6-10 decay to 3%)
        adj_future_eps = _eps_with_decay(eps_ttm, adj_g)

        # Sanity check 1: Future EPS ≤ $500
        if adj_future_eps > _EPS_CAP:
            reduced_g = _find_growth_for_eps_target(eps_ttm, _EPS_CAP)
            adj_notes.append(
                f"EPS sanity: Future EPS ${adj_future_eps:.0f} > ${_EPS_CAP:.0f}; "
                f"growth reduced {pct(adj_g)} → {pct(reduced_g)}")
            adj_g = reduced_g
            adj_pe = min(2 * adj_g * 100, _PE_CAP)
            adj_future_eps = _eps_with_decay(eps_ttm, adj_g)

        # Sanity check 2: Future Price ≤ 100× market cap
        market_cap = info.get("marketCap")
        if market_cap and market_cap > 0:
            max_price = market_cap * _MKTCAP_MULT_CAP
            adj_future_price_check = adj_future_eps * adj_pe
            if adj_future_price_check > max_price:
                reduced_g = _find_growth_for_price_target(eps_ttm, adj_pe, max_price)
                adj_notes.append(
                    f"Mkt-cap sanity: Future Price ${adj_future_price_check:,.0f} > "
                    f"100× mktcap ${max_price:,.0f}; growth reduced {pct(adj_g)} → {pct(reduced_g)}")
                adj_g = reduced_g
                adj_pe = min(2 * adj_g * 100, _PE_CAP)
                adj_future_eps = _eps_with_decay(eps_ttm, adj_g)

        adj_future_price = adj_future_eps * adj_pe
        adj_sticker      = adj_future_price / (1.15 ** 10)
        adj_mos          = adj_sticker / 2
    else:
        adj_pe = adj_future_eps = adj_future_price = adj_sticker = adj_mos = None

    r["adj_g"]            = adj_g
    r["adj_pe"]           = adj_pe
    r["adj_future_eps"]   = adj_future_eps
    r["adj_future_price"] = adj_future_price
    r["adj_sticker"]      = adj_sticker
    r["adj_mos"]          = adj_mos
    r["adj_notes"]        = adj_notes

    # Secondary intrinsic value: avg 3yr EPS × 10–20x P/E
    e3 = r["eps_3yr_avg"]
    r["secondary_low"]  = e3 * 10 if e3 else None
    r["secondary_high"] = e3 * 20 if e3 else None

    # Flag if primary sticker deviates >200% from secondary range
    sec_flag = False
    if r["sticker"] and r["secondary_low"] and r["secondary_high"]:
        if r["sticker"] > r["secondary_high"] * 3 or r["sticker"] < r["secondary_low"] / 3:
            sec_flag = True
    r["secondary_flag"] = sec_flag

    r["current_price"] = price
    r["current_pe"]    = info.get("trailingPE")

    return r


# ─────────────────────────────────────────────
# Main analysis — returns (name, answers, rule1)
# ─────────────────────────────────────────────

def analyze(ticker: str):
    print(f"\nFetching yfinance data for {ticker.upper()}...")
    t, info, fin, bal, cf = fetch_yf(ticker)

    if not info:
        print("Could not retrieve data. Check the ticker and your internet connection.")
        sys.exit(1)

    name   = info.get("longName", ticker.upper())
    sector = info.get("sector", "N/A")
    print(f"Company : {name}")
    print(f"Sector  : {sector}")

    # ── SEC EDGAR 10-K ──────────────────────────
    ten_k, sec_status = fetch_10k_text(ticker)
    if not ten_k:
        print(f"  Warning: {sec_status}. SEC-based questions will remain Manual Review.")
    print()

    answers: list[Answer] = []

    # ── scalar fields ───────────────────────────
    market_cap = info.get("marketCap")
    price      = info.get("currentPrice") or info.get("regularMarketPrice")
    shares_out = info.get("sharesOutstanding")
    beta_val   = info.get("beta")
    ev         = info.get("enterpriseValue")

    # ── Sanity-check price against market cap ───
    # yfinance occasionally returns sharesOutstanding 10x too high for some
    # tickers, making currentPrice 10x too low while marketCap stays correct.
    # If implied price from market cap differs from reported price by >20%,
    # use the market-cap-implied price and re-derive EPS from trailingPE.
    if market_cap and shares_out and shares_out > 0 and price:
        implied_price = market_cap / shares_out
        if abs(implied_price - price) / price > 0.20:
            corrected_price = implied_price
            pe_ratio = info.get("trailingPE")
            corrected_eps = (corrected_price / pe_ratio) if pe_ratio else None
            print(f"  Warning: price data mismatch detected.")
            print(f"    Reported price: ${price:.2f} | Market-cap-implied: ${corrected_price:.2f}")
            print(f"    Using implied price${' and corrected EPS $' + f'{corrected_eps:.2f}' if corrected_eps else ''}.")
            price      = corrected_price
            shares_out = market_cap / corrected_price
            # Patch info so downstream helpers (Rule #1 etc.) see correct values
            info = dict(info)
            info["currentPrice"] = corrected_price
            if corrected_eps:
                info["trailingEps"] = corrected_eps

    # ── income statement ────────────────────────
    gross_profit_r = row(fin, "Gross Profit")
    total_rev_r    = row(fin, "Total Revenue")
    ebitda_r       = row(fin, "EBITDA", "Normalized EBITDA")
    interest_exp_r = row(fin, "Interest Expense", "Interest Expense Non Operating")
    net_income_r   = row(fin, "Net Income")
    op_income_r    = row(fin, "Operating Income", "EBIT")
    depreciation_r = row(fin, "Depreciation", "Reconciled Depreciation")
    tax_r          = row(fin, "Tax Provision", "Income Tax Expense")
    pretax_r       = row(fin, "Pretax Income")
    cogs_r         = row(fin, "Cost Of Revenue", "Cost of Goods Sold")
    sga_r          = row(fin, "Selling General Administrative", "Selling General And Administrative")

    # ── cash flow ───────────────────────────────
    fcf_r      = row(cf, "Free Cash Flow")
    capex_r    = row(cf, "Capital Expenditure", "Purchase Of PPE")
    div_paid_r = row(cf, "Cash Dividends Paid", "Common Stock Dividend Paid")
    opcf_r     = row(cf, "Operating Cash Flow", "Cash Flow From Continuing Operating Activities",
                         "Cash Flows From Operations", "Net Cash Provided By Operating Activities")

    # ── balance sheet ───────────────────────────
    curr_assets_r = row(bal, "Current Assets")
    curr_liab_r   = row(bal, "Current Liabilities")
    total_debt_r  = row(bal, "Total Debt", "Long Term Debt And Capital Lease Obligation")
    cash_r        = row(bal, "Cash And Cash Equivalents",
                        "Cash Cash Equivalents And Short Term Investments")
    equity_r      = row(bal, "Stockholders Equity", "Total Equity Gross Minority Interest")
    inventory_r   = row(bal, "Inventory")
    receivables_r = row(bal, "Accounts Receivable", "Net Receivables")
    payables_r    = row(bal, "Accounts Payable", "Payables")

    # ── derived series ──────────────────────────
    gross_margins = [gp / rv for gp, rv in zip(gross_profit_r, total_rev_r)
                     if gp is not None and rv and rv != 0]
    op_margins    = [oi / rv for oi, rv in zip(op_income_r, total_rev_r)
                     if oi is not None and rv and rv != 0]
    sga_pcts      = [s / rv for s, rv in zip(sga_r, total_rev_r)
                     if s is not None and rv and rv != 0]
    cogs_pcts     = [abs(c) / rv for c, rv in zip(cogs_r, total_rev_r)
                     if c is not None and rv and rv != 0]

    # ROIC approx = NI / (Equity + Debt - Cash)
    roic_list = []
    for i in range(min(5, len(net_income_r))):
        ni = net_income_r[i] if i < len(net_income_r) else None
        eq = equity_r[i]     if i < len(equity_r)     else None
        td = total_debt_r[i] if i < len(total_debt_r) else None
        ca = cash_r[i]       if i < len(cash_r)       else None
        if None not in (ni, eq, td, ca):
            invested = eq + td - ca
            roic_list.append(ni / invested if invested != 0 else None)
    roic5 = avg(roic_list)

    # Owner earnings = NI + Depreciation - Capex
    oe_list = []
    for i in range(min(5, len(net_income_r))):
        ni  = net_income_r[i]   if i < len(net_income_r)   else None
        dep = depreciation_r[i] if i < len(depreciation_r) else None
        cap = abs(capex_r[i])   if i < len(capex_r)        else None
        if None not in (ni, dep, cap):
            oe_list.append(ni + dep - cap)
    oe_avg  = avg(oe_list)
    oe_stab = stable(oe_list)

    # Tax rates
    tax_rates = []
    for i in range(min(5, len(tax_r))):
        tp = tax_r[i]    if i < len(tax_r)    else None
        pt = pretax_r[i] if i < len(pretax_r) else None
        if tp is not None and pt and pt != 0:
            tax_rates.append(tp / pt)

    fcf5     = fcf_r[:5]
    fcf5_avg = avg(fcf5)
    fcf_ttm  = fcf_r[0] if fcf_r else None

    ebitda_ttm = info.get("ebitda") or (avg(ebitda_r[:1]) if ebitda_r else None)
    total_debt = total_debt_r[0] if total_debt_r else None
    cash_now   = cash_r[0]       if cash_r       else None
    int_exp    = abs(interest_exp_r[0]) if interest_exp_r else None

    sga_pct_avg  = avg(sga_pcts[:3])
    cogs_pct_avg = avg(cogs_pcts[:3])
    gm_avg3      = avg(gross_margins[:3])

    # Pre-compute share CAGR (needed for Q20 and Q37)
    sh_cagr = None
    shares_hist = safe(lambda: t.get_shares_full(start="2020-01-01"), None)
    if shares_hist is not None and len(shares_hist) > 0:
        try:
            annual_sh = shares_hist.resample("YE").last().dropna()
            if len(annual_sh) >= 4:
                sh_cagr = cagr(list(annual_sh.iloc[::-1]), 3)
        except Exception:
            pass

    # Peer cost comparison (Q8)
    peer_sga, peer_cogs, peer_names = fetch_peer_metrics(ticker, sector)

    # ══════════════════════════════════════════
    # MEANING & MOAT  (Q1–Q10)
    # ══════════════════════════════════════════

    # Q1
    gm3 = avg(gross_margins[:3])
    cond, detail = yesno(gm3 > 0.40 if gm3 is not None else None,
                         f"3yr avg gross margin = {pct(gm3)}")
    answers.append(Answer("Is gross margin > 40% averaged over last 3 years?", cond, detail))

    # Q2
    cond, detail = yesno(roic5 > 0.12 if roic5 is not None else None,
                         f"5yr avg approx ROIC = {pct(roic5)}")
    answers.append(Answer("Is ROIC > 12% averaged over last 5 years?", cond, detail))

    # Q3
    fcf5_stab = stable(fcf5)
    cond, detail = yesno(
        (fcf5_avg is not None and fcf5_avg > 0 and fcf5_stab) if fcf5 else None,
        f"5yr avg FCF = {fmt(fcf5_avg, 0)} | stable={fcf5_stab}"
    )
    answers.append(Answer("Is average FCF over last 5 years positive and stable?", cond, detail))

    # Q4
    fcf10     = fcf_r[:10]
    fcf10_avg = avg(fcf10)
    if fcf5_avg is not None and fcf10_avg is not None and fcf5_avg != 0:
        ratio = fcf10_avg / fcf5_avg
        cond, detail = yesno(ratio >= 0.80,
                             f"10yr avg FCF = {fmt(fcf10_avg, 0)} | ratio vs 5yr = {fmt(ratio)}")
    else:
        cond, detail = mr("Insufficient 10-year FCF data")
    answers.append(Answer("Is average FCF over last 10 years positive and >= 80% of 5yr avg?", cond, detail))

    # Q5
    fcf_cagr_val = cagr(fcf5, 5) if len([v for v in fcf5 if v]) >= 2 else None
    cond, detail = yesno(fcf_cagr_val >= 0.05 if fcf_cagr_val is not None else None,
                         f"5yr FCF CAGR = {pct(fcf_cagr_val)}")
    answers.append(Answer("Is 5-year CAGR of FCF >= 5%?", cond, detail))

    # Q6 — SEC
    result, detail, excerpt = sec_q6_retention(ten_k)
    answers.append(Answer("Is customer retention/repeat-purchase rate > 80%?",
                           result, detail, excerpt))

    # Q7 — SEC
    result, detail, excerpt = sec_q7_patents(ten_k)
    answers.append(Answer("Does company own patents/licenses/brand enabling premium pricing?",
                           result, detail, excerpt))

    # Q8 — peers + SEC
    result, detail, excerpt = sec_q8_cost_advantage(
        ten_k, sga_pct_avg, cogs_pct_avg, sector, peer_sga, peer_cogs, peer_names)
    answers.append(Answer("Does company show cost advantage (SG&A or COGS as % of sales below peers)?",
                           result, detail, excerpt))

    # Q9 — SEC
    result, detail, excerpt = sec_q9_switching(ten_k)
    answers.append(Answer("Are switching costs evident (high renewal rates, proprietary integration)?",
                           result, detail, excerpt))

    # Q10 — SEC: pull business section text, always MR (no auto-score)
    result, detail, excerpt = sec_q10_business_text(ten_k)
    answers.append(Answer("Can I explain how the company makes money in two sentences?",
                           result, detail, excerpt))

    # ══════════════════════════════════════════
    # MANAGEMENT  (Q11–Q20)
    # ══════════════════════════════════════════

    # Q11
    insider_pct = info.get("heldPercentInsiders")
    cond, detail = yesno(insider_pct > 0.05 if insider_pct is not None else None,
                         f"Insider ownership = {pct(insider_pct)}")
    answers.append(Answer("Is insider ownership > 5%?", cond, detail))

    # Q12
    if None not in (total_debt, cash_now, ebitda_ttm) and ebitda_ttm != 0:
        nd_ebitda = (total_debt - cash_now) / ebitda_ttm
        cond, detail = yesno(nd_ebitda < 2, f"Net-debt/EBITDA = {fmt(nd_ebitda)}")
    else:
        cond, detail = mr("Missing debt/EBITDA data")
    answers.append(Answer("Is net-debt/EBITDA < 2x?", cond, detail))

    # Q13
    if ebitda_ttm and int_exp and int_exp != 0:
        coverage = ebitda_ttm / int_exp
        cond, detail = yesno(coverage > 5, f"Interest coverage = {fmt(coverage)}x")
    elif int_exp == 0 or int_exp is None:
        cond, detail = "Yes", "No interest expense"
    else:
        cond, detail = mr("Missing interest/EBITDA data")
    answers.append(Answer("Is interest coverage (EBITDA/interest) > 5x?", cond, detail))

    # Q14
    div_rate = info.get("payoutRatio")
    if div_rate is not None:
        cond, detail = yesno(div_rate < 0.60, f"Payout ratio = {pct(div_rate)}")
    else:
        div_ttm = abs(div_paid_r[0]) if div_paid_r else 0
        if div_ttm == 0:
            cond, detail = "Yes", "No dividend paid (payout = 0%)"
        else:
            cond, detail = mr("Cannot determine payout ratio")
    answers.append(Answer("Is dividend payout ratio < 60%?", cond, detail))

    # Q15
    roic_consistent = (all(v > 0.12 for v in roic_list if v is not None)
                       and len(roic_list) >= 3) if roic_list else None
    cond, detail = yesno(roic_consistent,
                         f"ROIC each year: {[pct(v) for v in roic_list]}")
    answers.append(Answer("Is ROIC > 12% consistently over last 5 years?", cond, detail))

    # Q16 — SEC
    result, detail, excerpt = sec_q16_stock_acquisitions(ten_k)
    answers.append(Answer("Has management avoided large acquisitions financed with stock?",
                           result, detail, excerpt))

    # Q17 — SEC
    result, detail, excerpt = sec_q17_related_party(ten_k)
    answers.append(Answer("Are related-party transactions minimal or fully disclosed?",
                           result, detail, excerpt))

    # Q18
    oe_cagr_val = cagr(oe_list, min(len(oe_list) - 1, 4)) if len(oe_list) >= 2 else None
    cond, detail = yesno(oe_cagr_val >= 0.08 if oe_cagr_val is not None else None,
                         f"Owner earnings CAGR (~{min(len(oe_list)-1, 4) if oe_list else 0}yr) = {pct(oe_cagr_val)}")
    answers.append(Answer("Does management grow owner earnings > 8% CAGR?", cond, detail))

    # Q19 — SEC
    result, detail, excerpt = sec_q19_capital_allocation(ten_k)
    answers.append(Answer("Is capital-allocation policy clearly stated and consistently followed?",
                           result, detail, excerpt))

    # Q20 — active buybacks (sh_cagr < 0) AND pays dividends
    ann_divs_q20 = annual_dividends_completed(t)
    has_buybacks = sh_cagr is not None and sh_cagr < 0
    has_divs     = len(ann_divs_q20) > 0
    if has_buybacks and has_divs:
        cond   = "Yes"
        detail = (f"Active buybacks (share count CAGR = {pct(sh_cagr)}) "
                  f"AND dividends paid — both present")
    elif has_buybacks:
        cond   = "Yes"
        detail = (f"Active buybacks (share count CAGR = {pct(sh_cagr)}); "
                  f"no dividends, but capital is being returned")
    elif has_divs:
        cond   = "Manual Review Needed"
        detail = (f"Paying dividends but share count not decreasing "
                  f"(CAGR = {pct(sh_cagr) if sh_cagr is not None else 'N/A'}); "
                  f"check if buybacks are occurring")
    else:
        cond   = "No"
        detail = "No buybacks and no dividends detected"
    answers.append(Answer(
        "Does company return excess cash via dividends/buybacks when ROI is scarce?",
        cond, detail))

    # ══════════════════════════════════════════
    # FINANCIAL HEALTH  (Q21–Q32)
    # ══════════════════════════════════════════

    # Q21
    fcf3 = fcf_r[:3]
    fcf3_all_pos = all(v > 0 for v in fcf3 if v is not None) if len(fcf3) >= 3 else None
    cond, detail = yesno(fcf3_all_pos,
                         f"FCF last 3 yrs: {[fmt(v, 0) for v in fcf3]}")
    answers.append(Answer("Is FCF positive each of last 3 years?", cond, detail))

    # Q22
    if fcf_ttm and market_cap and market_cap != 0:
        fcf_yield = fcf_ttm / market_cap
        cond, detail = yesno(fcf_yield > 0.06, f"FCF yield = {pct(fcf_yield)}")
    else:
        cond, detail = mr("Missing FCF or market cap")
    answers.append(Answer("Is FCF yield > 6%?", cond, detail))

    # Q23
    cond, detail = yesno(
        (oe_avg is not None and oe_avg > 0 and oe_stab) if oe_list else None,
        f"Owner earnings avg = {fmt(oe_avg, 0)} | stable={oe_stab}"
    )
    answers.append(Answer("Are owner earnings positive and stable?", cond, detail))

    # Q24
    cr_val = info.get("currentRatio")
    if cr_val is None and curr_assets_r and curr_liab_r:
        cr_val = curr_assets_r[0] / curr_liab_r[0] if curr_liab_r[0] else None
    cond, detail = yesno(cr_val > 1.5 if cr_val is not None else None,
                         f"Current ratio = {fmt(cr_val)}")
    answers.append(Answer("Is current ratio > 1.5?", cond, detail))

    # Q25
    de = info.get("debtToEquity")
    if de is not None:
        de = de / 100
    elif total_debt and equity_r:
        eq0 = equity_r[0]
        de = total_debt / eq0 if eq0 and eq0 != 0 else None
    cond, detail = yesno(de < 0.5 if de is not None else None,
                         f"Debt/Equity = {fmt(de)}")
    answers.append(Answer("Is debt-to-equity < 0.5?", cond, detail))

    # Q26
    if fcf_ttm and int_exp and int_exp != 0:
        fcf_int_cov = fcf_ttm / int_exp
        cond, detail = yesno(fcf_int_cov > 3, f"FCF/Interest = {fmt(fcf_int_cov)}x")
    elif fcf_ttm and (int_exp == 0 or int_exp is None):
        cond, detail = "Yes", "No interest expense"
    else:
        cond, detail = mr("Missing FCF or interest data")
    answers.append(Answer("Does FCF cover interest expense > 3x?", cond, detail))

    # Q27
    cap0 = abs(capex_r[0])   if capex_r       else None
    dep0 = depreciation_r[0] if depreciation_r else None
    if cap0 and dep0 and dep0 != 0:
        ratio = cap0 / dep0
        cond, detail = yesno(0.8 <= ratio <= 1.2, f"Capex/Depreciation = {fmt(ratio)}x")
    else:
        cond, detail = mr("Missing capex or depreciation")
    answers.append(Answer("Are capex roughly aligned with depreciation (0.8x-1.2x)?", cond, detail))

    # Q28
    cogs0 = cogs_r[0]       if cogs_r      else None
    inv0  = inventory_r[0]  if inventory_r else None
    if cogs0 and inv0 and inv0 != 0:
        inv_turn = abs(cogs0) / inv0
        cond, detail = yesno(inv_turn > 4, f"Inventory turnover = {fmt(inv_turn)}x")
    elif not inventory_r:
        cond, detail = mr("No inventory data (may be service company)")
    else:
        cond, detail = mr("Missing COGS or inventory")
    answers.append(Answer("Is inventory turnover > 4x?", cond, detail))

    # Q29
    dso_list = []
    for i in range(min(5, len(receivables_r))):
        rec = receivables_r[i] if i < len(receivables_r) else None
        rev = total_rev_r[i]   if i < len(total_rev_r)   else None
        if rec and rev and rev != 0:
            dso_list.append(rec / (rev / 365))
    if len(dso_list) >= 2:
        cond, detail = yesno(dso_list[0] <= dso_list[-1] * 1.10,
                             f"DSO recent->old: {[fmt(d, 1) for d in dso_list]} days")
    else:
        cond, detail = mr("Insufficient data for DSO trend")
    answers.append(Answer("Is DSO stable or decreasing?", cond, detail))

    # Q30
    dio_list = []
    for i in range(min(5, len(inventory_r))):
        inv = inventory_r[i] if i < len(inventory_r) else None
        cog = cogs_r[i]      if i < len(cogs_r)      else None
        if inv and cog and cog != 0:
            dio_list.append(inv / (abs(cog) / 365))
    if len(dio_list) >= 2:
        cond, detail = yesno(dio_list[0] <= dio_list[-1] * 1.10,
                             f"DIO recent->old: {[fmt(d, 1) for d in dio_list]} days")
    else:
        cond, detail = mr("Insufficient data for DIO trend")
    answers.append(Answer("Is DIO stable or decreasing?", cond, detail))

    # Q31
    if len(tax_rates) >= 3:
        tr_stab = stable(tax_rates, threshold=0.15)
        tr_avg  = avg(tax_rates)
        cond, detail = yesno(tr_stab,
                             f"Tax rates: {[pct(r) for r in tax_rates]} | avg={pct(tr_avg)} | stable={tr_stab}")
    else:
        cond, detail = mr("Insufficient tax/pretax data")
    answers.append(Answer("Is tax rate stable and not reliant on one-time benefits?", cond, detail))

    # Q32
    dpo_list = []
    for i in range(min(5, len(payables_r))):
        ap  = payables_r[i] if i < len(payables_r) else None
        cog = cogs_r[i]     if i < len(cogs_r)     else None
        if ap and cog and cog != 0:
            dpo_list.append(ap / (abs(cog) / 365))
    if dso_list and dio_list and dpo_list:
        ccc = dio_list[0] + dso_list[0] - dpo_list[0]
        cond, detail = yesno(ccc < 0,
                             f"CCC = DIO({fmt(dio_list[0], 1)}) + DSO({fmt(dso_list[0], 1)}) "
                             f"- DPO({fmt(dpo_list[0], 1)}) = {fmt(ccc, 1)} days")
    else:
        cond, detail = mr("Insufficient data to compute CCC")
    answers.append(Answer("Does company have negative cash conversion cycle?", cond, detail))

    # ══════════════════════════════════════════
    # VALUATION  (Q33–Q43)
    # ══════════════════════════════════════════

    # Q33
    pe = info.get("trailingPE") or info.get("forwardPE")
    MARKET_PE = 25
    cond, detail = yesno(pe < MARKET_PE if pe is not None else None,
                         f"P/E = {fmt(pe)} vs market avg ~{MARKET_PE}x")
    answers.append(Answer("Is P/E below market average?", cond, detail))

    # Q34
    peg = info.get("pegRatio") or info.get("trailingPegRatio")
    cond, detail = yesno(0 < peg < 1 if peg is not None else None,
                         f"PEG = {fmt(peg)}")
    answers.append(Answer("Is PEG ratio < 1?", cond, detail))

    # Q35
    ev_ebitda = info.get("enterpriseToEbitda")
    if ev_ebitda is None and ev and ebitda_ttm and ebitda_ttm != 0:
        ev_ebitda = ev / ebitda_ttm
    cond, detail = yesno(ev_ebitda < 8 if ev_ebitda is not None else None,
                         f"EV/EBITDA = {fmt(ev_ebitda)}x")
    answers.append(Answer("Is EV/EBITDA < 8x?", cond, detail))

    # Q36
    if fcf_ttm and market_cap and market_cap != 0:
        fcf_yield2 = fcf_ttm / market_cap
        cond, detail = yesno(fcf_yield2 > 0.08, f"FCF yield = {pct(fcf_yield2)}")
    else:
        cond, detail = mr("Missing FCF or market cap")
    answers.append(Answer("Is FCF yield > 8%?", cond, detail))

    # Q37 — reuse pre-computed sh_cagr
    if sh_cagr is not None:
        cond, detail = yesno(sh_cagr < 0.02, f"Share count 3yr CAGR = {pct(sh_cagr)}")
    else:
        cond, detail = mr("Share history not available")
    answers.append(Answer("Is share dilution < 2% per year over last 3 years?", cond, detail))

    # Q38
    cond, detail = yesno(beta_val < 1.2 if beta_val is not None else None,
                         f"Beta = {fmt(beta_val)}")
    answers.append(Answer("Is beta < 1.2?", cond, detail))

    # Q39
    pb = info.get("priceToBook")
    if pb is not None:
        asset_heavy = any(s in sector.lower() for s in
                          ("utilities", "energy", "materials", "industrials", "real estate"))
        threshold_pb = 3.0 if asset_heavy else 1.5
        cond, detail = yesno(pb < threshold_pb,
                             f"P/B = {fmt(pb)} | threshold = {threshold_pb}x "
                             f"({'asset-heavy' if asset_heavy else 'asset-light'} sector: {sector})")
    else:
        cond, detail = mr("P/B not available")
    answers.append(Answer("Is P/B ratio < 1.5 (asset-light) or < 3 (asset-heavy)?", cond, detail))

    # Q40
    if oe_avg and shares_out and shares_out != 0 and price:
        oe_per_share = oe_avg / shares_out
        intrinsic_oe = oe_per_share * 8
        margin = intrinsic_oe / price - 1
        cond, detail = yesno(margin >= 0.50,
                             f"OE/share = {fmt(oe_per_share)} | intrinsic (x8) = {fmt(intrinsic_oe)} "
                             f"| price = {fmt(price)} | margin = {pct(margin)}")
    else:
        cond, detail = mr("Missing owner earnings, shares, or price")
    answers.append(Answer("Using owner earnings x 8, does intrinsic value exceed price by >= 50%?",
                           cond, detail))

    # Q41
    ebit0    = op_income_r[0] if op_income_r else None
    tax_rate = avg(tax_rates) if tax_rates else None
    if ebit0 and tax_rate is not None and shares_out and shares_out != 0 and price:
        after_tax_ebit = ebit0 * (1 - tax_rate)
        intrinsic_ebit = (after_tax_ebit / shares_out) * 10
        margin = intrinsic_ebit / price - 1
        cond, detail = yesno(margin >= 0.50,
                             f"After-tax EBIT/share = {fmt(after_tax_ebit / shares_out)} "
                             f"| intrinsic (x10) = {fmt(intrinsic_ebit)} "
                             f"| price = {fmt(price)} | margin = {pct(margin)}")
    else:
        cond, detail = mr("Missing EBIT, tax rate, shares, or price")
    answers.append(Answer("Using after-tax EBIT x 10, does intrinsic value exceed price by >= 50%?",
                           cond, detail))

    # Q42
    if oe_avg and market_cap and market_cap != 0:
        oe_yield = oe_avg / market_cap
        cond, detail = yesno(oe_yield >= 0.20, f"Avg OE / market cap = {pct(oe_yield)}")
    else:
        cond, detail = mr("Missing owner earnings or market cap")
    answers.append(Answer("Is average owner earnings over last 5 years >= 20% of market cap?",
                           cond, detail))

    # Q43
    if fcf5_avg and ev and ev != 0:
        fcf_ev_yield = fcf5_avg / ev
        cond, detail = yesno(fcf_ev_yield >= 0.10, f"Avg 5yr FCF / EV = {pct(fcf_ev_yield)}")
    else:
        cond, detail = mr("Missing FCF or enterprise value")
    answers.append(Answer("Is average FCF over last 5 years >= 10% of enterprise value?",
                           cond, detail))

    # ══════════════════════════════════════════
    # RISK & QUALITY  (Q44–Q58)
    # ══════════════════════════════════════════

    # Q44
    om_avg  = avg(op_margins[:5])
    om_stab = stable(op_margins[:5])
    cond, detail = yesno(
        (om_avg is not None and om_avg > 0.15 and om_stab) if op_margins else None,
        f"Avg op margin = {pct(om_avg)} | stable={om_stab}"
    )
    answers.append(Answer("Is operating margin > 15% and stable?", cond, detail))

    # Q45
    rev5     = total_rev_r[:5]
    rev_cagr = cagr(rev5, min(len([v for v in rev5 if v]), 4)) if len(rev5) >= 2 else None
    cond, detail = yesno(rev_cagr >= 0.05 if rev_cagr is not None else None,
                         f"Revenue 5yr CAGR = {pct(rev_cagr)}")
    answers.append(Answer("Is revenue growth > 5% CAGR?", cond, detail))

    # Q46 — WACC via CAPM
    wacc, wacc_detail = estimate_wacc(
        beta_val, int_exp, total_debt, cash_now, market_cap, avg(tax_rates) if tax_rates else None)
    cond, detail = yesno(
        (roic5 > wacc) if (roic5 is not None and wacc is not None) else None,
        f"ROIC = {pct(roic5)} vs WACC = {pct(wacc)} | {wacc_detail}"
    )
    answers.append(Answer("Is ROIC consistently above WACC?", cond, detail))

    # Q47
    cond, detail = yesno(roic5 >= 0.15 if roic5 is not None else None,
                         f"5yr avg approx ROIC = {pct(roic5)}")
    answers.append(Answer("Is 5-year average ROIC >= 15%?", cond, detail))

    # Q48
    fcf_conv_list = []
    for i in range(min(5, len(fcf_r))):
        f = fcf_r[i]        if i < len(fcf_r)        else None
        n = net_income_r[i] if i < len(net_income_r) else None
        if f is not None and n and n != 0:
            fcf_conv_list.append(f / n)
    fcf_conv_avg = avg(fcf_conv_list)
    cond, detail = yesno(fcf_conv_avg > 0.8 if fcf_conv_avg is not None else None,
                         f"Avg FCF/Net Income = {fmt(fcf_conv_avg)}")
    answers.append(Answer("Is FCF conversion (FCF/Net Income) > 0.8 over last 5 years?",
                           cond, detail))

    # Q49 — SEC
    result, detail, excerpt = sec_q49_concentration(ten_k)
    answers.append(Answer("Is revenue not dependent on a single customer (>10% concentration)?",
                           result, detail, excerpt))

    # Q50 — SEC
    result, detail, excerpt = sec_q50_commodity(ten_k)
    answers.append(Answer("Is revenue not heavily exposed to commodity prices?",
                           result, detail, excerpt))

    # Q51 — SEC
    result, detail, excerpt = sec_q51_secular(ten_k)
    answers.append(Answer("Does company operate in an industry with favorable secular trends?",
                           result, detail, excerpt))

    # Q52 — SEC
    result, detail, excerpt = sec_q52_litigation(ten_k)
    answers.append(Answer("Are there no material pending litigations?",
                           result, detail, excerpt))

    # Q53 — SEC
    result, detail, excerpt = sec_q53_restatements(ten_k)
    answers.append(Answer("Has company avoided restatements or auditor qualifications?",
                           result, detail, excerpt))

    # Q54 — SEC + gross margin proxy
    result, detail, excerpt = sec_q54_proprietary(ten_k, gm_avg3)
    answers.append(Answer("Does company generate high % of revenue from proprietary products?",
                           result, detail, excerpt))

    # Q55 — fixed: completed calendar years only
    ann_divs = annual_dividends_completed(t)
    if ann_divs and len(ann_divs) >= 5:
        last5 = ann_divs[:5][::-1]   # oldest->newest for comparison
        increasing = all(last5[i] <= last5[i + 1] for i in range(len(last5) - 1))
        cond, detail = yesno(increasing,
                             f"Annual dividends (completed yrs, oldest->newest): "
                             f"{[fmt(d, 4) for d in last5]}")
    elif ann_divs and len(ann_divs) >= 2:
        vals = ann_divs[::-1]
        increasing = all(vals[i] <= vals[i + 1] for i in range(len(vals) - 1))
        cond, detail = yesno(increasing,
                             f"Annual dividends ({len(vals)} completed yrs, oldest->newest): "
                             f"{[fmt(d, 4) for d in vals]}")
    elif ann_divs:
        cond, detail = mr("Only 1 completed year of dividend history")
    else:
        cond, detail = "No", "No dividends paid"
    answers.append(Answer("Is dividend history showing consistent increases over last 5 years?",
                           cond, detail))

    # Q56 — SEC
    result, detail, excerpt = sec_q56_obs(ten_k)
    answers.append(Answer("Are there no significant off-balance-sheet liabilities?",
                           result, detail, excerpt))

    # Q57 — revenue CAGR vs operating cash flow CAGR (within 3pp = quality growth)
    ocf5      = opcf_r[:5]
    ocf_cagr  = cagr(ocf5, min(len([v for v in ocf5 if v]), 4)) if len(ocf5) >= 2 else None
    if rev_cagr is not None and ocf_cagr is not None:
        diff = abs(rev_cagr - ocf_cagr)
        cond, detail = yesno(
            diff <= 0.03,
            f"Revenue CAGR = {pct(rev_cagr)} | Op. Cash Flow CAGR = {pct(ocf_cagr)} "
            f"| Diff = {pct(diff)} ({'within' if diff <= 0.03 else 'outside'} 3pp threshold)"
        )
    else:
        cond, detail = mr("Insufficient data for revenue vs operating cash flow comparison")
    answers.append(Answer("Is revenue growth > 5% CAGR without aggressive accounting?",
                           cond, detail))

    # Q58 — SEC
    result, detail, excerpt = sec_q58_accounting_changes(ten_k)
    answers.append(Answer("Is company free of frequent accounting policy changes?",
                           result, detail, excerpt))

    r1 = calc_rule1(info, net_income_r, shares_out, price,
                    fin=fin, total_rev_r=total_rev_r, op_income_r=op_income_r)
    return name, answers, r1


# ─────────────────────────────────────────────
# Output
# ─────────────────────────────────────────────

TOTAL_QUESTIONS = 58

CATEGORIES = [
    (0,  10, "Avoid"),
    (11, 20, "Weak"),
    (21, 30, "Average"),
    (31, 40, "Strong"),
    (41, 58, "Excellent"),
]

CATEGORY_COLORS = {
    "Avoid":     "\033[91m",
    "Weak":      "\033[93m",
    "Average":   "\033[94m",
    "Strong":    "\033[92m",
    "Excellent": "\033[96m",
}
RESET = "\033[0m"
BOLD  = "\033[1m"
DIM   = "\033[2m"

SECTIONS = {
    "MEANING & MOAT":   (1,  10),
    "MANAGEMENT":       (11, 20),
    "FINANCIAL HEALTH": (21, 32),
    "VALUATION":        (33, 43),
    "RISK & QUALITY":   (44, 58),
}

EXCERPT_WIDTH = 110   # max chars of 10-K snippet shown


def category(yes_count: int) -> str:
    for lo, hi, label in CATEGORIES:
        if lo <= yes_count <= hi:
            return label
    return "Excellent"


def _wrap(text: str, width: int, indent: str) -> str:
    """Simple word-wrap for excerpt display."""
    words = text.split()
    lines, line = [], []
    for w in words:
        if sum(len(x) + 1 for x in line) + len(w) > width:
            lines.append(indent + " ".join(line))
            line = [w]
        else:
            line.append(w)
    if line:
        lines.append(indent + " ".join(line))
    return "\n".join(lines)


def print_results(name: str, answers: list[Answer]):
    yes_count = sum(1 for a in answers if a.result == "Yes")
    no_count  = sum(1 for a in answers if a.result == "No")
    mr_count  = sum(1 for a in answers if a.result == "Manual Review Needed")
    cat       = category(yes_count)
    color     = CATEGORY_COLORS.get(cat, "")

    width = 96
    print("\n" + "=" * width)
    print(f"{BOLD}  {name}{RESET}")
    print("=" * width)

    for section, (start, end) in SECTIONS.items():
        print(f"\n{BOLD}-- {section} --{RESET}")
        for i, ans in enumerate(answers[start - 1:end], start=start):
            if ans.result == "Yes":
                tag_str = f"\033[92m[ YES ]{RESET}"
            elif ans.result == "No":
                tag_str = f"\033[91m[ NO  ]{RESET}"
            else:
                tag_str = f"\033[93m[ MR  ]{RESET}"

            print(f"  {i:2}. {tag_str}  {ans.question}")
            if ans.detail:
                print(f"           {BOLD}Data  :{RESET} {ans.detail}")
            if ans.excerpt:
                excerpt_short = ans.excerpt[:EXCERPT_WIDTH].replace("\n", " ")
                if len(ans.excerpt) > EXCERPT_WIDTH:
                    excerpt_short += "..."
                print(f"           {DIM}10-K  :{RESET} {excerpt_short}")

    print("\n" + "-" * width)
    print(f"  Score  : {BOLD}{yes_count} Yes{RESET}  |  {no_count} No  |  {mr_count} Manual Review")
    print(f"  Verdict: {color}{BOLD}{cat.upper()}{RESET}  "
          f"({yes_count}/{TOTAL_QUESTIONS} questions answered Yes)")
    print("=" * width + "\n")


def print_rule1(name: str, r: dict):
    width = 96

    def dollar(v):
        return f"${v:,.2f}" if v is not None else "N/A"

    def xfmt(v):
        return f"{v:.1f}x" if v is not None else "N/A"

    def verdict_block(cp, sp, mos):
        if cp is None or sp is None or mos is None:
            return None, None, None
        vs_mos     = (cp - mos) / mos * 100
        vs_sticker = (cp - sp) / sp * 100
        if cp <= mos:
            vstr   = f"\033[92m{BOLD}BUY{RESET}  - trading below MOS price"
            mstr   = f"\033[92m{abs(vs_mos):.1f}% below MOS{RESET}"
        elif cp <= sp:
            vstr   = f"\033[93m{BOLD}WATCH{RESET} - below sticker price but above MOS"
            mstr   = f"\033[93m{abs(vs_mos):.1f}% above MOS{RESET}"
        else:
            vstr   = f"\033[91m{BOLD}WAIT{RESET} - trading above sticker price"
            mstr   = f"\033[91m{abs(vs_mos):.1f}% above MOS{RESET}"
        sstr = (f"\033[92m{abs(vs_sticker):.1f}% below sticker{RESET}"
                if vs_sticker <= 0
                else f"\033[91m{abs(vs_sticker):.1f}% above sticker{RESET}")
        return vstr, mstr, sstr

    print("=" * width)
    print(f"{BOLD}  RULE #1 VALUATION  --  {name}{RESET}")
    print("=" * width)

    col = 46

    # ── Inputs ───────────────────────────────────────────
    print(f"\n  {BOLD}--- Inputs ---{RESET}")
    print(f"  {'Current EPS (TTM)':<{col}} {dollar(r['eps_ttm'])}")
    print(f"  {'Historical EPS Growth (5yr CAGR)':<{col}} {pct(r['hist_cagr'])}")
    print(f"  {'Analyst Growth Estimate (YoY consensus)':<{col}} {pct(r['analyst_growth'])}")
    print(f"  {'Growth Rate Used (conservative)':<{col}} {pct(r['growth_used'])}"
          f"    [{r['growth_source']}]")
    print(f"  {'Current P/E':<{col}} {xfmt(r['current_pe'])}")

    # ── Original Model ────────────────────────────────────
    print(f"\n  {BOLD}--- Original Model (Rule #1, unadjusted) ---{RESET}")
    print(f"  {'Future P/E  (2 x growth%)':<{col}} {xfmt(r['future_pe'])}")
    print(f"  {'Future EPS  (EPS x (1+g)^10)':<{col}} {dollar(r['future_eps'])}")
    print(f"  {'Future Price  (FutureEPS x FuturePE)':<{col}} {dollar(r['future_price'])}")
    print(f"  {'Sticker Price  (FuturePrice / 1.15^10)':<{col}} {dollar(r['sticker'])}")
    print(f"  {'MOS Price  (Sticker / 2)':<{col}} {dollar(r['mos'])}")

    # ── Adjusted Model ────────────────────────────────────
    print(f"\n  {BOLD}--- Adjusted Model (capped growth + 5yr decay to 3%) ---{RESET}")
    if r["adj_g"] is not None:
        print(f"  {'Growth Rate (capped ≤15%, decays to 3%)':<{col}} {pct(r['adj_g'])}")
        for note in r["adj_notes"]:
            print(f"  {'':4}\033[93m⚠  {note}{RESET}")
        print(f"  {'Future P/E  (2 x capped rate, ≤25x)':<{col}} {xfmt(r['adj_pe'])}")
        print(f"  {'Future EPS  (decay model)':<{col}} {dollar(r['adj_future_eps'])}")
        print(f"  {'Future Price':<{col}} {dollar(r['adj_future_price'])}")
        print(f"  {'Sticker Price  (FuturePrice / 1.15^10)':<{col}} {dollar(r['adj_sticker'])}")
        print(f"  {'MOS Price  (Sticker / 2)':<{col}} {dollar(r['adj_mos'])}")
    else:
        g = r["growth_used"]
        if g is not None and g <= 0:
            print(f"  N/A — growth rate is negative ({pct(g)}); projection requires positive growth")
        else:
            print(f"  N/A — insufficient data for projection")

    # ── Secondary Intrinsic Value Check ──────────────────
    print(f"\n  {BOLD}--- Secondary Check (avg 3yr EPS × 10–20x P/E) ---{RESET}")
    if r["secondary_low"] is not None:
        print(f"  {'Avg 3yr EPS':<{col}} {dollar(r['eps_3yr_avg'])}")
        print(f"  {'Intrinsic Range (10x – 20x)':<{col}} "
              f"{dollar(r['secondary_low'])} – {dollar(r['secondary_high'])}")
        if r["secondary_flag"]:
            print(f"  \033[91m{BOLD}⚠  PRIMARY STICKER DEVIATES >200% FROM SECONDARY RANGE — MANUAL REVIEW{RESET}")
    else:
        print(f"  N/A — insufficient EPS history")

    # ── Summary ───────────────────────────────────────────
    print()
    print("-" * width)
    cp      = r["current_price"]
    sp_orig = r["sticker"]
    sp_adj  = r["adj_sticker"]
    mos_adj = r["adj_mos"]

    print(f"  {'Current Price':<{col}} {dollar(cp)}")
    print(f"  {'Original Sticker Price':<{col}} {dollar(sp_orig)}")
    print(f"  {'Adjusted Sticker Price':<{col}} {dollar(sp_adj)}")
    print(f"  {'Adjusted MOS Price (buy target)':<{col}} {dollar(mos_adj)}")

    # Warning if adjusted differs from original by >50%
    if sp_orig is not None and sp_adj is not None and sp_orig > 0:
        diff_pct = abs(sp_adj - sp_orig) / sp_orig * 100
        if diff_pct > 50:
            print(f"\n  \033[93m{BOLD}⚠  Valuation adjusted for unsustainable growth assumptions."
                  f"  (Original: {dollar(sp_orig)}, Adjusted: {dollar(sp_adj)}, "
                  f"Δ {diff_pct:.0f}%){RESET}")

    # Verdict based on adjusted model (fall back to original if adjusted unavailable)
    sp_use  = sp_adj  if sp_adj  is not None else sp_orig
    mos_use = mos_adj if mos_adj is not None else r["mos"]
    verdict, mos_str, sticker_str = verdict_block(cp, sp_use, mos_use)
    if verdict:
        print(f"\n  Verdict    : {verdict}")
        print(f"  vs MOS     : {mos_str}")
        print(f"  vs Sticker : {sticker_str}")
    elif r["growth_used"] is None:
        print(f"\n  Verdict    : {BOLD}N/A{RESET} — no growth rate available for projection")
    elif r["adj_g"] is None:
        g = r["growth_used"]
        print(f"\n  Verdict    : {BOLD}N/A{RESET} — growth rate is negative ({pct(g)}); projection requires positive growth")

    print("=" * width + "\n")


# ─────────────────────────────────────────────
# NYSE Screener & auto-add logic
# ─────────────────────────────────────────────

PROGRESS_FILE   = "nyse_scan_progress.json"
RESULTS_FILE    = "nyse_scan_results.json"
SCORE_THRESHOLD = 21     # "Average" and above
POSITION_BUDGET = 5_000  # dollars allocated per portfolio entry


def get_nyse_tickers() -> list[tuple[str, str]]:
    """
    Fetch NYSE common-stock tickers from NASDAQ Trader's otherlisted.txt.
    Columns: ACT Symbol | Security Name | Exchange | CQS Symbol | ETF |
             Round Lot Size | Test Issue | NASDAQ Symbol
    Exchange code "N" = NYSE.  Filters out ETFs, test issues, and any
    symbol containing special characters (warrants, preferred shares, etc.).
    Returns a sorted list of (ticker, company_name).
    """
    url = "https://ftp.nasdaqtrader.com/SymbolDirectory/otherlisted.txt"
    print(f"Fetching NYSE ticker list from {url} ...")
    r = requests.get(url, timeout=30)
    r.raise_for_status()

    tickers: list[tuple[str, str]] = []
    for line in r.text.strip().splitlines()[1:]:   # skip header row
        if line.startswith("File Creation Time"):
            continue
        parts = line.split("|")
        if len(parts) < 7:
            continue
        symbol   = parts[0].strip()
        name     = parts[1].strip()
        exchange = parts[2].strip()
        etf      = parts[4].strip() if len(parts) > 4 else ""
        test     = parts[6].strip() if len(parts) > 6 else ""
        if exchange == "N" and etf != "Y" and test != "Y" and symbol:
            # Keep only clean alpha symbols (skip BRK.B-style, preferred, etc.)
            if re.match(r"^[A-Z]+$", symbol):
                tickers.append((symbol, name))

    tickers.sort(key=lambda x: x[0])
    print(f"Found {len(tickers)} NYSE common-stock tickers.\n")
    return tickers


def _load_progress() -> dict:
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"completed": [], "results": []}


def _save_progress(progress: dict) -> None:
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(progress, f, indent=2)


def _get_existing_tickers(endpoint: str) -> set[str]:
    """GET entries from the given API endpoint; return set of uppercase tickers."""
    website_url = os.environ.get("WEBSITE_URL", "").rstrip("/")
    if not website_url:
        return set()
    try:
        resp = requests.get(f"{website_url}{endpoint}", timeout=10)
        if resp.ok:
            return {e["ticker"].upper() for e in resp.json() if "ticker" in e}
    except Exception:
        pass
    return set()


def _post_to_watchlist(ticker: str, company: str, price: float) -> bool:
    """POST a stock to the website watchlist API."""
    website_url = os.environ.get("WEBSITE_URL", "").rstrip("/")
    if not website_url:
        return False
    try:
        resp = requests.post(
            f"{website_url}/api/watchlist",
            json={"ticker": ticker, "companyName": company, "priceWhenAdded": price},
            timeout=10,
        )
        return resp.status_code in (200, 201)
    except Exception:
        return False


def _post_to_portfolio(ticker: str, company: str, shares: int,
                       buy_price: float, buy_date: str) -> bool:
    """POST a stock to the website portfolio API."""
    website_url = os.environ.get("WEBSITE_URL", "").rstrip("/")
    if not website_url:
        return False
    try:
        resp = requests.post(
            f"{website_url}/api/portfolio",
            json={
                "ticker":      ticker,
                "companyName": company,
                "shares":      shares,
                "buyPrice":    buy_price,
                "buyDate":     buy_date,
            },
            timeout=10,
        )
        return resp.status_code in (200, 201)
    except Exception:
        return False


def auto_add(ticker: str, name: str, score: int,
             price: Optional[float], r1: Optional[dict]) -> tuple[str, str]:
    """
    Core decision function: portfolio, watchlist, or skip.

    Rules:
      - score < 21            → skip
      - score >= 21, price <= MOS and shares >= 1 → portfolio ($POSITION_BUDGET / price)
      - score >= 21, otherwise                    → watchlist

    Duplicate prevention: GETs current portfolio/watchlist before each POST.
    If WEBSITE_URL env var is not set, returns ('dry_run', ...) describing
    what would have happened without making any API calls.

    Returns (destination, message) where destination is one of:
      'portfolio'  successfully added to portfolio
      'watchlist'  successfully added to watchlist
      'duplicate'  ticker already exists in the target list
      'skipped'    score below threshold or no valid price
      'dry_run'    WEBSITE_URL not set — described action only
      'failed'     API call was made but returned an error
    """
    if score < SCORE_THRESHOLD:
        return ("skipped",
                f"Skipped — score {score}/{TOTAL_QUESTIONS} below threshold ({SCORE_THRESHOLD})")

    if price is None or price <= 0:
        return ("skipped",
                f"Skipped — no valid price available (score {score}/{TOTAL_QUESTIONS})")

    # MOS: prefer adjusted model, fall back to original
    mos: Optional[float] = None
    if r1:
        mos = r1.get("adj_mos") or r1.get("mos")

    website_url = os.environ.get("WEBSITE_URL", "").rstrip("/")
    today = datetime.date.today().isoformat()

    # Determine destination
    shares = int(POSITION_BUDGET / price) if price > 0 else 0
    use_portfolio = (mos is not None and price <= mos and shares >= 1)

    if use_portfolio:
        mos_str = f"${mos:.2f}"
        if not website_url:
            return ("dry_run",
                    f"[DRY RUN] PORTFOLIO: {ticker} — {shares} shares @ ${price:.2f}"
                    f"  (Score: {score}/{TOTAL_QUESTIONS}, MOS: {mos_str})"
                    f"  — set WEBSITE_URL to execute")

        if ticker.upper() in _get_existing_tickers("/api/portfolio"):
            return ("duplicate",
                    f"PORTFOLIO duplicate — {ticker} already exists, skipped")

        ok = _post_to_portfolio(ticker, name, shares, price, today)
        if ok:
            return ("portfolio",
                    f"Added to PORTFOLIO: {ticker} — {shares} shares @ ${price:.2f}"
                    f"  (Score: {score}/{TOTAL_QUESTIONS}, MOS: {mos_str})")
        return ("failed", f"PORTFOLIO POST failed for {ticker}")

    else:
        mos_str = f", MOS: ${mos:.2f}" if mos else ""
        reason  = (f"price ${price:.2f} > MOS ${mos:.2f}" if mos else "no MOS available")
        if not website_url:
            return ("dry_run",
                    f"[DRY RUN] WATCHLIST: {ticker}  (Score: {score}/{TOTAL_QUESTIONS}{mos_str},"
                    f" {reason})  — set WEBSITE_URL to execute")

        if ticker.upper() in _get_existing_tickers("/api/watchlist"):
            return ("duplicate",
                    f"WATCHLIST duplicate — {ticker} already exists, skipped")

        ok = _post_to_watchlist(ticker, name, price)
        if ok:
            return ("watchlist",
                    f"Added to WATCHLIST: {ticker}  (Score: {score}/{TOTAL_QUESTIONS}{mos_str})")
        return ("failed", f"WATCHLIST POST failed for {ticker}")


def _analyze_quiet(ticker: str):
    """
    Run analyze() with all output suppressed.
    Returns (name, yes_count, price, r1) or None on any failure.
    """
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            name, answers, r1 = analyze(ticker)
        yes_count = sum(1 for a in answers if a.result == "Yes")
        price = r1.get("current_price") if r1 else None
        return name, yes_count, price, r1
    except SystemExit:
        return None
    except Exception:
        return None


def run_screen_nyse(resume: bool = False) -> None:
    """
    Screen every NYSE common stock with the 58-question framework.
    Saves incremental progress to PROGRESS_FILE and final results to
    RESULTS_FILE.  Qualifying stocks are auto-added to portfolio or
    watchlist via auto_add() when WEBSITE_URL is set.
    """
    progress = _load_progress() if resume else {"completed": [], "results": []}
    completed_set = set(progress["completed"])

    tickers = get_nyse_tickers()
    total   = len(tickers)

    if resume and completed_set:
        remaining = total - len(completed_set)
        print(f"Resuming — {len(completed_set)} already done, {remaining} remaining.\n")

    for idx, (ticker, _hint) in enumerate(tickers, 1):
        if ticker in completed_set:
            continue

        print(f"Analyzing {idx}/{total}: {ticker} ...", end="", flush=True)

        result = _analyze_quiet(ticker)

        if result is None:
            print("  [SKIP — data unavailable]")
            progress["completed"].append(ticker)
            _save_progress(progress)
            time.sleep(1.5)
            continue

        name, score, price, r1 = result
        cat = category(score)
        destination, action_msg = auto_add(ticker, name, score, price, r1)

        print(f"  Score {score}/{TOTAL_QUESTIONS} [{cat}] — {action_msg}")

        progress["results"].append({
            "ticker":      ticker,
            "company":     name,
            "score":       score,
            "category":    cat,
            "price":       price,
            "destination": destination,
        })
        progress["completed"].append(ticker)
        _save_progress(progress)
        time.sleep(1.5)

    # Write final consolidated results file
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "scan_date":     datetime.datetime.now().isoformat(),
            "total_scanned": len(progress["results"]),
            "results":       progress["results"],
        }, f, indent=2)

    print(f"\nScan complete. Results saved to {RESULTS_FILE}")


def run_report() -> None:
    """Print a formatted summary of the latest scan results."""
    if not os.path.exists(RESULTS_FILE):
        print(f"No results file found ({RESULTS_FILE}). Run --screen-nyse first.")
        return

    with open(RESULTS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    results   = data.get("results", [])
    scan_date = data.get("scan_date", "unknown")
    total     = data.get("total_scanned", len(results))

    by_cat: dict[str, list] = {}
    for r in results:
        by_cat.setdefault(r["category"], []).append(r)

    width = 76
    print("\n" + "=" * width)
    print(f"  NYSE SCAN REPORT — {scan_date}")
    print("=" * width)
    print(f"  Total scanned : {total}")
    print()
    print("  Breakdown by score category:")
    for lo, hi, cat in CATEGORIES:
        entries = by_cat.get(cat, [])
        bar = "█" * min(len(entries), 40)
        print(f"    {cat:<12} ({lo:2d}–{hi:2d} pts): {len(entries):5d}  {bar}")

    qualifying = sorted(
        [r for r in results if r["score"] >= SCORE_THRESHOLD],
        key=lambda x: x["score"],
        reverse=True,
    )

    # Destination breakdown
    portfolio_entries = [r for r in qualifying if r.get("destination") == "portfolio"]
    watchlist_entries = [r for r in qualifying if r.get("destination") == "watchlist"]

    print(f"\n  Auto-add results:")
    print(f"    Added to portfolio : {len(portfolio_entries)}")
    print(f"    Added to watchlist : {len(watchlist_entries)}")
    print(f"    Duplicate/skipped  : {len(qualifying) - len(portfolio_entries) - len(watchlist_entries)}")

    print(f"\n  Qualifying stocks (score ≥ {SCORE_THRESHOLD}) — {len(qualifying)} found:\n")
    print(f"  {'Ticker':<8} {'Score':>5}  {'Category':<12} {'Dest':<10} {'Price':>8}  Company")
    print("  " + "-" * 70)
    for r in qualifying:
        price_str = f"${r['price']:.2f}" if r.get("price") else "   N/A"
        dest = r.get("destination", "—")
        print(f"  {r['ticker']:<8} {r['score']:>5}  {r['category']:<12} {dest:<10} {price_str:>8}  {r['company']}")
    print("=" * width + "\n")


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────

if __name__ == "__main__":
    args = sys.argv[1:]

    screen_nyse = "--screen-nyse" in args
    do_report   = "--report"      in args
    resume      = "--resume"      in args

    # Strip mode flags; parse remaining for --email / ticker
    remaining = [a for a in args if a not in ("--screen-nyse", "--report", "--resume")]

    email_arg = ""
    ticker    = ""
    i = 0
    while i < len(remaining):
        if remaining[i] in ("--email", "-e") and i + 1 < len(remaining):
            email_arg = remaining[i + 1]
            i += 2
        else:
            ticker = remaining[i].strip().upper()
            i += 1

    if email_arg:
        _SEC_HDR["User-Agent"] = f"StockAnalyzer {email_arg}"
    elif "user@example.com" in SEC_USER_AGENT:
        print("Tip: edit SEC_USER_AGENT at the top of the file, or pass --email your@email.com")
        print("     SEC EDGAR will still work but fair-access policy prefers a real contact.")
        print()

    if screen_nyse:
        run_screen_nyse(resume=resume)
    elif do_report:
        run_report()
    else:
        # ── Single-ticker mode ───────────────────────────────────────────
        if not ticker:
            ticker = input("Enter stock ticker (e.g. AAPL): ").strip().upper()
        if not ticker:
            print("No ticker entered.")
            sys.exit(1)

        name, answers, r1 = analyze(ticker)
        print_results(name, answers)
        print_rule1(name, r1)

        # Auto-add to portfolio or watchlist
        score = sum(1 for a in answers if a.result == "Yes")
        price = r1.get("current_price") if r1 else None
        destination, action_msg = auto_add(ticker, name, score, price, r1)
        print(f"\n  Auto-add: {action_msg}\n")
