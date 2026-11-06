"""使い方:
  python run.py daily [--mock]   企画→調査→執筆→審査→制作→分析を回す
  python run.py approve SLUG     確認待ちの記事を公開に回す
  python run.py reject SLUG      確認待ちの記事を破棄する
  python run.py report           分析と画面の再生成のみ
"""
import sys

from office import agents, core, render
from office.core import say


def daily(cfg, state):
    for _ in range(cfg["max_articles_per_day"]):
        plan = agents.plan(state, cfg)
        if not plan:
            break
        items, sample = agents.research(state, cfg, plan["keyword"])
        if not items:
            continue
        article = agents.write(state, plan["keyword"], plan["angle"], items)
        problems = agents.review(state, article, items, sample)
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
            "items": items, "content": article,
        })
        say(state, "designer", f"{slug} を組版（状態: {status}）", done=True, status=f"{slug} を組版済み")


def set_status(state, slug, new):
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
    if cmd == "daily":
        daily(cfg, state)
    elif cmd == "approve":
        set_status(state, args[1], "published")
    elif cmd == "reject":
        set_status(state, args[1], "rejected")
    elif cmd != "report":
        sys.exit(__doc__)
    agents.analyze(state)
    render.build(cfg, state)
    core.save_state(state)


if __name__ == "__main__":
    main()
