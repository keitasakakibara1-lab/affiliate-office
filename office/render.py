"""静的HTMLの生成（記事・一覧・オフィス画面）。"""
import html

from . import core
from .core import AGENTS

E = html.escape

CSS = """
:root{--bg:#f6f7fb;--fg:#1d2330;--mut:#667085;--card:#fff;--line:#e3e6ee;--acc:#2f6fed}
@media(prefers-color-scheme:dark){:root{--bg:#12151c;--fg:#e8ebf2;--mut:#98a2b3;--card:#1a1f2a;--line:#2a3140;--acc:#6b9bff}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.8 -apple-system,"Hiragino Sans","Noto Sans JP",sans-serif}
.wrap{max-width:760px;margin:0 auto;padding:20px 16px 60px}
h1{font-size:1.5rem;line-height:1.4}h2{font-size:1.15rem;margin-top:2em}
.pr{background:var(--card);border:1px solid var(--line);border-left:4px solid #d9a521;padding:10px 14px;border-radius:8px;font-size:.88rem;color:var(--mut)}
table{width:100%;border-collapse:collapse;font-size:.88rem;background:var(--card)}
th,td{border:1px solid var(--line);padding:8px;text-align:left;vertical-align:top}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin:14px 0}
.btn{display:inline-block;background:var(--acc);color:#fff;padding:8px 16px;border-radius:8px;text-decoration:none;font-size:.9rem}
.note{font-size:.8rem;color:var(--mut)}a{color:var(--acc)}
.gal{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0}.gal img{width:128px;height:128px;object-fit:cover;border-radius:8px;border:1px solid var(--line);background:#fff}
.rk{display:flex;gap:10px;align-items:flex-start;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px;margin:10px 0}
.rn{min-width:28px;height:28px;border-radius:50%;background:var(--acc);color:#fff;font-weight:700;text-align:center;line-height:28px;font-size:.85rem}
.rb{flex:1;min-width:0}.up{font-size:1.25rem;font-weight:700}.up small{font-size:.8rem;color:var(--mut);font-weight:400}
.nm{font-size:.9rem;line-height:1.5;margin:2px 0 4px;word-break:break-all}.ri img{width:72px;height:72px;object-fit:cover;border-radius:8px;border:1px solid var(--line)}
.sample{background:#fff3cd;color:#7a5b00;padding:8px 12px;border-radius:8px;font-size:.85rem}
"""

PR_TEXT = "本記事は広告（アフィリエイトリンク）を含みます。リンク経由で購入された場合、運営者に報酬が支払われることがあります。"


_SITE = {"url": "", "name": ""}


def _page(title, body, noindex=False, desc="", path="", date=""):
    import json as _json
    robots = '<meta name="robots" content="noindex">' if noindex else ""
    url = _SITE["url"].rstrip("/") + "/" + path if _SITE["url"] else ""
    meta = ""
    if desc:
        meta += f'<meta name="description" content="{E(desc)}">'
    if url and not noindex:
        meta += (f'<link rel="canonical" href="{E(url)}"><meta property="og:type" content="article">'
                 f'<meta property="og:title" content="{E(title)}"><meta property="og:description" content="{E(desc)}">'
                 f'<meta property="og:url" content="{E(url)}"><meta property="og:site_name" content="{E(_SITE["name"])}">')
        if date:
            ld = {"@context": "https://schema.org", "@type": "Article", "headline": title,
                  "datePublished": date, "dateModified": date, "mainEntityOfPage": url}
            meta += '<script type="application/ld+json">' + _json.dumps(ld, ensure_ascii=False).replace("</", "<\\/") + "</script>"
    foot = '<p class="note" style="margin-top:32px"><a href="about.html">運営者情報・記事の作り方</a></p>'
    return (f'<!doctype html><html lang="ja"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">{robots}{meta}'
            f"<title>{E(title)}</title><style>{CSS}</style></head><body><div class=\"wrap\">{body}{foot}</div></body></html>")


