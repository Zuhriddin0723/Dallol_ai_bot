import os
import anthropic
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("CLAUDE_KEY", "").strip()
print(f"Key starts with: {api_key[:20]}... ends with: ...{api_key[-10:]}")

client = anthropic.Anthropic(api_key=api_key)

try:
    # Try a very generic request to see what models are available if possible
    # Anthropic doesn't have a list models endpoint in the SDK usually, 
    # but we can try to trigger a better error message.
    message = client.messages.create(
        model="claude-3-5-sonnet-20240620",
        max_tokens=10,
        messages=[{"role": "user", "content": "hi"}]
    )
    print("SUCCESS")
except anthropic.APIStatusError as e:
    print(f"STATUS CODE: {e.status_code}")
    print(f"RESPONSE: {e.response.json()}")
    # print(f"HEADERS: {e.response.headers}")
except Exception as e:
    print(f"OTHER ERROR: {e}")
