import asyncio
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

VLLM_API_URL = os.getenv("VLLM_API_URL", "http://127.0.0.1:8000/v1")
VLLM_MODEL_NAME = os.getenv("VLLM_MODEL_NAME", "nanonets/Nanonets-OCR2-3B")

print(f"--- vLLM Connection Diagnostic ---")
print(f"Target URL: {VLLM_API_URL}")
print(f"Target Model: {VLLM_MODEL_NAME}")
print("-" * 30)

def test_connection():
    client = OpenAI(
        base_url=VLLM_API_URL,
        api_key="EMPTY"
    )
    
    try:
        print("1. Attempting to list models...")
        models = client.models.list()
        print(f"✓ Success! Models found: {[m.id for m in models.data]}")
        
        print("\n2. Attempting a minimal inference (1 token)...")
        response = client.chat.completions.create(
            model=VLLM_MODEL_NAME,
            messages=[
                {"role": "user", "content": "Hello"}
            ],
            max_tokens=1,
            temperature=0.0
        )
        print("✓ Success! Inference completed.")
        print("-" * 30)
        print("✅ vLLM server is UP and reachable.")
        return True
    except Exception as e:
        print(f"\n❌ ERROR: {type(e).__name__}: {e}")
        print("-" * 30)
        print("Possible causes:")
        print(f" - Is the vLLM server running?")
        print(f" - Is it listening on {VLLM_API_URL}?")
        print(f" - Is there a firewall blocking the connection?")
        print(f" - If running in Docker, check container networking.")
        return False

if __name__ == "__main__":
    test_connection()