def about_html(cfg):
    body = (f'<p><a href="index.html">← 記事一覧</a></p><div class="pr">{PR_TEXT}</div><h1>運営者情報・記事の作り方</h1>'
            f"<h2>このサイトについて</h2><p>{E(cfg['site_name'])}は、楽天市場の商品を、価格・レビュー・商品ページの記載仕様という確認できる情報で比べるサイトです。個人が運営しています。</p>"
            "<h2>記事の作り方</h2><p>楽天市場の公式API（楽天ウェブサービス）で商品情報を取得し、AI（Claude）が下書きを作成します。"
            "商品ページの説明文から抜き出した仕様は、原文と照合して確認できた値だけを使います。公開前に運営者が内容を確認し、承認した記事だけを掲載しています。</p>"
            "<h2>広告について</h2><p>当サイトは楽天アフィリエイトを利用しており、記事内のリンクから購入されると運営者に報酬が入ります。"
            "報酬の有無で商品の順位や評価を変えることはありません。</p>"
            "<h2>掲載内容の限界</h2><p>実機での検証や測定は行っていません。価格・在庫・仕様は変わるため、購入前に必ず商品ページでご確認ください。誤りに気づかれた場合は、修正しますので運営者へお知らせください。</p>")
    return _page("運営者情報・記事の作り方", body, desc="サイトの運営者情報、記事の作り方、広告（アフィリエイト）の扱いについて。", path="about.html")


def article_html(a):
    items, d = a["items"], a["content"]
    shown = sorted({p["i"] for p in d["picks"]})
    rows = "".join(
        f"<tr><td>商品{chr(65 + i)}</td><td>{E(items[i]['name'])}</td><td>{items[i]['price']:,}円</td>"
        f"<td>{items[i]['review_avg']:.2f}（{items[i]['review_count']:,}件）</td></tr>" for i in shown
    )
    cols = [c for c in a.get("spec_columns", []) if any(c in (items[i].get("specs") or {}) for i in shown)]
    spec_tbl = ""
    if cols:
        head = "".join(f"<th>{E(c)}</th>" for c in cols)
        body_rows = "".join(
            f"<tr><td>商品{chr(65 + i)}</td>" + "".join(f"<td>{E((items[i].get('specs') or {}).get(c, '記載なし'))}</td>" for c in cols) + "</tr>"
            for i in shown
        )
        spec_tbl = (f"<h2>仕様の比較</h2><p class=\"note\">商品ページの説明文に書かれている内容を抜き出しています（実測ではありません）。"
                    f"「記載なし」は、説明文に見当たらなかった項目です。</p><table><tr><th>記号</th>{head}</tr>{body_rows}</table>")
    picks = ""
    for p in d["picks"]:
        it = items[p["i"]]
        imgs = it.get("images") or ([it["image"]] if it.get("image") else [])
        gal = "".join(
            f'<a href="{E(it["url"])}" rel="sponsored nofollow noopener" target="_blank">'
            f'<img src="{E(u)}" alt="{E(it["name"][:60])}" loading="lazy" width="128" height="128"></a>'
            for u in imgs[:3]
        )
        gallery = f'<div class="gal">{gal}</div>' if gal else ""
        picks += (
            f'<div class="card"><b>商品{chr(65 + p["i"])}：{E(it["name"])}</b><br>'
            f'<span class="note">{it["price"]:,}円 ／ レビュー {it["review_avg"]:.2f}（{it["review_count"]:,}件）</span>'
            f'{gallery}<p><b>向いている人：</b>{E(p["who_for"])}<br><b>選ぶ理由：</b>{E(p["point"])}<br>'
            f'<b>弱み：</b>{E(p["tradeoff"])}</p>'
            f'<a class="btn" href="{E(it["url"])}" rel="sponsored nofollow noopener" target="_blank">楽天市場で見る</a></div>'
        )
    faq = "".join(f"<p><b>Q. {E(f['q'])}</b><br>{E(f['a'])}</p>" for f in d.get("faq", []))
    sample = '<p class="sample">これはサンプルデータによる動作確認用の記事です。実在の商品情報ではありません。</p>' if a.get("sample") else ""
    body = (
        f'<p><a href="index.html">← 記事一覧</a></p><div class="pr">{PR_TEXT}</div>{sample}'
        f"<h1>{E(d['title'])}</h1><p>{E(d['lead'])}</p>"
        f"<h2>比較の基準</h2><p>楽天市場のレビュー件数が多い順に、在庫のある商品から{len(items)}件を取得し、商品の種類が合う{len(shown)}件を掲載しています。"
        f"レビュー件数が少ない商品と、種類が合わない商品は除外しました。</p>"
        f"<table><tr><th>記号</th><th>商品</th><th>価格</th><th>レビュー</th></tr>{rows}</table>"
        f"<p class=\"note\">データ取得日時：{E(a['fetched_at'])}。価格・在庫は変動します。購入前に販売ページでご確認ください。</p>"
        f"{spec_tbl}<h2>タイプ別のおすすめ</h2>{picks}<h2>よくある疑問</h2>{faq}"
    )
    return _page(d["title"], body, noindex=bool(a.get("sample")), desc=d["lead"][:110],
                 path=f'{a["slug"]}.html', date=a["fetched_at"][:10])


