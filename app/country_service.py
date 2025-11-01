# --- country_service.py (FIXED - Better JSON parsing) ---
import os
import json
import asyncio
from groq import AsyncGroq
from pydantic import BaseModel, HttpUrl, ValidationError, TypeAdapter
from typing import List, Dict, Any

# --- Pydantic Models ---
class FintechStartup(BaseModel):
    name: str
    description: str
    website: HttpUrl

# --- The "Brain" / Service Layer ---
class CountryService:
    """
    This class contains the core business logic.
    It uses the Groq API to get real data.
    """
    def __init__(self):
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY environment variable not set.")
        self.client = AsyncGroq(api_key=api_key)
        self.model_name = "llama-3.1-8b-instant"

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

    def _normalize_startup_data(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Converts various JSON formats into a list of startup dicts.
        Handles cases where AI returns {name: [..], description: [..], website: [..]}
        """
        # Case 1: Already a list of objects
        if isinstance(data, list):
            return data
        
        # Case 2: Object with arrays for each field
        if isinstance(data, dict):
            # Check if it's the "parallel arrays" format
            if all(isinstance(v, list) for v in data.values()):
                names = data.get('name', [])
                descriptions = data.get('description', [])
                websites = data.get('website', [])
                
                # Combine parallel arrays into objects
                result = []
                for i in range(min(len(names), len(descriptions), len(websites))):
                    result.append({
                        'name': names[i],
                        'description': descriptions[i],
                        'website': websites[i]
                    })
                return result
            
            # Check if it's nested (e.g., {"startups": [...]})
            for value in data.values():
                if isinstance(value, list):
                    return value
        
        return []

    async def _get_real_fintech(self, country: str) -> List[FintechStartup]:
        """Gets real fintech data using the Groq API with JSON mode."""
        print(f"Getting fintech data for {country} (using Groq)...")
        prompt = f"Find the top 5 current biggest or most influential fintech startups in {country}."
        
        system_prompt = """You are a financial data analyst. Return ONLY a valid JSON array of objects.
Each object must have exactly these 3 fields:
- "name": string (the startup's name)
- "description": string (one sentence description)
- "website": string (full URL starting with https://)

Example format:
[
  {
    "name": "Example Fintech",
    "description": "A digital payment platform.",
    "website": "https://example.com"
  }
]

Return an empty array [] if no data is found. Do not add any other text."""

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
            
            # Normalize the data structure
            data_list = self._normalize_startup_data(data)
            
            if not data_list:
                print(f"AI returned JSON, but couldn't extract startups: {raw_text}")
                return []
            
            # Validate with Pydantic
            validated_startups: List[FintechStartup] = TypeAdapter(List[FintechStartup]).validate_python(data_list)
            print("...Fintech data received and parsed.")
            return validated_startups
            
        except json.JSONDecodeError as e:
            print(f"Error: Failed to decode JSON from AI response: {e}")
            print(f"Raw response was: {raw_text}")
            return []
        except ValidationError as e:
            print(f"Error: AI data failed Pydantic validation: {e}")
            print(f"Raw data was: {raw_text}")
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
                output_parts.append(f" - *{startup.description}*")
                output_parts.append(f" - {startup.website}")
        
        return "\n".join(output_parts)