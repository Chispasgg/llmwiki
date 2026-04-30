"""Server-mode storage: local disk with user-scoped paths.

Upload path:  {root}/users/{user_id}/uploads/{key}
Wiki path:    {root}/shared/wiki/{key}
Generated:    {root}/shared/generated/{key}
"""
import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


class ServerStorageService:
    def __init__(self, files_root: str, api_url: str = "http://localhost:1502") -> None:
        self._root = Path(files_root)
        self._api_url = api_url.rstrip("/")
        # Crear directorios base
        (self._root / "shared" / "wiki").mkdir(parents=True, exist_ok=True)
        (self._root / "shared" / "generated").mkdir(parents=True, exist_ok=True)

    def _resolve(self, user_id: str, key: str) -> Path:
        """Resolve physical path. Prevents path traversal."""
        base = (self._root / "users" / user_id / "uploads").resolve()
        path = (base / key).resolve()
        if not str(path).startswith(str(base)):
            raise ValueError(f"Path traversal detected: {key}")
        return path

    async def upload_bytes(
        self, key: str, data: bytes,
        content_type: str = "application/octet-stream",
        user_id: str = "",
    ) -> None:
        path = self._resolve(user_id, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    async def upload_file(
        self, key: str, file_path: str,
        content_type: str = "application/octet-stream",
        user_id: str = "",
    ) -> None:
        dest = self._resolve(user_id, key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file_path, dest)

    async def download_bytes(self, key: str, user_id: str = "") -> bytes:
        path = self._resolve(user_id, key)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {key}")
        return path.read_bytes()

    async def download_to_file(
        self, key: str, dest_path: str, user_id: str = ""
    ) -> None:
        src = self._resolve(user_id, key)
        if not src.exists():
            raise FileNotFoundError(f"File not found: {key}")
        shutil.copy2(src, dest_path)

    async def generate_url(self, key: str, user_id: str = "") -> str:
        return f"{self._api_url}/v1/files/{key}"

    async def generate_presigned_get(
        self, key: str, expires_in: int = 3600, user_id: str = ""
    ) -> str:
        return await self.generate_url(key, user_id)

    async def generate_presigned_put(
        self, key: str, content_type: str = "", expires_in: int = 3600, user_id: str = ""
    ) -> str:
        return await self.generate_url(key, user_id)
