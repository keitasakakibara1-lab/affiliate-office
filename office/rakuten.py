"""楽天市場商品検索API（2026年2月刷新後の仕様）。

- エンドポイント: openapi.rakuten.co.jp
- applicationId と accessKey の両方が必要
- Referer（アプリ登録時に許可したURL）ヘッダーが必須
"""
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

ENDPOINT = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20220601"
UUID_RE = re.compile(r"[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")


def _env(name):
    return os.environ.get(name, "").strip()


def configured():
    return bool(_env("RAKUTEN_APP_ID") and _env("RAKUTEN_ACCESS_KEY"))


def diagnose():
    """鍵の値は出さず、形式だけを表示する。"""
    app, key, aff = _env("RAKUTEN_APP_ID"), _env("RAKUTEN_ACCESS_KEY"), _env("RAKUTEN_AFFILIATE_ID")
    print(f"[診断] applicationId: 長さ{len(app)} UUID形式={bool(UUID_RE.fullmatch(app))} / "
          f"accessKey: 長さ{len(key)} pk_始まり={key.startswith('pk_')} / affiliateId: 長さ{len(aff)}")


def _get(q, referer):
    u = urllib.parse.urlparse(referer)
    headers = {
        "Referer": referer,
        "Origin": f"{u.scheme}://{u.netloc}",
        "User-Agent": "Mozilla/5.0 (compatible; affiliate-office/1.0)",
        "Accept": "application/json",
    }
    req = urllib.request.Request(ENDPOINT + "?" + urllib.parse.urlencode(q), headers=headers)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def search(keyword, hits, referer, min_price=0):
    app, key, aff = _env("RAKUTEN_APP_ID"), _env("RAKUTEN_ACCESS_KEY"), _env("RAKUTEN_AFFILIATE_ID")
    q = {
        "format": "json",
        "formatVersion": 2,
        "applicationId": app,
        "accessKey": key,
        "keyword": keyword,
        "hits": min(max(hits * 3, 10), 30),  # 後で絞るため多めに取る
        "sort": "-reviewCount",
        "availability": 1,
        "imageFlag": 1,
    }
    if min_price:
        q["minPrice"] = min_price
    if aff:
        q["affiliateId"] = aff

    # 通常→affiliateIdなし→最小パラメータの順に試し、どれで通るかを記録する（原因の切り分け用）
    no_aff = {k: v for k, v in q.items() if k != "affiliateId"}
    minimal = {"format": "json", "applicationId": app, "accessKey": key, "keyword": keyword, "hits": 10}
    attempts, data = [], None
    for label, params in (("通常", q), ("affiliateIdなし", no_aff), ("最小パラメータ", minimal)):
        try:
            data = _get(params, referer)
            print(f"[楽天API] 「{label}」の呼び出しが成功")
            break
        except urllib.error.HTTPError as e:
            # URLにはキーが含まれるため出力しない。状態と本文だけ記録する
            body = e.read().decode("utf-8", "replace")[:300].replace("\n", " ")
            attempts.append(f"{label}: {e.code} {body}")
            if e.code != 400:
                break
    if data is None:
        diagnose()
        raise RuntimeError("楽天API失敗 | " + " | ".join(attempts)) from None

    items = []
    for it in data.get("Items", []):
        it = it.get("Item", it)
        count = int(it.get("reviewCount") or 0)
        avg = float(it.get("reviewAverage") or 0)
        if count < 20:  # レビューが薄い商品は比較の根拠にならない
            continue
        imgs = it.get("mediumImageUrls") or []
        img = imgs[0] if imgs and isinstance(imgs[0], str) else (imgs[0].get("imageUrl") if imgs else "")
        items.append({
            "name": it["itemName"],
            "price": int(it["itemPrice"]),
            "shop": it.get("shopName", ""),
            "review_avg": avg,
            "review_count": count,
            "url": it.get("affiliateUrl") or it["itemUrl"],
            "image": img,
        })
        if len(items) >= hits:
            break
    return items


def mock_items(keyword, hits):
    base = [(2980, 4.4, 1820), (4480, 4.6, 960), (1980, 4.1, 3410), (6980, 4.7, 410), (3480, 4.3, 702)]
    return [{
        "name": f"【サンプル】{keyword} モデル{chr(65 + i)}",
        "price": p, "shop": f"サンプルショップ{i + 1}",
        "review_avg": a, "review_count": c,
        "url": f"https://example.com/sample/{i + 1}", "image": "",
    } for i, (p, a, c) in enumerate(base[:hits])]
