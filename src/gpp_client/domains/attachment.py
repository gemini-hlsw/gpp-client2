"""
Attachment domain.

Metadata queries are generated GraphQL operations; content transfer (upload,
update, download) speaks the ODB's REST endpoints. Downloads follow the
presigned URL with a bare, unauthenticated request, since storage services
reject unexpected headers.
"""

from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import urlparse

import httpx

from gpp_client._executor import AsyncExecutor, SyncExecutor
from gpp_client._generated.domains import (
    AsyncAttachmentOperations,
    AttachmentOperations,
)
from gpp_client._generated.enums import AttachmentType
from gpp_client.errors import (
    GPPError,
    GPPReadOnlyError,
    GPPResponseError,
    GPPValidationError,
)
from gpp_client.rest import map_transport_error, process_text

__all__ = ["AsyncAttachmentAPI", "AttachmentAPI"]

logger = logging.getLogger(__name__)

_ATTACHMENT_PATH = "/attachment"


def _resolve_content(file_path: str | Path | None, content: bytes | None) -> bytes:
    """Resolve upload bytes from exactly one source."""
    if (file_path is None) == (content is None):
        raise GPPValidationError("Provide exactly one of 'file_path' or 'content'.")
    if content is not None:
        return content
    assert file_path is not None  # guaranteed by the exclusivity check
    path = Path(file_path).expanduser()
    if not path.is_file():
        raise GPPValidationError(f"'{path}' is not a file.")
    return path.read_bytes()


def _upload_params(
    *,
    program_id: str,
    attachment_type: AttachmentType | str,
    file_name: str,
    description: str | None,
) -> dict[str, str]:
    params = {
        "programId": program_id,
        "fileName": file_name,
        "attachmentType": str(AttachmentType(attachment_type).value),
    }
    if description and description.strip():
        params["description"] = description.strip()
    return params


def _update_params(*, file_name: str, description: str | None) -> dict[str, str]:
    params = {"fileName": file_name}
    if description and description.strip():
        params["description"] = description.strip()
    return params


def _filename_from_presigned_url(download_url: str) -> str:
    name = Path(urlparse(download_url).path).name
    if not name:
        raise GPPError("Could not determine filename from presigned URL.")
    return name


def _resolve_destination(
    save_to: str | Path | None, filename: str, overwrite: bool
) -> Path:
    directory = Path(save_to).expanduser() if save_to is not None else Path.home()
    if directory.exists() and not directory.is_dir():
        raise GPPValidationError(f"'save_to' must be a directory: {directory}")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    if path.exists() and not overwrite:
        raise GPPError(f"File {path} already exists and overwrite is False.")
    return path


def _check_writable(executor: SyncExecutor | AsyncExecutor, action: str) -> None:
    """REST writes honor read_only exactly like GraphQL mutations."""
    if executor.core.read_only:
        raise GPPReadOnlyError(f"Cannot {action}: this client is read-only.")


