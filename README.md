# agent-migrator
Migration tool for moving OpenAI and Azure OpenAI Assistants -> AI Agent Service

## Setup Instructions

### 1. Install Requirements

```bash
pip install -r requirements.txt
```

### 2. Set Environment Variables

```bash
AZURE_OPENAI_API_KEY="your_azure_openai_api_key"
OPENAI_API_VERSION="2024-08-01-preview" # or your desired API version
AZURE_OPENAI_ENDPOINT="your_azure_openai_endpoint"
PROJECT_CONNECTION_STRING="your_project_connection_string"
MODEL_DEPLOYMENT_NAME="your_model_deployment_name"
```
### 3. Run the Agent Migration Script

```bash
python migrate_agents.py
```
#### Verify
Login to your AI Agent Service account and verify that the agents have been migrated successfully.

### 4 Run Thread Migration Script

```bash
python migrate_threads.py
```
#### Verify
Login to your AI Agent Service account and verify that the threads have been migrated successfully.
