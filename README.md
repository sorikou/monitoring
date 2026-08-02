# monitoring-next

小説投稿サイトなどの更新を30分ごとに確認し、変更があった場合にGmailで通知する監視システムの再構築用リポジトリです。

旧版は隣の `../monitoring-reference/` に参照専用で残し、このリポジトリは独立したGit履歴で管理します。

## 設計方針

- 作品一覧の正本はGoogleスプレッドシートとする
- urlwatchへ渡すYAMLは `generated/` に自動生成し、人が直接編集しない
- サイトごとの抽出設定は `config/site-presets.yaml` に置く
- 通常ユーザーは作品URLとサイト種類だけを登録する
- 監視間隔は30分とする
- 初回登録時は基準データだけを保存し、通知しない
- 監視の停止は作品の物理削除ではなく無効化で扱う
- 旧版のSQLiteはローカルの `state/db.sqlite` に引き継ぐが、Publicリポジトリにはコミットしない
- Gmail認証情報などの秘密情報はGitHub Secretsで管理し、Gitへコミットしない

## ディレクトリ

| パス | 役割 |
|---|---|
| `app/` | 将来のGoogle Apps ScriptまたはWeb管理画面 |
| `config/` | 通知設定とサイト別の監視ルール |
| `scripts/registry/` | Googleスプレッドシートから作品一覧を取得・検査する処理 |
| `scripts/monitoring/` | urlwatch用データの生成と監視実行に関する処理 |
| `migration/` | 旧版から移行するための資料。移行完了後に削除可能 |
| `state/` | urlwatchの監視履歴。SQLite本体はGit管理外 |
| `generated/` | GitHub Actionsが生成するファイル |
| `tests/fixtures/` | URL重複、プリセット選択、抽出結果などのテストデータ |
| `backups/` | 移行前バックアップ。Git管理外 |

## 現在の段階

初期構造、旧版ファイルの安全な退避、既存URLの一括変換処理まで作成済みです。自動実行ワークフローはまだ有効化していません。旧ワークフローは `migration/workflow.legacy.yml` に参考資料として置かれており、`.github/workflows/` には実行可能なワークフローがありません。

## 既存の55件を手入力せずに使う

旧版のURL一覧は `migration/urls_template.legacy.yaml` に保存済みです。次のコマンドで、重複を検査しながら既存55件を一括変換できます。外部サイトへのアクセスは行いません。

```powershell
python scripts/registry/import_legacy.py
```

このコマンドは次の2ファイルを作ります。

- `migration/registry-seed.csv`: Googleスプレッドシートへ一括インポートする初期データ
- `generated/urls.yaml`: 旧版のフィルターを保った、すぐにurlwatchへ渡せる監視データ

`registry-seed.csv` はリポジトリに同梱します。Googleスプレッドシートで「ファイル」→「インポート」→「アップロード」を選び、このCSVを読み込めば、URLを1件ずつ入力する必要はありません。列は `enabled`、`site`、`url`、`name` です。

`generated/urls.yaml` は自動生成物なのでGit管理外です。将来のGitHub Actionsでも、監視実行前に同じ生成処理を呼び出します。

## 自動実行を有効にする前の手順

1. 作品一覧の生成処理を実装する
2. Gmail通知を無効にした状態で手動テストする
3. `state/db.sqlite` を使い、旧版と監視結果を比較する
4. GitHubリポジトリに `MAIL_USER` と `MAIL_PASS` をSecretsとして登録する
5. PublicリポジトリへSQLiteをコミットせずに監視状態を維持する方法を決める
6. 必要最小限の権限を持つ新ワークフローを作る
7. 手動実行で通知が1通だけ届くことを確認する
8. 旧版の定期実行を停止してから、新版の30分ごとの実行を有効にする

SQLiteには取得済みページの内容が含まれる可能性があります。このPublicリポジトリでは `state/db.sqlite` をGit管理外とし、公開履歴に含めません。GitHub Actionsを有効にする前に、監視状態を保存するための非公開ストレージを別途用意してください。

## ローカル設定

`.env.example` を設定項目の一覧として参照してください。実際の `.env`、Gmailのアプリパスワード、Googleの認証JSON、アクセストークンはGitへ追加しません。
