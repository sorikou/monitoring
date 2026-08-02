# state

urlwatchの監視履歴をローカルで保持する場所です。

旧版から移行した `db.sqlite` はこのディレクトリにありますが、取得済みページ内容が含まれる可能性があるため、PublicリポジトリではGit管理しません。`.gitignore` により `db.sqlite` と付随するSQLiteファイルを除外しています。

監視履歴を別の環境へ移す場合は、Gitではなく非公開の安全な経路で `state/db.sqlite` をコピーしてください。
