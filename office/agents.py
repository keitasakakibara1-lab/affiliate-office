"""6役のエージェント。LLM未設定時はモック動作で一周できる。"""
import csv
import re

from . import core, rakuten
from .core import say, llm_available, llm_json

NG_WORDS = ["最安", "絶対", "必ず", "No.1", "ナンバーワン", "奇跡", "治る", "痩せる", "効果が出", "業界最高"]

WRITER_SYSTEM = """あなたは比較記事の執筆担当です。次の規則を厳守します。
- 提供された商品データ（名称・価格・レビュー平均・レビュー件数）に書かれた事実だけを使う。仕様・性能・効果を推測で書かない。
- 各おすすめには「向いている人」「選ぶ理由」「弱み（トレードオフ）」を必ず書く。弱みが書けない商品は選ばない。
- 「最安」「絶対」「No.1」など断定・最上級表現、健康や医療の効果を示す表現は使わない。
- 数字はデータにあるものだけ。レビューは「件数が多い」など事実で表現し、評価の優劣を断定しない。
- キーワードの商品種別に当てはまらない商品（例：ハブの検索に出たSDカードリーダー単体、ケース、ケーブルのみ）は picks に含めない。種別が合う商品が3件未満なら picks は空配列にする。
- 出力はJSONのみ。キー: title, lead, picks[{i, who_for, point, tradeoff}], faq[{q, a}]。iは商品データの添字。"""


# ---------- 企画（ナツメ） ----------
def plan(state, cfg):
    from collections import Counter
    rej = Counter(a["keyword"] for a in state["articles"] if a["status"] == "rejected")
    used = {a["keyword"] for a in state["articles"] if a["status"] != "rejected"} | {k for k, n in rej.items() if n >= 2}
    cands = [t for t in cfg["topics"] if t not in used]
    if not cands:
        say(state, "planner", "候補キーワードが尽きました。config.jsonに追加してください", status="ネタ切れ")
        return None
    kw, angle = cands[0], "レビュー件数と価格帯で比べる"
    if llm_available():
        try:
            r = llm_json(
                "あなたは比較記事の企画担当です。JSONのみで答えます。",
                f"候補: {cands}\n収益の状況: {state['revenue']}\n"
                '収益見込みと検索意図が明確なものを1つ選び、{"keyword":候補のいずれか,"angle":切り口}を返して。'
                "切り口は40字以内で、価格帯・レビュー件数・レビュー平均で比べる範囲に限り、"
                "実測・性能・発熱・互換性など商品データにない事実は含めないこと。",
                500,
            )
            if r.get("keyword") in cands:
                kw, angle = r["keyword"], r.get("angle", angle)
        except Exception as e:  # 企画の失敗では止めない
            say(state, "planner", f"LLM企画に失敗、先頭候補を採用（{e}）")
    say(state, "planner", f"今日のお題は「{kw}」。切り口は「{angle}」", done=True, status=f"「{kw}」を企画済み")
    return {"keyword": kw, "angle": angle}


# ---------- 調査（ドングリ） ----------
def research(state, cfg, kw):
    n = cfg["items_per_article"]
    if core.MOCK or not rakuten.configured():
        items, sample = rakuten.mock_items(kw, n), True
        say(state, "researcher", "楽天APIキー未設定のためサンプルデータを使用")
    else:
        items = rakuten.search(kw, n, cfg["site_url"], cfg.get("min_price", 0))
        sample = False
    if len(items) < 3:
        say(state, "researcher", f"「{kw}」は比較できる商品が{len(items)}件のみ。見送り", status="調査見送り")
        return None, False
    say(state, "researcher", f"{len(items)}商品を取得（レビュー件数順）", done=True, status="商品データ取得済み")
    return items, sample


# ---------- 執筆（ハチミツ） ----------
def write(state, kw, angle, items):
    if llm_available():
        data = llm_json(WRITER_SYSTEM, f"キーワード: {kw}\n切り口: {angle}\n商品データ:\n" + _items_json(items))
    else:
        data = _mock_article(kw, items)
    say(state, "writer", f"『{data['title']}』を書き上げました", done=True, status="執筆済み")
    return data


def _items_json(items):
    import json
    slim = [{"i": i, **{k: v for k, v in it.items() if k in ("name", "price", "review_avg", "review_count")}}
            for i, it in enumerate(items)]
    return json.dumps(slim, ensure_ascii=False)


