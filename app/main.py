from fastapi import FastAPI, HTTPException, Response, Body
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import os
import uuid
# import uvicorn
from .country_service import CountryService, CountryInfo

# --- FastAPI App ---
app = FastAPI(
    title="Country Info A2A Agent",
    description="An AI agent that provides history and fintech info for countries.",
)

service = CountryService()

# --- A2A/JSON-RPC Models ---
class TaskRequestParams(BaseModel):
    """The 'params' for a task request, containing the skill and input."""
    skill_id: str
    input: Dict[str, Any]

class JsonRpcRequest(BaseModel):
    """The overall JSON-RPC request body."""
    jsonrpc: str = "2.0"
    method: str = "tasks/send"
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    params: TaskRequestParams

class TaskResultPart(BaseModel):
    """A part of the task's result. We'll return our data here."""
    type: str = "application/json"
    content: Any

class TaskResult(BaseModel):
    """The 'result' field in a successful JSON-RPC response."""
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    status: str = "completed"
    parts: List[TaskResultPart]

class JsonRpcSuccessResponse(BaseModel):
    """The full response for a successful task."""
    jsonrpc: str = "2.0"
    id: str
    result: TaskResult

class JsonRpcError(BaseModel):
    """The 'error' field for a failed JSON-RPC response."""
    code: int
    message: str
    data: Optional[Dict[str, Any]] = None

class JsonRpcErrorResponse(BaseModel):
    """The full response for a failed task."""
    jsonrpc: str = "2.0"
    id: str
    error: JsonRpcError

# --- A2A Agent Manifest ---
@app.get("/.well-known/agent.json")
async def agent_manifest():
    """
    Provides the agent's "business card" or manifest.
    This tells other agents what this agent can do.
    """
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

# --- A2A Task Endpoint ---
@app.post("/tasks/send", response_model=None)
async def tasks_send(request: JsonRpcRequest, response: Response):
    """
    This is the main "workshop" endpoint.
    It receives tasks, executes them, and returns the result.
    """
    try:
        if request.params.skill_id != "get_country_details":
            raise ValueError(f"Unknown skill: {request.params.skill_id}")
        
        country_name = request.params.input.get("country_name")
        if not country_name:
            raise ValueError("Missing required parameter: 'country_name'")
            
        country_data: CountryInfo = await service.get_country_details(country_name)
        
        result_part = TaskResultPart(content=country_data)
        
        task_result = TaskResult(parts=[result_part])
        
        json_response = JsonRpcSuccessResponse(
            id=request.id,
            result=task_result
        )
        
        return json_response

    except Exception as e:
        error_response = JsonRpcErrorResponse(
            jsonrpc="2.0",
            id=request.id,
            error=JsonRpcError(
                code=-32000, # Standard JSON-RPC server error
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