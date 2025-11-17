# Bot Service Multitenant with Teams SSO and Azure OpenAI

This repository hosts a **Microsoft Teams bot** written in Python using the Microsoft Agents SDK. It implements:

- ✅ **Single Sign-On (SSO)** flow recommended by Microsoft for Teams bots
- ✅ **Azure OpenAI integration** with streaming responses
- ✅ **User-Assigned Managed Identity** for secure Azure authentication
- ✅ **Multi-tenant support** with optional tenant validation
- ✅ **Automatic token exchange** for seamless authentication

## 🎯 Key Features

### Authentication
- **Teams SSO**: Automatic authentication using Teams identity
- **Token Exchange**: Silent authentication without user prompts
- **OAuth Fallback**: Manual sign-in card if SSO fails
- **JWT Validation**: Secure token handling and claims extraction

### AI Integration
- **Azure OpenAI**: GPT-4 powered conversations
- **Streaming Responses**: Real-time token streaming for better UX
- **Personalized Context**: Uses authenticated user's name
- **Error Handling**: Graceful degradation on API failures

### Security
- **Managed Identity**: No secrets in code or environment
- **Tenant Validation**: Restrict access to specific Azure AD tenants
- **Secure Tokens**: Proper JWT handling and validation
- **HTTPS Required**: Production-ready security

## 📁 Structure

```
src/
├── agent.py      # Bot logic, SSO handling, and Azure OpenAI integration
├── server.py     # CloudAdapter bootstrap, HTTP routes, and middleware
└── main.py       # Entry point, environment loading, and logging

teams-manifest/
├── manifest.json # Teams app manifest with SSO configuration
└── README.md     # Instructions for creating app package

DEPLOYMENT.md     # Complete deployment guide
```

## ⚙️ Requirements

- **Python 3.12+** (included in dev container)
- **Azure Bot Service** with User-Assigned Managed Identity
- **Azure AD App Registration** configured for SSO
- **OAuth Connection** configured in Azure Bot Service
- **Azure OpenAI Service** with deployed model
- **Public HTTPS endpoint** (Azure Web App, ngrok for testing)

## 🔐 Environment Variables

The project automatically loads variables from `.env`. Required variables:

### Bot Framework Authentication
| Variable | Description | Example |
| --- | --- | --- |
| `MicrosoftAppId` | Bot Service App ID (Client ID) | `a1b2c3d4-e5f6-7890-abcd-ef1234567890` |
| `MicrosoftAppPassword` | Leave empty for Managed Identity | `` |
| `MicrosoftAppTenantId` | Azure AD Tenant ID | `f9e8d7c6-b5a4-3210-fedc-ba9876543210` |
| `MicrosoftAppType` | Authentication type | `UserAssignedMSI` |

### OAuth Configuration
| Variable | Description | Example |
| --- | --- | --- |
| `OAUTH_CONNECTION_NAME` | OAuth connection name in Bot Service | `EntraIDConnection` |

### Azure OpenAI
| Variable | Description | Example |
| --- | --- | --- |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI endpoint URL | `https://your-resource.openai.azure.com/` |
| `AZURE_OPENAI_API_KEY` | API key | `your-api-key` |
| `AZURE_OPENAI_API_VERSION` | API version | `2025-04-01-preview` |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | Model deployment name | `gpt-4.1` |

### Server Configuration
| Variable | Description | Default |
| --- | --- | --- |
| `PUBLIC_BASE_URL` | Public bot endpoint URL | Required |
| `PORT` | Local server port | `8000` |
| `LOG_LEVEL` | Logging level | `INFO` |

### Multi-tenant Control (Optional)
| Variable | Description | Example |
| --- | --- | --- |
| `ALLOWED_TENANTS` | Comma-separated tenant IDs | `tenant-id-1,tenant-id-2` |

> ⚠️ Leave `ALLOWED_TENANTS` empty to allow all tenants (public bot).

