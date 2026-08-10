"""
The GPP client entry points.

``GPPClient`` is synchronous; ``AsyncGPPClient`` is its async twin with an
identical surface. Which deployment either talks to is a runtime choice
resolved from arguments, ``GPP_*`` environment variables, and configuration
profiles - see :mod:`gpp_client.config`.
"""

from __future__ import annotations

from pathlib import Path
from types import TracebackType
from typing import Any, Self

import httpx

from gpp_client._executor import AsyncExecutor, ExecutorCore, SyncExecutor
from gpp_client._ws import AsyncWsTransport, SyncWsTransport, WsConfig, get_ws_url
from gpp_client.config import ResolvedConfig, resolve_config
from gpp_client.domains import (
    AsyncAttachmentAPI,
    AsyncCallForProposalsAPI,
    AsyncGoatsAPI,
    AsyncObservationAPI,
    AsyncProgramAPI,
    AsyncSchedulerAPI,
    AsyncTargetAPI,
    AsyncWorkflowStateAPI,
    AttachmentAPI,
    CallForProposalsAPI,
    GoatsAPI,
    ObservationAPI,
    ProgramAPI,
    SchedulerAPI,
    TargetAPI,
    WorkflowStateAPI,
)
from gpp_client.environments import Environment

__all__ = ["AsyncGPPClient", "GPPClient"]

_DEFAULT_TIMEOUT = 30.0
_PING_QUERY = "query Ping { programs(LIMIT: 1) { matches { id } } }"


class _ClientBase:
    """Configuration and metadata shared by the sync and async clients."""

    _config: ResolvedConfig
    _read_only: bool

    def _resolve(
        self,
        *,
        environment: Environment | str | None,
        profile: str | None,
        url: str | None,
        schema: str | None,
        token: str | None,
        read_only: bool,
        config_path: Path | None,
    ) -> None:
        from gpp_client._generated.operations import SCHEMA_SOURCES

        self._config = resolve_config(
            environment=environment,
            profile=profile,
            url=url,
            schema=schema,
            token=token,
            available_sources=SCHEMA_SOURCES,
            config_path=config_path,
        )
        self._read_only = read_only

    def _core(self) -> ExecutorCore:
        return ExecutorCore(
            environment_name=self._config.environment_name,
            schema_source=self._config.schema_source,
            read_only=self._read_only,
        )

    def _ws_config(self, timeout: float) -> WsConfig:
        return WsConfig(
            url=get_ws_url(self._config.base_url),
            token=self._config.token,
            connect_timeout=timeout,
        )

    def _http_kwargs(
        self,
        timeout: float,
        transport: httpx.BaseTransport | httpx.AsyncBaseTransport | None,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "base_url": self._config.base_url,
            "headers": {"Authorization": f"Bearer {self._config.token}"},
            "timeout": timeout,
        }
        if transport is not None:
            kwargs["transport"] = transport
        return kwargs

    @property
    def environment(self) -> str:
        """Name of the active environment (``"custom"`` for explicit URLs)."""
        return self._config.environment_name

    @property
    def config(self) -> ResolvedConfig:
        """The resolved runtime configuration."""
        return self._config

    @property
    def read_only(self) -> bool:
        """Whether this client refuses to execute mutations."""
        return self._read_only

    def supports(self, name: str) -> bool:
        """
        Report whether an operation or field is available in this environment.

        Parameters
        ----------
        name : str
            A generated operation name (``"getProgramById"``), a domain
            method reference (``"programs.get_by_id"``), or a ``Type.field``
            pair (``"ObservingMode.gnirsImaging"``).

        Returns
        -------
        bool
            ``True`` if available in the active environment. Names codegen
            never restricted return ``True``.
        """
        from gpp_client._generated.operations import (
            FIELD_AVAILABILITY,
            OPERATION_TEXT,
        )

        source = self._config.schema_source
        availability = FIELD_AVAILABILITY.get(name)
        if availability is not None:
            return source in availability
        if "." in name:
            normalized = name.split(".")[-1].replace("_", "").lower()
        else:
            normalized = name.replace("_", "").lower()
        for operation_name, texts in OPERATION_TEXT.items():
            if operation_name.replace("_", "").lower() == normalized:
                return source in texts
        return True

    def __repr__(self) -> str:
        return (
            f"<{type(self).__name__} environment={self.environment!r} "
            f"url={self._config.base_url!r} "
            f"schema_source={self._config.schema_source!r} "
            f"read_only={self._read_only}>"
        )


