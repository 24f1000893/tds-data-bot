# Data Analyst Telegram Bot

An LLM-powered Telegram bot that acts as an agentic data analyst. When messaged a data-analysis question, it dynamically writes, executes, and verifies a Python script to compute the correct answer, and replies with the required JSON response.

## Features

- **Agentic Code Execution**: Dynamically writes and runs Python scripts to download datasets, process inline data, and compute correct results.
- **Multi-turn Context**: Tracks conversation history per chat session to support follow-up questions.
- **Self-contained Server**: Exposes a built-in lightweight HTTP server on port 8000 to serve the run logs (`run.jsonl`) required by the grader.
- **Zero-Dependency Polling**: Uses Python's built-in `urllib` to query the Telegram API, preventing dependency conflicts or configuration issues.
- **Multi-LLM Support**: Works with Google Gemini API, OpenAI API, or the IITM AI Proxy.

## Configuration

The bot reads configuration from environment variables or a `.env` file in the same directory:

```env
# Required: Telegram Bot Token from @BotFather
BOT_TOKEN=your-telegram-bot-token

# Required: At least one LLM key (the bot auto-detects and uses what is provided)
GEMINI_API_KEY=your-gemini-api-key
# OR
AIPROXY_TOKEN=your-iitm-aiproxy-token
# OR
OPENAI_API_KEY=your-openai-api-key

# Optional: Public tunnel URL (e.g., Serveo, localhost.run, Ngrok)
PUBLIC_URL=https://your-custom-subdomain.serveo.net
```

## Running the Bot

1. Install the required data-science packages for the agent:
   ```bash
   pip install -r requirements.txt
   ```

2. Run the bot:
   ```bash
   python3 bot.py
   ```

3. Expose port `8000` to the internet (so the grader can download `run.jsonl`):
   ```bash
   ssh -R 80:localhost:8000 serveo.net
   ```
   *Note: Set the generated HTTPS URL as `PUBLIC_URL` in your `.env` so that the bot replies with the correct log URL.*
