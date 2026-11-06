"""使い方:
  python run.py daily [--mock]   企画→調査→執筆→審査→制作→分析を回す
  python run.py approve SLUG     確認待ちの記事・ランキングを公開に回す（カンマ区切りで複数、ALL-RANKINGS で全ランキング）
  python run.py reject SLUG      確認待ちの記事を破棄する
  python run.py redo SLUG        確認待ちの記事を取り下げ、同じ話題を次回作り直す
  python run.py demand           候補キーワードの需要の目安を計測する
  python run.py report           分析と画面の再生成のみ
"""
import json
import sys
import time

from office import agents, core, ranking, render
from office.core import say


def update_rankings(cfg, state):
    """単価ランキングを更新する。新規は確認待ち、公開済み・確認待ちは中身だけ最新に差し替える。"""
    rks = state.setdefault("rankings", {})
    for rk in cfg.get("rankings", []):
        try:
            r = ranking.build(state, cfg, rk)
        except Exception as e:  # 1つの失敗で他を止めない
            say(state, "researcher", f"「{rk['keyword']}」のランキング更新に失敗（{type(e).__name__}: {str(e)[:120]}）")
            continue
        if not r:
            cur = rks.get("rank-" + rk["id"])
            if cur and cur["status"] == "pending":  # 古い確認待ちは、誤りを含む可能性があるため破棄する
                del rks["rank-" + rk["id"]]
            continue
        cur = rks.get(r["slug"])
        if cur and cur["status"] in ("published", "pending"):
            r["status"] = cur["status"]
        else:
            r["status"] = "pending" if cfg["require_human_approval"] else "published"
        rks[r["slug"]] = r
        say(state, "designer", f"ランキング {r['slug']} を更新（状態: {r['status']}）", done=True)


def daily(cfg, state):
    update_rankings(cfg, state)
    tried = set()  # 同じ実行の中で、同じ話題を繰り返さない
    for _ in range(cfg["max_articles_per_day"]):
        plan = agents.plan(state, cfg, tried)
        if not plan:
            break
        tried.add(plan["keyword"])
        items, sample = agents.research(state, cfg, plan["keyword"])
        if not items:
            continue
        spec_cols = agents.extract_specs(state, plan["keyword"], items)
        if not sample:
            agents.record_prices(items)
        try:
            article = agents.write(state, plan["keyword"], plan["angle"], items)
            problems = agents.review(state, article, items, sample)
        except Exception as e:  # 1記事の失敗で、他の記事と状態を失わない
            say(state, "writer", f"「{plan['keyword']}」の執筆・審査に失敗、見送り（{type(e).__name__}）")
            continue
        slug = f"{core.now():%Y%m%d}-{len(state['articles']) + 1:03d}"
        if problems:
            status = "rejected"
        elif sample:
            status = "sample"
        elif cfg["require_human_approval"]:
            status = "pending"
        else:
            status = "published"
        state["articles"].append({
            "slug": slug, "keyword": plan["keyword"], "status": status, "sample": sample,
            "problems": problems, "fetched_at": core.now().strftime("%Y-%m-%d %H:%M JST"),
            "items": items, "spec_columns": spec_cols, "content": article,
        })
        say(state, "designer", f"{slug} を組版（状態: {status}）", done=True, status=f"{slug} を組版済み")


def demand(cfg):
    from office import rakuten
    out = []
    for kw in cfg.get("demand_candidates", []):
        try:
            r = rakuten.probe(kw, cfg["site_url"], cfg.get("min_price", 0))
        except Exception as e:
            r = {"keyword": kw, "error": type(e).__name__}
        out.append(r)
        print(r)
        time.sleep(1.2)  # 楽天APIは1秒1回程度に抑える
    core.DATA.mkdir(exist_ok=True)
    (core.DATA / "demand.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


def set_status(state, slug, new):
    r = state.get("rankings", {}).get(slug)
    if r is not None:
        if r["status"] != "pending":
            sys.exit(f"確認待ちではありません: {slug}")
        r["status"] = new
        say(state, "designer", f"{slug} を {new} にしました", done=True)
        return
    for a in state["articles"]:
        if a["slug"] == slug and a["status"] == "pending":
            a["status"] = new
            say(state, "designer", f"{slug} を {new} にしました", done=True)
            return
    sys.exit(f"確認待ちの記事が見つかりません: {slug}")


def main():
    args = sys.argv[1:]
    if "--mock" in args:
        core.MOCK = True
        args.remove("--mock")
    cmd = args[0] if args else "daily"
    cfg, state = core.load_config(), core.load_state()
    if cmd == "demand":
        demand(cfg)
        return
    if cmd == "daily":
        daily(cfg, state)
    elif cmd == "approve":
        spec = args[1]
        if spec == "ALL-RANKINGS":  # 確認待ちのランキングをすべて公開に回す
            slugs = [k for k, r in state.get("rankings", {}).items() if r["status"] == "pending"]
        else:
            slugs = [x.strip() for x in spec.split(",") if x.strip()]
        for slug in slugs:
            set_status(state, slug, "published")
    elif cmd == "reject":
        set_status(state, args[1], "rejected")
    elif cmd == "redo":
        set_status(state, args[1], "withdrawn")
    elif cmd != "report":
        sys.exit(__doc__)
    agents.analyze(state)
    render.build(cfg, state)
    core.save_state(state)


if __name__ == "__main__":
    main()
