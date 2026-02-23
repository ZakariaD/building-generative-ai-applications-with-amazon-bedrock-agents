import requests
from fastmcp import FastMCP
import logging
import os, sys
import boto3
import json
from starlette.requests import Request
from starlette.responses import PlainTextResponse

mcp = FastMCP("usajobs-search")
# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Log startup info
logger.info("Starting USAJobs MCP Server")
logger.info(f"Environment variables: AWS_REGION={os.getenv('AWS_REGION')}, MCP_SECRET_NAME={os.getenv('MCP_SECRET_NAME')}")


def _get_usajobs_credentials():
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

@mcp.custom_route("/", methods=["GET"])
async def root(request: Request) -> PlainTextResponse:
    return PlainTextResponse("USAJobs MCP Server")

@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> PlainTextResponse:
    return PlainTextResponse("OK")

@mcp.tool()
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
        email, api_key = _get_usajobs_credentials()
        
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

if __name__ == "__main__":
    mcp.run(host="0.0.0.0", transport="streamable-http")
    