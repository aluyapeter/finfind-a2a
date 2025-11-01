# --- main.py (FIXED v2 - Added debugging and verified structure) ---
from fastapi import FastAPI, Response, Request, BackgroundTasks
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import os
import uuid
import uvicorn
import json
import httpx

# --- Import our "Brain" ---
from app.country_service import CountryService

# --- FastAPI App ---
app = FastAPI(
    title="Country Info A2A Agent",
    description="An AI agent that provides history and fintech info for countries.",
)

# --- Instantiate our "Brain" ---
service = CountryService()

# --- A2A/JSON-RPC Models (for sending a message) ---
class ChatMessagePart(BaseModel):
    kind: str = "text"
    text: str

class ChatMessage(BaseModel):
    kind: str = "message"  # Must be "message"
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

# --- Error models ---
class JsonRpcError(BaseModel):
    code: int
    message: str
    data: Optional[Dict[str, Any]] = None

class JsonRpcErrorResponse(BaseModel):
    jsonrpc: str = "2.0"
    id: str
    error: JsonRpcError

# --- BACKGROUND WORKER FUNCTION ---
async def process_and_send_response(
    country_name: str,
    webhook_url: str,
    request_id: str,
    token: Optional[str] = None
):
    """
    This function runs in the background.
    It calls the AI, builds the response, and POSTs it to the Telex webhook.
    """
    print(f"--- BACKGROUND TASK: Processing for {country_name} ---")
    try:
        # 1. Call our service
        chat_response_string: str = await service.get_country_details(country_name)

        # 2. Build the chat-focused request
        response_part = ChatMessagePart(kind="text", text=chat_response_string)
        response_message = ChatMessage(
            kind="message",
            role="agent",
            parts=[response_part]
        )
        message_params = MessageParams(message=response_message)
        json_request_to_telex = ChatRpcRequest(
            id=request_id,
            method="message/send",
            params=message_params
        )

        # DEBUG: Print the exact JSON we're sending
        request_json = json_request_to_telex.model_dump(mode='json')
        print(f"--- BACKGROUND TASK: Request JSON structure ---")
        print(json.dumps(request_json, indent=2))

        # 3. Build webhook headers
        webhook_headers = {"Content-Type": "application/json"}
        if token:
            webhook_headers["Authorization"] = f"Bearer {token}"
            print(f"--- BACKGROUND TASK: Attaching 'token' to Authorization header ---")
        else:
            print(f"--- BACKGROUND TASK: No 'token' was passed. This will cause a 401. ---")

        # 4. Send the new request to the webhook
        async with httpx.AsyncClient() as client:
            print(f"--- BACKGROUND TASK: Sending new 'message/send' request to {webhook_url} ---")
            webhook_response = await client.post(
                webhook_url,
                json=request_json,  # Using json= instead of content= for proper serialization
                headers=webhook_headers
            )
            print(f"--- WEBHOOK RESPONSE STATUS: {webhook_response.status_code} ---")
            try:
                print(f"--- WEBHOOK RESPONSE BODY: {webhook_response.json()} ---")
            except Exception:
                print(f"--- WEBHOOK RESPONSE BODY (text): {webhook_response.text} ---")

        print(f"--- BACKGROUND TASK: Complete ---")

    except Exception as e:
        print(f"--- BACKGROUND TASK ERROR: {str(e)} ---")
        import traceback
        print(traceback.format_exc())
        
        error_response = JsonRpcErrorResponse(
            jsonrpc="2.0",
            id=request_id,
            error=JsonRpcError(code=-32000, message=f"An error occurred: {str(e)}")
        )
        try:
            async with httpx.AsyncClient() as client:
                webhook_headers = {"Content-Type": "application/json"}
                if token:
                    webhook_headers["Authorization"] = f"Bearer {token}"
                await client.post(
                    webhook_url,
                    json=error_response.model_dump(mode='json'),
                    headers=webhook_headers
                )
        except Exception as e2:
            print(f"--- BACKGROUND TASK: Failed to send error to webhook: {str(e2)} ---")

