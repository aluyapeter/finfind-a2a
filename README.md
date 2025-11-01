# FinFind: A Python-based A2A AI Agent

FinFind is an AI agent built with Python, FastAPI, and Groq, designed to integrate with the **Telex.im** platform. It functions as an "AI Coworker" that can provide a brief history and a list of the top 5 fintech startups for any given country.

###  deployed_url
`https://finfind-a2a-production.up.railway.app/`

### Features

* **A2A Compliant:** Implements the Agent-to-Agent (A2A) protocol.
* **AI Powered:** Uses the Groq API with LLaMA 3.1 for fast and accurate data retrieval.
* **Robust Parsing:** Includes advanced parsing for both incoming Telex requests and "dirty" JSON from the AI.
* **Telex Integrated:** Connects directly to the Telex.im platform as an "AI Colleague" using a synchronous (blocking) response.
* **Deployable:** Configured for easy deployment on Railway.

### Tech Stack

* **Backend:** Python 3.12
* **Framework:** FastAPI
* **AI:** Groq (using `llama-3.1-8b-instant`)
* **Server:** Uvicorn
* **Deployment:** Railway (via `Procfile`)
* **Core Libraries:** `httpx`, `pydantic`

---

## How It Works: Architecture

The agent follows the A2A protocol, which consists of two main parts:

1.  **The Manifest (`/.well-known/agent.json`)**
    This is the agent's public "business card". When Telex (or any other A2A platform) first connects, it reads this file to learn the agent's name, description, and (most importantly) the endpoint where it can send tasks.

2.  **The Task Endpoint (`/tasks/send`)**
    This is the "front door" for all work. All requests from Telex are sent to this single `POST` endpoint. The logic in `main.py` is responsible for:
    * Parsing the complex JSON-RPC request from Telex.
    * Finding the *actual* user message (e.g., "Nigeria") inside a messy `parts` array.
    * Calling the `CountryService` (the "brain") to do the work.
    * Formatting the AI's response into the *exact* JSON-RPC response structure that Telex expects.
    * Returning this response **synchronously** (blocking) to display it in the chat.

---

## 🔧 Setup and Installation (Local)

To run this project on your local machine:

### 1. Prerequisites
* Python 3.10+
* A Groq API Key (get one from [groq.com](https://groq.com/))

### 2. Installation
1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/your-username/finfind-a2a.git](https://github.com/your-username/finfind-a2a.git)
    cd finfind-a2a
    ```

2.  **Create and activate a virtual environment:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Set Environment Variables:**
    Create a `.env` file in the root directory and add your API key:
    ```
    GROQ_API_KEY="your-groq-api-key-here"
    AGENT_BASE_URL="http://localhost:8000"
    ```

### 3. Run the Server
1.  Load the environment variables (or set them manually):
    ```bash
    export $(grep -v '^#' .env | xargs)
    ```

2.  Run the Uvicorn server from the root directory:
    ```bash
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
    ```
    The agent is now running on `http://localhost:8000`.

---

## 🚀 Deployment (Railway)

This project is configured to deploy directly to Railway.

1.  **`Procfile`:** The root of this project contains a `Procfile`:
    ```
    web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
    ```
    This tells Railway how to start the web server, correctly using the port Railway provides.

2.  **Environment Variables:** In your Railway project's "Variables" tab, you must set:
    * `GROQ_API_KEY`: Your Groq API key.
    * `AGENT_BASE_URL`: Your public Railway URL (e.g., `https://finfind-a2a-production.up.railway.app`).

---

## 🤖 Telex.im Integration

To add this agent to your Telex.im workspace:

1.  Log in to Telex.
2.  Find the "AI Coworkers" section and choose to add or create a new one.
3.  You will be prompted to paste a "Workflow JSON".
4.  Paste the following JSON, making sure to **use your own public Railway URL** in the `url` field.

```json
{
  "active": false,
  "category": "utilities",
  "description": "An agent that provides history and top 5 fintech startups for a specific country.",
  "id": "country_info_agent_01",
  "long_description": "\n      You are a helpful research assistant. Your primary function is to help users get details for a specific country.\n\n      When a user provides a country name, you will use your 'get_country_details' skill.\n\n      You will return:\n      1. A brief history of the country.\n      2. A list of the top 5 fintech startups in that country.\n    ",
  "name": "FinFind Agent",
  "nodes": [
    {
      "id": "country_info_node",
      "name": "Country Info Node",
      "parameters": {},
      "position": [
        800,
        -100
      ],
      "type": "a2a/mastra-a2a-node",
      "typeVersion": 1,
      "url": "https://finfind-a2a-production.up.railway.app/tasks/send"
    }
  ],
  "pinData": {},
  "settings": {
    "executionOrder": "v1"
  },
  "short_description": "Provides country history and fintech info."
}
