r"""ローカルファイルを Google ドライブにアップロードする(サービスアカウント認証)。

事前準備:
  1. Google Cloud でプロジェクトを作成し、「Google Drive API」を有効化する。
  2. サービスアカウントを作成し、JSON キーをダウンロードする。
  3. アップロード先のフォルダ(または共有ドライブ)を、サービスアカウントの
     メールアドレス(xxx@xxx.iam.gserviceaccount.com)に「編集者」で共有する。
     ※サービスアカウント自身のドライブには保存容量がないため、
       共有されたフォルダ/共有ドライブ以外へのアップロードは失敗します。
  4. pip install google-api-python-client google-auth

使い方:
  python upload_to_drive.py ./sample.pdf --folder-id <1wCDM7k6Ktrf8FEuUkO9180qoKQdVMQh-> \
      --credentials ./service_account.json

  環境変数でも指定可能:
    "C:\Users\komor\Desktop\AIエンジニア\part4_課題\4-3-2_API連携実践基礎①\project-d794f2fc-88a8-4acd-b5b-e4aeaeba2d09.json"  サービスアカウント JSON のパス
    DRIVE_FOLDER_ID1wCDM7k6Ktrf8FEuUkO9180qoKQdVMQh-                 アップロード先フォルダ ID
"""

from __future__ import annotations

import argparse
import mimetypes
import os
import sys
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

# ファイルの作成・アップロードに必要な最小限のスコープ
SCOPES = ["https://www.googleapis.com/auth/drive.file"]

# このサイズを超えたら再開可能(チャンク)アップロードを使う
RESUMABLE_THRESHOLD = 5 * 1024 * 1024
CHUNK_SIZE = 5 * 1024 * 1024  # 256KB の倍数であること


def get_drive_service(credentials_path: str):
    """サービスアカウントの JSON キーで認証し、Drive API クライアントを返す。"""
    if not os.path.isfile(credentials_path):
        raise FileNotFoundError(f"認証情報ファイルが見つかりません: {credentials_path}")

    creds = service_account.Credentials.from_service_account_file(
        credentials_path, scopes=SCOPES
    )
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
        supportsAllDrives=True,  # 共有ドライブ対応
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
    parser.add_argument("file", help="アップロードするローカルファイルのパス")
    parser.add_argument(
        "--credentials",
        default=os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"),
        help="サービスアカウント JSON キーのパス",
    )
    parser.add_argument(
        "--folder-id",
        default=os.environ.get("DRIVE_FOLDER_ID"),
        help="アップロード先フォルダ ID(サービスアカウントに共有済みであること)",
    )
    parser.add_argument("--name", help="ドライブ上でのファイル名(省略時は元の名前)")
    args = parser.parse_args()

    if not args.credentials:
        parser.error("--credentials か環境変数 GOOGLE_APPLICATION_CREDENTIALS を指定してください")
    if not args.folder_id:
        print(
            "警告: フォルダ ID 未指定です。サービスアカウントのドライブには容量がないため、"
            "失敗する可能性があります。",
            file=sys.stderr,
        )

    try:
        service = get_drive_service(args.credentials)
        result = upload_file(service, args.file, args.folder_id, args.name)
    except (FileNotFoundError, HttpError) as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 1

    print("アップロード完了")
    print(f"  名前: {result['name']}")
    print(f"  ID  : {result['id']}")
    print(f"  URL : {result.get('webViewLink', '-')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
