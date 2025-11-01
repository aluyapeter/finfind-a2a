# --- main.py (FINAL WEBHOOK VERSION) ---

from fastapi import FastAPI, Response, Request, BackgroundTasks
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import os
import uuid
import uvicorn
import json
import httpx # <--- NEW IMPORT

# --- Import our "Brain" ---
from app.country_service import CountryService

# --- FastAPI App ---
app = FastAPI(
    title="Country Info A2A Agent",
    description="An AI agent that provides history and fintech info for countries.",
)

# --- Instantiate our "Brain" ---
service = CountryService()


# --- A2A/JSON-RPC Models (for Chat) ---
class ChatMessagePart(BaseModel):
    kind: str = "text"
    text: str

class ChatMessage(BaseModel):
    role: str = "assistant"
    parts: List[ChatMessagePart]
    messageId: str = Field(default_factory=lambda: str(uuid.uuid4()))

class MessageResult(BaseModel):
    message: ChatMessage

class ChatRpcResponse(BaseModel):
    jsonrpc: str = "2.0"
    id: str
    result: MessageResult

# --- Error models ---
class JsonRpcError(BaseModel):
    code: int
    message: str
    data: Optional[Dict[str, Any]] = None

class JsonRpcErrorResponse(BaseModel):
    jsonrpc: str = "2.0"
    id: str
    error: JsonRpcError

# --- NEW BACKGROUND WORKER FUNCTION ---
async def process_and_send_response(country_name: str, webhook_url: str, request_id: str):
    """
    This function runs in the background.
    It calls the AI, builds the response, and POSTs it to the Telex webhook.
    """
    print(f"--- BACKGROUND TASK: Processing for {country_name} ---")
    try:
        # 1. Call our service
        chat_response_string: str = await service.get_country_details(country_name)
        
        # 2. Build the chat-focused response
        response_part = ChatMessagePart(text=chat_response_string)
        response_message = ChatMessage(parts=[response_part])
        message_result = MessageResult(message=response_message)
        
        json_response = ChatRpcResponse(
            id=request_id,
            result=message_result
        )
        
        # 3. Send the response to the webhook
        async with httpx.AsyncClient() as client:
            print(f"--- BACKGROUND TASK: Sending response to {webhook_url} ---")
            # We use .model_dump_json() to send the raw JSON string
            await client.post(
                webhook_url,
                content=json_response.model_dump_json(),
                headers={"Content-Type": "application/json"}
            )
        print(f"--- BACKGROUND TASK: Complete ---")

    except Exception as e:
        print(f"--- BACKGROUND TASK ERROR: {str(e)} ---")
        # Try to send an error message back to the webhook
        error_response = JsonRpcErrorResponse(
            jsonrpc="2.0",
            id=request_id,
            error=JsonRpcError(code=-32000, message=f"An error occurred: {str(e)}")
        )
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    webhook_url,
                    content=error_response.model_dump_json(),
                    headers={"Content-Type": "application/json"}
                )
        except Exception as e2:
            print(f"--- BACKGROUND TASK: Failed to send error to webhook: {str(e2)} ---")

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


# --- A2A Task Endpoint (NEW WEBHOOK VERSION) ---
@app.post("/tasks/send", response_model=None)
async def tasks_send(request: Request, background_tasks: BackgroundTasks): # <--- Added BackgroundTasks
    
    raw_body = {}
    request_id = "unknown"
    
    try:
        raw_body = await request.json()
        print(f"--- TELEX REQUEST BODY (WEBHOOK) ---")
        
        request_id = raw_body.get("id", f"telex-{uuid.uuid4()}")
        
        # --- Extract country name ---
        country_name_raw = None
        params = raw_body.get("params", {})
        
        if "input" in params and isinstance(params.get("input"), dict):
            country_name_raw = params["input"].get("country_name")

        if not country_name_raw and "message" in params and isinstance(params.get("message"), dict):
            message = params["message"]
            if "parts" in message and isinstance(message.get("parts"), list) and len(message["parts"]) > 0:
                parts = message["parts"]
                if "text" in parts[0] and parts[0].get("kind") == "text":
                    country_name_raw = parts[0]["text"]
        
        if not country_name_raw:
            raise ValueError("Could not find a 'country_name' or 'message.parts[0].text' in the request.")
            
        country_name = country_name_raw.split()[0]
            
        print(f"--- Extracted country: {country_name} (from: {country_name_raw}) ---")

        # --- Extract webhook URL ---
        webhook_url = None
        if "configuration" in params and "pushNotificationConfig" in params["configuration"]:
            webhook_url = params["configuration"]["pushNotificationConfig"].get("url")
        
        if not webhook_url:
            raise ValueError("No pushNotificationConfig.url found in request.")
        
        print(f"--- Webhook URL: {webhook_url} ---")

        # --- Add task to background ---
        background_tasks.add_task(process_and_send_response, country_name, webhook_url, request_id)
        
        # --- Immediately return 200 OK ---
        # This tells Telex "Task accepted"
        return Response(status_code=200)

    except Exception as e:
        print(f"--- ERROR IN /tasks/send (sync part) ---")
        print(f"Error: {str(e)}")
        print(f"--- Failing request body was: ---")
        print(json.dumps(raw_body, indent=2))
        
        return Response(status_code=500, content=f"Failed to process request: {str(e)}")


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