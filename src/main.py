"""Entrypoint used to bootstrap the aiohttp bot server."""

from __future__ import annotations

import logging
import os

from aiohttp import web
from dotenv import load_dotenv

from server import BotSettings, create_app


def _load_env_file() -> None:
	load_dotenv(override=True)


def _env(*names: str, default: str | None = None) -> str | None:
	for name in names:
		value = os.getenv(name)
		if value:
			return value.strip()
	return default


def build_settings() -> BotSettings:
	port = int(os.getenv("PORT", "8000"))
	app_id = _env("BOTSERVICE_APP_ID", "MicrosoftAppId")
	if not app_id:
		raise RuntimeError("MicrosoftAppId is not defined")

	app_type = os.getenv("MicrosoftAppType", "MultiTenant")
	client_secret = _env("BOTSERVICE_APP_SECRET", "BOT_SERVICE_CLIENT_SECRET", "MicrosoftAppPassword")
	tenant_id = _env("BOTSERVICE_TENANT_ID", "MicrosoftAppTenantId", "TENANT_ID")
	connection_name = _env("OAUTH_CONNECTION_NAME", "AZUREBOTOAUTHCONNECTIONNAME")
	if not connection_name:
		raise RuntimeError("OAUTH_CONNECTION_NAME is not defined")

	public_base_url = _env("PUBLIC_BASE_URL")
	if not public_base_url:
		public_base_url = f"http://localhost:{port}/api/messages"
		logging.warning(
			"PUBLIC_BASE_URL is not set. Using %s for development only.",
			public_base_url,
		)

	allowed = [tenant.strip() for tenant in os.getenv("ALLOWED_TENANTS", "").split(",") if tenant.strip()]

	return BotSettings(
		app_id=app_id,
		app_type=app_type,
		tenant_id=tenant_id,
		client_secret=client_secret,
		oauth_connection_name=connection_name,
		public_base_url=public_base_url,
		port=port,
		allowed_tenants=allowed,
	)


def main() -> None:
	_load_env_file()
	log_level = getattr(logging, os.getenv("LOG_LEVEL", "INFO"), logging.INFO)
	logging.basicConfig(level=log_level)
	settings = build_settings()
	app = create_app(settings)
	web.run_app(app, port=settings.port)


if __name__ == "__main__":
	main()

