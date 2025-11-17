# Bot Service Multitenant with Teams SSO

This repository hosts a Microsoft Teams bot written in Python using the Microsoft Agents SDK. It implements the **Single Sign-On (SSO)** flow recommended by Microsoft for Teams bots, including automatic token exchange support and the OAuth fallback card.

## 📁 Structure

```
src/
├── agent.py      # Bot logic and SSO handling
├── server.py     # CloudAdapter bootstrap and HTTP routes
└── main.py       # Entry point, env loading, and logging setup
```

## ⚙️ Requirements

- Python 3.12 (already included in the dev container).
- An Azure App Registration for the bot (App ID plus secret, or Managed Identity).
- An **OAuth Connection** configured in Azure Bot Service (for example `EntraIDConnection`).
- A public URL (ngrok, Azure Web App, etc.) pointing to `/api/messages`.

## 🔐 Environment variables

The project automatically loads the variables defined in `.env`. Set at least:

| Variable | Description |
| --- | --- |
| `MicrosoftAppId` / `BOTSERVICE_APP_ID` | Bot Service App ID. |
| `MicrosoftAppPassword` / `BOTSERVICE_APP_SECRET` | Bot secret (ClientSecret auth only). |
| `MicrosoftAppTenantId` | Tenant ID (`organizations` for multitenant). |
| `MicrosoftAppType` | `UserAssignedMSI`, `SystemAssignedMSI`, `SingleTenant`, or `MultiTenant`. |
| `OAUTH_CONNECTION_NAME` | Exact OAuth Connection name configured in Azure Bot Service. |
| `PUBLIC_BASE_URL` | Full public URL, e.g. `https://my-bot.ngrok.app/api/messages`. |
| `PORT` | Local port (defaults to `8000`). |

> ⚠️ If `PUBLIC_BASE_URL` is not defined, the bot falls back to `http://localhost:<PORT>/api/messages`, which only works for local testing.

## ▶️ Local run

1. Install dependencies (already present in the dev container):
   ```bash
   pip install -r requirements.txt
   ```
2. Start the bot:
   ```bash
   python src/main.py
   ```
3. Expose the port via ngrok or another tunnel and update the Azure Bot Service messaging endpoint.

## 🧠 What the bot does

- Attempts to retrieve the SSO token via `get_token`.
- If Teams already exchanged the token, decodes the JWT and replies with the user profile.
- If no token is available, sends an OAuth card with the correct `TokenExchangeState` automatically.
- Handles the `signin/tokenExchange` and `signin/verifyState` invokes exactly as documented by Microsoft.

## ✅ Health check

`GET /health` returns `{ "status": "ok" }`, which is handy for Azure deployment probes.

## 📚 Useful references

- [Bot SSO overview](https://learn.microsoft.com/en-us/microsoftteams/platform/bots/how-to/authentication/bot-sso-overview)
- [Register an app for bots](https://learn.microsoft.com/en-us/microsoftteams/platform/bots/how-to/authentication/bot-sso-register-aad)
- [Configure an OAuth connection](https://learn.microsoft.com/en-us/microsoftteams/platform/bots/how-to/authentication/auth-oauth-provider)

## 🚀 Suggested next steps

- Add Microsoft Graph calls using the OBO token.
- Persist state in external storage (Cosmos DB, Azure Table Storage, etc.).
- Package everything into a container to deploy on Azure Container Apps.