class AttachmentAPI(AttachmentOperations):
    """
    Attachment operations: generated metadata queries plus REST transfer.
    """

    def __init__(self, executor: SyncExecutor, http: httpx.Client) -> None:
        super().__init__(executor)
        self._http = http

    def upload(
        self,
        program_id: str,
        *,
        attachment_type: AttachmentType | str,
        file_name: str,
        description: str | None = None,
        file_path: str | Path | None = None,
        content: bytes | None = None,
    ) -> str:
        """
        Upload a new attachment for a program and return its ID.

        Parameters
        ----------
        program_id : str
            The program to attach to.
        attachment_type : AttachmentType | str
            The attachment type.
        file_name : str
            File name to store.
        description : str | None, optional
            Optional description.
        file_path : str | Path | None, optional
            Path whose contents are uploaded. Exclusive with ``content``.
        content : bytes | None, optional
            Raw bytes to upload. Exclusive with ``file_path``.
        """
        _check_writable(self._executor, "upload an attachment")
        body = _resolve_content(file_path, content)
        params = _upload_params(
            program_id=program_id,
            attachment_type=attachment_type,
            file_name=file_name,
            description=description,
        )
        try:
            response = self._http.post(_ATTACHMENT_PATH, params=params, content=body)
        except httpx.HTTPError as exc:
            raise map_transport_error(exc, str(self._http.base_url)) from exc
        attachment_id = process_text(response).strip()
        if not attachment_id:
            raise GPPResponseError(
                response.status_code, "Upload returned an empty attachment id."
            )
        return attachment_id

    def update_by_id(
        self,
        attachment_id: str,
        *,
        file_name: str,
        description: str | None = None,
        file_path: str | Path | None = None,
        content: bytes | None = None,
    ) -> None:
        """
        Replace an attachment's content and metadata by ID.

        Parameters
        ----------
        attachment_id : str
            The attachment to update.
        file_name : str
            New file name (required by the endpoint).
        description : str | None, optional
            New description.
        file_path : str | Path | None, optional
            Path whose contents replace the attachment. Exclusive with
            ``content``.
        content : bytes | None, optional
            Raw replacement bytes. Exclusive with ``file_path``.
        """
        _check_writable(self._executor, "update an attachment")
        body = _resolve_content(file_path, content)
        params = _update_params(file_name=file_name, description=description)
        try:
            response = self._http.put(
                f"{_ATTACHMENT_PATH}/{attachment_id}", params=params, content=body
            )
        except httpx.HTTPError as exc:
            raise map_transport_error(exc, str(self._http.base_url)) from exc
        process_text(response)

    def delete_by_id(self, attachment_id: str) -> None:
        """
        Delete an attachment by ID.

        Parameters
        ----------
        attachment_id : str
            The attachment to delete.
        """
        _check_writable(self._executor, "delete an attachment")
        try:
            response = self._http.delete(f"{_ATTACHMENT_PATH}/{attachment_id}")
        except httpx.HTTPError as exc:
            raise map_transport_error(exc, str(self._http.base_url)) from exc
        process_text(response)

    def get_download_url_by_id(self, attachment_id: str) -> str:
        """
        Get the presigned download URL for an attachment.

        Parameters
        ----------
        attachment_id : str
            The attachment ID.
        """
        try:
            response = self._http.get(f"{_ATTACHMENT_PATH}/url/{attachment_id}")
        except httpx.HTTPError as exc:
            raise map_transport_error(exc, str(self._http.base_url)) from exc
        return process_text(response).strip()

    def download_by_id(
        self,
        attachment_id: str,
        save_to: str | Path | None = None,
        *,
        overwrite: bool = False,
        chunk_size: int = 1024 * 1024,
    ) -> Path:
        """
        Download an attachment to disk and return the file path.

        Parameters
        ----------
        attachment_id : str
            The attachment ID.
        save_to : str | Path | None, optional
            Destination directory; defaults to the home directory.
        overwrite : bool, default=False
            Whether to replace an existing file.
        chunk_size : int, default=1 MiB
            Streaming chunk size in bytes.
        """
        download_url = self.get_download_url_by_id(attachment_id)
        path = _resolve_destination(
            save_to, _filename_from_presigned_url(download_url), overwrite
        )
        try:
            with (
                httpx.Client() as bare,
                bare.stream("GET", download_url) as response,
            ):
                if response.status_code >= 400:
                    raise GPPResponseError(
                        response.status_code, "Presigned download failed."
                    )
                with path.open("wb") as handle:
                    for chunk in response.iter_bytes(chunk_size):
                        handle.write(chunk)
        except httpx.HTTPError as exc:
            raise map_transport_error(exc, download_url) from exc
        logger.info("Downloaded %s", path)
        return path


