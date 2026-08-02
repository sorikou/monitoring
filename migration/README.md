# migration

このディレクトリには、旧リポジトリから移行するためだけの資料を置きます。移行完了後に削除できます。

| 旧版 | 新版での配置 | 状態 |
|---|---|---|
| `urls_template.yaml` | `migration/urls_template.legacy.yaml` | 内容を変換せずコピー済み |
| 旧版のURL 55件 | `migration/registry-seed.csv` | スプレッドシート一括取込用に生成済み |
| `urlwatch.yaml` | `config/urlwatch.yaml` | 通知設定の土台としてコピー済み |
| `db/db.sqlite` | `state/db.sqlite` | ローカルへコピー済み。PublicのGit履歴からは除外 |
| `.github/workflows/urlwatch.yml` | `migration/workflow.legacy.yml` | 参考資料としてコピー済み |
| `scripts/*.py` | 旧版を参照 | 未移植。必要な処理だけを整理して移植する |

`workflow.legacy.yml` は30分ごとの定期実行とGmail通知を含みます。テスト完了前に `.github/workflows/` へ移動しないでください。旧版と新版が同時に動くと通知が重複します。

`urls_template.legacy.yaml` には旧版由来の文字コード上の問題が含まれる可能性があります。移行元を保全するため、このファイル自体は直接修正せず、抽出した共通ルールを `config/site-presets.yaml` に新規記述します。

初期データを再生成する場合は、プロジェクトルートで `python scripts/registry/import_legacy.py` を実行します。重複URLや不正なURLがあれば生成を中止します。

`state/db.sqlite` はローカルに残しますが、取得済みページ内容の公開を避けるため `.gitignore` で除外しています。公開リポジトリへコミットしないでください。
