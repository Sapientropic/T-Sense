# Getting Telegram API Credentials

You need `api_id` and `api_hash` from Telegram to use tgcli. Here's how to get them.

## Normal Method

1. Go to **https://my.telegram.org/apps**
2. Log in with your phone number
3. Fill in the form (app name, short name, etc. — anything works)
4. Copy the `api_id` (number) and `api_hash` (string)

Use an official Telegram app on your account first. Telegram's API docs say developer notifications are sent to the phone number tied to this process, so use your active account and an up-to-date number.

## Common Issue: "ERROR" on the Form

Telegram sometimes shows a blank ERROR page. This is often network or account risk scoring, but Telegram does not publish a precise public reason for this generic error.

### Fixes (in order of reliability)

**Option A: Official app + mobile cellular data**
- Confirm you can receive Telegram service messages in the official mobile or desktop app
- Switch your computer/phone to mobile data (not Wi-Fi)
- Disable VPN/proxy/datacenter egress for this step
- Open `https://my.telegram.org/apps` again in a normal browser session

**Option B: Different local browser or clean profile**
- Try a private/incognito window or a fresh local browser profile
- Disable extensions that modify requests or block scripts
- Keep the browser on your own machine; do not enter Telegram codes into remote browsers

**Option C: Wait and retry**
- If you recently retried many times, wait 24 hours before trying again
- Make sure you are not trying to create a second API app for the same phone number; Telegram's current API documentation says each number can only have one `api_id` connected to it

### If All Else Fails

Try again from a different trusted local network after 24 hours. If your account is restricted or cannot create an API app after repeated attempts, use Telegram's official support/recovery channels rather than borrowing someone else's credentials.

Do **not** use GitHub Codespaces, Colab, hosted browsers, or other remote cloud shells to log in to `my.telegram.org`. The confirmation code is sent via Telegram, and entering it into a remote environment expands the account and credential exposure surface.

## After Getting Credentials

Edit the tgcli config created by setup:

- Mac/Linux: `~/.config/tgcli/config.toml`
- Windows: `%USERPROFILE%\.config\tgcli\config.toml`

```toml
api_id = 12345678
api_hash = "your_api_hash_here"
session_store = "file"
```

Then authenticate:

```bash
# Mac/Linux
source .venv/bin/activate
tg auth login

# Windows
.venv\Scripts\activate.bat
tg auth login
```

Telegram will send a verification code to your app. Enter it when prompted.

## Security Notes

- **Never share** your `api_hash` or commit it to Git
- **Never share** your `.session` file (it's your login token)
- `config.toml` and `*.session` are in `.gitignore` by default
- Each phone number currently gets one `api_id` in Telegram's official API flow
- Avoid copying credentials into cloud notebooks, hosted shells, screenshots, or chat logs
