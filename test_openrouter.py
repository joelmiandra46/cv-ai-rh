import os
import requests

api_key = os.getenv("OPENROUTER_API_KEY")

url = "https://openrouter.ai/api/v1/chat/completions"

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

data = {
    "model": "openrouter/free",
    "messages": [
        {
            "role": "user",
            "content": "Réponds simplement : OpenRouter fonctionne."
        }
    ]
}

response = requests.post(
    url,
    headers=headers,
    json=data,
    timeout=120
)

print("Status :", response.status_code)
print(response.text)