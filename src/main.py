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
	
	# Azure OpenAI Configuration
	azure_openai_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
	if not azure_openai_endpoint:
		raise RuntimeError("AZURE_OPENAI_ENDPOINT is not defined. Please set it in your .env file.")
	
	azure_openai_api_key = os.getenv("AZURE_OPENAI_API_KEY")
	if not azure_openai_api_key:
		raise RuntimeError("AZURE_OPENAI_API_KEY is not defined. Please set it in your .env file.")
	
	azure_openai_api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
	azure_openai_deployment_name = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
	if not azure_openai_deployment_name:
		raise RuntimeError("AZURE_OPENAI_DEPLOYMENT_NAME is not defined. Please set it in your .env file.")

	# Multi-tenant Access Control
	allowed = [tenant.strip() for tenant in os.getenv("ALLOWED_TENANTS", "").split(",") if tenant.strip()]

	return BotSettings(
		app_id=app_id,
		app_type=app_type,
		tenant_id=tenant_id,
		client_secret=client_secret,
		oauth_connection_name=connection_name,
		public_base_url=public_base_url,
		azure_openai_endpoint=azure_openai_endpoint,
		azure_openai_api_key=azure_openai_api_key,
		azure_openai_api_version=azure_openai_api_version,
		azure_openai_deployment_name=azure_openai_deployment_name,
		port=port,
		allowed_tenants=allowed,
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
	logger.info("Starting Teams SSO Bot with Azure OpenAI integration...")
	
	try:
		settings = build_settings()
		logger.info(f"Bot App ID: {settings.app_id}")
		logger.info(f"App Type: {settings.app_type}")
		logger.info(f"OAuth Connection: {settings.oauth_connection_name}")
		logger.info(f"Public URL: {settings.public_base_url}")
		logger.info(f"Azure OpenAI Deployment: {settings.azure_openai_deployment_name}")
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


