"""楽天市場商品検索API（2026年2月刷新後の仕様）。

- エンドポイント: openapi.rakuten.co.jp
- applicationId と accessKey の両方が必要
- Referer（アプリ登録時に許可したURL）ヘッダーが必須
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

ENDPOINT = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20220601"


def configured():
    return bool(os.environ.get("RAKUTEN_APP_ID") and os.environ.get("RAKUTEN_ACCESS_KEY"))


def search(keyword, hits, referer, min_price=0):
    q = {
        "format": "json",
        "formatVersion": 2,
        "applicationId": os.environ["RAKUTEN_APP_ID"],
        "accessKey": os.environ["RAKUTEN_ACCESS_KEY"],
        "keyword": keyword,
        "hits": min(max(hits * 3, 10), 30),  # 後で絞るため多めに取る
        "sort": "-reviewCount",
        "availability": 1,
        "imageFlag": 1,
    }
    if min_price:
        q["minPrice"] = min_price
    if os.environ.get("RAKUTEN_AFFILIATE_ID"):
        q["affiliateId"] = os.environ["RAKUTEN_AFFILIATE_ID"]
    u = urllib.parse.urlparse(referer)
    headers = {
        "Referer": referer,
        "Origin": f"{u.scheme}://{u.netloc}",
        "User-Agent": "Mozilla/5.0 (compatible; affiliate-office/1.0)",
        "Accept": "application/json",
    }
    req = urllib.request.Request(ENDPOINT + "?" + urllib.parse.urlencode(q), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        # URLにはキーが含まれるため出力しない。本文だけ出す
        body = e.read().decode("utf-8", "replace")[:500]
        raise RuntimeError(f"楽天API {e.code}: {body}") from None

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
