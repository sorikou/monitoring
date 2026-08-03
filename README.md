# monitoring-next

小説投稿サイトなどの更新を1時間ごとに確認し、変更があった場合にGmailで通知する監視システムの再構築用リポジトリです。

旧版は隣の `../monitoring-reference/` に参照専用で残し、このリポジトリは独立したGit履歴で管理します。

## 設計方針

- 作品一覧の正本はGoogleスプレッドシートとする
- urlwatchへ渡すYAMLは `generated/` に自動生成し、人が直接編集しない
- サイトごとの抽出設定は `config/site-presets.yaml` に置く
- 通常ユーザーは作品URLとサイト種類だけを登録する
- 監視間隔は1時間とする
- 初回登録時は基準データだけを保存し、通知しない
- 監視の停止は作品の物理削除ではなく無効化で扱う
- 旧版のSQLiteはローカルの `state/db.sqlite` に引き継ぐが、Publicリポジトリにはコミットしない
- Gmail認証情報などの秘密情報はGitHub Secretsで管理し、Gitへコミットしない

## ディレクトリ

| パス | 役割 |
|---|---|
| `app/` | Google Apps Scriptの作品管理Web画面 |
| `config/` | 通知設定とサイト別の監視ルール |
| `scripts/registry/` | Googleスプレッドシートから作品一覧を取得・検査する処理 |
| `scripts/monitoring/` | urlwatch用データの生成と監視実行に関する処理 |
| `migration/` | 旧版から移行するための資料。移行完了後に削除可能 |
| `state/` | urlwatchの監視履歴。SQLite本体はGit管理外 |
| `generated/` | GitHub Actionsが生成するファイル |
| `tests/fixtures/` | URL重複、プリセット選択、抽出結果などのテストデータ |
| `backups/` | 移行前バックアップ。Git管理外 |

## 現在の段階

初期構造、旧版ファイルの安全な退避、既存URLの一括変換、9種類のサイト別プリセット、公開CSVの取得・検査、監視用YAML生成、メール無効のローカル監視まで実装済みです。通知なしCIと手動監視はGitHub Actionsでも成功しています。監視状態はPrivateの `sorikou/monitoring-state` に保存します。Gmailの1通限定テストと再送防止も確認済みで、通常55件を1時間ごとに監視するワークフローを使用します。作品の追加・編集・停止・アーカイブを行う自分専用のApps Script Web管理画面も本番シートへ接続してデプロイ済みです。旧ワークフローは `migration/workflow.legacy.yml` に参考資料として残しています。

## セットアップとテスト

Python 3.12を用意し、プロジェクトルートで実行します。通常の開発では `requirements.txt`、GitHub ActionsではローカルとLinuxの解決結果を固定した `requirements-lock.txt` を使用します。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python scripts/registry/import_legacy.py --check
```

テストでは、55件・URL重複なし・ID重複なし・旧版と新プリセットのフィルター完全一致・無効行の除外・メール無効設定を確認します。

## 既存の55件を手入力せずに使う

旧版のURL一覧は `migration/urls_template.legacy.yaml` に保存済みです。次のコマンドで、重複を検査しながら既存55件を一括変換できます。外部サイトへのアクセスは行いません。

```powershell
python scripts/registry/import_legacy.py
```

このコマンドは次の2ファイルを作ります。

- `migration/registry-seed.csv`: Googleスプレッドシートへ一括インポートする初期データ
- `generated/urls.yaml`: 旧版のフィルターを保った、すぐにurlwatchへ渡せる監視データ

`registry-seed.csv` はリポジトリに同梱します。Googleスプレッドシートで「ファイル」→「インポート」→「アップロード」を選び、このCSVを読み込めば、URLを1件ずつ入力する必要はありません。列は次の8個です。

```text
id | enabled | site | preset | url | name | memo | updated_at
```

- `id`: 並び替え後も変わらない固定ID
- `enabled`: 監視対象なら `TRUE`。停止するときは行を削除せず `FALSE`
- `site`: サイト識別子
- `preset`: `config/site-presets.yaml` の抽出ルール名
- `url`: `http` または `https` の監視URL
- `name`: 空ならURLを名前として使用
- `memo`: 管理メモ。監視処理では使用しない
- `updated_at`: 最終編集日

この8列は移行用の旧形式です。Web管理画面では `name` を `title` に変更し、`created_at` と `archived` を加えた10列形式を使用します。監視側は両方を読めるため、本番シートを切り替えるまで既存の定期監視は止まりません。

`generated/urls.yaml` は自動生成物なのでGit管理外です。将来のGitHub Actionsでも、監視実行前に同じ生成処理を呼び出します。

## GoogleスプレッドシートからYAMLを作る

55件を登録済みの正本は [Monitoring Registry](https://docs.google.com/spreadsheets/d/1vAWAh3O06_n74x5J-FubE8tIHVKeZeRlGF5p49yCYUM/edit?usp=sharing) です。閲覧可能な公開設定になっており、このURLをそのまま `REGISTRY_ENDPOINT` に指定できます。通常の `https://docs.google.com/spreadsheets/d/.../edit#gid=...` 形式はCSVエクスポートURLへ自動変換します。`gid` がない場合は先頭の表示タブを取得します。取得失敗時に旧データへフォールバックせず、必ずエラー終了します。

```powershell
$env:REGISTRY_ENDPOINT = "https://docs.google.com/spreadsheets/d/1vAWAh3O06_n74x5J-FubE8tIHVKeZeRlGF5p49yCYUM/edit?usp=sharing"
python scripts/registry/fetch_registry.py
python scripts/monitoring/generate_urls.py
```