def _rank_stats(r):
    import statistics
    its = r["items"]
    ups = [i["unit_price"] for i in its]
    med = statistics.median(ups)
    top = its[0]
    bal = next((n for n, i in enumerate(its, 1) if i["review_avg"] >= 4.3 and i["review_count"] >= 100), None)
    return {"min": ups[0], "max": ups[-1], "med": med, "ratio": ups[-1] / ups[0],
            "saving": (med - top["unit_price"]) * top["total"], "bal": bal}


def ranking_html(r, related=()):
    base = r["basis"]["base"]
    unit = {"L": "L", "kg": "kg", "個": "個"}[base]
    label = r["basis"]["label"]
    st = _rank_stats(r)
    n_items = len(r["items"])

    def card(n, it):
        img = (f'<a href="{E(it["url"])}" rel="sponsored nofollow noopener" target="_blank">'
               f'<img src="{E(it["image"])}" alt="" loading="lazy" width="72" height="72"></a>') if it.get("image") else ""
        tot = f'{it["total"]:.2f}'.rstrip("0").rstrip(".")
        post = {"込み": "送料込み", "別": "送料別"}.get(it.get("postage"), "送料要確認")
        hist = ""
        if it.get("n_seen"):
            diff = (it["price"] / it["low_seen"] - 1) * 100
            hist = (f'<div class="note">当サイトの記録（{it["n_seen"]}日分）では、この商品の最も低い価格と同じです。</div>' if diff <= 0.5
                    else f'<div class="note">当サイトの記録（{it["n_seen"]}日分）の最も低い価格より、約{diff:.0f}%高い価格です。</div>')
        return (
            f'<div class="rk"><div class="rn">{n}</div>'
            f'<div class="rb"><div class="up">約{it["unit_price"]:.1f}円<small> / {E(unit)}</small></div>'
            f'<div class="nm"><a href="{E(it["url"])}" rel="sponsored nofollow noopener" target="_blank">{E(it["name"][:90])}</a></div>'
            f'<div class="note">{it["price"]:,}円（{post}）／ 総量 {tot}{unit} ／ レビュー {it["review_avg"]:.2f}（{it["review_count"]:,}件）／ {E(it.get("shop", ""))}</div>'
            f'{hist}<div style="margin-top:8px"><a class="btn" href="{E(it["url"])}" rel="sponsored nofollow noopener" target="_blank">楽天市場で見る</a></div>'
            f'</div><div class="ri">{img}</div></div>'
        )

    top_cards = "".join(card(n, it) for n, it in enumerate(r["items"][:5], 1))
    rest = r["items"][5:]
    rest_cards = ("<details><summary><b>6位〜%d位を見る</b></summary>" % n_items
                  + "".join(card(n, it) for n, it in enumerate(rest, 6)) + "</details>") if rest else ""
    ratio_txt = f"{st['ratio']:.1f}倍" if st["ratio"] >= 1.15 else "小さな差"
    summary = (
        f"<div class=\"card\"><b>このランキングで分かること</b><ul>"
        f"<li>掲載{n_items}件の{E(label)}の価格は、約{st['min']:.0f}円〜{st['max']:.0f}円で、最大で{ratio_txt}の差があります。</li>"
        f"<li>1位は、掲載商品の中央値（約{st['med']:.0f}円/{unit}）で同じ量（{r['items'][0]['total']:.0f}{unit}）を買う場合に比べて、約{max(st['saving'], 0):,.0f}円安くなります（送料・クーポンは含みません）。</li>"
        + (f"<li>レビュー4.3以上・100件以上の商品の中では、{st['bal']}位の商品が最も単価が低くなっています。</li>" if st["bal"] else "")
        + "</ul></div>"
    )
    notes = "".join(f"<li>{E(x)}</li>" for x in r.get("notes", []))
    howto = ("<h2>このランキングの使い方</h2><ul>"
             f"<li>必要な量を決めて、その量に近い商品から選ぶと、単価の差を活かせます。</li>"
             "<li>「送料別」の商品は、送料を足した合計で比べてください。</li>"
             "<li>商品名に期間限定価格やクーポンの記載がある場合は、期間外に価格が変わります。</li></ul>")
    body = (
        f'<p><a href="index.html">← 一覧</a></p><div class="pr">{PR_TEXT}</div>'
        f"<h1>{E(r['title'])}</h1>"
        f"<p>楽天市場でレビュー件数の多い商品のうち、商品名・説明文に内容量が明記されている商品を、<b>{E(label)}の価格が安い順</b>に並べています。"
        f"毎日、価格を取得し直して更新します。</p>"
        f"{summary}"
        f"<p class=\"note\">最終更新：{E(r['updated'])}。種類が合う{r['fetched']}件のうち、内容量を確認できた商品から掲載しています。"
        f"内容量は商品名・説明文の記載から抜き出し、原文と照合できた数字だけを使っています。誤りがある場合は購入ページの記載を優先してください。</p>"
        f"{top_cards}{rest_cards}"
        f"<p class=\"note\">価格は取得時点のものです。商品名は販売者の表記です。単価の安さは、味・品質・好みへの合い方を示すものではありません。</p>"
        f"{howto}<h2>選ぶときの注意</h2><ul>{notes}</ul>"
        + (("<h2>ほかのランキング</h2><ul>" + "".join(f'<li><a href="{E(x["slug"])}.html">{E(x["title"])}</a></li>' for x in related) + "</ul>") if related else "")
    )
    ym = r["updated"][:7].replace("-", "年") + "月"
    page_title = f"{r['title']}【{ym}更新】"
    return _page(page_title, body, desc=f"{r['keyword']}を{label}の価格が安い順に比較。{n_items}件の単価の差は最大{ratio_txt}。毎日更新。", path=f"{r['slug']}.html", date=r["updated"][:10])