## ▶️ Local Development

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
# Edit .env with your configuration
```

### 3. Run the Bot

```bash
python src/main.py
```

### 4. Expose with ngrok (for Teams testing)

```bash
ngrok http 8000
```

Update `PUBLIC_BASE_URL` in `.env` with your ngrok URL.

## 🚀 Deployment

See **[DEPLOYMENT.md](DEPLOYMENT.md)** for complete deployment instructions including:

- Azure AD App Registration configuration
- OAuth Connection setup
- Managed Identity configuration
- Teams app package creation
- Testing checklist
- Troubleshooting guide

## 🧠 How It Works

### SSO Flow

1. **User sends message** → Bot checks for existing token
2. **No token found** → Bot sends OAuth card with SSO prompt
3. **Teams intercepts** → Performs automatic token exchange
4. **Token received** → Bot validates and extracts user claims
5. **User authenticated** → Message sent to Azure OpenAI with user context
6. **AI response** → Streamed back to user in real-time

### Token Exchange (Silent Authentication)

When SSO is properly configured:
- Teams client automatically exchanges ID token for access token
- No user interaction required after initial consent
- Tokens cached for subsequent requests
- Seamless user experience

### Fallback Flow

If SSO fails (misconfigured or first use):
- OAuth card appears with sign-in button
- User clicks and authenticates via browser
- Token stored for future requests
- Works on all platforms (mobile, web, desktop)

## 🏗️ Architecture

```
┌─────────────┐
│   Teams     │
│   Client    │
└──────┬──────┘
       │
       │ HTTPS (Bot Framework Protocol)
       │
┌──────▼──────────────────────────────┐
│   aiohttp Web Server                │
│   - JWT Authorization Middleware    │
│   - Cloud Adapter                   │
└──────┬──────────────────────────────┘
       │
       │
┌──────▼──────────────────────────────┐
│   TeamsSsoAgent                     │
│   - Token validation                │
│   - User authentication             │
│   - Message routing                 │
└──────┬──────────────────────────────┘
       │
       ├───────────────┐
       │               │
┌──────▼────────┐ ┌───▼──────────────┐
│  Bot Service  │ │  Azure OpenAI    │
│  OAuth Token  │ │  Chat API        │
│  Exchange     │ │  (Streaming)     │
└───────────────┘ └──────────────────┘
```

## ✅ Health Check

The bot exposes a health endpoint at `/health`:

```bash
curl https://your-bot-url.azurewebsites.net/health
```

Response:
```json
{"status": "ok"}
```

## 📚 References

- [Bot SSO Overview](https://learn.microsoft.com/en-us/microsoftteams/platform/bots/how-to/authentication/bot-sso-overview)
- [Register App for SSO](https://learn.microsoft.com/en-us/microsoftteams/platform/bots/how-to/authentication/bot-sso-register-aad)
- [Configure OAuth Connection](https://learn.microsoft.com/en-us/microsoftteams/platform/bots/how-to/authentication/auth-oauth-provider)
- [User-Assigned Managed Identity](https://learn.microsoft.com/en-us/azure/bot-service/bot-service-quickstart-registration?view=azure-bot-service-4.0&tabs=userassigned)
- [Microsoft Agents SDK](https://github.com/microsoft/agents)
- [Azure OpenAI Service](https://learn.microsoft.com/en-us/azure/ai-services/openai/)

## 🚀 Next Steps

- **Enhance AI**: Add function calling, RAG, conversation memory
- **Microsoft Graph**: Integrate SharePoint, OneDrive, Calendar
- **Adaptive Cards**: Rich UI for better user experience
- **State Management**: Persist conversation history
- **Analytics**: Track usage and performance
- **Multi-language**: Add i18n support

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 📄 License

MIT License - see LICENSE file for details

---

**Built with ❤️ using Microsoft Agents SDK and Azure OpenAI**