取得時は、共通の必須列、`title` または旧 `name`、`enabled`、任意の `archived`、URL形式、固定ID、URL重複、プリセット存在、サイトとプリセットの対応、有効行が1件以上あることを検査します。`archived=TRUE` の行は、`enabled` の値にかかわらず監視対象から除外します。

Google Sheetを準備する前は、同梱CSVを指定して同じ処理を確認できます。

```powershell
python scripts/registry/fetch_registry.py --endpoint migration/registry-seed.csv
python scripts/monitoring/generate_urls.py --endpoint migration/registry-seed.csv
```

## メールを送らずローカル監視する

`config/urlwatch.local.yaml` は標準出力だけを有効にし、メールを明示的に無効化しています。実行ラッパーは設定を再検査し、メールが無効でなければurlwatchを起動しません。また、メール関連の環境変数を子プロセスから除去します。

```powershell
python scripts/monitoring/run_local.py --verbose
```

代表3件だけを試す場合は、次のように生成します。

```powershell
python scripts/monitoring/generate_urls.py `
  --endpoint migration/registry-seed.csv `
  --output generated/urls.sample.yaml `
  --include-id monitor-0001 `
  --include-id monitor-0031 `
  --include-id monitor-0047
python scripts/monitoring/run_local.py --urls generated/urls.sample.yaml --verbose
```

WindowsではラッパーがPython UTF-8モードを有効にするため、日本語の抽出正規表現もCP932へ誤変換されません。

## Web管理画面

`app/` にはGoogle Apps Script用の管理画面を実装しています。管理できるのは、作品一覧、検索、追加、編集、監視の停止・再開、プリセット選択、URL重複検査、アーカイブ・復元です。GitHub Actionsの実行やGmail送信は行いません。

[Web管理画面](https://script.google.com/macros/s/AKfycbwMzS4Vt66VVsEs8iSWKC4ZykGjk_7zxpQSN6hQXE7Fx9DGnxcR5Bb26Xc2Nh2cHriz/exec) は本番の [Monitoring Registry](https://docs.google.com/spreadsheets/d/1vAWAh3O06_n74x5J-FubE8tIHVKeZeRlGF5p49yCYUM/edit?usp=sharing) へ接続済みです。Web管理画面は所有者本人のみアクセスでき、スプレッドシートの公開閲覧設定とは独立しています。55件、監視中55件、停止中0件、アーカイブ0件の読み込みを確認済みです。

切り替え前の原本は [バックアップ](https://docs.google.com/spreadsheets/d/16X4LffDJEPVRjdtAktuRkRz4ZE0xpIyEKxStF9lkJbU/edit?usp=drivesdk) として保存しました。55件をコピーした [monitoring-registry-test](https://docs.google.com/spreadsheets/d/1dTRLFKwU7D6khoyIIP-nKU--FkQB-_eWXrmBEnjuuco/edit) も、今後の変更確認用に残しています。どちらも本番Webアプリの接続先ではありません。

Apps Scriptへの設定、自分だけがアクセスできるWebアプリとしてのデプロイ、機能確認、運用方法は [app/README.md](app/README.md) を参照してください。更新処理はLock Serviceで直列化し、固定IDの重複を防ぎます。Web実行時はアクティブシートに依存せず、Script Propertiesに保存した明示的な本番スプレッドシートIDを使用します。

## GitHub Actions

現在は次の2ワークフローを使用します。

- `Validate registry`: Push、Pull Request、手動実行で、固定依存の導入、単体テスト、公開スプレッドシート55件の取得、YAML生成を検査します。SQLiteとSecretsは使用しません。
- `Monitor`: 毎時7分の `schedule` と `workflow_dispatch` で起動します。Privateの `sorikou/monitoring-state` からDBを取得し、更新後DBを同じPrivateリポジトリへ保存します。定期実行は通常55件をGmail通知ありで監視します。手動実行の `send_email` と `run_full_monitoring` の初期値はどちらも `false` です。

手動監視は同時実行を禁止し、20分でタイムアウトします。通常実行は55件でなければYAML生成を中止し、DBがない場合や保存できない場合も失敗します。

手動実行の `send_email=true` はGmail動作確認専用です。既存URLと同じDBキーを持つ1件だけを固定テスト値へ変更するため、初回は最大1通、同条件の再実行では変更なしとなり再送されません。確認後は `send_email=false` を実行し、通常55件の状態へ戻します。

手動実行の `run_full_monitoring=true` は、定期実行と同じ通常55件・Gmail有効の経路を確認するために使用します。`send_email` と同時に有効にはできません。

Private状態リポジトリだけを読み書きできるSSH Deploy Keyを用意し、その秘密鍵をPublicリポジトリの `STATE_REPO_SSH_KEY` に登録します。広い権限のPersonal Access Tokenは保存しません。`MAIL_USER` と `MAIL_PASS` は通知なしの手動監視が成功してから登録します。

## 自動実行を有効にする前の手順

1. Googleスプレッドシートを正本として接続する
2. Privateの `sorikou/monitoring-state` にSQLiteを保存する
3. `Validate registry` が成功することを確認する
4. `Monitor manually without email` を1回成功させる
5. `MAIL_USER` と `MAIL_PASS` をSecretsとして登録する
6. 手動実行で通知が1通だけ届くことを確認する
7. 旧版の定期実行を停止してから、新版の1時間ごとの実行を有効にする（完了後、最初の2～3回を確認する）

SQLiteには取得済みページの内容が含まれる可能性があります。このPublicリポジトリでは `state/db.sqlite` をGit管理外とし、公開履歴に含めません。GitHub Actionsの監視状態はPrivateの `sorikou/monitoring-state` だけに保存します。

## ローカル設定

`.env.example` を設定項目の一覧として参照してください。実際の `.env`、Gmailのアプリパスワード、Googleの認証JSON、アクセストークンはGitへ追加しません。
