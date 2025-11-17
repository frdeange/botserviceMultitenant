"""HTTP server wiring for the Teams SSO bot with Azure OpenAI."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List

from aiohttp import web
from microsoft_agents.hosting.aiohttp import CloudAdapter, jwt_authorization_middleware
from microsoft_agents.hosting.core.authorization.agent_auth_configuration import (
	AgentAuthConfiguration,
)
from microsoft_agents.hosting.core.authorization.auth_types import AuthTypes
from microsoft_agents.hosting.core.authorization.connections import Connections
from microsoft_agents.authentication.msal.msal_connection_manager import (
	MsalConnectionManager,
)

from agent import AgentSettings, TeamsSsoAgent


@dataclass(slots=True)
class BotSettings:
	"""Container with the configuration necessary to run the bot server."""

	app_id: str
	app_type: str
	tenant_id: str | None
	client_secret: str | None
	oauth_connection_name: str
	public_base_url: str
	azure_openai_endpoint: str
	azure_openai_api_key: str
	azure_openai_api_version: str
	azure_openai_deployment_name: str
	port: int = 8000
	allowed_tenants: List[str] = field(default_factory=list)

	def auth_type(self) -> AuthTypes:
		"""Determine authentication type from app_type string."""
		type_name = (self.app_type or "").lower()
		if type_name in {"userassignedmsi", "user-assigned"}:
			return AuthTypes.user_managed_identity
		if type_name in {"systemassignedmsi", "system-assigned"}:
			return AuthTypes.system_managed_identity
		return AuthTypes.client_secret


def _build_service_connection(settings: BotSettings) -> AgentAuthConfiguration:
	return AgentAuthConfiguration(
		auth_type=settings.auth_type(),
		client_id=settings.app_id,
		tenant_id=settings.tenant_id,
		client_secret=settings.client_secret,
		connection_name="SERVICE_CONNECTION",
	)


def _build_connection_manager(settings: BotSettings) -> Connections:
	"""Build MSAL connection manager with proper configuration for Managed Identity."""
	service_connection = _build_service_connection(settings)
	
	# Build connection configuration dictionary with correct parameter names
	connection_config = {
		"SETTINGS": {
			"auth_type": service_connection.AUTH_TYPE,
			"client_id": service_connection.CLIENT_ID,
			"tenant_id": service_connection.TENANT_ID,
			"scopes": ["https://api.botframework.com/.default"],
		}
	}
	
	# Add client_secret only if not using Managed Identity
	if service_connection.AUTH_TYPE == AuthTypes.client_secret:
		connection_config["SETTINGS"]["client_secret"] = service_connection.CLIENT_SECRET
	
	return MsalConnectionManager(
		CONNECTIONS={"SERVICE_CONNECTION": connection_config}
	)


def _build_adapter(connection_manager: Connections) -> CloudAdapter:
	return CloudAdapter(connection_manager=connection_manager)


def _build_agent(settings: BotSettings) -> TeamsSsoAgent:
	"""Build the Teams SSO agent with all required settings."""
	return TeamsSsoAgent(
		AgentSettings(
			bot_app_id=settings.app_id,
			oauth_connection_name=settings.oauth_connection_name,
			public_base_url=settings.public_base_url,
			azure_openai_endpoint=settings.azure_openai_endpoint,
			azure_openai_api_key=settings.azure_openai_api_key,
			azure_openai_api_version=settings.azure_openai_api_version,
			azure_openai_deployment_name=settings.azure_openai_deployment_name,
			allowed_tenants=settings.allowed_tenants,
		)
	)


async def _messages(request: web.Request) -> web.StreamResponse:
	adapter: CloudAdapter = request.app["adapter"]
	agent: TeamsSsoAgent = request.app["agent"]
	return await adapter.process(request, agent)


async def _health(_: web.Request) -> web.Response:
	return web.json_response({"status": "ok"})


def create_app(settings: BotSettings) -> web.Application:
	"""Create an aiohttp application for the Teams bot."""
	connection_manager = _build_connection_manager(settings)
	adapter = _build_adapter(connection_manager)
	agent = _build_agent(settings)
	service_connection = _build_service_connection(settings)

	app = web.Application(middlewares=[jwt_authorization_middleware])
	app["adapter"] = adapter
	app["agent"] = agent
	app["agent_configuration"] = service_connection
	app["settings"] = settings

	app.router.add_post("/api/messages", _messages)
	app.router.add_get("/health", _health)

	return app

