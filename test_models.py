import os
import anthropic
from dotenv import load_dotenv

load_dotenv()
client = anthropic.Anthropic(api_key=os.getenv("CLAUDE_KEY").strip())

models = [
    "claude-3-5-sonnet-20240620",
    "claude-sonnet-5",
    "claude-opus-4-7",
    "claude-haiku-4-5",
    "claude-3-5-sonnet-latest"
]

for model in models:
    print(f"Testing model: {model}...")
    try:
        message = client.messages.create(
            model=model,
            max_tokens=10,
            messages=[{"role": "user", "content": "hi"}]
        )
        print(f"SUCCESS for {model}: {message.content[0].text}")
    except Exception as e:
        print(f"FAILED for {model}: {e}")
    print("-" * 20)
