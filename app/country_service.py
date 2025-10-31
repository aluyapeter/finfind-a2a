# --- country_service.py (FINAL PARSER v3) ---

import os
import json
import asyncio
from groq import AsyncGroq
from pydantic import BaseModel, HttpUrl, ValidationError, TypeAdapter
from typing import List, Coroutine, Any, Awaitable, Dict

# --- Pydantic Models (Unchanged) ---
class FintechStartup(BaseModel):
    name: str
    description: str
    website: HttpUrl

# --- The "Brain" / Service Layer ---
class CountryService:
    """
    This class contains the core business logic.
    It now uses the Groq API to get real data.
    """
    
    def __init__(self):
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY environment variable not set.")
        
        self.client = AsyncGroq(api_key=api_key)
        self.model_name = "llama3-70b-8192" # The correct, working model

    async def _get_real_history(self, country: str) -> str:
        """Gets the real history of a country using the Groq API."""
        print(f"Getting history for {country} (using Groq)...")
        prompt = f"Provide a brief history of {country}, focusing on its early days and key historical milestones. Keep it to about 3-4 paragraphs."
        
        try:
            chat_completion = await self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "You are a helpful historian."},
                    {"role": "user", "content": prompt}
                ],
                model=self.model_name,
                temperature=0.2,
            )
            
            content = chat_completion.choices[0].message.content
            if content is None:
                raise ValueError("API returned empty content for history")

            print("...History received.")
            return content
        
        except Exception as e:
            print(f"Error getting history: {e}")
            return f"Error: Could not retrieve history for {country}."

    async def _get_real_fintech(self, country: str) -> List[FintechStartup]:
        """Gets real fintech data using the Groq API with JSON mode."""
        print(f"Getting fintech data for {country} (using Groq)...")
        
        prompt = f"Find the top 5 current biggest or most influential fintech startups in {country}."
        system_prompt = """
        You are a financial data analyst. You must return your answer *only*
        as a valid JSON array of objects. Do not add any other text.
        
        Each object in the array must have 3 keys:
        1. "name" (string): The startup's name.
        2. "description" (string): A brief, one-sentence description.
        3. "website" (string): The full, valid homepage URL.
        
        If you cannot find any data, return an empty array [].
        """
        
        data_list: List[Dict[str, Any]] = []
        raw_text: str | None = None
        
        try:
            chat_completion = await self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                model=self.model_name,
                response_format={"type": "json_object"}, 
            )
            
            raw_text = chat_completion.choices[0].message.content
            if raw_text is None:
                raise ValueError("API returned empty content for fintech")
            
            data = json.loads(raw_text)
            
            # --- NEW ROBUST PARSING LOGIC (v3) ---
            parsed_list: List[Dict[str, Any]] = []
            
            if isinstance(data, list):
                # AI behaved: [ {...}, {...} ]
                for item in data:
                    if isinstance(item, list):
                        for sub_item in item:
                             if isinstance(sub_item, dict) and sub_item:
                                parsed_list.append(sub_item)
                    elif isinstance(item, dict) and item:
                        parsed_list.append(item)
            
            elif isinstance(data, dict):
                # AI sent an object. Check for nested list or object-of-objects
                found_list = False
                for key in data:
                    if isinstance(data[key], list):
                        # AI sent: { "startups": [ {...}, {...} ] }
                        for item in data[key]:
                            if isinstance(item, dict) and item:
                                parsed_list.append(item)
                        found_list = True
                        break
                
                if not found_list:
                    # AI sent: { "Flutterwave": {...}, "Kudi": {...} }
                    for key in data:
                        if isinstance(data[key], dict) and "name" in data[key]:
                            parsed_list.append(data[key])
            
            data_list = parsed_list
            # --- END NEW LOGIC ---

            if not data_list:
                print(f"AI returned JSON, but we couldn't parse a valid list: {raw_text}")
                return []

            validated_startups: List[FintechStartup] = TypeAdapter(List[FintechStartup]).validate_python(data_list)
            
            print("...Fintech data received and parsed.")
            return validated_startups

        except json.JSONDecodeError as e:
            print(f"Error: Failed to decode JSON from AI response: {e}")
            print(f"Raw response was: {raw_text}")
            return []
        except ValidationError as e:
            print(f"Error: AI data failed Pydantic validation: {e}")
            print(f"Raw data list was: {data_list}")
            return []
        except Exception as e:
            print(f"An unknown error occurred getting fintech: {e}")
            return []

    async def get_country_details(self, country_name: str) -> str:
        """
        This is the main public method. It returns a formatted string.
        """
        
        history_task = self._get_real_history(country_name)
        fintech_task = self._get_real_fintech(country_name)
        
        history_data, fintech_data = await asyncio.gather(history_task, fintech_task)
        
        # --- Format the output as a Markdown string ---
        output_parts = []
        output_parts.append(f"Here is the information you requested for **{country_name}**:\n")
        output_parts.append("---")
        
        output_parts.append("### History")
        output_parts.append(history_data)
        output_parts.append("\n---\n")
        
        output_parts.append("### Top Fintech Startups")
        if not fintech_data:
            output_parts.append("No fintech data could be found.")
        else:
            for i, startup in enumerate(fintech_data):
                output_parts.append(f"**{i+1}. {startup.name}**")
                output_parts.append(f"   - *{startup.description}*")
                output_parts.append(f"   - {startup.website}")
        
        return "\n".join(output_parts)