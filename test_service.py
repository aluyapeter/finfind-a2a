# # --- test_service.py ---
# # (Place this in your root 'finfind-a2a/' folder)

# import asyncio
# import os
# import sys
# import google.generativeai as genai

# # We MUST check the venv path to prove it's the right one
# print(f"--- Running Python from: {sys.executable}")
# print("--- Loading libraries from: ")
# print("\n".join(sys.path))
# print("-" * 30)

# try:
#     # This import will work if you are in the root
#     # 'finfind-a2a/' folder
#     from app.country_service import CountryService
#     from google.generativeai import __version__ as genai_version
#     print(f"--- Successfully imported CountryService.")
#     print(f"--- Google GenAI library version: {genai_version}")
    
# except ImportError as e:
#     print(f"--- FAILED TO IMPORT: {e}")
#     print("--- STOP! Run this command from your root 'finfind-a2a' folder.")
#     sys.exit(1)
# except Exception as e:
#     print(f"--- An unknown error happened on import: {e}")
#     sys.exit(1)

# print("-" * 30)

# async def main():
#     """Directly tests the CountryService."""
    
#     if not os.getenv("GOOGLE_API_KEY"):
#         print("--- STOP! GOOGLE_API_KEY is NOT set.")
#         print("--- Please set it and try again.")
#         return

#     print("--- API Key is set.")
#     print("--- Instantiating CountryService...")
    
#     try:
#         service = CountryService()

#     # Manually override the model *just for this test*
#         service.model = genai.GenerativeModel(model_name="gemini-pro") # type: ignore

#         print("--- Service instantiated.")
#         print("--- MODEL OVERRIDDEN. Using 'gemini-pro'.") # <--- So we know
#         print("--- Calling _get_real_history('Nigeria')...")

#         history = await service._get_real_history("Nigeria")
        
#         print("\n" + "="*30)
#         print("--- TEST SUCCEEDED ---")
#         print(history)
#         print("="*30 + "\n")

#     except Exception as e:
#         print("\n" + "!"*30)
#         print("--- TEST FAILED ---")
#         print(f"--- The error is: {e}")
#         print("!"*30 + "\n")
        
#         # This will print the full, detailed error
#         import traceback
#         traceback.print_exc()

# if __name__ == "__main__":
#     asyncio.run(main())