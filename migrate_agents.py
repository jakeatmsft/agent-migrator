import os
import json
import time
from typing import List, Dict, Any
import logging
import requests
from openai import AzureOpenAI
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv
from azure.ai.projects.models import FunctionTool, CodeInterpreterTool, ToolSet

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize Azure OpenAI Assistants API client
assistants_client = AzureOpenAI(
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version=os.getenv("OPENAI_API_VERSION"), 
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
)

# Initialize Azure AI Agents API client
agent_client = AIProjectClient.from_connection_string(
    credential=DefaultAzureCredential(),
    conn_str=os.environ["PROJECT_CONNECTION_STRING"],
)

def backup_assistants(assistants: List[Dict[str, Any]], filename: str = "assistants_backup.json"):
    """Backs up a list of assistant objects to a JSON file."""
    assistants_data = [assistant.model_dump() for assistant in assistants]
    try:
        #create backup folder "backup" if it doesn't exist
        if not os.path.exists("backup"):
            os.makedirs("backup")
        with open(f"backup/{filename}", "w") as f:
            json.dump(assistants_data, f, indent=4)
        logger.info(f"Assistants backed up to {filename}")
    except Exception as e:
        logger.error(f"Failed to backup assistants to {filename}: {e}")

def list_all_assistants(client: AzureOpenAI) -> List[Dict[str, Any]]:
    """Lists all assistants from the Assistants API."""
    try:
        response = client.beta.assistants.list(order="desc", limit=100)
        assistants = response.data
        logger.info(f"Retrieved {len(assistants)} assistants.")
        return assistants
    except Exception as e:
        logger.error(f"Error retrieving assistants: {e}")
        return []

def transform_assistant_to_agent(assistant: Dict[str, Any]) -> Dict[str, Any]:
    """Transforms an assistant's configuration to match the agent's expected format."""
    agent_payload = {
        "name": assistant.name,
        "instructions": assistant.instructions,
        "model": os.getenv("MODEL_DEPLOYMENT_NAME"),
        "tools": assistant.tools,
    }
    return agent_payload

def create_agent(client: AIProjectClient, agent_config: Dict[str, Any]) -> bool:
    """Creates an agent using the Agents API."""
    try:
        toolset = ToolSet()
        for tool in agent_config.get("tools", []):
            if tool.type == "function":
                toolset.add(FunctionTool(tool.function))
            elif tool.type == "code_interpreter":
                toolset.add(CodeInterpreterTool())
            else:
                logger.warning(f"Unsupported tool type: {tool.type}. Skipping.")

        agent = client.agents.create_agent(
            model=os.getenv("MODEL_DEPLOYMENT_NAME"),
            name=agent_config["name"],
            instructions=agent_config["instructions"],
            toolset=toolset
        )
        logger.info(f"Successfully created agent: {agent.name}")
        return True
    except Exception as e:
        logger.error(f"Failed to create agent '{agent_config['name']}': {e}")
        return False

def create_agent_with_retries(client: AIProjectClient, agent_config: Dict[str, Any], max_retries: int = 3) -> bool:
    """Creates an agent with retry logic in case of transient failures."""
    for attempt in range(1, max_retries + 1):
        try:
            if create_agent(client, agent_config):
                return True
        except Exception as e:
            logger.error(f"Attempt {attempt} - Error creating agent: {e}")
            if attempt < max_retries:
                sleep_time = 2 ** attempt
                logger.info(f"Retrying in {sleep_time} seconds...")
                time.sleep(sleep_time)
            else:
                logger.error(f"Exceeded maximum retries for agent '{agent_config['name']}'")
                return False
    return False

def migrate_assistants_to_agents():
    """Orchestrates the migration of assistants to agents."""
    # Step 1: List all assistants
    assistants = list_all_assistants(assistants_client)

    if not assistants:
        logger.info("No assistants found. Exiting migration.")
        return

    # Step 2: Backup existing assistants
    backup_assistants(assistants)

    # Step 3: Iterate through each assistant and create an agent
    for assistant in assistants:
        agent_config = transform_assistant_to_agent(assistant)

        # Step 4: Create the agent with retries
        if create_agent_with_retries(agent_client, agent_config):
            logger.info(f"Agent '{agent_config['name']}' created successfully.")
        else:
            logger.error(f"Failed to create agent '{agent_config['name']}'. Check logs for details.")

        # Optional: Add a delay to respect rate limits
        time.sleep(1)  # Adjust as per API rate limits

if __name__ == "__main__":
    migrate_assistants_to_agents()