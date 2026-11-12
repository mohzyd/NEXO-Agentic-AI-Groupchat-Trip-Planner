# NEXO: Agentic-AI Groupchat Trip Planner

NEXO helps friends plan trips together in one place. It combines real-time group chat, polls, an AI planning assistant, budget suggestions, and per-member PayPal Sandbox contributions.

> **Payments are for testing only.** NEXO uses PayPal's Sandbox environment. Use Sandbox test accounts and never enter real payment credentials.

## Features

- Real-time chat with public and password-protected rooms.
- Polls for coordinating group decisions.
- AI replies when mentioned with `@ai`, using recent conversation and poll results as context.
- AI-generated trip budget suggestions that the group leader can review and edit.
- Payment proposals with individual member pledges and separate PayPal Sandbox checkouts.
- GIF search with manual loading, capped at 10 results per search.

The AI provides planning assistance; it does not book travel, charge users, or make decisions on their behalf. Payment checkouts require each member's explicit action.

## Requirements

- Windows 10 or later.
- Python 3.10 or later.
- A Groq API key for AI features.
- A PayPal Developer account with a Sandbox business app. Create Sandbox buyer accounts to test checkout.

## Setup

Open PowerShell in the project directory (the directory containing `main.py` and `requirements.txt`):

```powershell
py -3 -m venv venv
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.sample .env
```

Edit `.env` and add your credentials:

```dotenv
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=openai/gpt-oss-20b

PAYPAL_CLIENT_ID=your_sandbox_business_app_client_id
PAYPAL_CLIENT_SECRET=your_sandbox_business_app_secret
PAYPAL_CURRENCY=USD
```

Get the PayPal Client ID and Secret from the **Sandbox** app credentials in the PayPal Developer Dashboard. Keep `.env` private: do not commit it or share its contents. The checked-in `.env.sample` is only a template.

AI features require a working Groq key and available model access. The chat can still be used without AI, but AI replies and budget suggestions will not work.

## Run

From the project directory, start the desktop app:

```powershell
.\venv\Scripts\python.exe main.py
```

## Try the AI and payments

1. Join a room with multiple participants.
2. Discuss trip preferences in chat. Mention `@ai` to ask NEXO for planning help.
3. Use **Suggest budget with AI** in the payment dialog to request a budget based on recent chat and poll results. The leader can edit the suggestion before proposing it.
4. The room leader creates a payment proposal with a description and target.
5. Members pledge contributions until the target is fully pledged.
6. Each member starts their own PayPal Sandbox checkout for their pledge. Sign in with a Sandbox buyer account to approve the test payment.
7. NEXO confirms the captured Sandbox amount before marking that member's contribution paid.

No real funds are transferred. A proposal is complete only after all member contributions have been captured successfully in Sandbox.

## PayPal and AI integration

- **PayPal Developer Platform — Sandbox REST API:** The backend authenticates with the Sandbox OAuth 2.0 API and uses Orders API v2 to create and capture test checkouts.
- **Groq API — Chat Completions:** The `openai/gpt-oss-20b` model provides chat assistance and structured trip-budget suggestions.

## Troubleshooting (How to solve problems)

- **AI is not configured:** Check that `.env` is in the project directory and contains a valid `GROQ_API_KEY`.
- **PayPal Sandbox is not configured:** Check the Sandbox business app Client ID and Secret in `.env`; do not use live credentials.
- **Checkout does not open:** Confirm the room target is fully pledged, the member pledged, and the PayPal Sandbox API is reachable.
- **Dependencies fail to install:** Confirm Python 3.10+ is installed and retry the `pip install -r requirements.txt` command.
