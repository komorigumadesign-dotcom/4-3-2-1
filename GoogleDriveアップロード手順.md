# Google ドライブへのファイルアップロード手順(OAuth ユーザー認証)

`upload_to_drive.py` でローカルファイルを Google ドライブにアップロードするための、
セットアップから実行、トラブル対応までの一連の流れ。

## 1. 認証方式の選び方(経緯)

| 方式 | 個人の Gmail | 備考 |
|---|---|---|
| サービスアカウント | 使えない | 保存容量がなく、`storageQuotaExceeded`(403)になる。マイドライブのフォルダを共有しても同じ |
| サービスアカウント + 共有ドライブ | 使えない | Google Workspace(有料)が必要 |
| **OAuth 2.0 ユーザー認証** | **使える** | 自分のドライブの容量を使う。このスクリプトが採用している方式 |

## 2. 初回セットアップ

### 2-1. ライブラリのインストール
```powershell
pip install google-api-python-client google-auth google-auth-oauthlib
```

### 2-2. Google Cloud の設定
1. [Google Cloud コンソール](https://console.cloud.google.com/) を開き、プロジェクトを選ぶ(なければ作成)。
2. 「API とサービス」→「ライブラリ」→「Google Drive API」を**有効化**する。
3. 「Google Auth Platform(OAuth 同意画面)」を設定する。
   - アプリ名: 任意(例: `Drive Uploader`)
   - ユーザーサポートメール / 連絡先: 自分の Gmail
   - 対象(ユーザーの種類): **外部**
4. 「対象」→「テストユーザー」に**自分の Gmail を追加**する(忘れると `access_denied` になる)。
5. 「クライアント」→「クライアントを作成」→ アプリの種類 **デスクトップ アプリ** → 作成。
6. 「JSON をダウンロード」し、`credentials.json` に改名して `upload_to_drive.py` と同じフォルダに置く。

### 2-3. アップロード先フォルダの指定
- Google ドライブで保存先フォルダを開き、URL の `/folders/` の後ろの文字列がフォルダ ID。
- `upload_to_drive.py` の `DEFAULT_FOLDER_ID` に設定する。または、環境変数 `DRIVE_FOLDER_ID` か `--folder-id` で指定する。
- フォルダは、認証するアカウント(自分)のドライブにあればよい(共有設定は不要)。

## 3. 実行方法

```powershell
# UP フォルダ内の全ファイルをアップロード(VS Code の実行ボタン ▶ でも可)
python upload_to_drive.py

# 特定のファイルだけアップロード
python upload_to_drive.py .\sample.pdf

# フォルダ ID・ドライブ上の名前を指定
python upload_to_drive.py .\sample.pdf --folder-id <フォルダID> --name 別名.pdf
```

成功すると、名前・ID・URL がターミナルに表示される。

### 初回だけの認証操作
1. 実行するとブラウザが開く。**スクリプトは止めずに待たせたまま**操作する。
2. 自分の Gmail を選ぶ。
3. 「このアプリは Google で確認されていません」と出たら「詳細」→「(安全でないページ)に移動」。
4. Drive へのアクセス項目に**チェックを入れて**「続行」。
5. 「認証フローが完了しました」と出れば成功。以降は `token.json` が使われ、ブラウザ操作は不要。

## 4. ファイル構成

| ファイル | 役割 | Git |
|---|---|---|
| `upload_to_drive.py` | 本体 | コミットする |
| `credentials.json` | OAuth クライアント ID(秘密情報) | `.gitignore` 済み |
| `token.json` | 認証後に自動生成されるトークン(秘密情報) | `.gitignore` 済み |
| `UP/` | アップロードしたいファイルを置く場所 | `.gitignore` 済み |

## 5. トラブルシューティング

| 症状 | 原因と対処 |
|---|---|
| `SyntaxError: (unicode error) 'unicodeescape' ...` | Python コード内の `"C:\Users\..."` の `\U` が原因。パスは `r"C:\Users\..."`(raw 文字列)か `/` 区切りで書く。`help=` など説明文にパスを書かない |
| `error: the following arguments are required: file` | 古い版のコード。現在は `file` は省略可能(省略時は `UP` フォルダを使う) |
| 403 `storageQuotaExceeded`(Service Accounts do not have storage quota) | サービスアカウントでは個人ドライブに保存できない。OAuth 方式を使う |
| `access_denied`(エラー 403) | OAuth 同意画面の「テストユーザー」に自分の Gmail が入っていない |
| `localhost で接続が拒否されました`(ERR_CONNECTION_REFUSED) | 許可操作中にスクリプトが終了していた。古いブラウザタブを閉じ、スクリプトを再実行して新しいタブで許可する |
| 404(フォルダが見つからない) | フォルダ ID の誤り、または別アカウントでログインしている。スコープは `drive` が必要(`drive.file` では既存フォルダが見えない) |
| `FileNotFoundError: OAuth クライアント情報が見つかりません` | `credentials.json` を同じフォルダに置く |
| 数日後に再認証を求められる / `RefreshError` | 同意画面が「テスト」状態だとトークンは 7 日で失効する。`token.json` を削除して再実行する |
| 許可後に 403(権限不足) | 許可時に Drive の項目へチェックを入れ忘れた。`token.json` を削除して再実行し、チェックを入れる |

## 6. セキュリティ上の注意
- `credentials.json`、`token.json`、サービスアカウントの JSON キーは Git にコミットしない。
- 使わなくなったサービスアカウントのキーは、Google Cloud の「IAM と管理」→「サービスアカウント」→「キー」から削除する。
- `token.json` を削除すれば、ローカルのログイン状態を消せる。Google アカウント側の権限は
  「Google アカウント」→「セキュリティ」→「サードパーティのアクセス」から取り消せる。
