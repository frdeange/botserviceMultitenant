"""Entrypoint to bootstrap the aiohttp bot server with Teams SSO and Azure OpenAI."""

from __future__ import annotations

import logging
import os

from aiohttp import web
from dotenv import load_dotenv

from server import BotSettings, create_app


def _load_env_file() -> None:
	"""Load environment variables from .env file."""
	load_dotenv(override=True)


def _env(*names: str, default: str | None = None) -> str | None:
	"""Get environment variable from multiple possible names."""
	for name in names:
		value = os.getenv(name)
		if value:
			return value.strip()
	return default


def build_settings() -> BotSettings:
	"""Build bot settings from environment variables."""
	port = int(os.getenv("PORT", "8000"))
	
	# Bot Framework Identity Configuration
	app_id = _env("BOTSERVICE_APP_ID", "MicrosoftAppId")
	if not app_id:
		raise RuntimeError("MicrosoftAppId is not defined. Please set it in your .env file.")

	app_type = os.getenv("MicrosoftAppType", "MultiTenant")
	client_secret = _env("BOTSERVICE_APP_SECRET", "BOT_SERVICE_CLIENT_SECRET", "MicrosoftAppPassword")
	tenant_id = _env("BOTSERVICE_TENANT_ID", "MicrosoftAppTenantId", "TENANT_ID")
	
	# OAuth Connection Configuration
	connection_name = _env("OAUTH_CONNECTION_NAME", "AZUREBOTOAUTHCONNECTIONNAME")
	if not connection_name:
		raise RuntimeError("OAUTH_CONNECTION_NAME is not defined. Please set it in your .env file.")

	# Public URL Configuration
	public_base_url = _env("PUBLIC_BASE_URL")
	if not public_base_url:
		public_base_url = f"http://localhost:{port}/api/messages"
		logging.warning(
			"PUBLIC_BASE_URL is not set. Using %s for development only.",
			public_base_url,
		)
	
	# Ensure PUBLIC_BASE_URL starts with https:// (except for localhost)
	if not public_base_url.startswith(("http://", "https://")):
		public_base_url = f"https://{public_base_url}"
		logging.info(f"Added https:// prefix to PUBLIC_BASE_URL: {public_base_url}")
	
	# Azure AI Foundry Agent Service configuration
	foundry_project_endpoint = os.getenv("AZURE_FOUNDRY_PROJECT_ENDPOINT")
	foundry_agent_name = os.getenv("AZURE_FOUNDRY_AGENT_NAME")
	
	if not foundry_project_endpoint:
		raise RuntimeError("AZURE_FOUNDRY_PROJECT_ENDPOINT environment variable is required")

	# Multi-tenant Access Control
	allowed = [tenant.strip() for tenant in os.getenv("ALLOWED_TENANTS", "").split(",") if tenant.strip()]

	return BotSettings(
		app_id=app_id,
		app_type=app_type,
		tenant_id=tenant_id,
		client_secret=client_secret,
		oauth_connection_name=oauth_connection_name,
		public_base_url=public_base_url,
		foundry_project_endpoint=foundry_project_endpoint,
		foundry_agent_name=foundry_agent_name,
		port=port,
		allowed_tenants=allowed_tenants,
	)


def main() -> None:
	"""Main entry point for the bot application."""
	_load_env_file()
	log_level = getattr(logging, os.getenv("LOG_LEVEL", "INFO"), logging.INFO)
	logging.basicConfig(
		level=log_level,
		format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
	)
	
	logger = logging.getLogger(__name__)
	logger.info("Starting Teams SSO Bot with Azure AI Foundry Agent Service integration...")
	
	try:
		settings = build_settings()
		logger.info(f"Bot App ID: {settings.app_id}")
		logger.info(f"App Type: {settings.app_type}")
		logger.info(f"OAuth Connection: {settings.oauth_connection_name}")
		logger.info(f"Public URL: {settings.public_base_url}")
		logger.info(f"AI Foundry Agent: {settings.foundry_agent_name}")
		logger.info(f"AI Foundry Project: {settings.foundry_project_endpoint}")
		if settings.allowed_tenants:
			logger.info(f"Allowed Tenants: {', '.join(settings.allowed_tenants)}")
		else:
			logger.info("Allowed Tenants: ALL (no restrictions)")
		
		app = create_app(settings)
		logger.info(f"Server starting on port {settings.port}...")
		web.run_app(app, port=settings.port)
	except Exception as e:
		logger.error(f"Failed to start bot: {e}", exc_info=True)
		raise


if __name__ == "__main__":
	main()


