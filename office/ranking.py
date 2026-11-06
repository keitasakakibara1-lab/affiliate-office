"""毎日更新の単価ランキング。

内容量は商品名・説明文に明記された数字だけを使い、原文と照合できたものだけを表に載せる。
単価の計算（価格 ÷ 総量）はコードで行い、LLMには計算させない。
"""
import re
import statistics
import unicodedata

from . import core, rakuten
from .core import say, llm_available, llm_json

BASE_UNITS = {  # 比較の基準単位 → {記載の単位: 基準への換算係数}
    "L": {"ml": 0.001, "mL": 0.001, "ミリリットル": 0.001, "L": 1, "l": 1, "リットル": 1},
    "kg": {"g": 0.001, "kg": 1, "グラム": 0.001, "キロ": 1},
    "個": {"個": 1, "本": 1, "袋": 1, "杯": 1, "枚": 1},
}
BASE_LABEL = {"L": "1Lあたり", "kg": "1kgあたり", "個": "1個あたり"}
BASE_TEXT = {"L": "L", "kg": "kg", "個": "個"}


def _norm(t):
    return unicodedata.normalize("NFKC", t or "").replace(",", "")


def _fmt(n):
    return str(int(n)) if float(n).is_integer() else str(n)


def num_in(n, src):
    """数字nが原文srcに、独立した数として現れるか（'5' が '500' に一致しないように境界を見る）。"""
    return re.search(r"(?<![\d.])" + re.escape(_fmt(n)) + r"(?![\d.])", _norm(src)) is not None


def total_amount(nums, unit, base, src):
    """掛け合わせる数字と単位から、基準単位での総量を返す。原文に無い数字があればNone。"""
    f = BASE_UNITS[base].get(unit)
    if f is None or not isinstance(nums, list) or not (1 <= len(nums) <= 4):
        return None
    total = 1.0
    for n in nums:
        if isinstance(n, bool) or not isinstance(n, (int, float)) or n <= 0:
            return None
        if n != 1 and not num_in(n, src):
            return None
        total *= n
    return total * f


def extract_amounts(state, rk, items):
    """商品名・説明文から内容量を抜き出し、基準単位での総量を items[i]['total'] に入れる。"""
    base = rk["basis"]["base"]
    slim = [{"i": i, "name": it["name"], "caption": (it.get("caption") or "")[:400]} for i, it in enumerate(items)]
    import json
    r = llm_json(
        "あなたは商品の内容量を抜き出す担当です。商品名と説明文に明記された数字だけを写し、"
        "推測・補完・計算はしません。JSONのみで答えます。",
        f"カテゴリ: {rk['keyword']}\n比較の基準単位: {base}\n商品:\n{json.dumps(slim, ensure_ascii=False)}\n"
        "各商品について、全体の内容量を『掛け合わせる数字のリスト』と単位で答えて。"
        "例: 500ml×24本 → amount=[500,24], unit=\"ml\"。5kg×2袋 → amount=[5,2], unit=\"kg\"。"
        "ドリップバッグ50袋 → amount=[50], unit=\"個\"。"
        "単位は ml, L, g, kg, 個 のいずれか。数字は原文にある数だけ（合計値を自分で計算して書かない）。"
        "内容量が不明・曖昧なら amount は null。"
        '{"rows":[{"i":0,"amount":[500,24],"unit":"ml"}]}を返して。',
        4000,
    )
    ok = 0
    for row in r.get("rows", []):
        i = row.get("i")
        if not isinstance(i, int) or not (0 <= i < len(items)) or not row.get("amount"):
            continue
        t = total_amount(row["amount"], row.get("unit"), base, items[i]["name"] + " " + (items[i].get("caption") or ""))
        if t and t > 0:
            items[i]["total"] = t
            ok += 1
    return ok


def build(state, cfg, rk):
    """1つのランキングを作る。作れない場合はNone。"""
    if core.MOCK or not rakuten.configured() or not llm_available():
        say(state, "researcher", f"「{rk['keyword']}」の単価ランキングは、APIキー未設定のため作成しません")
        return None
    items = rakuten.search(rk["keyword"], 30, cfg["site_url"], cfg.get("min_price", 0))
    fetched = len(items)
    n = extract_amounts(state, rk, items)
    rows = []
    for it in items:
        if it.get("total"):
            it["unit_price"] = it["price"] / it["total"]
            rows.append(it)
    excluded_outlier = 0
    if len(rows) >= 5:
        m = statistics.median(r["unit_price"] for r in rows)
        kept = [r for r in rows if 0.25 * m <= r["unit_price"] <= 4 * m]  # 極端な値は誤抽出の疑い
        excluded_outlier = len(rows) - len(kept)
        rows = kept
    for it in items:
        it.pop("caption", None)
    if len(rows) < 5:
        say(state, "researcher", f"「{rk['keyword']}」は内容量を確認できた商品が{len(rows)}件のみ。更新を見送り")
        return None
    rows.sort(key=lambda r: r["unit_price"])
    rows = rows[:15]
    keep = ("name", "price", "shop", "review_avg", "review_count", "url", "image", "postage", "total", "unit_price")
    rows = [{k: r.get(k) for k in keep} for r in rows]
    rakuten_ids = [r for r in items if r.get("code")]
    try:
        from . import agents
        agents.record_prices(rakuten_ids)
    except Exception:
        pass
    say(state, "researcher",
        f"「{rk['keyword']}」: {fetched}件中{n}件で内容量を確認、{len(rows)}件を掲載（極端な値{excluded_outlier}件を除外）", done=True)
    return {
        "slug": "rank-" + rk["id"], "id": rk["id"], "keyword": rk["keyword"], "title": rk["title"],
        "basis": rk["basis"], "notes": rk.get("notes", []), "items": rows,
        "fetched": fetched, "confirmed": n, "excluded_outlier": excluded_outlier,
        "updated": core.now().strftime("%Y-%m-%d %H:%M JST"),
    }
