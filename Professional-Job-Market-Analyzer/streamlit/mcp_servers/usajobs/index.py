import requests
from fastmcp import FastMCP
import logging
import os
import boto3
import json

mcp = FastMCP("usajobs-search")
logger = logging.getLogger(__name__)

def _get_usajobs_credentials():
    """Get USAJobs API credentials from AWS Secrets Manager"""
    try:
        secrets_client = boto3.client(
            'secretsmanager',
            region_name=os.getenv('AWS_REGION'),
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            aws_session_token=os.getenv('AWS_SESSION_TOKEN')
        )
        secret_name = os.getenv('USAJOBS_SECRET_NAME')
        
        if not secret_name:
            raise ValueError("USAJOBS_SECRET_NAME environment variable not set")
        
        response = secrets_client.get_secret_value(SecretId=secret_name)
        secret = json.loads(response['SecretString'])
        
        return secret['USAJOBS_EMAIL'], secret['USAJOBS_API_KEY']
    except Exception as e:
        raise ValueError(f"Failed to retrieve USAJobs credentials from Secrets Manager: {e}")

@mcp.tool()
def search_usajobs(keywords: str, location: str = '', limit: int = 10) -> str:
    """
    Search US government jobs using USAJobs API.
    
    Sample prompts:
    - "Find cybersecurity jobs in government"
    - "Search for data analyst positions in federal agencies"
    - "Look for government tech jobs in Washington DC"
    """
    try:
   
        email, api_key = _get_usajobs_credentials()
        
        if not email or not api_key:
            return "USAJobs credentials not found. Set USAJOBS_EMAIL and USAJOBS_API_KEY"
        
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
        
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        
        jobs = []
        for job in data.get('SearchResult', {}).get('SearchResultItems', []):
            job_data = job.get('MatchedObjectDescriptor', {})
            title = job_data.get('PositionTitle', 'Unknown Title')
            org = job_data.get('OrganizationName', 'Unknown Organization')
            location = job_data.get('PositionLocationDisplay', 'Unknown Location')
            summary = job_data.get('UserArea', {}).get('Details', {}).get('JobSummary', 'No summary')
            
            jobs.append(f"Job: {title} at {org} in {location}\nSummary: {summary[:200]}...")
        
        return "\n\n".join(jobs) if jobs else "No government jobs found"
        
    except Exception as e:
        logger.error(f"Error searching USAJobs: {e}")
        return f"Error: {e}"

    
if __name__ == "__main__":
    mcp.run()
    