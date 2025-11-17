"""Bot agent implementation with Teams SSO helpers."""

from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass
from http import HTTPStatus
from typing import Any, Optional

import jwt
from microsoft_agents.activity import (
	ActionTypes,
	Activity,
	CardAction,
	OAuthCard,
	SignInConstants,
	TokenExchangeInvokeRequest,
	TokenExchangeInvokeResponse,
	TokenResponse,
)
from microsoft_agents.activity.token_exchange_state import TokenExchangeState
from microsoft_agents.hosting.core.activity_handler import (
	ActivityHandler,
	_InvokeResponseException,
)
from microsoft_agents.hosting.core.card_factory import CardFactory
from microsoft_agents.hosting.core.channel_adapter import ChannelAdapter
from microsoft_agents.hosting.core.message_factory import MessageFactory
from microsoft_agents.hosting.core.turn_context import TurnContext


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AgentSettings:
	"""Runtime settings injected into the agent."""

	bot_app_id: str
	oauth_connection_name: str
	public_base_url: str


class TeamsSsoAgent(ActivityHandler):
	"""Activity handler that implements Teams SSO best practices."""

	def __init__(self, settings: AgentSettings):
		super().__init__()
		self._settings = settings

	async def on_message_activity(self, turn_context: TurnContext) -> None:
		token_response = await self._get_user_token(turn_context)
		if token_response and token_response.token:
			await self._reply_with_profile(turn_context, token_response)
			return

		await self._send_sign_in_card(turn_context)

	async def on_sign_in_invoke(self, turn_context: TurnContext):
		activity = turn_context.activity
		if activity.name == SignInConstants.token_exchange_operation_name:
			exchange_result = await self._handle_token_exchange(turn_context)
			if exchange_result:
				response = TokenExchangeInvokeResponse(
					id=exchange_result["id"],
					connection_name=exchange_result["connectionName"],
				)
				return self._create_invoke_response(response)

			raise _InvokeResponseException(HTTPStatus.PRECONDITION_FAILED)

		if activity.name == SignInConstants.verify_state_operation_name:
			magic_code = (activity.value or {}).get("state")
			token_response = await self._get_user_token(turn_context, magic_code)
			if token_response and token_response.token:
				return self._create_invoke_response()
			raise _InvokeResponseException(HTTPStatus.BAD_REQUEST)

		return await super().on_sign_in_invoke(turn_context)

	async def _reply_with_profile(
		self, turn_context: TurnContext, token_response: TokenResponse
	) -> None:
		claims = self._decode_jwt(token_response.token)
		display_name = claims.get("name") or claims.get("preferred_username")
		tenant = claims.get("tid")
		lines = [
			"✅ Authentication completed via Teams SSO.",
			f"User: {display_name or 'unknown'}",
		]
		if tenant:
			lines.append(f"Tenant: {tenant}")
		lines.append("You can request protected resources with this signed-in session.")
		await turn_context.send_activity("\n".join(lines))

	async def _send_sign_in_card(self, turn_context: TurnContext) -> None:
		logger.info("No cached token found, sending OAuth card to Teams client.")
		state = TokenExchangeState(
			connection_name=self._settings.oauth_connection_name,
			conversation=turn_context.activity.get_conversation_reference(),
			relates_to=turn_context.activity.relates_to,
			agent_url=self._settings.public_base_url,
			ms_app_id=self._settings.bot_app_id,
		).get_encoded_state()

		user_token_client = self._get_user_token_client(turn_context)
		sign_in_resource = await user_token_client.agent_sign_in.get_sign_in_resource(
			state=state
		)

		oauth_card = OAuthCard(
			text="Sign in to continue",
			connection_name=self._settings.oauth_connection_name,
			buttons=[
				CardAction(
					title="Sign in",
					type=ActionTypes.signin,
					value=sign_in_resource.sign_in_link,
				)
			],
			token_exchange_resource=sign_in_resource.token_exchange_resource,
			token_post_resource=sign_in_resource.token_post_resource,
		)

		await turn_context.send_activity(
			MessageFactory.attachment(CardFactory.oauth_card(oauth_card))
		)

	async def _get_user_token(
		self, turn_context: TurnContext, magic_code: Optional[str] = None
	) -> Optional[TokenResponse]:
		user_token = self._get_user_token_client(turn_context).user_token
		return await user_token.get_token(
			user_id=turn_context.activity.from_property.id,
			connection_name=self._settings.oauth_connection_name,
			channel_id=turn_context.activity.channel_id,
			code=magic_code,
		)

	async def _handle_token_exchange(self, turn_context: TurnContext) -> Optional[dict]:
		request = TokenExchangeInvokeRequest(**turn_context.activity.value)
		user_token_client = self._get_user_token_client(turn_context)
		token_response = await user_token_client.user_token.exchange_token(
			user_id=turn_context.activity.from_property.id,
			connection_name=request.connection_name
			or self._settings.oauth_connection_name,
			channel_id=turn_context.activity.channel_id,
			body=request.model_dump(mode="json", by_alias=True, exclude_none=True),
		)

		if token_response and token_response.token:
			return {
				"id": request.id,
				"connectionName": request.connection_name
				or self._settings.oauth_connection_name,
			}

		return None

	def _get_user_token_client(self, turn_context: TurnContext):
		client = turn_context.turn_state.get(ChannelAdapter.USER_TOKEN_CLIENT_KEY)
		if not client:
			raise ValueError("UserTokenClient not available on TurnContext")
		return client

	@staticmethod
	def _decode_jwt(raw_token: str) -> dict[str, Any]:
		try:
			return jwt.decode(
				raw_token,
				options={"verify_signature": False, "verify_aud": False},
			)
		except jwt.PyJWTError:
			return {}

