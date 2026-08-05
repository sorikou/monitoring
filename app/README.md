# Monitoring Registry Web

Googleスプレッドシートを正本のまま使い、監視作品をブラウザから管理するGoogle Apps Script Webアプリです。

この画面で行うのは、一覧、検索、追加、編集、監視の停止・再開、アーカイブ・復元です。GitHub Actionsの起動、urlwatchの実行、Gmail送信は行いません。スプレッドシートを更新した後、次回の定期監視が通常どおり読み取ります。

## 稼働中の本番環境

- [Web管理画面](https://script.google.com/macros/s/AKfycbwMzS4Vt66VVsEs8iSWKC4ZykGjk_7zxpQSN6hQXE7Fx9DGnxcR5Bb26Xc2Nh2cHriz/exec)（Googleへのログインなしでアクセス可能）
- [本番スプレッドシート](https://docs.google.com/spreadsheets/d/1vAWAh3O06_n74x5J-FubE8tIHVKeZeRlGF5p49yCYUM/edit?usp=sharing)（監視処理が読む正本）
- [Apps Scriptプロジェクト](https://script.google.com/u/0/home/projects/1BCnkth3UsK9auhL7a7WSSildYoc6rfPF-fvTWabHEeT9YGUrGpH_bA_l/edit)
- [切り替え前バックアップ](https://docs.google.com/spreadsheets/d/16X4LffDJEPVRjdtAktuRkRz4ZE0xpIyEKxStF9lkJbU/edit?usp=drivesdk)

2026年8月3日に本番シートを10列へ移行し、55件、監視中55件、停止中0件、アーカイブ0件でWeb管理画面から読み込めることを確認済みです。Script Propertiesの `SPREADSHEET_ID` は本番シートを明示的に指定しています。

## ファイル

- `Code.gs`: 検査、登録、更新、停止、アーカイブ、復元、同時更新ロック
- `Index.html`: 自分用の管理画面
- `appsscript.json`: Asia/Tokyo、V8、自分だけが利用できるWebアプリ設定

## データ列

`Registry` シートは次の10列を使います。

```text
id | enabled | site | preset | url | title | memo | created_at | updated_at | archived
```

- `id` は登録時に `monitor-0056` のように自動採番し、編集では変更しません。
- `enabled=FALSE` は一時停止です。
- アーカイブ時は `archived=TRUE` と `enabled=FALSE` を同時に設定し、行を削除しません。
- `site` はURLのホスト名からサーバー側で決定します。プリセットによるサイト制限はありません。
- URLはアーカイブ済みを含む全行で重複を拒否します。
- URLを変更するときは画面とサーバーの両方で確認を要求します。

監視側Pythonは従来の8列（`name`）と新しい10列（`title`）の両方に対応します。`archived=TRUE` の行は、`enabled` の値にかかわらず監視対象から除外します。

## テスト用スプレッドシート

原本を変更せずに作成した [monitoring-registry-test](https://docs.google.com/spreadsheets/d/1dTRLFKwU7D6khoyIIP-nKU--FkQB-_eWXrmBEnjuuco/edit) は、今後の変更確認用に残しています。55件を保持し、10列スキーマへ移行済みです。現在の本番Webアプリの接続先はこのテストシートではありません。

## Apps Scriptへ設定する

1. テスト用スプレッドシートを開き、「拡張機能」→「Apps Script」を選びます。
2. 既存の `コード.gs` を削除し、このフォルダの `Code.gs` の内容を貼り付けます。
3. HTMLファイル `Index` を作り、`Index.html` の内容を貼り付けます。
4. 「プロジェクトの設定」→「マニフェスト ファイルをエディタで表示する」を有効にし、`appsscript.json` の内容へ置き換えます。
5. 関数一覧から `setupForBoundSpreadsheet` を選び、1回実行します。
6. 初回の権限確認で、このスプレッドシートへのアクセスを許可します。
7. 実行ログの戻り値で `rowCount: 55` と、テスト用スプレッドシートIDを確認します。

`setupForBoundSpreadsheet` は、Webアプリ実行時にアクティブシートへ依存しないよう、対象IDをScript Propertiesへ保存します。旧8列のシートで実行した場合は、データを保ったまま10列へ移行します。すでに10列なら再実行しても列移行は行いません。

## 一般公開する

1. Apps Script右上の「デプロイ」→「新しいデプロイ」を選びます。
2. 種類を「ウェブアプリ」にします。
3. 「次のユーザーとして実行」は自分を選びます。
4. 「アクセスできるユーザー」は「全員」を選びます。
5. デプロイ後のURLを開きます。

本番デプロイは一般公開です。未ログイン環境からも表示でき、URLを知る人は作品の追加・編集・停止・アーカイブを実行できます。Webアプリは所有者権限で本番シートへ書き込むため、URLを秘密として扱うか、必要になった時点で認証・認可を追加してください。

## 機能テスト（15項目）

テスト用シートで次を確認します。

1. 初回表示が55件で、監視中55件になる。
2. タイトル、URL、ID、メモで検索できる。
3. 監視中、停止中、アーカイブで絞り込める。
4. 正しいURLとプリセットで1件追加でき、IDが自動採番される。
5. 同じURLをもう一度登録すると拒否される。
6. `http://` / `https://` 以外のURLが拒否される。
7. 未登録のサイトでも任意のプリセットを選んで登録でき、`site` はURLから自動設定される。
8. タイトルとメモを編集でき、IDは変わらない。
9. URL変更時に警告が表示され、確認しない限り保存されない。
10. 「停止」で `enabled=FALSE` になり一覧に残る。
11. 「再開」で `enabled=TRUE` に戻る。
12. 「保管」で `archived=TRUE`、`enabled=FALSE` になる。
13. 「復元」で `archived=FALSE`、`enabled=TRUE` に戻る。
14. 2つのタブから同時に追加しても、Lock ServiceによりIDが重複しない。
15. テスト終了後にCSV取得とYAML生成を実行し、アーカイブ・停止行が除外される。

追加したテスト行は、最後にアーカイブして残すか、テスト用シートだけで削除して構いません。本番では物理削除せずアーカイブを使用します。

## 本番運用

本番接続への切り替えは完了しています。コードを変更した場合はApps Scriptへ反映し、新しいバージョンへデプロイします。接続先だけを変更する場合は、プロジェクト設定のScript Propertiesにある `SPREADSHEET_ID` を変更します。

管理画面で変更した後は、次回のGitHub Actionsより前に `Validate registry` を手動実行すると、件数、重複、プリセット存在、YAML生成を安全に確認できます。管理画面は登録データだけを変更し、GitHub SecretsやPrivateのSQLiteにはアクセスしません。
