# --- main.py (FINAL - Simplified) ---
from fastapi import FastAPI, Response, Request, BackgroundTasks
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import os
import uuid
import json
import httpx

from app.country_service import CountryService

app = FastAPI(
    title="Country Info A2A Agent",
    description="An AI agent that provides history and fintech info for countries.",
)

service = CountryService()

# --- Models ---
class ChatMessagePart(BaseModel):
    kind: str = "text"
    text: str

class ChatMessage(BaseModel):
    kind: str = "message"
    role: str = "agent"
    parts: List[ChatMessagePart]
    messageId: str = Field(default_factory=lambda: str(uuid.uuid4()))

class MessageParams(BaseModel):
    message: ChatMessage

class ChatRpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: str
    method: str = "message/send"
    params: MessageParams

# --- Background Task ---
async def process_and_send_response(
    country_name: str,
    webhook_url: str,
    request_id: str,
    token: Optional[str] = None
):
    print(f"--- BACKGROUND TASK: Processing for {country_name} ---")
    try:
        # Get the data
        chat_response_string: str = await service.get_country_details(country_name)
        
        # Build response
        response_message = ChatMessage(
            kind="message",
            role="agent",
            parts=[ChatMessagePart(kind="text", text=chat_response_string)]
        )
        
        json_request = ChatRpcRequest(
            id=request_id,
            method="message/send",
            params=MessageParams(message=response_message)
        )
        
        # Send to webhook
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            print(f"--- Sending response to webhook ---")
            response = await client.post(
                webhook_url,
                json=json_request.model_dump(mode='json'),
                headers=headers
            )
            print(f"--- Webhook response: {response.status_code} - {response.text} ---")
        
        print(f"--- BACKGROUND TASK: Complete ---")
        
    except Exception as e:
        print(f"--- BACKGROUND TASK ERROR: {str(e)} ---")
        import traceback
        print(traceback.format_exc())

# --- Agent Manifest ---
@app.get("/.well-known/agent.json")
async def agent_manifest():
    base_url = os.getenv("AGENT_BASE_URL", "http://localhost:8000")
    return {
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

# --- Task Endpoint ---
@app.post("/tasks/send")
async def tasks_send(request: Request, background_tasks: BackgroundTasks):
    raw_body = {}
    request_id = "unknown"
    
    try:
        raw_body = await request.json()
        request_id = raw_body.get("id", f"telex-{uuid.uuid4()}")
        
        print(f"--- Received request {request_id} ---")
        
        # Extract country name
        country_name_raw = None
        params = raw_body.get("params", {})
        
        # Try input.country_name first
        if "input" in params and isinstance(params.get("input"), dict):
            country_name_raw = params["input"].get("country_name")
        
        # Try message.parts
        if not country_name_raw and "message" in params:
            message = params.get("message", {})
            parts = message.get("parts", [])
            
            for part in parts:
                if part.get("kind") == "text" and "text" in part:
                    text = part["text"].strip()
                    # Skip HTML, errors, and long instructions
                    if (text and 
                        not text.startswith("<") and 
                        not text.startswith("\n") and
                        "Sorry" not in text and
                        "You are a" not in text and
                        len(text) < 100):
                        country_name_raw = text
                        break
        
        if not country_name_raw:
            raise ValueError("Could not find country name in request")
        
        # Clean up country name
        country_name = country_name_raw.split()[0]
        if "<" in country_name:
            import re
            country_name = re.sub(r'<[^>]+>', '', country_name).strip()
        
        print(f"--- Country: {country_name} ---")
        
        # Get webhook config
        config = params.get("configuration", {}).get("pushNotificationConfig", {})
        webhook_url = config.get("url")
        token = config.get("token")
        blocking = config.get("blocking", False)
        
        print(f"--- Blocking mode: {blocking} ---")
        
        # If blocking mode, wait for result before responding
        if blocking:
            print(f"--- BLOCKING MODE: Processing synchronously ---")
            chat_response = await service.get_country_details(country_name)
            
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "kind": "message",
                    "role": "agent",
                    "parts": [{
                        "kind": "text",
                        "text": chat_response
                    }],
                    "messageId": str(uuid.uuid4())
                }
            }
        
        # Non-blocking mode: use webhook
        if not webhook_url:
            raise ValueError("No webhook URL provided for non-blocking mode")
        
        # Start background task
        background_tasks.add_task(
            process_and_send_response,
            country_name,
            webhook_url,
            request_id,
            token
        )
        
        # Return immediate acknowledgment with message
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "kind": "message",
                "role": "agent",
                "parts": [{
                    "kind": "text",
                    "text": f"🔍 Looking up information about {country_name}..."
                }],
                "messageId": str(uuid.uuid4())
            }
        }
        
    except Exception as e:
        print(f"--- ERROR: {str(e)} ---")
        import traceback
        print(traceback.format_exc())
        
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": -32000,
                "message": f"Failed to process request: {str(e)}"
            }
        }

@app.get("/")
def read_root():
    return {"message": "Country Info Agent is running"}
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