import requests
from fastmcp import FastMCP
import logging
import matplotlib.pyplot as plt
import boto3
import os, sys
import json
from datetime import datetime
from starlette.requests import Request
from starlette.responses import PlainTextResponse


mcp = FastMCP("adzuna-search")
# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Log startup info
logger.info("Starting Adzuna MCP Server")
logger.info(f"Environment variables: AWS_REGION={os.getenv('AWS_REGION')}, MCP_SECRET_NAME={os.getenv('MCP_SECRET_NAME')}")

def _get_adzuna_credentials():
    """Get Adzuna API credentials from AWS Secrets Manager"""
    try:
        logger.debug("Attempting to retrieve Adzuna credentials from Secrets Manager")
        
        # Initialize boto3 session and get credentials
        secrets_client = boto3.client('secretsmanager')
        
        secret_name = os.getenv('MCP_SECRET_NAME')
        logger.debug(f"Using secret name: {secret_name}")
        
        if not secret_name:
            raise ValueError("MCP_SECRET_NAME environment variable not set")
        
        response = secrets_client.get_secret_value(SecretId=secret_name)
        secret = json.loads(response['SecretString'])
        logger.info("Successfully retrieved credentials from Secrets Manager")
        
        return secret['API_ID'], secret['API_KEY']
    except Exception as e:
        logger.error(f"Failed to retrieve Adzuna credentials: {e}")
        raise ValueError(f"Failed to retrieve Adzuna credentials from Secrets Manager: {e}")

@mcp.custom_route("/", methods=["GET"])
async def root(request: Request) -> PlainTextResponse:
    return PlainTextResponse("Adzuna MCP Server")

@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> PlainTextResponse:
    return PlainTextResponse("OK")

@mcp.tool()
def search_adzuna_jobs(keywords: str, location: str = 'us', limit: int = 10, 
                      salary_min: int = None, salary_max: int = None, 
                      company: str = None, full_time: bool = None,
                      location0: str = None, location1: str = None) -> str:
    """
    Advanced job search using Adzuna API with filters.
    
    Sample prompts:
    - "Find software engineer jobs paying over $100,000 in London"
    - "Search for full-time Python developer jobs at Google in NYC"
    - "Look for data scientist roles between $80k-$150k salary in San Francisco"
    
    :param keywords: Job search keywords
    :param location: Country code (us, gb, au, etc.)
    :param limit: Number of results (max 50)
    :param salary_min: Minimum salary filter
    :param salary_max: Maximum salary filter
    :param company: Company name filter
    :param full_time: Filter for full-time jobs only
    :param location0: First level location filter (e.g., 'UK', 'US')
    :param location1: Second level location filter (e.g., 'London', 'New York')
    """
    logger.info(f"Starting job search with keywords='{keywords}', location='{location}', limit={limit}")
    
    try:
        logger.debug("Retrieving Adzuna credentials")
        app_id, app_key = _get_adzuna_credentials()
        
        if not app_id or not app_key:
            logger.error("Adzuna credentials not found")
            return "Adzuna credentials not found. Check MCP_SECRET_NAME environment variable"
        
        logger.debug(f"Using app_id: {app_id[:5]}...")
        
        url = f"https://api.adzuna.com/v1/api/jobs/{location}/search/1"
        params = {
            'app_id': app_id,
            'app_key': app_key,
            'what': keywords,
            'results_per_page': min(limit, 50),
            'content-type': 'application/json'
        }
        
        if salary_min:
            params['salary_min'] = salary_min
        if salary_max:
            params['salary_max'] = salary_max
        if company:
            params['company'] = company
        if full_time is not None:
            params['full_time'] = 1 if full_time else 0
        if location0:
            params['location0'] = location0
        if location1:
            params['location1'] = location1
        
        logger.debug(f"Making API request to {url} with params: {params}")
        response = requests.get(url, params=params, timeout=30)
        logger.debug(f"API response status: {response.status_code}")
        
        response.raise_for_status()
        data = response.json()
        
        total_results = data.get('count', 0)
        logger.info(f"Found {total_results} total jobs")
        
        jobs = []
        for i, job in enumerate(data.get('results', [])):
            logger.debug(f"Processing job {i+1}")
            title = job.get('title', 'Unknown Title')
            company = job.get('company', {}).get('display_name', 'Unknown Company')
            location = job.get('location', {}).get('display_name', 'Unknown Location')
            salary = job.get('salary_min', 0)
            salary_max = job.get('salary_max', 0)
            contract_type = job.get('contract_type', 'Unknown')
            
            salary_info = f"${salary:,}" if salary else "Not specified"
            if salary_max and salary_max != salary:
                salary_info = f"${salary:,} - ${salary_max:,}"
            
            jobs.append(f"Job: {title} at {company}\nLocation: {location}\nSalary: {salary_info}\nType: {contract_type}")
        
        result_header = f"Found {total_results} jobs (showing {len(jobs)}):\n\n"
        result = result_header + "\n\n".join(jobs) if jobs else "No jobs found"
        logger.info(f"Returning {len(jobs)} job results")
        return result
        
    except requests.exceptions.RequestException as e:
        logger.error(f"API request error: {e}")
        return f"API request failed: {e}"
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {e}")
        return f"Failed to parse API response: {e}"
    except Exception as e:
        logger.error(f"Unexpected error searching Adzuna jobs: {e}", exc_info=True)
        return f"Error: {e}"

