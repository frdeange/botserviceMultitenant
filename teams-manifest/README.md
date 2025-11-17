# Teams App Manifest

This directory contains the Microsoft Teams app manifest configuration for the SSO bot.

## ⚠️ IMPORTANT - Security Notice

**The `manifest.json` file contains sensitive deployment information and is excluded from version control.**

- ✅ `manifest.example.json` - Template for other users (safe to commit)

## 🚀 Getting Started

### 1. Create Your Manifest

Copy the example file and customize it:

```bash
cd teams-manifest
cp manifest.example.json manifest.json
```

### 2. Update Values

Edit `manifest.json` and replace ALL placeholder values:

- `YOUR-BOT-APP-ID-HERE` → Your actual Bot Service App ID
- `your-app-name.azurewebsites.net` → Your actual Azure Web App domain
- `com.yourcompany.teamsssobot` → Your package name (reverse domain notation)
- Update company information in the `developer` section

## 🎨 Creating Icons

### Color Icon (192x192)
- Transparent background
- PNG format
- 192x192 pixels
- Represents your bot in the Teams app store

### Outline Icon (32x32)
- White icon on transparent background
- PNG format
- 32x32 pixels
- Used in Teams UI elements

## 📦 Creating the App Package

Once you have all three files:

```bash
cd teams-manifest
zip -r ../teams-app.zip manifest.json color.png outline.png
```

## 🔧 Configuration Notes

**IMPORTANT: Update the following values in manifest.json before deploying:**

### 1. Bot/App ID
Replace `YOUR-BOT-APP-ID-HERE` with your actual Bot Service App ID in:
- `id` (root level)
- `bots[0].botId`
- `webApplicationInfo.id`
- `webApplicationInfo.resource` (in the URL)

### 2. Domain
Replace `your-app-name.azurewebsites.net` with your actual Azure Web App domain in:
- `validDomains[0]`
- `webApplicationInfo.resource`

**Example values:**
```json
"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
"validDomains": ["mybot-app.azurewebsites.net", "token.botframework.com"],
"resource": "api://mybot-app.azurewebsites.net/a1b2c3d4-e5f6-7890-abcd-ef1234567890"
```

### 3. Developer Information
Update the following fields:
- `developer.name` - Your company or organization name
- `developer.websiteUrl` - Your website
- `developer.privacyUrl` - Privacy policy URL
- `developer.termsOfUseUrl` - Terms of use URL

### 4. Package Name
- `packageName` - Use reverse domain notation (e.g., `com.yourcompany.botname`)

## 🔐 Azure AD App Registration (Required for SSO)

For SSO to work, you MUST configure your Azure AD App Registration:

### 1. Expose an API
In Azure Portal > App Registrations > Your App > Expose an API:

1. Set **Application ID URI** to:
   ```
   api://your-app-name.azurewebsites.net/YOUR-BOT-APP-ID
   ```
   (Replace with your domain and App ID)

2. Add a scope:
   - Scope name: `access_as_user`
   - Who can consent: Admins and users
   - Admin consent display name: `Teams can access user profile`
   - Admin consent description: `Allows Teams to call the app's web APIs as the current user`
   - User consent display name: `Teams can access your user profile and make requests on your behalf`
   - User consent description: `Enable Teams to call this app's APIs with the same rights that you have`
   - State: Enabled

### 2. Authorize Client Applications
Add the following pre-authorized applications:

**Microsoft Teams Mobile/Desktop:**
- Client ID: `1fec8e78-bce4-4aaf-ab1b-5451cc387264`
- Authorized scopes: `api://[your-domain]/[your-app-id]/access_as_user`

**Microsoft Teams Web:**
- Client ID: `5e3ce6c0-2b1f-4285-8d4b-75ee78787346`
- Authorized scopes: `api://[your-domain]/[your-app-id]/access_as_user`

### 3. API Permissions
Add the following Microsoft Graph permissions:
- `User.Read` (Delegated)
- `openid` (Delegated)
- `profile` (Delegated)
- `email` (Delegated)

## 🚀 Uploading to Teams

### For Testing (Developer)
1. Go to Teams
2. Click Apps > Manage your apps
3. Click "Upload an app"
4. Select "Upload a custom app"
5. Choose your `teams-app.zip` file

### For Organization
Work with your Teams admin to upload the app to your organization's app catalog.

## 🔗 Additional Resources

- [Teams App Manifest Schema](https://learn.microsoft.com/en-us/microsoftteams/platform/resources/schema/manifest-schema)
- [SSO for Teams Bots](https://learn.microsoft.com/en-us/microsoftteams/platform/bots/how-to/authentication/bot-sso-overview)
- [App Registration for SSO](https://learn.microsoft.com/en-us/microsoftteams/platform/bots/how-to/authentication/bot-sso-register-aad)
