"""Development-only OpenRouter request example.

Set OPENROUTER_API_KEYS in an untracked .env file. Never put a credential in code.
"""

import os

import requests


api_key = os.environ["OPENROUTER_API_KEYS"].split(",")[0].strip()
response = requests.post(
    "https://openrouter.ai/api/v1/chat/completions",
    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    json={
        "model": os.getenv("OPENROUTER_MODEL", "google/gemini-2.5-flash"),
        "messages": [{"role": "user", "content": "Explain the selected study material."}],
        "temperature": 0.4,
        "max_tokens": 100,
    },
    timeout=30,
)
response.raise_for_status()
print(response.json()["choices"][0]["message"]["content"])