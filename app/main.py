# --- main.py (FINAL v3) ---

from fastapi import FastAPI, HTTPException, Response, Body, Request
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import os
import uuid
import uvicorn
import json

# --- Import our "Brain" ---
from app.country_service import CountryService, CountryInfo

# --- FastAPI App ---
app = FastAPI(
    title="Country Info A2A Agent",
    description="An AI agent that provides history and fintech info for countries.",
)

# --- Instantiate our "Brain" ---
service = CountryService()


# --- A2A/JSON-RPC Models ---
# We STILL need these for our *response*
class TaskResultPart(BaseModel):
    type: str = "application/json"
    content: Any

class TaskResult(BaseModel):
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    status: str = "completed"
    parts: List[TaskResultPart]

class JsonRpcSuccessResponse(BaseModel):
    jsonrpc: str = "2.0"
    id: str
    result: TaskResult

class JsonRpcError(BaseModel):
    code: int
    message: str
    data: Optional[Dict[str, Any]] = None

class JsonRpcErrorResponse(BaseModel):
    jsonrpc: str = "2.0"
    id: str
    error: JsonRpcError

# --- A2A Agent Manifest (Unchanged) ---
@app.get("/.well-known/agent.json")
async def agent_manifest():
    base_url = os.getenv("AGENT_BASE_URL", "http://localhost:8000")
    
    manifest = {
        "name": "CountryInfoAgent",
        "description": "An AI agent that provides history and top fintech startups for a specific country.",
        "url": base_url,
        "version": "1.0.0",
        
        "skills": [
            {
                "id": "get_country_details",
                "name": "Get Country Details",
                "description": "Fetches the history and a list of top fintech startups for a specific country.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "country_name": {
                            "type": "string",
                            "description": "The name of the country to query."
                        }
                    },
                    "required": ["country_name"]
                }
            }
        ],
        
        "endpoints": {
            "task_send": f"{base_url}/tasks/send"
        }
    }
    return manifest


# --- A2A Task Endpoint (NEW ROBUST VERSION) ---
@app.post("/tasks/send", response_model=None)
async def tasks_send(request: Request, response: Response):
    
    raw_body = {}
    request_id = "unknown"
    
    try:
        raw_body = await request.json()
        print(f"--- TELEX REQUEST BODY ---")
        print(json.dumps(raw_body, indent=2))
        print(f"--------------------------")
        
        request_id = raw_body.get("id", f"telex-{uuid.uuid4()}")
        
        # --- NEW LOGIC TO FIND THE COUNTRY NAME ---
        country_name = None
        params = raw_body.get("params", {})
        
        # Guess 1: Formal A2A format (from our curl test)
        if "input" in params and isinstance(params.get("input"), dict):
            country_name = params["input"].get("country_name")

        # Guess 2: Telex Chat format (from your logs)
        if not country_name and "message" in params and isinstance(params.get("message"), dict):
            message = params["message"]
            if "parts" in message and isinstance(message.get("parts"), list) and len(message["parts"]) > 0:
                parts = message["parts"]
                if "text" in parts[0] and parts[0].get("kind") == "text":
                    country_name = parts[0]["text"]

        if not country_name:
            raise ValueError("Could not find a 'country_name' or 'message.parts[0].text' in the request.")
            
        # --- END NEW LOGIC ---
            
        print(f"--- Extracted country: {country_name} ---")
        country_data: CountryInfo = await service.get_country_details(country_name)
        
        result_part = TaskResultPart(content=country_data)
        task_result = TaskResult(parts=[result_part])
        
        json_response = JsonRpcSuccessResponse(
            id=request_id,
            result=task_result
        )
        return json_response

    except Exception as e:
        print(f"--- ERROR IN /tasks/send ---")
        print(f"Error: {str(e)}")
        print(f"--- Failing request body was: ---")
        print(json.dumps(raw_body, indent=2))
        print(f"------------------------------")
        
        error_response = JsonRpcErrorResponse(
            jsonrpc="2.0",
            id=request_id,
            error=JsonRpcError(
                code=-32000,
                message=f"An error occurred: {str(e)}",
            )
        )
        response.status_code = 500
        return error_response


# --- Simple root endpoint for testing (Unchanged) ---
@app.get("/")
def read_root():
    return {"message": "Country Info Agent is running. Visit '/.well-known/agent.json' for details."}


# --- To run this server: ---
# In your terminal, run:
#    AGENT_BASE_URL="http://localhost:8000" uvicorn main:app --reload
#
#    Use this curl command in your terminal to test:
#
#    curl -X POST "http://localhost:8000/tasks/send" \
#    -H "Content-Type: application/json" \
#    -d '{
#        "jsonrpc": "2.0",
#        "method": "tasks/send",
#        "id": "12345",
#        "params": {
#            "skill_id": "get_country_details",
#            "input": {
#                "country_name": "Nigeria"
#            }
#        }
#    }'