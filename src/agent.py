"""Bot agent implementation with Teams SSO and Azure AI Foundry Agent Service integration."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from http import HTTPStatus
from typing import Any, Optional

import jwt
from azure.ai.projects import AIProjectClient
from azure.ai.agents.models import MessageDeltaChunk, ThreadMessage, ThreadRun, RunStep
from azure.ai.agents.models import AgentStreamEvent
from azure.identity import DefaultAzureCredential

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
	# Azure AI Foundry configuration
	foundry_project_endpoint: str
	foundry_agent_name: str
	allowed_tenants: list[str]


class TeamsSsoAgent(ActivityHandler):
	"""Activity handler that implements Teams SSO best practices with Azure OpenAI integration."""

	def __init__(self, settings: AgentSettings):
		super().__init__()
		self._settings = settings
		
		# Initialize Azure AI Foundry Project Client with Managed Identity only
		credential = DefaultAzureCredential()
		
		self._project_client = AIProjectClient(
			endpoint=settings.foundry_project_endpoint,
			credential=credential
		)
		
		# Get the agent from AI Foundry by name
		try:
			self._agent = self._project_client.agents.get(agent_name=settings.foundry_agent_name)
			logger.info(f"Retrieved AI Foundry agent: {self._agent.name} (ID: {self._agent.id})")
		except Exception as e:
			logger.error(f"Failed to retrieve agent '{settings.foundry_agent_name}': {e}")
			raise
		
		# Thread storage: {conversation_id: thread_id}
		# AI Foundry manages conversation history in threads automatically
		self._conversation_threads: dict[str, str] = {}
		
		logger.info(f"TeamsSsoAgent initialized with Azure AI Foundry Agent: {self._agent.name}")

	async def on_message_activity(self, turn_context: TurnContext) -> None:
		"""Handle incoming messages with authentication and Azure AI Foundry Agent processing."""
		
		# Multi-tenant validation (if configured)
		if not await self._validate_tenant(turn_context):
			return
		
		# Get user token for authentication
		token_response = await self._get_user_token(turn_context)
		if token_response and token_response.token:
			# Check for special commands
			user_message = turn_context.activity.text.strip()
			user_message_lower = user_message.lower()
			conversation_id = turn_context.activity.conversation.id
			
			if user_message_lower in ["/reset", "/clear", "/new"]:
				# Delete the AI Foundry thread to start fresh
				if conversation_id in self._conversation_threads:
					thread_id = self._conversation_threads[conversation_id]
					try:
						self._project_client.agents.threads.delete(thread_id)
						del self._conversation_threads[conversation_id]
						logger.info(f"Deleted AI Foundry thread {thread_id} for conversation {conversation_id}")
					except Exception as e:
						logger.warning(f"Failed to delete thread: {e}")
				
				await turn_context.send_activity(
					"🔄 Conversation history cleared! Starting fresh. How can I help you?"
				)
				return
			
			# User is authenticated - process message with Azure AI Foundry Agent
			await self._process_message_with_agent(turn_context, token_response)
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

	async def _process_message_with_agent(
		self, turn_context: TurnContext, token_response: TokenResponse
	) -> None:
		"""Process user message with Azure AI Foundry Agent using streaming response."""
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
			# Get or create thread for this conversation
			if conversation_id not in self._conversation_threads:
				# Create new thread in AI Foundry
				thread = self._project_client.agents.create_thread()
				self._conversation_threads[conversation_id] = thread.id
				logger.info(f"Created new AI Foundry thread {thread.id} for conversation {conversation_id}")
			
			thread_id = self._conversation_threads[conversation_id]
			
			# Create message in the thread with user context
			# Note: The agent's system prompt handles the Neocase context
			# We add user info as additional context
			message_content = f"[User: {display_name}]\n\n{user_message}"
			
			self._project_client.agents.messages.create(
				thread_id=thread_id,
				role="user",
				content=message_content
			)
			
			logger.info(f"Created message in thread {thread_id}")
			
			# Create and stream the run using the correct API
			with self._project_client.agents.runs.stream(
				thread_id=thread_id,
				agent_id=self._agent.id
			) as stream:
				# Process streaming events
				accumulated_text = ""
				
				for event_type, event_data, _ in stream:
					# Handle different event types
					if isinstance(event_data, MessageDeltaChunk):
						# Text delta from the agent
						if event_data.text:
							text_chunk = event_data.text
							accumulated_text += text_chunk
							turn_context.streaming_response.queue_text_chunk(text_chunk)
					
					elif isinstance(event_data, ThreadRun):
						if event_data.status == "completed":
							logger.info(f"Agent run completed for thread {thread_id}")
						elif event_data.status == "failed":
							logger.error(f"Agent run failed: {event_data.last_error}")
							turn_context.streaming_response.queue_text_chunk(
								"\n\n⚠️ An error occurred while processing your message."
							)
					
					elif event_type == AgentStreamEvent.ERROR:
						logger.error(f"Agent stream error: {event_data}")
						turn_context.streaming_response.queue_text_chunk(
							"\n\n⚠️ An error occurred while processing your message."
						)
					
					elif event_type == AgentStreamEvent.DONE:
						logger.info("Stream completed")
						break
			
			logger.info(f"Successfully streamed response ({len(accumulated_text)} chars) to {conversation_id}")
			
		except Exception as e:
			logger.error(f"Error during Azure AI Foundry Agent streaming: {e}", exc_info=True)
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
					"👋 Welcome to the **Neocase AI Assistant**!\n\n"
					"I'm here to help you discover how Neocase Software transforms customer service and case management with AI-powered automation.\n\n"
					"**Features:**\n"
					"✅ Persistent conversation memory (powered by Azure AI Foundry)\n"
					"✅ Teams SSO authentication\n"
					"✅ Streaming responses for better experience\n\n"
					"**Commands:**\n"
					"• `/reset` or `/clear` - Start a fresh conversation\n\n"
					"Ask me about Neocase's solutions, features, or how it integrates with Microsoft Teams!"
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