def _range_txt(r):
    u = {"L": "L", "kg": "kg", "個": "個"}[r["basis"]["base"]]
    its = r["items"]
    return f"約{its[0]['unit_price']:.0f}〜{its[-1]['unit_price']:.0f}円/{u}（{len(its)}件）"


def index_html(cfg, arts, ranks=()):
    groups = {}
    for r in ranks:
        groups.setdefault(r.get("group", "その他"), []).append(r)
    rk = "".join(
        f"<li><b>{E(g)}</b><ul>" + "".join(f'<li><a href="{E(r["slug"])}.html">{E(r["title"])}</a> <span class="note">{_range_txt(r)}</span></li>' for r in rs) + "</ul></li>"
        for g, rs in groups.items())
    lis = rk + "".join(
        f'<li><a href="{E(a["slug"])}.html">{E(a["content"]["title"])}</a>'
        f'{" <span class=note>(サンプル)</span>" if a.get("sample") else ""}</li>' for a in arts
    ) or "<li>公開済みの記事はまだありません。</li>"
    body = (f"<h1>{E(cfg['site_name'])}</h1><div class=\"pr\">{PR_TEXT}</div>"
            f"<p>購入前の比較で迷わないための、数字で確認できる範囲の比較メモです。</p><ul>{lis}</ul>")
    return _page(cfg["site_name"], body, noindex=(all(a.get("sample") for a in arts) and not ranks),
                 desc=f'{cfg["site_name"]}：楽天市場の商品を、価格・レビュー・記載仕様で比べる比較メモ。')


def bear_svg(color):
    return (f'<svg viewBox="0 0 80 80" width="64" height="64" class="bear">'
            f'<circle cx="18" cy="20" r="11" fill="{color}"/><circle cx="62" cy="20" r="11" fill="{color}"/>'
            f'<circle cx="40" cy="44" r="29" fill="{color}"/><ellipse cx="40" cy="54" rx="13" ry="10" fill="#fff" opacity=".85"/>'
            f'<circle cx="30" cy="40" r="3.2" fill="#222"/><circle cx="50" cy="40" r="3.2" fill="#222"/>'
            f'<ellipse cx="40" cy="50" rx="4" ry="3" fill="#222"/></svg>')


OFFICE_CSS = """
.hd{display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:6px}
.stats{display:flex;gap:10px;flex-wrap:wrap;margin:12px 0}
.stat{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:8px 14px;min-width:90px}
.stat b{display:block;font-size:1.4rem;line-height:1.2}.stat span{font-size:.75rem;color:var(--mut)}
.desks{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:10px}
.desk{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px;display:flex;gap:10px;align-items:center}
.bear{animation:bob 3s ease-in-out infinite;flex:none}@keyframes bob{50%{transform:translateY(-3px)}}
.desk .n{font-weight:700}.desk .r{font-size:.75rem;color:var(--mut)}.desk .s{font-size:.8rem}
.log{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px 14px;margin-top:14px;max-height:360px;overflow:auto}
.log div{font-size:.85rem;padding:4px 0;border-bottom:1px dashed var(--line)}.log i{color:var(--mut);font-style:normal;font-size:.75rem}
"""


