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


def _cache_path():
    return core.DATA / "amounts.json"


def _load_cache():
    import json
    p = _cache_path()
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _save_cache(c):
    import json
    core.DATA.mkdir(exist_ok=True)
    _cache_path().write_text(json.dumps(c, ensure_ascii=False), encoding="utf-8")


def _key(rk, it):
    import hashlib
    h = hashlib.md5((it["name"] + "|" + (it.get("caption") or "")[:400]).encode("utf-8")).hexdigest()[:8]
    return f"{rk['id']}:{it.get('code', '')}:{h}"


def extract_amounts(state, rk, items):
    """内容量を items[i]['total']（基準単位）に入れる。結果は商品コード単位でキャッシュし、同じ商品はAIに再度聞かない。"""
    import json
    base = rk["basis"]["base"]
    cache = _load_cache()
    todo = []
    for i, it in enumerate(items):
        c = cache.get(_key(rk, it))
        if c is None:
            todo.append(i)
        else:
            if c.get("fits", True) and c.get("total"):
                it["total"] = c["total"]
            it["_fits"] = c.get("fits", True)
    for k in range(0, len(todo), 30):  # 30件ずつ
        idx = todo[k:k + 30]
        slim = [{"i": i, "name": items[i]["name"], "caption": (items[i].get("caption") or "")[:400]} for i in idx]
        spec = rk.get("spec") or rk["keyword"]
        r = llm_json(
            "あなたは商品の内容量を抜き出す担当です。商品名と説明文に明記された数字だけを写し、"
            "推測・補完・計算はしません。JSONのみで答えます。",
            f"対象の種類: {spec}\n比較の基準単位: {base}\n商品:\n{json.dumps(slim, ensure_ascii=False)}\n"
            "各商品について次を答えて。"
            "(1) fits: 商品が『対象の種類』にちょうど当てはまるか（サイズ違い・種類違い・別商品はfalse）。"
            "(2) amount: 全体の内容量を『掛け合わせる数字のリスト』で。例: 500ml×24本 → [500,24]、5kg×2袋 → [5,2]、50袋 → [50]。"
            "(3) unit: ml, L, g, kg, 個 のいずれか（本・袋・枚・缶・ロールなどの数は個）。"
            "数字は原文にある数だけ（合計値を自分で計算して書かない）。不明・曖昧なら amount は null。"
            '{"rows":[{"i":0,"fits":true,"amount":[500,24],"unit":"ml"}]}を返して。',
            4000,
        )
        got = {row.get("i"): row for row in r.get("rows", []) if isinstance(row, dict)}
        for i in idx:
            row = got.get(i)
            if row is None:
                continue  # 回答が無い商品はキャッシュしない（次回に再挑戦）
            it = items[i]
            fits = bool(row.get("fits", True))
            t = None
            if row.get("amount"):
                t = total_amount(row["amount"], row.get("unit"), base, it["name"] + " " + (it.get("caption") or ""))
            cache[_key(rk, it)] = {"fits": fits, "total": t if (t and t > 0) else None}
            it["_fits"] = fits
            if fits and t and t > 0:
                it["total"] = t
    _save_cache(cache)
    return sum(1 for it in items if it.get("total"))


def build(state, cfg, rk):
    """1つのランキングを作る。作れない場合はNone。"""
    if core.MOCK or not rakuten.configured() or not llm_available():
        say(state, "researcher", f"「{rk['keyword']}」の単価ランキングは、APIキー未設定のため作成しません")
        return None
    import time
    items, seen = [], set()
    for page in range(1, rk.get("pages", 2) + 1):  # 候補を増やすため2ページ取得（1秒1回程度に抑える）
        for it in rakuten.search(rk["keyword"], 30, cfg["site_url"], rk.get("min_price", cfg.get("min_price", 0)), page):
            if it.get("code") not in seen:
                seen.add(it.get("code"))
                items.append(it)
        time.sleep(1.2)
    fetched = len(items)
    req, exc = rk.get("require", []), rk.get("exclude", [])
    items = [it for it in items
             if (not req or any(w in it["name"] for w in req)) and not any(w in it["name"] for w in exc)]
    matched = len(items)
    n = extract_amounts(state, rk, items)
    rows = []
    lo, hi = rk.get("total_min"), rk.get("total_max")  # 容量帯（例：米5kg帯）で絞る
    for it in items:
        if it.get("total") and it.get("_fits", True):
            if (lo is not None and it["total"] < lo) or (hi is not None and it["total"] > hi):
                continue
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
        it.pop("_fits", None)
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
        f"「{rk['keyword']}」: 取得{fetched}件→種類が合う{matched}件→内容量を確認{n}件→掲載{len(rows)}件（極端な値{excluded_outlier}件を除外）", done=True)
    return {
        "slug": "rank-" + rk["id"], "id": rk["id"], "group": rk.get("group", "その他"), "keyword": rk["keyword"], "title": rk["title"],
        "basis": rk["basis"], "notes": rk.get("notes", []), "items": rows,
        "fetched": matched, "confirmed": n, "excluded_outlier": excluded_outlier,
        "updated": core.now().strftime("%Y-%m-%d %H:%M JST"),
    }
