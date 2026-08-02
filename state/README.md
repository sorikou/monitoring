# state

urlwatchの監視履歴をローカルで保持する場所です。

`state/db.sqlite` には取得済みページの内容が含まれる可能性があるため、Publicの `sorikou/monitoring` ではGit管理しません。`.gitignore` はSQLite本体、WAL、SHMなどの付属ファイルを除外します。

GitHub Actionsでは、Privateの `sorikou/monitoring-state` にある `db.sqlite` を実行前に取得し、`state/db.sqlite` として使用します。Privateリポジトリだけに書き込める専用Deploy Keyを `STATE_REPO_SSH_KEY` として使用し、監視後は更新済みDBをPrivateリポジトリへ戻します。DBを取得できない場合や保存に失敗した場合は、ワークフローを失敗させます。

PublicリポジトリのGit履歴へSQLiteを追加しないでください。