def office_html(cfg, state):
    arts = state["articles"]
    cnt = lambda s: sum(1 for a in arts if a["status"] == s)
    rev = state["revenue"]
    desks = ""
    for k, meta in AGENTS.items():
        st = state["agents"][k]
        desks += (f'<div class="desk">{bear_svg(meta["color"])}<div><div class="n">{meta["name"]}'
                  f' <span class="r">{meta["role"]}担当</span></div><div class="s">{E(st["status"])}</div>'
                  f'<div class="r">累計 {st["done"]} 件</div></div></div>')
    log = "".join(
        f'<div><i>{E(l["t"])}</i> <b style="color:{AGENTS[l["agent"]]["color"]}">{AGENTS[l["agent"]]["name"]}</b>：{E(l["msg"])}</div>'
        for l in reversed(state["log"][-40:])
    )
    stats = [("公開済み", cnt("published")), ("確認待ち", cnt("pending")), ("差し戻し", cnt("rejected")),
             ("サンプル", cnt("sample")), ("累計報酬(円)", f"{rev['total']:,}"), ("成果(件)", rev["orders"])]
    stat_html = "".join(f'<div class="stat"><b>{v}</b><span>{k}</span></div>' for k, v in stats)
    body = (f'<style>{OFFICE_CSS}</style><div class="hd"><h1>AI Affiliate Office</h1>'
            f'<span class="note">更新 {core.now().strftime("%Y-%m-%d %H:%M")} JST</span></div>'
            f'<div class="stats">{stat_html}</div><div class="desks">{desks}</div>'
            f'<h2>オフィスチャット</h2><div class="log">{log}</div>')
    return _page("AI Affiliate Office", body, noindex=True)


def build(cfg, state):
    core.DOCS.mkdir(exist_ok=True)
    core.REVIEW.mkdir(exist_ok=True)
    for old in list(core.DOCS.glob("*.html")) + list(core.REVIEW.glob("*.html")):
        old.unlink()
    public = [a for a in state["articles"] if a["status"] in ("published", "sample")]
    for a in state["articles"]:
        if a["status"] == "pending":
            (core.REVIEW / f"{a['slug']}.html").write_text(article_html(a), encoding="utf-8")
    _SITE["url"], _SITE["name"] = cfg.get("site_url", ""), cfg.get("site_name", "")
    for a in public:  # URL設定後に再生成（canonical用）
        (core.DOCS / f"{a['slug']}.html").write_text(article_html(a), encoding="utf-8")
    rpub = [r for r in state.get("rankings", {}).values() if r["status"] == "published"]
    def _rel(r):
        return [x for x in rpub if x["slug"] != r["slug"] and x.get("group") == r.get("group")][:8]
    for r in rpub:
        (core.DOCS / f"{r['slug']}.html").write_text(ranking_html(r, _rel(r)), encoding="utf-8")
    for r in state.get("rankings", {}).values():
        if r["status"] == "pending":
            (core.REVIEW / f"{r['slug']}.html").write_text(ranking_html(r), encoding="utf-8")
    (core.DOCS / "index.html").write_text(index_html(cfg, public, rpub), encoding="utf-8")
    (core.DOCS / "about.html").write_text(about_html(cfg), encoding="utf-8")
    base = cfg.get("site_url", "").rstrip("/")
    urls = [base + "/", base + "/about.html"] + [f"{base}/{a['slug']}.html" for a in public if not a.get("sample")] + [f"{base}/{r['slug']}.html" for r in rpub]
    lastmod = {f"{base}/{a['slug']}.html": a["fetched_at"][:10] for a in public}
    lastmod.update({f"{base}/{r['slug']}.html": r["updated"][:10] for r in rpub})
    sm = "".join(f"<url><loc>{E(u)}</loc>" + (f"<lastmod>{lastmod[u]}</lastmod>" if u in lastmod else "") + "</url>" for u in urls)
    (core.DOCS / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + sm + "</urlset>", encoding="utf-8")
    (core.DOCS / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n", encoding="utf-8")
    # 運営画面は公開サイトに含めない（収益やログが外部に出るため）
    (core.REVIEW / "office.html").write_text(office_html(cfg, state), encoding="utf-8")
