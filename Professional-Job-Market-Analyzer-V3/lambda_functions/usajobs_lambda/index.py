import json
import requests
import boto3
import os, sys
import logging

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

def get_usajobs_credentials():
    """Get USAJobs API credentials from AWS Secrets Manager"""
    try:
        logger.debug("Attempting to retrieve USAJobs credentials from Secrets Manager")
        
        # Initialize boto3 session and get credentials
        secrets_client = boto3.client('secretsmanager')
        
        secret_name = os.getenv('MCP_SECRET_NAME')
        logger.debug(f"Using secret name: {secret_name}")
        
        secret_name = os.getenv('MCP_SECRET_NAME')
        logger.debug(f"Using secret name: {secret_name}")
        
        if not secret_name:
            raise ValueError("MCP_SECRET_NAME environment variable not set")
        
        response = secrets_client.get_secret_value(SecretId=secret_name)
        secret = json.loads(response['SecretString'])
        logger.info("Successfully retrieved credentials from Secrets Manager")
        
        return secret['API_ID'], secret['API_KEY']
    except Exception as e:
        logger.error(f"Failed to retrieve USAJobs credentials: {e}")
        raise ValueError(f"Failed to retrieve USAJobs credentials from Secrets Manager: {e}")


def search_usajobs(keywords: str, location: str = '', limit: int = 10) -> str:
    """
    Search US government jobs using USAJobs API.
    
    Sample prompts:
    - "Find cybersecurity jobs in government"
    - "Search for data analyst positions in federal agencies"
    - "Look for government tech jobs in Washington DC"
    """
    logger.info(f"Starting job search with keywords='{keywords}', location='{location}', limit={limit}")
    
    try:
        logger.debug("Retrieving USAJobs credentials")
        email, api_key = get_usajobs_credentials()
        
        if not email or not api_key:
            logger.error("USAJobs credentials not found")
            return "USAJobs credentials not found. Check MCP_SECRET_NAME environment variable"
        
        logger.debug(f"Using email: {email[:5]}...@{email.split('@')[1] if '@' in email else 'unknown'}")
        
        url = "https://data.usajobs.gov/api/search"
        headers = {
            'Host': 'data.usajobs.gov',
            'User-Agent': email,
            'Authorization-Key': api_key
        }
        
        params = {
            'Keyword': keywords,
            'LocationName': location,
            'ResultsPerPage': limit
        }
        
        logger.debug(f"Making API request to {url} with params: {params}")
        response = requests.get(url, headers=headers, params=params, timeout=30)
        logger.debug(f"API response status: {response.status_code}")
        
        response.raise_for_status()
        data = response.json()
        
        total_jobs = data.get('SearchResult', {}).get('SearchResultCount', 0)
        logger.info(f"Found {total_jobs} total jobs")
        
        jobs = []
        for i, job in enumerate(data.get('SearchResult', {}).get('SearchResultItems', [])):
            logger.debug(f"Processing job {i+1}")
            job_data = job.get('MatchedObjectDescriptor', {})
            title = job_data.get('PositionTitle', 'Unknown Title')
            org = job_data.get('OrganizationName', 'Unknown Organization')
            location = job_data.get('PositionLocationDisplay', 'Unknown Location')
            summary = job_data.get('UserArea', {}).get('Details', {}).get('JobSummary', 'No summary')
            
            jobs.append(f"Job: {title} at {org} in {location}\nSummary: {summary[:200]}...")
        
        result = "\n\n".join(jobs) if jobs else "No government jobs found"
        logger.info(f"Returning {len(jobs)} job results")
        return result
        
    except requests.exceptions.RequestException as e:
        logger.error(f"API request error: {e}")
        return f"API request failed: {e}"
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {e}")
        return f"Failed to parse API response: {e}"
    except Exception as e:
        logger.error(f"Unexpected error searching USAJobs: {e}", exc_info=True)
        return f"Error: {e}"


def lambda_handler(event, context):
    """Lambda handler for USAJobs search"""
    try:
        logger.info(f"Received event: {json.dumps(event)}")
        logger.info(f"Context: {context}")
        
        # Get tool name from Bedrock Agent Core context
        tool_name = context.client_context.custom['bedrockAgentCoreToolName']
        params = event  # Event contains the parameters directly
        
        logger.info(f"Original tool name: {tool_name}")
        
        # Extract actual tool name after delimiter
        delimiter = "___"
        if delimiter in tool_name:
            tool_name = tool_name[tool_name.index(delimiter) + len(delimiter):]
        
        logger.info(f"Converted tool name: {tool_name}")
        
        if tool_name == 'search_usajobs':
            result = search_usajobs(**params)
        else:
            result = f"Unknown tool: {tool_name}"
        
        return {
            'statusCode': 200,
            'body': result
        }
        
    except Exception as e:
        logger.error(f"Lambda handler error: {e}")
        return {
            'statusCode': 500,
            'body': f"Error: {str(e)}"
        }