class AsyncAttachmentAPI(AsyncAttachmentOperations):
    """
    Attachment operations (async): generated metadata queries plus REST
    transfer.
    """

    def __init__(self, executor: AsyncExecutor, http: httpx.AsyncClient) -> None:
        super().__init__(executor)
        self._http = http

    async def upload(
        self,
        program_id: str,
        *,
        attachment_type: AttachmentType | str,
        file_name: str,
        description: str | None = None,
        file_path: str | Path | None = None,
        content: bytes | None = None,
    ) -> str:
        """
        Upload a new attachment for a program and return its ID.

        Parameters
        ----------
        program_id : str
            The program to attach to.
        attachment_type : AttachmentType | str
            The attachment type.
        file_name : str
            File name to store.
        description : str | None, optional
            Optional description.
        file_path : str | Path | None, optional
            Path whose contents are uploaded. Exclusive with ``content``.
        content : bytes | None, optional
            Raw bytes to upload. Exclusive with ``file_path``.
        """
        _check_writable(self._executor, "upload an attachment")
        body = _resolve_content(file_path, content)
        params = _upload_params(
            program_id=program_id,
            attachment_type=attachment_type,
            file_name=file_name,
            description=description,
        )
        try:
            response = await self._http.post(
                _ATTACHMENT_PATH, params=params, content=body
            )
        except httpx.HTTPError as exc:
            raise map_transport_error(exc, str(self._http.base_url)) from exc
        attachment_id = process_text(response).strip()
        if not attachment_id:
            raise GPPResponseError(
                response.status_code, "Upload returned an empty attachment id."
            )
        return attachment_id

    async def update_by_id(
        self,
        attachment_id: str,
        *,
        file_name: str,
        description: str | None = None,
        file_path: str | Path | None = None,
        content: bytes | None = None,
    ) -> None:
        """
        Replace an attachment's content and metadata by ID.

        Parameters
        ----------
        attachment_id : str
            The attachment to update.
        file_name : str
            New file name (required by the endpoint).
        description : str | None, optional
            New description.
        file_path : str | Path | None, optional
            Path whose contents replace the attachment. Exclusive with
            ``content``.
        content : bytes | None, optional
            Raw replacement bytes. Exclusive with ``file_path``.
        """
        _check_writable(self._executor, "update an attachment")
        body = _resolve_content(file_path, content)
        params = _update_params(file_name=file_name, description=description)
        try:
            response = await self._http.put(
                f"{_ATTACHMENT_PATH}/{attachment_id}", params=params, content=body
            )
        except httpx.HTTPError as exc:
            raise map_transport_error(exc, str(self._http.base_url)) from exc
        process_text(response)

    async def delete_by_id(self, attachment_id: str) -> None:
        """
        Delete an attachment by ID.

        Parameters
        ----------
        attachment_id : str
            The attachment to delete.
        """
        _check_writable(self._executor, "delete an attachment")
        try:
            response = await self._http.delete(f"{_ATTACHMENT_PATH}/{attachment_id}")
        except httpx.HTTPError as exc:
            raise map_transport_error(exc, str(self._http.base_url)) from exc
        process_text(response)

    async def get_download_url_by_id(self, attachment_id: str) -> str:
        """
        Get the presigned download URL for an attachment.

        Parameters
        ----------
        attachment_id : str
            The attachment ID.
        """
        try:
            response = await self._http.get(f"{_ATTACHMENT_PATH}/url/{attachment_id}")
        except httpx.HTTPError as exc:
            raise map_transport_error(exc, str(self._http.base_url)) from exc
        return process_text(response).strip()

    async def download_by_id(
        self,
        attachment_id: str,
        save_to: str | Path | None = None,
        *,
        overwrite: bool = False,
        chunk_size: int = 1024 * 1024,
    ) -> Path:
        """
        Download an attachment to disk and return the file path.

        Parameters
        ----------
        attachment_id : str
            The attachment ID.
        save_to : str | Path | None, optional
            Destination directory; defaults to the home directory.
        overwrite : bool, default=False
            Whether to replace an existing file.
        chunk_size : int, default=1 MiB
            Streaming chunk size in bytes.
        """
        download_url = await self.get_download_url_by_id(attachment_id)
        path = _resolve_destination(
            save_to, _filename_from_presigned_url(download_url), overwrite
        )
        try:
            async with (
                httpx.AsyncClient() as bare,
                bare.stream("GET", download_url) as response,
            ):
                if response.status_code >= 400:
                    raise GPPResponseError(
                        response.status_code, "Presigned download failed."
                    )
                with path.open("wb") as handle:
                    async for chunk in response.aiter_bytes(chunk_size):
                        handle.write(chunk)
        except httpx.HTTPError as exc:
            raise map_transport_error(exc, download_url) from exc
        logger.info("Downloaded %s", path)
        return path
