"""6役のエージェント。LLM未設定時はモック動作で一周できる。"""
import csv
import re

from . import core, rakuten
from .core import say, llm_available, llm_json

NG_WORDS = ["最安", "絶対", "必ず", "No.1", "ナンバーワン", "奇跡", "治る", "痩せる", "効果が出", "業界最高"]

WRITER_SYSTEM = """あなたは比較記事の執筆担当です。次の規則を厳守します。
- 提供された商品データ（label・名称・価格・レビュー平均・レビュー件数）に書かれた事実だけを使う。仕様・性能・効果を推測で書かない。
- 本文で商品を指すときは、各商品の label（例：商品A）を使う。添字 i や「i=0」「商品0」のような番号は本文に書かない。商品名・リンク・価格は、本文とは別に表と商品カードで表示される。
- 各おすすめには「向いている人」「選ぶ理由」「弱み（トレードオフ）」を必ず書く。弱みが書けない商品は選ばない。
- キーワードの商品種別に当てはまらない商品（例：ハブの検索に出たSDカードリーダー単体、ケース、ケーブルのみ）は picks に含めない。種別が合う商品が3件未満なら picks は空配列にする。除外した商品がある場合は、lead で除外した旨と理由を1文書く。
- 件数・評価・価格の範囲は、picks に載せた商品だけで計算した値にする。
- 商品名に価格・クーポン・セール・期間の表記がある場合でも、価格はデータの値を使う。lead か faq で「商品名にクーポンやセールの表記があるが、実際の価格・期間は購入ページで確認が必要」と、全体に向けて1か所で注意する。
- 容量・サイズなどが商品名に複数併記されている商品は、その商品の弱みに「複数の表記がある」ことを書く。
- 認証・受賞・ランキング（「1位」「〇冠」「PSE認証」など）は商品名に書かれた販売者の表記にすぎない。「商品名に〜と記載」と表現し、事実として断定しない。
- specs は商品説明文に明記された仕様を機械的に抜き出し、原文との一致を確認済みの値。おすすめの理由と弱みには、specs の具体的な値（重量・サイズ・DPI・容量など）を使って違いを説明する。specs にない項目は「記載なし」と書かず、触れない。
- 検索語の特性（軽量・静音など）を裏付ける仕様値が specs にない場合だけ、lead に「実測比較ではない」と書く。
- 価格帯は「1,500円台」のように書き、「前半」「後半」は使わない。
- 「最安」「絶対」「No.1」など断定・最上級表現、健康や医療の効果を示す表現は使わない。レビューは件数や平均評価という事実で表現し、優劣を断定しない。
- 出力はJSONのみ。キー: title, lead, picks[{i, who_for, point, tradeoff}], faq[{q, a}]。iは商品データの添字。"""


# ---------- 企画（ナツメ） ----------
def plan(state, cfg, exclude=()):
    from collections import Counter
    arts = state["articles"]
    rej = Counter(a["keyword"] for a in arts if a["status"] == "rejected")
    withdrawn = {a["keyword"] for a in arts if a["status"] == "withdrawn"}
    kept = {a["keyword"] for a in arts if a["status"] not in ("rejected", "withdrawn")}
    skip = kept | {k for k, n in rej.items() if n >= 2} | set(exclude)
    cands = [t for t in cfg["topics"] if t not in skip]
    # 取り下げた話題 → 差し戻された話題 → 新しい話題 の順で優先する
    cands.sort(key=lambda t: 0 if t in withdrawn else (1 if rej.get(t) else 2))
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
                1500,
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


def _norm(t):
    import unicodedata
    return unicodedata.normalize("NFKC", t or "").replace(",", "")


def _grounded(value, src):
    """抽出値が原文に実在するか。数字はすべて原文に含まれ、数字なしの値は原文に部分一致すること。"""
    v, src = _norm(value), _norm(src)
    nums = re.findall(r"\d+(?:\.\d+)?", v)
    return all(n in src for n in nums) if nums else v in src


