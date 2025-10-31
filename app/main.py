from fastapi import FastAPI, HTTPException, Response, Body, Request
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import os
import uuid
# import uvicorn
import json
from app.country_service import CountryService, CountryInfo


app = FastAPI(
    title="Country Info A2A Agent",
    description="An AI agent that provides history and fintech info for countries.",
)


service = CountryService()

class TaskRequestParams(BaseModel):
    skill_id: str
    input: Dict[str, Any]

class JsonRpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    method: str = "tasks/send"
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    params: TaskRequestParams

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


@app.post("/tasks/send", response_model=None)
async def tasks_send(request: Request, response: Response):
    """
    This is the main "workshop" endpoint.
    It now accepts a raw request to handle Telex's simple chat format.
    """
    
    raw_body = {}
    request_id = "unknown"
    
    try:
        raw_body = await request.json()
        
        print(f"--- TELEX REQUEST BODY ---")
        print(json.dumps(raw_body, indent=2))
        print(f"--------------------------")

        request_id = raw_body.get("id", f"telex-{uuid.uuid4()}")
        
        country_name = None
        
        if "params" in raw_body and isinstance(raw_body.get("params"), dict):
            params = raw_body["params"]
            if "input" in params and isinstance(params.get("input"), dict):
                country_name = params["input"].get("country_name")

            if not country_name and "input" in params:
                 if isinstance(params["input"], str):
                    country_name = params["input"]

            if not country_name:
                country_name = params.get("prompt") or params.get("message")
        
        if not country_name:
            country_name = raw_body.get("prompt") or raw_body.get("message")

        if not country_name:
            raise ValueError("Could not find a 'country_name', 'prompt', or 'message' in the request body.")
            
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