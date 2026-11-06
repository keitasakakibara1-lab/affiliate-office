"""設定・状態・LLM呼び出しの共通部。"""
import json
import os
import pathlib
import re
import datetime as dt

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DOCS = ROOT / "docs"        # 公開される静的サイト（GitHub Pages）
REVIEW = ROOT / "review"    # 人間確認待ちの下書き（公開されない）
JST = dt.timezone(dt.timedelta(hours=9))

AGENTS = {
    "planner":    {"name": "ナツメ", "role": "企画",   "color": "#e8833a"},
    "researcher": {"name": "ドングリ", "role": "調査", "color": "#4a7fd4"},
    "writer":     {"name": "ハチミツ", "role": "執筆", "color": "#d9a521"},
    "reviewer":   {"name": "クリ",   "role": "審査",   "color": "#2f9e6e"},
    "designer":   {"name": "モミジ", "role": "制作",   "color": "#c8456b"},
    "analyst":    {"name": "ユズ",   "role": "分析",   "color": "#7a5cc4"},
}

MOCK = False


def now():
    return dt.datetime.now(JST)


def load_config():
    return json.loads((ROOT / "config.json").read_text(encoding="utf-8"))


def load_state():
    p = DATA / "state.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {
        "agents": {k: {"done": 0, "status": "待機中"} for k in AGENTS},
        "log": [],
        "articles": [],
        "revenue": {"total": 0, "orders": 0, "clicks": 0, "by_slug": {}},
    }


def save_state(state):
    DATA.mkdir(exist_ok=True)
    state["log"] = state["log"][-80:]
    (DATA / "state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def say(state, agent, msg, done=False, status=None):
    """エージェントの発言をログに残し、状態を更新する。"""
    a = state["agents"][agent]
    if done:
        a["done"] += 1
    a["status"] = status or msg
    state["log"].append({"t": now().strftime("%m/%d %H:%M"), "agent": agent, "msg": msg})
    print(f"[{AGENTS[agent]['name']}/{AGENTS[agent]['role']}] {msg}")


def llm_available():
    return (not MOCK) and bool(os.environ.get("ANTHROPIC_API_KEY"))


def llm(system, user, max_tokens=4000):
    import anthropic
    cfg = load_config()
    client = anthropic.Anthropic()
    r = client.messages.create(
        model=cfg["model"],
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return r.content[0].text


def llm_json(system, user, max_tokens=4000):
    text = llm(system, user, max_tokens)
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("JSONが返らなかった: " + text[:200])
    return json.loads(m.group(0))