@mcp.tool()
def get_adzuna_salary_stats(keywords: str, location: str = 'us', location0: str = None, location1: str = None) -> str:
    """
    Get salary statistics for a job title/keyword.
    
    Sample prompts:
    - "What's the salary range for software engineers in London?"
    - "Show me salary statistics for data scientists in NYC"
    - "Python developer salary breakdown in San Francisco"
    
    :param keywords: Job search keywords
    :param location: Country code (us, gb, au, etc.)
    :param location0: First level location filter (e.g., 'UK', 'US')
    :param location1: Second level location filter (e.g., 'London', 'New York')
    """
    logger.info(f"Getting salary stats for keywords='{keywords}', location='{location}'")
    
    try:
        logger.debug("Retrieving Adzuna credentials")
        app_id, app_key = _get_adzuna_credentials()
        
        if not app_id or not app_key:
            logger.error("Adzuna credentials not found")
            return "Adzuna credentials not found. Check MCP_SECRET_NAME environment variable"
        
        logger.debug(f"Using app_id: {app_id[:5]}...")
        
        url = f"https://api.adzuna.com/v1/api/jobs/{location}/histogram"
        params = {
            'app_id': app_id,
            'app_key': app_key,
            'what': keywords,
            'content-type': 'application/json'
        }
        
        if location0:
            params['location0'] = location0
        if location1:
            params['location1'] = location1
        
        logger.debug(f"Making API request to {url} with params: {params}")
        response = requests.get(url, params=params, timeout=30)
        logger.debug(f"API response status: {response.status_code}")
        
        response.raise_for_status()
        data = response.json()
        
        histogram = data.get('histogram', {})
        if not histogram:
            logger.info(f"No salary data found for '{keywords}'")
            return f"No salary data found for '{keywords}'"
        
        logger.info(f"Found salary data with {len(histogram)} ranges")
        result = f"Salary Statistics for '{keywords}' in {location.upper()}:\n\n"
        
        for salary_range, count in histogram.items():
            result += f"${salary_range}: {count} jobs\n"
        
        logger.info("Returning salary statistics")
        return result
        
    except requests.exceptions.RequestException as e:
        logger.error(f"API request error: {e}")
        return f"API request failed: {e}"
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {e}")
        return f"Failed to parse API response: {e}"
    except Exception as e:
        logger.error(f"Unexpected error getting salary stats: {e}", exc_info=True)
        return f"Error: {e}"