# --- A2A Agent Manifest ---
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

# --- A2A Task Endpoint ---
@app.post("/tasks/send", response_model=None)
async def tasks_send(request: Request, background_tasks: BackgroundTasks):
    raw_body = {}
    request_id = "unknown"
    try:
        raw_body = await request.json()
        print(f"--- INCOMING TELEX REQUEST ---")
        print(json.dumps(raw_body, indent=2))
        
        request_id = raw_body.get("id", f"telex-{uuid.uuid4()}")

        # --- Extract country name ---
        country_name_raw = None
        params = raw_body.get("params", {})
        
        # Try method 1: Look for input.country_name
        if "input" in params and isinstance(params.get("input"), dict):
            country_name_raw = params["input"].get("country_name")
        
        # Try method 2: Look in message.parts for text
        if not country_name_raw and "message" in params and isinstance(params.get("message"), dict):
            message = params["message"]
            if "parts" in message and isinstance(message.get("parts"), list):
                # Look through all parts for the first text that looks like a country name
                for part in message["parts"]:
                    if part.get("kind") == "text" and "text" in part:
                        text = part["text"].strip()
                        # Skip HTML tags, long instructions, and error messages
                        if (text and 
                            not text.startswith("<") and 
                            not text.startswith("\n") and
                            "Sorry" not in text and
                            "You are a" not in text and
                            len(text) < 100):  # Country names are short
                            country_name_raw = text
                            break
        
        if not country_name_raw:
            print(f"--- ERROR: Could not extract country name from request ---")
            print(f"--- Available params keys: {list(params.keys())} ---")
            if "message" in params:
                print(f"--- Message parts: {params['message'].get('parts', [])[:3]} ---")  # First 3 parts only
            raise ValueError("Could not find a country name in the request.")
        
        # Extract just the country name (first word)
        country_name = country_name_raw.split()[0] if " " in country_name_raw else country_name_raw
        # Remove any HTML tags if present
        if "<" in country_name:
            import re
            country_name = re.sub(r'<[^>]+>', '', country_name).strip()
        
        print(f"--- Extracted country: '{country_name}' (from: '{country_name_raw}') ---")

        # --- Extract webhook config ---
        webhook_url = None
        token = None
        if "configuration" in params and "pushNotificationConfig" in params["configuration"]:
            config = params["configuration"]["pushNotificationConfig"]
            webhook_url = config.get("url")
            token = config.get("token")
        
        if not webhook_url:
            raise ValueError("No pushNotificationConfig.url found in request.")
        
        if not token:
            print(f"--- WARNING: No 'token' found in pushNotificationConfig. Auth will likely fail. ---")
        
        print(f"--- Webhook URL: {webhook_url} ---")
        print(f"--- Token Found: {'Yes' if token else 'No'} ---")

        # --- Pass the token to the background task ---
        background_tasks.add_task(
            process_and_send_response,
            country_name,
            webhook_url,
            request_id,
            token=token
        )

        # --- Return a proper JSON-RPC response with Task status ---
        task_response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "kind": "task",
                "id": request_id,
                "status": {
                    "state": "working",
                    "message": {
                        "kind": "message",
                        "role": "agent",
                        "parts": [{
                            "kind": "text",
                            "text": f"Fetching information about {country_name}... This will take a moment."
                        }],
                        "messageId": str(uuid.uuid4())
                    }
                }
            }
        }
        
        return Response(
            status_code=200,
            content=json.dumps(task_response),
            media_type="application/json"
        )

    except Exception as e:
        print(f"--- ERROR IN /tasks_send (sync part) ---")
        print(f"Error: {str(e)}")
        import traceback
        print(traceback.format_exc())
        print(f"--- Failing request body was: ---")
        print(json.dumps(raw_body, indent=2))
        return Response(status_code=500, content=f"Failed to process request: {str(e)}")

# --- Simple root endpoint for testing ---
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