def _mock_article(kw, items):
    by_count = max(range(len(items)), key=lambda i: items[i]["review_count"])
    by_price = min(range(len(items)), key=lambda i: items[i]["price"])
    by_avg = max(range(len(items)), key=lambda i: items[i]["review_avg"])
    picks = []
    for i, who, point, trade in [
        (by_count, "迷ったら実績重視で選びたい人", "取得時点でレビュー件数が最も多い", "価格は中位で、特別に安いわけではない"),
        (by_price, "まず安く試したい人", "候補の中で価格が最も低い", "レビュー平均は他に劣る場合がある"),
        (by_avg, "評価の高さを重視する人", "レビュー平均が候補の中で最も高い", "価格が高めになりやすい"),
    ]:
        if i not in [p["i"] for p in picks]:
            picks.append({"i": i, "who_for": who, "point": point, "tradeoff": trade})
    return {
        "title": f"{kw}の選び方：レビュー件数と価格で{len(items)}商品を比べる",
        "lead": f"{kw}を、楽天市場のレビュー件数・平均評価・価格という確認できる数字だけで比べました。"
                "仕様の優劣は断定せず、選ぶ基準を整理することに絞っています。",
        "picks": picks,
        "faq": [{"q": "価格は変わりますか？", "a": "掲載価格は取得時点のものです。購入前に販売ページでご確認ください。"}],
    }


# ---------- 審査（クリ）：公開前の関門 ----------
def review(state, article, items, sample):
    problems = []
    texts = [article.get("title", ""), article.get("lead", "")]
    for p in article.get("picks", []):
        texts += [p.get("who_for", ""), p.get("point", ""), p.get("tradeoff", "")]
        if not isinstance(p.get("i"), int) or not (0 <= p["i"] < len(items)):
            problems.append("存在しない商品を参照している")
        if not p.get("tradeoff"):
            problems.append("弱み（トレードオフ）が未記載")
    for f in article.get("faq", []):
        texts += [f.get("q", ""), f.get("a", "")]
    body = "".join(texts)
    for w in NG_WORDS:
        if w in body:
            problems.append(f"禁止表現「{w}」")
    if len(article.get("picks", [])) < 2:
        problems.append("比較対象が2商品未満")
    # 本文中の数字が商品データに由来するか（価格・件数の捏造を検知）
    allowed = {str(it["price"]) for it in items} | {str(it["review_count"]) for it in items}
    for it in items:  # 商品名に書かれた容量・ワット数などは根拠があるので許可
        allowed |= set(re.findall(r"\d+", it["name"].replace(",", "")))
    flat = body.replace(",", "")
    # 「1500円台」「1000件を超える」など、価格帯・件数帯の区切りとしての数字も許可
    band = set(re.findall(r"(\d+)(?=(?:円|件)(?:台|以下|未満|以上|前後|超|を超|から|〜|クラス))", flat))
    for num in re.findall(r"\d{3,}", flat):
        if num not in allowed and num not in band and not (len(num) == 4 and num.startswith("20")):
            problems.append(f"データにない数字「{num}」")
    # LLMによる二次審査（任意）
    if llm_available() and not problems:
        try:
            r = llm_json(
                "あなたは広告審査担当です。景品表示法・ステマ規制・Googleのスパムポリシーの観点で、"
                "根拠のない断定、誇大表現、薄い内容を指摘します。JSONのみ。",
                f"記事:\n{body}\n商品データ:\n{_items_json(items)}\n"
                '{"problems":["具体的な問題..."]}を返して。問題がなければ空配列。',
                800,
            )
            problems += r.get("problems", [])
        except Exception as e:
            say(state, "reviewer", f"LLM審査に失敗（{e}）。ルール審査のみで判定")
    problems = list(dict.fromkeys(problems))
    if problems:
        say(state, "reviewer", "差し戻し：" + " / ".join(problems[:3]), done=True, status="差し戻し")
    else:
        say(state, "reviewer", "審査を通過しました", done=True, status="審査通過")
    return problems


# ---------- 分析（ユズ） ----------
def analyze(state):
    """data/revenue.csv（date,slug,clicks,orders,reward）を集計する。"""
    p = core.DATA / "revenue.csv"
    rev = {"total": 0, "orders": 0, "clicks": 0, "by_slug": {}}
    if p.exists():
        with p.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                s = row.get("slug") or "(不明)"
                d = rev["by_slug"].setdefault(s, {"clicks": 0, "orders": 0, "reward": 0})
                for k in ("clicks", "orders", "reward"):
                    v = int(float(row.get(k) or 0))
                    d[k] += v
                    if k != "reward":
                        rev[k] += v
                    else:
                        rev["total"] += v
    state["revenue"] = rev
    published = sum(1 for a in state["articles"] if a["status"] == "published")
    per = f"1記事あたり約{rev['total'] // published}円" if published and rev["total"] else "実績データなし"
    say(state, "analyst", f"累計報酬{rev['total']:,}円・成果{rev['orders']}件（{per}）", done=True, status="収益を集計済み")