@mcp.tool()
def get_adzuna_salary_chart(keywords: str, location: str = 'us', location0: str = None, location1: str = None, save_path: str = None) -> str:
    """
    Generate a visual salary histogram chart for a job title/keyword.
    
    Sample prompts:
    - "Create a salary chart for software engineers in London"
    - "Generate salary histogram for data scientists in New York"
    - "Show me a visual salary breakdown for Python developers in San Francisco"
    
    :param keywords: Job search keywords
    :param location: Country code (us, gb, au, etc.)
    :param location0: First level location filter (e.g., 'UK', 'US')
    :param location1: Second level location filter (e.g., 'London', 'New York')
    :param save_path: Optional path to save the chart image
    """
    logger.info(f"Generating salary chart for keywords='{keywords}', location='{location}'")
    
    try:
        logger.debug("Retrieving Adzuna credentials")
        app_id, app_key = _get_adzuna_credentials()
        
        if not app_id or not app_key:
            logger.error("Adzuna credentials not found")
            return "Adzuna credentials not found. Check MCP_SECRET_NAME environment variable"
        
        logger.debug(f"Using app_id: {app_id[:5]}...")
        
        url = f"https://api.adzuna.com/v1/api/jobs/{location}/histogram"
        params = {
            'app_id': app_id,
            'app_key': app_key,
            'what': keywords,
            'content-type': 'application/json'
        }
        
        # Add location hierarchy filters
        if location0:
            params['location0'] = location0
        if location1:
            params['location1'] = location1
        
        logger.debug(f"Making API request to {url} with params: {params}")
        response = requests.get(url, params=params, timeout=30)
        logger.debug(f"API response status: {response.status_code}")
        
        response.raise_for_status()
        data = response.json()
        
        histogram = data.get('histogram', {})
        if not histogram:
            logger.info(f"No salary data found for '{keywords}'")
            return f"No salary data found for '{keywords}'"
        
        logger.info(f"Found salary data with {len(histogram)} ranges")
        
        # Parse salary ranges and job counts
        salary_ranges = []
        job_counts = []
        
        for salary_range, count in histogram.items():
            # Extract numeric values from salary ranges like "40000-50000"
            if '-' in salary_range:
                min_sal, max_sal = salary_range.split('-')
                avg_salary = (int(min_sal) + int(max_sal)) / 2
            else:
                avg_salary = int(salary_range)
            
            salary_ranges.append(avg_salary)
            job_counts.append(count)
        
        # Sort by salary range
        sorted_data = sorted(zip(salary_ranges, job_counts))
        salary_ranges, job_counts = zip(*sorted_data)
        
        # Create the chart with better colors
        plt.figure(figsize=(14, 9))
        colors = ['#2E86AB', '#A23B72', '#F18F01', '#C73E1D', '#6A994E', '#7209B7', '#F72585', '#4361EE']
        bar_colors = [colors[i % len(colors)] for i in range(len(salary_ranges))]
        
        bars = plt.bar(range(len(salary_ranges)), job_counts, 
                      color=bar_colors, alpha=0.8, edgecolor='white', linewidth=2)
        
        # Customize the chart with better styling
        plt.style.use('default')
        plt.gca().set_facecolor('#f8f9fa')
        plt.gcf().patch.set_facecolor('white')
        
        location_str = f"{location0.upper()}/{location1.upper()}" if location0 and location1 else location.upper()
        plt.title(f'Salary Distribution for "{keywords}" in {location_str}', 
                 fontsize=18, fontweight='bold', pad=25, color='#2c3e50')
        plt.xlabel('Salary Range (USD)', fontsize=14, fontweight='bold', color='#34495e')
        plt.ylabel('Number of Jobs', fontsize=14, fontweight='bold', color='#34495e')
        
        # Format x-axis labels with better styling
        salary_labels = [f'${int(sal/1000)}K' for sal in salary_ranges]
        plt.xticks(range(len(salary_ranges)), salary_labels, rotation=45, fontsize=12, color='#2c3e50')
        plt.yticks(fontsize=12, color='#2c3e50')
        
        # Add value labels on bars with better contrast
        for i, (bar, count) in enumerate(zip(bars, job_counts)):
            plt.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(job_counts)*0.02,
                    str(count), ha='center', va='bottom', fontweight='bold', 
                    fontsize=11, color='#2c3e50')
        
        # Add grid for better readability
        plt.grid(axis='y', alpha=0.4, linestyle='-', linewidth=0.5, color='#bdc3c7')
        
        # Add statistics text with better styling
        total_jobs = sum(job_counts)
        avg_jobs_per_range = total_jobs / len(job_counts)
        stats_text = f'Total Jobs: {total_jobs}\nAvg per Range: {avg_jobs_per_range:.0f}'
        plt.text(0.02, 0.98, stats_text, transform=plt.gca().transAxes, 
                verticalalignment='top', fontsize=12, fontweight='bold',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='#ecf0f1', 
                         edgecolor='#34495e', alpha=0.9), color='#2c3e50')
        
        plt.tight_layout()
        
        # Save the chart to S3
        if not save_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"salary_chart_{keywords.replace(' ', '_')}_{location}_{timestamp}.png"
            save_path = filename
        
        # Save to temporary file first
        temp_path = f"/tmp/{save_path}"
        plt.savefig(temp_path, dpi=300, bbox_inches='tight')
        plt.close()
        
        # Upload to S3
        bucket_name = os.getenv('CHARTS_BUCKET_NAME')
        if bucket_name:
            try:
                s3_client = boto3.client('s3')
                s3_client.upload_file(temp_path, bucket_name, save_path)
                logger.info(f"Chart uploaded to S3: s3://{bucket_name}/{save_path}")
                # Clean up temp file
                os.remove(temp_path)
                save_path = f"s3://{bucket_name}/{save_path}"
            except Exception as e:
                logger.error(f"Failed to upload chart to S3: {e}")
                os.remove(temp_path)
                return f"Error uploading chart to S3: {e}"
        else:
            logger.error("CHARTS_BUCKET_NAME environment variable not set")
            os.remove(temp_path)
            return "Error: S3 bucket not configured for chart storage"
        
        # Return summary with chart path
        result = f"Salary Chart Generated for '{keywords}' in {location.upper()}:\n\n"
        result += f"Chart saved to: {save_path}\n\n"
        result += "Salary Distribution Summary:\n"
        
        for salary, count in zip(salary_ranges, job_counts):
            result += f"${salary/1000:.0f}K: {count} jobs\n"
        
        result += f"\nTotal Jobs Analyzed: {total_jobs}"
        
        logger.info("Successfully generated salary chart")
        return result
        
    except requests.exceptions.RequestException as e:
        logger.error(f"API request error: {e}")
        return f"API request failed: {e}"
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {e}")
        return f"Failed to parse API response: {e}"
    except Exception as e:
        logger.error(f"Unexpected error generating salary chart: {e}", exc_info=True)
        return f"Error: {e}"

