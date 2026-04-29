"""Service layer ABCs — application ports in the Hexagonal Architecture sense.

These interfaces encode business rules and use cases.
Concrete implementations (local.py, hosted.py) are the adapters.
Routes depend only on these ABCs, never on concrete implementations.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class UserService(ABC):

    @abstractmethod
    async def get_profile(self) -> dict:
        """Return the current user's profile.

        Returns a dict with: id, email, display_name, onboarded.
        """

    @abstractmethod
    async def complete_onboarding(self) -> None:
        """Mark the user as having completed onboarding."""

    @abstractmethod
    async def get_usage(self) -> dict:
        """Return the user's current resource usage.

        Returns a dict with: total_pages, total_storage_bytes, document_count,
        max_pages, max_storage_bytes.
        """


class KBService(ABC):

    @abstractmethod
    async def list(self) -> list[dict]:
        """Return all knowledge bases owned by the current user."""

    @abstractmethod
    async def get(self, kb_id: str) -> dict | None:
        """Return a single knowledge base by ID, or None if not found or not owned."""

    @abstractmethod
    async def create(self, name: str, description: str | None) -> dict:
        """Create a new knowledge base.

        Raises HTTPException(400) if capacity limits are reached.
        Raises HTTPException(409) if a name conflict cannot be resolved.
        """

    @abstractmethod
    async def update(self, kb_id: str, name: str | None, description: str | None) -> dict | None:
        """Update a knowledge base. Returns None if not found or not owned."""

    @abstractmethod
    async def delete(self, kb_id: str) -> bool:
        """Delete a knowledge base. Returns True if deleted, False if not found.

        Raises HTTPException(400) in local mode (deletion not allowed).
        """


class DocumentService(ABC):

    @abstractmethod
    async def list(self, kb_id: str, path: str | None = None) -> list[dict]:
        """List documents in a knowledge base, optionally filtered by path."""

    @abstractmethod
    async def get(self, doc_id: str) -> dict | None:
        """Return a document by ID, or None if not found or not owned."""

    @abstractmethod
    async def get_content(self, doc_id: str) -> dict | None:
        """Return id, content, version for a document, or None if not found."""

    @abstractmethod
    async def get_url(self, doc_id: str) -> dict | None:
        """Return a presigned or local URL to access the document file.

        Returns {'url': str} or None if not found.
        Raises HTTPException(501) if storage is not configured (hosted mode).
        """

    @abstractmethod
    async def create_note(self, kb_id: str, filename: str, path: str, content: str) -> dict:
        """Create a new markdown note document.

        Raises HTTPException(404) if the knowledge base does not exist.
        Raises HTTPException(409) if a document with the same filename+path already exists.
        """

    @abstractmethod
    async def update_content(self, doc_id: str, content: str) -> dict | None:
        """Replace the full content of a document. Returns None if not found."""

    @abstractmethod
    async def update_metadata(self, doc_id: str, fields: dict) -> dict | None:
        """Update metadata fields of a document. Returns None if not found.

        Allowed keys: filename, path, title, date, tags, metadata.
        Raises ValueError for unknown field names.
        """

    @abstractmethod
    async def delete(self, doc_id: str) -> bool:
        """Delete or archive a document. Returns True if deleted, False if not found."""

    @abstractmethod
    async def bulk_delete(self, doc_ids: list[str]) -> int:
        """Delete or archive multiple documents. Returns count of affected rows."""


class ServiceFactory(ABC):
    """Creates scoped service instances bound to a specific user_id."""

    @abstractmethod
    def user_service(self, user_id: str) -> UserService:
        """Return a UserService scoped to user_id."""

    @abstractmethod
    def kb_service(self, user_id: str) -> KBService:
        """Return a KBService scoped to user_id."""

    @abstractmethod
    def document_service(self, user_id: str) -> DocumentService:
        """Return a DocumentService scoped to user_id."""
