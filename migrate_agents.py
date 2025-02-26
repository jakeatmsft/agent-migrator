import os  
import json  
import time  
from typing import List, Dict, Any  
import requests  
from openai import AzureOpenAI  
import logging  
import os
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential, AzureCliCredential
from dotenv import load_dotenv
load_dotenv()  # Load environment variables from .env file if needed
from azure.ai.projects.models import Tool, ToolSet, FunctionTool, CodeInterpreterTool

  
# Configure logging  
logging.basicConfig(level=logging.INFO)  
logger = logging.getLogger(__name__)  
  
# Initialize the Assistants API client  
assistants_client = AzureOpenAI(  
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),  
    api_version="2024-08-01-preview",  # Ensure this matches your API version  
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")  
)  
  
# Initialize the Agents API client (if different, modify accordingly)  

agent_client = AIProjectClient.from_connection_string(
    credential=AzureCliCredential(),
    conn_str=os.environ["PROJECT_CONNECTION_STRING"],
)  
  
def backup_assistants(assistants: List[Dict[str, Any]], filename: str = "assistants_backup.json"):
    """
    Back up the list of assistants to a JSON file.
    """
    # Convert each Assistant object to a dictionary
    assistants_data = [assistant.model_dump() for assistant in assistants]
    with open(filename, "w") as f:
        json.dump(assistants_data, f, indent=4)
    print(f"Assistants backed up to {filename}.")
  
def list_all_assistants(client: AzureOpenAI) -> List[Dict[str, Any]]:  
    """  
    List all assistants using the Assistants API.  
    """  
    try:  
        response = client.beta.assistants.list(order="desc", limit=100)  # Adjust limit as needed  
        assistants = response.data  # Assuming 'data' contains the list  
        print(f"Retrieved {len(assistants)} assistants.")  
        return assistants  
    except Exception as e:  
        print(f"Error retrieving assistants: {e}")  
        return []  
  
def transform_assistant_to_agent(assistant: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform an assistant's configuration to match the agent's expected format.
    Modify this function based on the actual differences between the APIs.
    """

    agent_payload = {
        "name": assistant.name,
        "instructions": assistant.instructions,
        "model": os.getenv("MODEL_DEPLOYMENT_NAME"),
        "tools": assistant.tools,
        # Add any additional required fields here
    }
    return agent_payload
  
def create_agent(client: AzureOpenAI, agent_config: Dict[str, Any]) -> bool:  
    """  
    Create an agent using the Agents API.  
    Returns True if creation is successful, False otherwise.  
    """  
    
    try:  
        toolset = ToolSet()
        for tool in agent_config.get("tools", [])  :
            if tool.type == "function":
                # Assuming 'function' tool type maps to FunctionTool
                toolset.add(FunctionTool(tool.function))  # Adjust based on actual structure
            elif tool.type == "code_interpreter":
                toolset.add(CodeInterpreterTool())
            else:
                print(f"Unsupported tool type: {tool.type}. Skipping.")
            
        agent = agent_client.agents.create_agent(
            model=os.getenv("MODEL_DEPLOYMENT_NAME"),  # Ensure this corresponds to the agent's model  
            name=agent_config["name"],  
            instructions=agent_config["instructions"],  
            toolset= toolset
            # Include other parameters if necessary  
        )  
        print(f"Successfully created agent: {agent.name}")  
        return True  
    except Exception as e:  
        print(f"Failed to create agent '{agent_config['name']}': {e}")  
        return False  
  
def create_agent_with_retries(client: AIProjectClient, agent_config: Dict[str, Any], max_retries: int = 5) -> bool:  
    """  
    Create an agent with retry logic in case of transient failures.  
    """  
    for attempt in range(1, max_retries + 1):  
        try:  
            success = create_agent(client, agent_config)  
            if success:  
                return True  
        except Exception as e:  
            logger.error(f"Attempt {attempt} - Error: {e}")  
            if attempt < max_retries:  
                sleep_time = 2 ** attempt  
                logger.info(f"Retrying in {sleep_time} seconds...")  
                time.sleep(sleep_time)  
            else:  
                logger.error(f"Exceeded maximum retries for agent '{agent_config['name']}'")  
                return False  
    return False  
  
def migrate_assistants_to_agents():  
    """  
    Orchestrate the migration of assistants to agents.  
    """  
    # Step 1: List all assistants  
    assistants = list_all_assistants(assistants_client)  
      
    if not assistants:  
        print("No assistants found. Exiting migration.")  
        return  
      
    # Step 2: Backup existing assistants  
    backup_assistants(assistants)  
      
    # Step 3: Iterate through each assistant and create an agent  
    for assistant in assistants:  
        agent_config = transform_assistant_to_agent(assistant)  
          
        # Optional: Check if the agent already exists to avoid duplicates  
        # Implement a function to check existing agents if necessary  
          
        # Step 4: Create the agent with retries  
        success = create_agent_with_retries(agent_client, agent_config)  
          
        if success:  
            print(f"Agent '{agent_config['name']}' created successfully.")  
        else:  
            print(f"Failed to create agent '{agent_config['name']}'. Check logs for details.")  
          
        # Optional: Add a delay to respect rate limits  
        time.sleep(1)  # Adjust as per API rate limits  
  
if __name__ == "__main__":  
    migrate_assistants_to_agents()  