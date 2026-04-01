"""
File storage service
Handles image upload, storage, and deletion
"""

import hashlib
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import UploadFile

from app.core.config import settings


class StorageService:
    """File storage service for managing uploaded images"""

    def __init__(self):
        """Initialize storage service"""
        self.upload_dir = Path(settings.UPLOAD_DIR)
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def _generate_filename(self, original_filename: str, user_id: str) -> str:
        """
        Generate unique filename

        Args:
            original_filename: Original file name
            user_id: User ID

        Returns:
            Unique filename
        """
        # Get file extension
        ext = Path(original_filename).suffix.lower()
        if not ext:
            ext = ".jpg"

        # Generate unique filename with timestamp and UUID
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid4())[:8]
        filename = f"{user_id}_{timestamp}_{unique_id}{ext}"

        return filename

    def _get_user_directory(self, user_id: str) -> Path:
        """
        Get user's upload directory

        Args:
            user_id: User ID

        Returns:
            Path to user directory
        """
        user_dir = self.upload_dir / str(user_id)
        user_dir.mkdir(parents=True, exist_ok=True)
        return user_dir

    async def save_image(self, file: UploadFile, user_id: str) -> tuple[str, str]:
        """
        Save uploaded image

        Args:
            file: Uploaded file
            user_id: User ID

        Returns:
            Tuple of (file_path, file_url)
        """
        # Generate filename
        filename = self._generate_filename(file.filename or "image.jpg", user_id)

        # Get user directory
        user_dir = self._get_user_directory(user_id)

        # Save file
        file_path = user_dir / filename
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Generate URL (full URL with base URL)
        relative_path = f"{user_id}/{filename}"
        # Use http://localhost:8000 for development
        base_url = "http://localhost:8000"
        file_url = f"{base_url}/uploads/{relative_path}"

        return str(file_path), file_url

    def save_image_bytes(
        self,
        data: bytes,
        user_id: str,
        original_name: str = "upload.jpg",
    ) -> tuple[str, str]:
        """
        Save raw image bytes (e.g. analysis upload preview for target_garment).
        Returns (absolute file_path, public http URL under /uploads/).
        """
        ext = Path(original_name).suffix.lower()
        if not ext or ext not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
            ext = ".jpg"
        filename = self._generate_filename(f"preview{ext}", user_id)
        user_dir = self._get_user_directory(user_id)
        file_path = user_dir / filename
        with open(file_path, "wb") as buffer:
            buffer.write(data)
        relative_path = f"{user_id}/{filename}"
        base_url = f"http://127.0.0.1:{settings.PORT}"
        file_url = f"{base_url}/uploads/{relative_path}"
        return str(file_path), file_url

    def delete_image(self, file_path: str) -> bool:
        """
        Delete image file

        Args:
            file_path: Path to file

        Returns:
            True if deleted, False otherwise
        """
        try:
            path = Path(file_path)
            if path.exists() and path.is_file():
                path.unlink()
                return True
            return False
        except Exception:
            return False

    def get_image_hash(self, file_path: str) -> Optional[str]:
        """
        Calculate MD5 hash of image file

        Args:
            file_path: Path to file

        Returns:
            MD5 hash or None if file doesn't exist
        """
        try:
            path = Path(file_path)
            if not path.exists():
                return None

            md5_hash = hashlib.md5()
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    md5_hash.update(chunk)

            return md5_hash.hexdigest()
        except Exception:
            return None

    def get_file_size(self, file_path: str) -> Optional[int]:
        """
        Get file size in bytes

        Args:
            file_path: Path to file

        Returns:
            File size or None if file doesn't exist
        """
        try:
            path = Path(file_path)
            if path.exists():
                return path.stat().st_size
            return None
        except Exception:
            return None

    def cleanup_user_directory(self, user_id: str) -> bool:
        """
        Delete all files in user's directory

        Args:
            user_id: User ID

        Returns:
            True if successful, False otherwise
        """
        try:
            user_dir = self.upload_dir / str(user_id)
            if user_dir.exists():
                shutil.rmtree(user_dir)
                return True
            return False
        except Exception:
            return False

    def _save_bytes(self, data: bytes, relative_path: str) -> tuple[str, str]:
        """
        Save raw bytes to a file path.

        Args:
            data: Raw bytes to save
            relative_path: Relative path within upload directory (e.g. "user_id/tryon/result.jpg")

        Returns:
            Tuple of (absolute_path, url)
        """
        file_path = self.upload_dir / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "wb") as f:
            f.write(data)
        base_url = "http://localhost:8000"
        file_url = f"{base_url}/uploads/{relative_path}"
        return str(file_path), file_url


# Global storage service instance
storage_service = StorageService()


def get_storage_service() -> StorageService:
    """
    Get storage service instance

    Returns:
        StorageService instance
    """
    return storage_service
