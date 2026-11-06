# Affiliate Office

楽天アフィリエイトの比較記事を、6役のAIで回す最小モデル。

## 流れ
企画(ナツメ) → 調査(ドングリ:楽天API) → 執筆(ハチミツ) → 審査(クリ:公開関門) → 制作(モミジ) → 分析(ユズ)

## 動作確認（キー不要）
    python run.py daily --mock
    open review/office.html   # オフィス画面（公開されない）
    open docs/index.html      # 公開サイト（サンプルはnoindex）

## 本番に必要なもの
1. 楽天ウェブサービスでアプリ登録 → applicationId / accessKey。アプリ設定のURLに公開サイトURLを登録（Refererチェックがあるため）
2. 楽天アフィリエイトのアフィリエイトID
3. GitHubリポジトリのSecretsに登録: ANTHROPIC_API_KEY, RAKUTEN_APP_ID, RAKUTEN_ACCESS_KEY, RAKUTEN_AFFILIATE_ID
4. config.json の site_url を実URLに変更し、GitHub Pagesを docs/ で公開

## 運用
- 実データの記事は `pending` になり review/ に出る。目視で確認し `python run.py approve SLUG`（またはActionsのapprove入力）で公開
- 収益は data/revenue.csv（date,slug,clicks,orders,reward）に楽天の管理画面から転記
- 審査の禁止表現は office/agents.py の NG_WORDS で調整

## 注意
- 1日の上限は config.json の max_articles_per_day。量を増やすほどスパム判定のリスクが上がる
- 記事の冒頭に広告表示（ステマ規制対応）を自動で入れている。削除しないこと
