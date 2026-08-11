"""
The GPP client entry points.

``GPPClient`` is synchronous; ``AsyncGPPClient`` is its async twin with an
identical surface. Both subclass the gqlforge-generated vendored client
(:mod:`gpp_client2._generated.client`) and specialize it for GPP: runtime
configuration resolution (see :mod:`gpp_client2.config`), the ``/odb``
GraphQL path and ``/ws`` WebSocket path conventions, curated domain APIs,
and a restricted-field preflight for raw queries.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from gpp_client2._executor import ExecutorCore
from gpp_client2._generated.client import AsyncClient, Client
from gpp_client2._generated.operations import RESTRICTED_FIELD_NAMES
from gpp_client2.config import ResolvedConfig, resolve_config
from gpp_client2.domains import (
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
from gpp_client2.environments import Environment
from gpp_client2.errors import GPPFieldUnavailableError

__all__ = ["AsyncGPPClient", "GPPClient"]

_DEFAULT_TIMEOUT = 30.0
_GRAPHQL_PATH = "/odb"
_WS_PATH = "/ws"
_PING_QUERY = "query Ping { programs(LIMIT: 1) { matches { id } } }"


def _ws_url(base_url: str) -> str:
    """WebSocket endpoint for a deployment base URL, e.g. ``wss://host/ws``."""
    parsed = urlsplit(base_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return urlunsplit((scheme, parsed.netloc, _WS_PATH, "", ""))


class GPPExecutorCore(ExecutorCore):
    """
    The vendored executor core plus GPP's raw-query field preflight.

    Field names whose availability codegen restricted to some schema
    sources are rejected before any network call when the active source
    does not serve them.
    """

    def raw_payload(
        self,
        query: str,
        variables: dict[str, Any] | None,
        operation_name: str | None,
    ) -> dict[str, Any]:
        payload = super().raw_payload(query, variables, operation_name)
        try:
            from graphql.language.visitor import Visitor

            from graphql import FieldNode, parse, visit

            document = parse(query)
        except Exception:
            return payload  # let the server report the syntax error

        source = self.source
        violations: list[tuple[str, tuple[str, ...]]] = []

        class _RestrictedFieldVisitor(Visitor):
            def enter_field(self, node: FieldNode, *args: Any) -> None:
                availability = RESTRICTED_FIELD_NAMES.get(node.name.value)
                if availability is not None and source not in availability:
                    violations.append((node.name.value, availability))

        visit(document, _RestrictedFieldVisitor())
        if violations:
            field_name, availability = violations[0]
            raise GPPFieldUnavailableError(field_name, source, availability)
        return payload


class _ClientBase:
    """Configuration resolution and metadata shared by both clients."""

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
        from gpp_client2._generated.operations import SCHEMA_SOURCES

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

    def _rest_kwargs(
        self,
        timeout: float,
        transport: httpx.BaseTransport | httpx.AsyncBaseTransport | None,
    ) -> dict[str, Any]:
        """httpx arguments for the REST client rooted at the deployment."""
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
        from gpp_client2._generated.operations import (
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


class GPPClient(_ClientBase, Client):
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

    executor_core_class = GPPExecutorCore

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
        base_url = self._config.base_url.rstrip("/")
        # REST endpoints (attachments, scheduler files) live at the
        # deployment root, not under the GraphQL path.
        self._rest_http = httpx.Client(**self._rest_kwargs(timeout, transport))
        super().__init__(
            base_url + _GRAPHQL_PATH,
            token=self._config.token,
            source=self._config.schema_source,
            read_only=read_only,
            timeout=timeout,
            transport=transport,
            ws_url=_ws_url(base_url),
        )

    def _wire_domains(self) -> None:
        self.programs = ProgramAPI(self._executor)
        self.observations = ObservationAPI(self._executor)
        self.targets = TargetAPI(self._executor)
        self.attachments = AttachmentAPI(self._executor, self._rest_http)
        self.calls_for_proposals = CallForProposalsAPI(self._executor)
        self.goats = GoatsAPI(self._executor)
        self.scheduler = SchedulerAPI(self._executor, self._rest_http)
        self.workflow_state = WorkflowStateAPI(self._executor)

    def graphql(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
        operation_name: str | None = None,
    ) -> Any:
        """
        Execute a raw GraphQL operation and return the ``data`` dict.

        The escape hatch for queries the client does not ship. Nothing
        validates the text beyond a cheap availability pre-flight; the
        server is the judge.
        """
        return super().graphql(query, variables, operation_name)

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
        super().close()
        self._rest_http.close()


class AsyncGPPClient(_ClientBase, AsyncClient):
    """
    Asynchronous client for the Gemini Program Platform.

    Accepts the same parameters as :class:`GPPClient`; every operation is a
    coroutine.

    Examples
    --------
    >>> async with AsyncGPPClient(environment="development") as gpp:
    ...     program = await gpp.programs.get_by_id("p-123")
    """

    executor_core_class = GPPExecutorCore

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
        base_url = self._config.base_url.rstrip("/")
        # REST endpoints (attachments, scheduler files) live at the
        # deployment root, not under the GraphQL path.
        self._rest_http = httpx.AsyncClient(**self._rest_kwargs(timeout, transport))
        super().__init__(
            base_url + _GRAPHQL_PATH,
            token=self._config.token,
            source=self._config.schema_source,
            read_only=read_only,
            timeout=timeout,
            transport=transport,
            ws_url=_ws_url(base_url),
        )

    def _wire_domains(self) -> None:
        self.programs = AsyncProgramAPI(self._executor)
        self.observations = AsyncObservationAPI(self._executor)
        self.targets = AsyncTargetAPI(self._executor)
        self.attachments = AsyncAttachmentAPI(self._executor, self._rest_http)
        self.calls_for_proposals = AsyncCallForProposalsAPI(self._executor)
        self.goats = AsyncGoatsAPI(self._executor)
        self.scheduler = AsyncSchedulerAPI(self._executor, self._rest_http)
        self.workflow_state = AsyncWorkflowStateAPI(self._executor)

    async def graphql(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
        operation_name: str | None = None,
    ) -> Any:
        """
        Execute a raw GraphQL operation and return the ``data`` dict.

        The escape hatch for queries the client does not ship. Nothing
        validates the text beyond a cheap availability pre-flight; the
        server is the judge.
        """
        return await super().graphql(query, variables, operation_name)

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

    async def aclose(self) -> None:
        """Close the underlying HTTP connections."""
        await super().aclose()
        await self._rest_http.aclose()

    async def close(self) -> None:
        """Alias of :meth:`aclose`, keeping the sync and async surfaces
        identical."""
        await self.aclose()
