import os
import openai
import requests
import json
from typing import List, Dict
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file

# --- Logging ---
def log(message: str):
    print(f"[INFO] {message}")

# --- OpenAI Client Initialization ---
def initialize_client(api_key: str, endpoint: str, api_version: str = "2024-08-01-preview") -> openai.OpenAI:
    return openai.AzureOpenAI(
        api_version=api_version,
        azure_endpoint=endpoint,
        api_key=api_key
    )

# --- Thread Operations ---
def list_threads(client: openai.OpenAI) -> List[Dict]:
    endpoint = f"{client.base_url}/threads"
    headers = {
        'api-key': os.getenv("AZURE_OPENAI_API_KEY"),
        'Content-Type': 'application/json',
    }
    params = {
        'api-version': '2024-08-01-preview',
    }
    response = requests.get(endpoint, headers=headers, params=params)
    response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
    return response.json()['data']

def retrieve_messages(client: openai.OpenAI, thread_id: str) -> List[Dict]:
    messages = []
    for message in client.beta.threads.messages.list(thread_id=thread_id):
        messages.append(message)
    return messages

def generate_summary(client: openai.OpenAI, messages: List[Dict], api_key: str, endpoint: str) -> str:
    prompt = "Summarize the following conversation threads:\n\n"
    for msg in reversed(messages):
        prompt += f"Agent:{msg.assistant_id}, "
        for content in msg.content:
            if content.type == "text":
                prompt += f"Text:{content.text.value}\n"
            elif content.type == "image_file":
                prompt += f"Image File ID: {content.image_file.file_id}\n"
            else:
                prompt += f"Unknown content type: {content.type}\n"

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a helpful assistant that summarizes conversations."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=1000,
        temperature=0,
    )
    return response.choices[0].message.content

def create_thread(proj_client: AIProjectClient, messages: List[Dict], metadata: Dict, tool_resources: Dict = None, thread_agent_id: str = None) -> Dict:
    payload = {
        "messages": messages,
        "metadata": metadata
    }
    if tool_resources:
        payload["tool_resources"] = tool_resources
        
    thread_reference={
        "orig_thread_id": metadata['orig_thread_id'],
    }

    thread = proj_client.agents.create_thread()
    proj_client.agents.update_thread(thread.id, metadata=thread_reference)
    # Assuming create_message takes content directly, not a structured message
    message = proj_client.agents.create_message(thread_id=thread.id, role="user", content=metadata['summary'])
    return thread

# --- Main Migration ---
def migrate_threads():
    # Initialize source client
    source_client = initialize_client(
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
    )

    log(f"Project Connection String: {os.getenv('PROJECT_CONNECTION_STRING')}")

    with AIProjectClient.from_connection_string(
        credential=DefaultAzureCredential(),
        conn_str=os.getenv("PROJECT_CONNECTION_STRING")
    ) as project_client:
        # Explicit type hinting for IntelliSense
        destination_client = project_client.inference.get_azure_openai_client(
            api_version = os.getenv("AZURE_OPENAI_API_VERSION"),
        )

        log("Listing threads from the source client...")
        threads = list_threads(source_client)
        log(f"Found {len(threads)} threads to migrate.")

        # Get first agent from destination client
        agent = project_client.agents.list_agents().data[0]
        log(f"Using agent ID: {agent.id}")

        for thread in threads:
            thread_id = thread.get('id')
            log(f"Migrating thread ID: {thread_id}")

            # Retrieve messages from the source thread
            messages = retrieve_messages(source_client, thread_id)          
            
            log(f"Retrieved {len(messages)} messages from thread ID: {thread_id}")

            if not messages:
                log(f"No messages found for thread ID: {thread_id}. Skipping migration.")
                continue
            
            #create backup folder "backup" if it doesn't exist
            if not os.path.exists("backup"):
                os.makedirs("backup")
            
            #backup messages save messages as json file in backup folder
            serializable_messages = [msg.model_dump() for msg in messages]
            with open(f"backup/{thread_id}.json", "w") as f:
                json.dump(serializable_messages, f, indent=4)
            
            # Generate a summary of the messages
            summary = generate_summary(
                client = destination_client,
                messages=messages,
                api_key=os.getenv("AZURE_OPENAI_API_KEY_SOURCE"),
                endpoint=os.getenv("AZURE_OPENAI_ENDPOINT_SOURCE")
            )
            log(f"Generated summary for thread ID: {thread_id}")

            # Prepare metadata with the summary
            metadata = thread.get('metadata', {})
            metadata['orig_thread_id'] = thread_id
            metadata['summary'] = summary

            # Handle tool_resources if present
            tool_resources = thread.get('tool_resources', {})

            # Create the thread in the destination client
            new_thread = create_thread(
                proj_client=project_client,
                messages=messages,
                metadata=metadata,
                tool_resources=tool_resources,
                thread_agent_id=agent.id
            )
            new_thread_id = new_thread.id
            log(f"Created new thread with ID: {new_thread_id} in the destination client.\n")

    log("Migration completed successfully.")

# --- Main Execution ---
if __name__ == "__main__":
    try:
        migrate_threads()
    except Exception as e:
        log(f"An error occurred during migration: {str(e)}")