@mcp.tool()
def get_adzuna_job_categories(location: str = 'us', location0: str = None, location1: str = None) -> str:
    """
    Get available job categories and their job counts.
    
    Sample prompts:
    - "Show me all job categories in London"
    - "What are the top job categories in NYC?"
    - "List job market categories in San Francisco"
    
    :param location: Country code (us, gb, au, etc.)
    :param location0: First level location filter (e.g., 'UK', 'US')
    :param location1: Second level location filter (e.g., 'London', 'New York')
    """
    try:
        app_id, app_key = _get_adzuna_credentials()
        
        url = f"https://api.adzuna.com/v1/api/jobs/{location}/categories"
        params = {
            'app_id': app_id,
            'app_key': app_key,
            'content-type': 'application/json'
        }
        
        if location0:
            params['location0'] = location0
        if location1:
            params['location1'] = location1
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        
        categories = data.get('results', [])
        if not categories:
            return "No categories found"
        
        result = f"Job Categories in {location.upper()}:\n\n"
        
        for category in categories[:20]:  # Show top 20
            tag = category.get('tag', 'Unknown')
            count = category.get('count', 0)
            result += f"{tag}: {count:,} jobs\n"
        
        return result
        
    except Exception as e:
        logger.error(f"Error getting job categories: {e}")
        return f"Error: {e}"

@mcp.tool()
def get_adzuna_top_companies(location: str = 'us', limit: int = 20, location0: str = None, location1: str = None) -> str:
    """
    Get top companies by job count.
    
    Sample prompts:
    - "Who are the top hiring companies in London?"
    - "Show me top 10 companies by job postings in NYC"
    - "Which companies are hiring the most in San Francisco?"
    
    :param location: Country code (us, gb, au, etc.)
    :param limit: Number of companies to return (default 20)
    :param location0: First level location filter (e.g., 'UK', 'US')
    :param location1: Second level location filter (e.g., 'London', 'New York')
    """
    try:
        app_id, app_key = _get_adzuna_credentials()
        
        url = f"https://api.adzuna.com/v1/api/jobs/{location}/top_companies"
        params = {
            'app_id': app_id,
            'app_key': app_key,
            'content-type': 'application/json'
        }
        
        if location0:
            params['location0'] = location0
        if location1:
            params['location1'] = location1
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        
        companies = data.get('leaderboard', [])
        if not companies:
            return "No company data found"
        
        result = f"Top Companies in {location.upper()} (by job count):\n\n"
        
        for i, company in enumerate(companies[:limit], 1):
            name = company.get('canonical_name', 'Unknown')
            count = company.get('count', 0)
            result += f"{i}. {name}: {count:,} jobs\n"
        
        return result
        
    except Exception as e:
        logger.error(f"Error getting top companies: {e}")
        return f"Error: {e}"