def extract_specs(state, kw, items):
    """商品説明文から比較用の仕様を抜き出し、原文と一致した値だけを残す。説明文は保存しない。"""
    import json
    cols = []
    if llm_available() and any(it.get("caption") for it in items):
        try:
            slim = [{"i": i, "name": it["name"], "caption": it.get("caption", "")[:800]} for i, it in enumerate(items)]
            r = llm_json(
                "あなたは商品仕様の抽出担当です。商品名と説明文に明記された値だけを、原文のまま短く写します。"
                "推測・換算・補完・言い換えはしません。書かれていない項目はnullです。JSONのみで答えます。",
                f"カテゴリ: {kw}\n商品:\n{json.dumps(slim, ensure_ascii=False)}\n"
                "購入者がこのカテゴリで選ぶ決め手になる項目（重量・サイズ・容量・対応機種・DPIなど）を3〜6個選び、"
                '{"columns":["項目名"],"rows":[{"i":0,"values":{"項目名":"原文の値またはnull"}}]}を返して。',
                3000,
            )
            rows = {x.get("i"): x.get("values", {}) for x in r.get("rows", []) if isinstance(x, dict)}
            for c in r.get("columns", [])[:6]:
                got = 0
                for i, it in enumerate(items):
                    v = (rows.get(i) or {}).get(c)
                    src = it["name"] + " " + it.get("caption", "")
                    if isinstance(v, str) and v.strip() and v != "null" and _grounded(v, src):
                        it.setdefault("specs", {})[c] = v.strip()
                        got += 1
                if got >= 3:  # 3商品以上で取れた項目だけ比較表に使う
                    cols.append(c)
                else:
                    for it in items:
                        it.get("specs", {}).pop(c, None)
        except Exception as e:
            say(state, "researcher", f"仕様抽出に失敗、価格とレビューのみで進行（{e}）")
    for it in items:
        it.pop("caption", None)
        if not it.get("specs"):
            it.pop("specs", None)
    n = sum(1 for it in items if it.get("specs"))
    say(state, "researcher", f"仕様を抽出：{len(cols)}項目（{'・'.join(cols) or 'なし'}）、{n}商品で取得", done=True)
    return cols


def record_prices(items):
    """価格履歴を data/prices.json に蓄積する（1日1回、商品コードごと）。"""
    import json
    p = core.DATA / "prices.json"
    h = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    day = f"{core.now():%Y-%m-%d}"
    for it in items:
        if it.get("code"):
            rows = h.setdefault(it["code"], [])
            if not rows or rows[-1][0] != day:
                rows.append([day, it["price"]])
    core.DATA.mkdir(exist_ok=True)
    p.write_text(json.dumps(h, ensure_ascii=False), encoding="utf-8")


def _items_json(items):
    import json
    slim = [{"i": i, "label": f"商品{chr(65 + i)}", **{k: v for k, v in it.items() if k in ("name", "price", "review_avg", "review_count", "specs")}}
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



def _page_text(article, items):
    """公開ページの表示内容をテキスト化する（審査用）。"""
    from . import render
    html_ = render.article_html({
        "slug": "x", "sample": False, "items": items, "content": article,
        "fetched_at": core.now().strftime("%Y-%m-%d %H:%M JST"),
    })
    html_ = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html_, flags=re.S)
    html_ = re.sub(r'<img[^>]*alt="([^"]*)"[^>]*>', r" [画像:\1] ", html_)
    html_ = re.sub(r"<a [^>]*>", " [リンク] ", html_)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html_))

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
    if re.search(r"i\s*=\s*\d|商品\s*\d+(?=[はのとがをも、。・）)\s])", body):
        problems.append("内部番号（i=0・商品0など）が本文に残っている")
    if len(article.get("picks", [])) < 2:
        problems.append("比較対象が2商品未満")
    # 本文中の数字が商品データに由来するか（価格・件数の捏造を検知）
    allowed = {str(it["price"]) for it in items} | {str(it["review_count"]) for it in items}
    for it in items:  # 商品名に書かれた容量・ワット数などは根拠があるので許可
        allowed |= set(re.findall(r"\d+", it["name"].replace(",", "")))
    for it in items:  # 説明文から原文照合済みの仕様値の数字も許可
        for v in (it.get("specs") or {}).values():
            allowed |= set(re.findall(r"\d+", _norm(v)))
    allowed.add(str(sum(it["review_count"] for it in items)))
    prices = [it["price"] for it in items]
    allowed |= {str(abs(a - b)) for a in prices for b in prices}  # 価格差は計算で得られる数字
    flat = body.replace(",", "")
    # 「1500円台」「1000件を超える」など、価格帯・件数帯の区切りとしての数字も許可
    band = set(re.findall(r"(\d+)(?=(?:円|件)(?:台|以下|未満|以上|前後|超|を超|から|〜|クラス))", flat))
    for num in re.findall(r"\d{3,}", flat):
        if num not in allowed and num not in band and not (len(num) == 4 and num.startswith("20")):
            problems.append(f"データにない数字「{num}」")
    # LLMによる二次審査（任意）
    if llm_available() and not problems:
        try:
            page = _page_text(article, items)
            r = llm_json(
                "あなたは広告審査担当です。渡すのは、公開される記事ページの全表示内容"
                "（広告表示・比較表・商品カード・リンク・画像を含む）です。"
                "根拠のない断定や誇大表現、誤認を招く価格・数値の扱い、データと矛盾する記述、"
                "内部番号やテンプレートの露出、広告表示の欠落（ページ内に表示があれば問題なし）の"
                "『重大な問題』だけを指摘します。"
                "このサイトは実機検証をせず、価格・レビュー件数・平均評価で比べるデータ比較の記事です。"
                "実機検証がないこと自体、文章の好み、軽微な表現は指摘しません。"
                "記事内で検証していないと明示されていれば問題なしです。JSONのみで答えます。",
                f"ページ内容:\n{page}\n商品データ:\n{_items_json(items)}\n"
                '{"problems":["具体的な重大問題..."]}を返して。なければ空配列。',
                3000,
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
