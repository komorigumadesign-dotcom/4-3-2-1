r"""ローカルファイルを Google ドライブにアップロードする(OAuth 2.0 ユーザー認証)。

サービスアカウントは保存容量を持たないため、個人の Gmail ドライブへは保存できません。
そのため、ユーザー自身のアカウントで認証する OAuth 方式を使います。

事前準備:
  1. Google Cloud でプロジェクトを作成し、「Google Drive API」を有効化する。
  2. 「OAuth 同意画面」を設定し、テストユーザーに自分の Gmail を追加する。
  3. 「認証情報」→「OAuth クライアント ID」→ アプリの種類「デスクトップアプリ」を作成し、
     JSON をダウンロードして、このスクリプトと同じフォルダに credentials.json として置く。
  4. pip install google-api-python-client google-auth google-auth-oauthlib

初回実行:
  ブラウザが開くので Google にログインして許可する。以降は token.json に保存された
  トークンが自動で使われ(期限切れ時は自動更新)、ブラウザ操作は不要。

使い方:
  python upload_to_drive.py                       # UP フォルダ内の全ファイルをアップロード
  python upload_to_drive.py ./sample.pdf          # 指定ファイルのみ
  python upload_to_drive.py ./sample.pdf --folder-id <フォルダID> --name 別名.pdf

  環境変数 DRIVE_FOLDER_ID でもアップロード先フォルダ ID を指定可能。
"""

from __future__ import annotations

import argparse
import mimetypes
import os
import sys
from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

# 既存のフォルダへアップロードするには drive スコープが必要
# (drive.file だと、このアプリが作っていないフォルダは見えず 404 になる)
SCOPES = ["https://www.googleapis.com/auth/drive"]

# このサイズを超えたら再開可能(チャンク)アップロードを使う
RESUMABLE_THRESHOLD = 5 * 1024 * 1024
CHUNK_SIZE = 5 * 1024 * 1024  # 256KB の倍数であること

# 既定値(引数・環境変数を省略したときに使われる)
BASE_DIR = Path(__file__).resolve().parent
DEFAULT_UPLOAD_DIR = BASE_DIR / "UP"
DEFAULT_CLIENT_SECRET = BASE_DIR / "credentials.json"  # OAuth クライアント ID の JSON
DEFAULT_TOKEN = BASE_DIR / "token.json"  # 認証後に自動生成される
DEFAULT_FOLDER_ID = "1wCDM7k6Ktrf8FEuUkO9180qoKQdVMQh-"


def get_drive_service(client_secret_path: Path, token_path: Path):
    """OAuth でユーザー認証し、Drive API クライアントを返す。"""
    creds = None
    if token_path.is_file():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if creds and not creds.valid:
        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError:
                creds = None  # 失効 → 再認証
        else:
            creds = None

    if not creds:
        if not client_secret_path.is_file():
            raise FileNotFoundError(
                f"OAuth クライアント情報が見つかりません: {client_secret_path}"
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_path), SCOPES)
        creds = flow.run_local_server(port=0)  # ブラウザが開く
        token_path.write_text(creds.to_json(), encoding="utf-8")

    return build("drive", "v3", credentials=creds, cache_discovery=False)


def upload_file(
    service,
    file_path: str,
    folder_id: str | None = None,
    drive_filename: str | None = None,
) -> dict:
    """ファイルをアップロードし、作成されたファイルのメタデータを返す。"""
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"アップロードするファイルが見つかりません: {path}")

    mime_type, _ = mimetypes.guess_type(path.name)
    mime_type = mime_type or "application/octet-stream"

    metadata = {"name": drive_filename or path.name}
    if folder_id:
        metadata["parents"] = [folder_id]

    resumable = path.stat().st_size > RESUMABLE_THRESHOLD
    media = MediaFileUpload(
        str(path),
        mimetype=mime_type,
        resumable=resumable,
        chunksize=CHUNK_SIZE if resumable else -1,
    )

    request = service.files().create(
        body=metadata,
        media_body=media,
        fields="id, name, mimeType, size, webViewLink",
        supportsAllDrives=True,
    )

    if not resumable:
        return request.execute()

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"  アップロード中... {int(status.progress() * 100)}%")
    return response


def main() -> int:
    parser = argparse.ArgumentParser(description="Google ドライブへファイルをアップロード")
    parser.add_argument(
        "file",
        nargs="?",
        default=None,
        help="アップロードするファイルのパス(省略時は UP フォルダ内の全ファイル)",
    )
    parser.add_argument(
        "--client-secret",
        default=str(DEFAULT_CLIENT_SECRET),
        help="OAuth クライアント ID の JSON のパス(既定: credentials.json)",
    )
    parser.add_argument(
        "--token",
        default=str(DEFAULT_TOKEN),
        help="認証トークンの保存先(既定: token.json)",
    )
    parser.add_argument(
        "--folder-id",
        default=os.environ.get("DRIVE_FOLDER_ID") or DEFAULT_FOLDER_ID,
        help="アップロード先フォルダ ID",
    )
    parser.add_argument("--name", help="ドライブ上でのファイル名(省略時は元の名前。単一ファイル時のみ)")
    args = parser.parse_args()

    if args.file:
        targets = [Path(args.file)]
    else:
        if not DEFAULT_UPLOAD_DIR.is_dir():
            parser.error(f"UP フォルダが見つかりません: {DEFAULT_UPLOAD_DIR}")
        targets = sorted(p for p in DEFAULT_UPLOAD_DIR.iterdir() if p.is_file())
        if not targets:
            parser.error(f"UP フォルダにファイルがありません: {DEFAULT_UPLOAD_DIR}")

    try:
        service = get_drive_service(Path(args.client_secret), Path(args.token))
        for target in targets:
            print(f"アップロード: {target.name}")
            result = upload_file(
                service,
                str(target),
                args.folder_id,
                args.name if len(targets) == 1 else None,
            )
            print("  完了")
            print(f"  名前: {result['name']}")
            print(f"  ID  : {result['id']}")
            print(f"  URL : {result.get('webViewLink', '-')}")
    except (FileNotFoundError, HttpError) as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