@mcp.tool()
def search_adzuna_by_location(keywords: str, where: str, location: str = 'us', limit: int = 10) -> str:
    """
    Search jobs by specific location (city, state, etc.).
    
    Sample prompts:
    - "Find software engineer jobs in San Francisco"
    - "Search for data scientist roles in New York City"
    - "Look for tech jobs in Austin, Texas"
    
    :param keywords: Job search keywords
    :param where: Specific location (e.g., "New York", "San Francisco")
    :param location: Country code (us, gb, au, etc.)
    :param limit: Number of results
    """
    try:
        app_id, app_key = _get_adzuna_credentials()
        
        url = f"https://api.adzuna.com/v1/api/jobs/{location}/search/1"
        params = {
            'app_id': app_id,
            'app_key': app_key,
            'what': keywords,
            'where': where,
            'results_per_page': min(limit, 50),
            'content-type': 'application/json'
        }
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        
        jobs = []
        for job in data.get('results', []):
            title = job.get('title', 'Unknown Title')
            company = job.get('company', {}).get('display_name', 'Unknown Company')
            location_name = job.get('location', {}).get('display_name', 'Unknown Location')
            salary = job.get('salary_min', 0)
            
            salary_info = f"${salary:,}" if salary else "Not specified"
            jobs.append(f"Job: {title} at {company}\nLocation: {location_name}\nSalary: {salary_info}")
        
        total_results = data.get('count', 0)
        result_header = f"Jobs for '{keywords}' in {where} (Found {total_results}):\n\n"
        
        return result_header + "\n\n".join(jobs) if jobs else f"No jobs found for '{keywords}' in {where}"
        
    except Exception as e:
        logger.error(f"Error searching jobs by location: {e}")
        return f"Error: {e}"


@mcp.tool()
def get_adzuna_job_details(job_id: str, location: str = 'us') -> str:
    """
    Get detailed information about a specific job posting.
    
    Sample prompts:
    - "Get details for job ID 12345"
    - "Show me full information for this job posting"
    
    :param job_id: Unique job identifier
    :param location: Country code (us, gb, au, etc.)
    """
    try:
        app_id, app_key = _get_adzuna_credentials()
        
        response = requests.get(
            f"https://api.adzuna.com/v1/api/jobs/{location}/details/{job_id}",
            params={'app_id': app_id, 'app_key': app_key, 'content-type': 'application/json'}
        )
        response.raise_for_status()
        job = response.json()
        
        # Extract job data with defaults
        title = job.get('title', 'Unknown Title')
        company = job.get('company', {}).get('display_name', 'Unknown Company')
        location_info = job.get('location', {}).get('display_name', 'Unknown Location')
        description = job.get('description', 'No description available')
        salary_min = job.get('salary_min', 0)
        salary_max = job.get('salary_max', 0)
        contract_type = job.get('contract_type', 'Unknown')
        created = job.get('created', 'Unknown')
        
        # Format salary
        if salary_min and salary_max:
            salary_info = f"${salary_min:,} - ${salary_max:,}"
        elif salary_min:
            salary_info = f"${salary_min:,}+"
        else:
            salary_info = "Not specified"
        
        # Build result
        return f"""Job Details:

Title: {title}
Company: {company}
Location: {location_info}
Salary: {salary_info}
Contract Type: {contract_type}
Posted: {created}

Description:
{description[:1000]}..."""
        
    except Exception as e:
        logger.error(f"Error getting job details: {e}")
        return f"Error: {e}"

@mcp.tool()
def search_adzuna_geodata(location_query: str, location: str = 'us') -> str:
    """
    Search for location data and get geographic job market info.
    
    Sample prompts:
    - "Find job market data for San Francisco"
    - "Search locations matching 'New York'"
    - "Get geographic data for tech hubs in California"
    
    :param location_query: Location search term
    :param location: Country code (us, gb, au, etc.)
    """
    try:
        app_id, app_key = _get_adzuna_credentials()
        
        params = {
            'app_id': app_id,
            'app_key': app_key,
            'q': location_query,
            'content-type': 'application/json'
        }
        
        response = requests.get(
            f"https://api.adzuna.com/v1/api/geodata/{location}/locations",
            params=params
        )
        response.raise_for_status()
        data = response.json()
        
        locations = data.get('locations', [])
        if not locations:
            return f"No location data found for '{location_query}'"
        
        result = f"Location Data for '{location_query}':\n\n"
        
        for loc in locations[:10]:  # Limit to top 10
            display_name = loc.get('display_name', 'Unknown')
            area = loc.get('area', [])
            area_str = ' > '.join(area) if area else 'Unknown Area'
            
            result += f"Location: {display_name}\nArea: {area_str}\n\n"
        
        return result
        
    except Exception as e:
        logger.error(f"Error searching geodata: {e}")
        return f"Error: {e}"
    

if __name__ == "__main__":
    mcp.run(host="0.0.0.0", transport="streamable-http")
    