import os
from google import genai
from dotenv import load_dotenv

def test_generation():
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    model_name = "gemini-3-flash-preview" # or "models/gemini-3-flash-preview"
    
    client = genai.Client(api_key=api_key)
    
    print(f"Testing generation with model: {model_name}")
    try:
        resp = client.models.generate_content(model=model_name, contents="Say hello in isiZulu")
        print(f"Success! Response: {resp.text}")
    except Exception as e:
        print(f"Failed with {model_name}: {e}")
        
    model_name_with_prefix = "models/gemini-3-flash-preview"
    print(f"\nTesting generation with model: {model_name_with_prefix}")
    try:
        resp = client.models.generate_content(model=model_name_with_prefix, contents="Say hello in isiZulu")
        print(f"Success! Response: {resp.text}")
    except Exception as e:
        print(f"Failed with {model_name_with_prefix}: {e}")

if __name__ == "__main__":
    test_generation()
