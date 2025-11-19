"""Bot agent implementation with Teams SSO and Azure OpenAI integration."""

from __future__ import annotations

import logging
import os
from collections import defaultdict
from dataclasses import dataclass
from http import HTTPStatus
from typing import Any, Optional

import jwt
from openai import AsyncAzureOpenAI

from microsoft_agents.activity import (
	ActionTypes,
	Activity,
	ActivityTypes,
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
	azure_openai_endpoint: str
	azure_openai_api_key: str
	azure_openai_api_version: str
	azure_openai_deployment_name: str
	allowed_tenants: list[str]


class TeamsSsoAgent(ActivityHandler):
	"""Activity handler that implements Teams SSO best practices with Azure OpenAI integration."""

	def __init__(self, settings: AgentSettings):
		super().__init__()
		self._settings = settings
		
		# Initialize Azure OpenAI client
		self._openai_client = AsyncAzureOpenAI(
			api_version=settings.azure_openai_api_version,
			azure_endpoint=settings.azure_openai_endpoint,
			api_key=settings.azure_openai_api_key
		)
		
		# Conversation history storage: {conversation_id: [{"role": "user", "content": "..."}]}
		# Note: This is in-memory storage. For production, consider Azure CosmosDB or Redis
		self._conversation_history: dict[str, list[dict[str, str]]] = defaultdict(list)
		self._max_history_messages = 20  # Keep last 20 messages (10 exchanges)
		
		logger.info("TeamsSsoAgent initialized with Azure OpenAI support and conversation memory")

	async def on_message_activity(self, turn_context: TurnContext) -> None:
		"""Handle incoming messages with authentication and Azure OpenAI processing."""
		
		# Multi-tenant validation (if configured)
		if not await self._validate_tenant(turn_context):
			return
		
		# Get user token for authentication
		token_response = await self._get_user_token(turn_context)
		if token_response and token_response.token:
			# Check for special commands
			user_message = turn_context.activity.text.strip().lower()
			conversation_id = turn_context.activity.conversation.id
			
			if user_message in ["/reset", "/clear", "/new"]:
				# Clear conversation history
				if conversation_id in self._conversation_history:
					self._conversation_history[conversation_id].clear()
					logger.info(f"Cleared conversation history for {conversation_id}")
				
				await turn_context.send_activity(
					"🔄 Conversation history cleared! Starting fresh. How can I help you?"
				)
				return
			
			# User is authenticated - process message with Azure OpenAI
			await self._process_message_with_openai(turn_context, token_response)
			return

		# User not authenticated - send sign-in card
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

	async def _validate_tenant(self, turn_context: TurnContext) -> bool:
		"""Validate that the request comes from an allowed tenant."""
		if not self._settings.allowed_tenants:
			# No tenant restrictions configured
			return True
		
		# Get tenant ID from conversation (available in Teams)
		user_tenant_id = getattr(turn_context.activity.conversation, "tenant_id", None)
		
		if user_tenant_id and user_tenant_id not in self._settings.allowed_tenants:
			logger.warning(
				f"Unauthorized tenant access attempt: {user_tenant_id}. "
				f"Allowed tenants: {self._settings.allowed_tenants}"
			)
			await turn_context.send_activity(
				"I'm sorry, but your organization is not authorized to use this bot. "
				"Please contact your administrator for access."
			)
			return False
		
		if user_tenant_id:
			logger.info(f"Tenant {user_tenant_id} authorized successfully")
		
		return True

	async def _process_message_with_openai(
		self, turn_context: TurnContext, token_response: TokenResponse
	) -> None:
		"""Process user message with Azure OpenAI using streaming response."""
		user_message = turn_context.activity.text
		conversation_id = turn_context.activity.conversation.id
		
		# Decode JWT to get user info
		claims = self._decode_jwt(token_response.token)
		display_name = claims.get("name") or claims.get("preferred_username") or "User"
		
		logger.info(f"Processing message from {display_name} ({conversation_id}): {user_message[:50]}...")
		
		# Enable streaming response for better UX
		turn_context.streaming_response.set_feedback_loop(True)
		turn_context.streaming_response.set_generated_by_ai_label(True)
		
		try:
			# Get or initialize conversation history
			history = self._conversation_history[conversation_id]
			
			# Add current user message to history
			history.append({"role": "user", "content": user_message})
			
			# Build messages for API call (system message + history)
			messages = [
				{
					"role": "system",
					"content": f"You are a helpful AI assistant in Microsoft Teams. The user's name is {display_name}. "
							   "Respond naturally and helpfully to user queries. Maintain context from previous messages."
				}
			]
			messages.extend(history)
			
			logger.info(f"Conversation {conversation_id}: {len(history)} messages in history")
			
			# Call Azure OpenAI with streaming enabled
			streamed_response = await self._openai_client.chat.completions.create(
				model=self._settings.azure_openai_deployment_name,
				messages=messages,
				stream=True,
			)
			
			# Collect assistant response while streaming
			assistant_response = ""
			async for chunk in streamed_response:
				if chunk.choices and chunk.choices[0].delta.content:
					content = chunk.choices[0].delta.content
					assistant_response += content
					turn_context.streaming_response.queue_text_chunk(content)
			
			# Add assistant response to history
			history.append({"role": "assistant", "content": assistant_response})
			
			# Trim history if it gets too long (keep last N messages)
			if len(history) > self._max_history_messages:
				history[:] = history[-self._max_history_messages:]
				logger.info(f"Trimmed conversation history to {self._max_history_messages} messages")
			
			logger.info(f"Successfully sent streaming response to {conversation_id}")
			
		except Exception as e:
			logger.error(f"Error during Azure OpenAI streaming: {e}", exc_info=True)
			turn_context.streaming_response.queue_text_chunk(
				"An error occurred while processing your message. Please try again later."
			)
		finally:
			# Always end the stream
			await turn_context.streaming_response.end_stream()

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

	async def on_members_added_activity(self, members_added, turn_context: TurnContext) -> None:
		"""Handle new members joining the conversation."""
		for member in members_added:
			if member.id != turn_context.activity.recipient.id:
				await turn_context.send_activity(
					"👋 Welcome! I'm your AI assistant powered by Azure OpenAI.\n\n"
					"**Features:**\n"
					"✅ Conversational memory - I remember our chat history\n"
					"✅ Teams SSO authentication\n"
					"✅ Streaming responses for better experience\n\n"
					"**Commands:**\n"
					"• `/reset` or `/clear` - Start a new conversation\n\n"
					"Ask me anything to get started!"
				)

	@staticmethod
	def _decode_jwt(raw_token: str) -> dict[str, Any]:
		"""Decode JWT token without signature verification (for reading claims only)."""
		try:
			return jwt.decode(
				raw_token,
				options={"verify_signature": False, "verify_aud": False},
			)
		except jwt.PyJWTError:
			return {}