class GPPClient(_ClientBase):
    """
    Synchronous client for the Gemini Program Platform.

    Parameters
    ----------
    environment : Environment | str, optional
        Target environment (``"development"``, ``"staging"``,
        ``"production"``). Case-insensitive.
    profile : str, optional
        Configuration profile name from the config file.
    url : str, optional
        Explicit base URL, e.g. a local ODB. Overrides the environment URL.
    schema : str, optional
        Schema source whose generated query text to use with a custom
        ``url``. Defaults to the newest committed schema.
    token : str, optional
        GPP API token.
    read_only : bool, default=False
        When ``True``, the client refuses to execute mutations.
        Subscriptions are reads and stay available.
    timeout : float, default=30.0
        Request timeout in seconds; also the WebSocket connect timeout for
        subscriptions.
    transport : httpx.BaseTransport, optional
        Custom HTTP transport, e.g. ``httpx.MockTransport`` in tests.

    Examples
    --------
    >>> with GPPClient(environment="development") as gpp:
    ...     program = gpp.programs.get_by_id("p-123")
    """

    programs: ProgramAPI
    """Program operations."""

    observations: ObservationAPI
    """Observation operations."""

    targets: TargetAPI
    """Target operations."""

    attachments: AttachmentAPI
    """Attachment metadata queries and content transfer."""

    calls_for_proposals: CallForProposalsAPI
    """Call for Proposals operations."""

    goats: GoatsAPI
    """GOATS bulk queries."""

    scheduler: SchedulerAPI
    """Scheduler queries, file endpoints, and the assembled program tree."""

    workflow_state: WorkflowStateAPI
    """Observation workflow state operations."""

    def __init__(
        self,
        *,
        environment: Environment | str | None = None,
        profile: str | None = None,
        url: str | None = None,
        schema: str | None = None,
        token: str | None = None,
        read_only: bool = False,
        timeout: float = _DEFAULT_TIMEOUT,
        transport: httpx.BaseTransport | None = None,
        config_path: Path | None = None,
    ) -> None:
        self._resolve(
            environment=environment,
            profile=profile,
            url=url,
            schema=schema,
            token=token,
            read_only=read_only,
            config_path=config_path,
        )
        self._http = httpx.Client(**self._http_kwargs(timeout, transport))
        core = self._core()
        self._executor = SyncExecutor(
            self._http, core, ws=SyncWsTransport(self._ws_config(timeout), core)
        )
        self.programs = ProgramAPI(self._executor)
        self.observations = ObservationAPI(self._executor)
        self.targets = TargetAPI(self._executor)
        self.attachments = AttachmentAPI(self._executor, self._http)
        self.calls_for_proposals = CallForProposalsAPI(self._executor)
        self.goats = GoatsAPI(self._executor)
        self.scheduler = SchedulerAPI(self._executor, self._http)
        self.workflow_state = WorkflowStateAPI(self._executor)

    def graphql(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
        *,
        operation_name: str | None = None,
    ) -> Any:
        """
        Execute a raw GraphQL operation and return the ``data`` dict.

        The escape hatch for queries the client does not ship. Nothing
        validates the text beyond a cheap availability pre-flight; the
        server is the judge.
        """
        return self._executor.run_raw(query, variables, operation_name)

    def ping(self) -> tuple[bool, str | None]:
        """
        Check that the deployment is reachable and the token works.

        Returns
        -------
        tuple[bool, str | None]
            ``(True, None)`` on success, else ``(False, reason)``.
        """
        try:
            self._executor.run_raw(_PING_QUERY, operation_name="Ping")
        except Exception as exc:
            return False, str(exc)
        return True, None

    def close(self) -> None:
        """Close the underlying HTTP connections."""
        self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()


class AsyncGPPClient(_ClientBase):
    """
    Asynchronous client for the Gemini Program Platform.

    Accepts the same parameters as :class:`GPPClient`; every operation is a
    coroutine.

    Examples
    --------
    >>> async with AsyncGPPClient(environment="development") as gpp:
    ...     program = await gpp.programs.get_by_id("p-123")
    """

    programs: AsyncProgramAPI
    """Program operations."""

    observations: AsyncObservationAPI
    """Observation operations."""

    targets: AsyncTargetAPI
    """Target operations."""

    attachments: AsyncAttachmentAPI
    """Attachment metadata queries and content transfer."""

    calls_for_proposals: AsyncCallForProposalsAPI
    """Call for Proposals operations."""

    goats: AsyncGoatsAPI
    """GOATS bulk queries."""

    scheduler: AsyncSchedulerAPI
    """Scheduler queries, file endpoints, and the assembled program tree."""

    workflow_state: AsyncWorkflowStateAPI
    """Observation workflow state operations."""

    def __init__(
        self,
        *,
        environment: Environment | str | None = None,
        profile: str | None = None,
        url: str | None = None,
        schema: str | None = None,
        token: str | None = None,
        read_only: bool = False,
        timeout: float = _DEFAULT_TIMEOUT,
        transport: httpx.AsyncBaseTransport | None = None,
        config_path: Path | None = None,
    ) -> None:
        self._resolve(
            environment=environment,
            profile=profile,
            url=url,
            schema=schema,
            token=token,
            read_only=read_only,
            config_path=config_path,
        )
        self._http = httpx.AsyncClient(**self._http_kwargs(timeout, transport))
        core = self._core()
        self._executor = AsyncExecutor(
            self._http, core, ws=AsyncWsTransport(self._ws_config(timeout), core)
        )
        self.programs = AsyncProgramAPI(self._executor)
        self.observations = AsyncObservationAPI(self._executor)
        self.targets = AsyncTargetAPI(self._executor)
        self.attachments = AsyncAttachmentAPI(self._executor, self._http)
        self.calls_for_proposals = AsyncCallForProposalsAPI(self._executor)
        self.goats = AsyncGoatsAPI(self._executor)
        self.scheduler = AsyncSchedulerAPI(self._executor, self._http)
        self.workflow_state = AsyncWorkflowStateAPI(self._executor)

    async def graphql(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
        *,
        operation_name: str | None = None,
    ) -> Any:
        """
        Execute a raw GraphQL operation and return the ``data`` dict.

        The escape hatch for queries the client does not ship. Nothing
        validates the text beyond a cheap availability pre-flight; the
        server is the judge.
        """
        return await self._executor.run_raw(query, variables, operation_name)

    async def ping(self) -> tuple[bool, str | None]:
        """
        Check that the deployment is reachable and the token works.

        Returns
        -------
        tuple[bool, str | None]
            ``(True, None)`` on success, else ``(False, reason)``.
        """
        try:
            await self._executor.run_raw(_PING_QUERY, operation_name="Ping")
        except Exception as exc:
            return False, str(exc)
        return True, None

    async def close(self) -> None:
        """Close the underlying HTTP connections."""
        await self._http.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()
