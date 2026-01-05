import os
from google import genai
from dotenv import load_dotenv

def list_available_models():
    # Load environment variables from .env
    load_dotenv()
    
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY not found in .env file.")
        return

    client = genai.Client(api_key=api_key)
    
    print("Fetching available models...")
    try:
        # Use the models.list method to see available models
        models = client.models.list()
        
        print(f"{'Model Name':<50}")
        print("-" * 50)
        for model in models:
            # The model object has a 'name' attribute
            print(f"{model.name}")
            
    except Exception as e:
        print(f"Failed to list models: {e}")

if __name__ == "__main__":
    list_available_models()
