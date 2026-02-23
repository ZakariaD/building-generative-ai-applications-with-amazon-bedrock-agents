from mcp import StdioServerParameters, stdio_client
from strands import Agent, tool
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient
import os, boto3

# Initialize boto3 session and get credentials
session = boto3.Session()
credentials = session.get_credentials()
aws_region = session.region_name or os.getenv("AWS_REGION", "us-east-1")

# Extract credentials for MCP servers
aws_env = {
    "AWS_REGION": aws_region,
    "AWS_ACCESS_KEY_ID": credentials.access_key,
    "AWS_SECRET_ACCESS_KEY": credentials.secret_key,
    "AWS_SESSION_TOKEN": credentials.token if credentials.token else ""
}

# Adzuna MCP Client
adzuna_client = MCPClient(
    lambda: stdio_client(
        StdioServerParameters(
            command="python3", 
            args=["/app/mcp_servers/adzuna/index.py"],
            env={
                "ADZUNA_SECRET_NAME": os.getenv("ADZUNA_SECRET_NAME"),
                **aws_env
            }
        )
    )
)

# USAJobs MCP Client
usajobs_client = MCPClient(
    lambda: stdio_client(
        StdioServerParameters(
            command="python3", 
            args=["/app/mcp_servers/usajobs/index.py"],
            env={
                "USAJOBS_SECRET_NAME": os.getenv("USAJOBS_SECRET_NAME"),
                **aws_env
            }
        )
    )
)

bedrock_model = BedrockModel(
    model_id=os.getenv("BEDROCK_MODEL"),
    temperature=0.7,
    boto_session = session
)

ADZUNA_AGENT_PROMPT = """
You are a job market analyst specializing in private sector employment data.

**CRITICAL REQUIREMENTS:**
1. Use ONLY data returned from tool calls
2. Do NOT supplement with external knowledge or assumptions
3. Base ALL analysis exclusively on returned responses
4. If no data is returned, state that naturally
5. **NEVER call the same MCP tool twice in one analysis**
6. **Use EXACT job title only for salary charts - no additional keywords**

**User Profile Data Usage:**
When provided with user profile information, you MUST:
1. Use salary_min and salary_max parameters in search_adzuna_jobs with user's target salary range
2. Include user's skills and focus areas as keywords in job searches
3. Parse location correctly (location0='us', location1=city name)
4. Consider work preferences ONLY if reflected in returned data
5. Factor in experience level ONLY based on search results

Available Tools:
**Job Search:**
- search_adzuna_jobs: Advanced job search with salary filters (salary_min/max), company filters, location hierarchy (location0/location1)
- search_adzuna_by_location: Search by specific city/region using 'where' parameter
- get_adzuna_job_details: Detailed job posting information by job_id

**Market Analytics:**
- get_adzuna_salary_stats: Salary statistics and ranges by job title/keyword
- get_adzuna_salary_chart: Visual salary distribution charts with location filtering
- get_adzuna_job_categories: Job market categories and counts by location
- get_adzuna_top_companies: Top hiring companies by job volume
- search_adzuna_geodata: Geographic location data and market insights

**MANDATORY Analysis Steps:**
1. Call search_adzuna_jobs ONCE with user's salary expectations and combined keywords
2. Call get_adzuna_salary_chart ONCE with EXACT job title only (no skills/keywords)
3. Call get_adzuna_top_companies ONCE for market context
4. **DO NOT repeat any tool calls**
5. Base insights EXCLUSIVELY on returned data

**CHART GENERATION RULES:**
- Use get_adzuna_salary_chart with EXACT job title only
- Example: If job title is "Senior Software Engineer", use exactly "Senior Software Engineer"
- Do NOT add skills, technologies, or other keywords to chart generation
- Generate only ONE chart per analysis

**OUTPUT REQUIREMENTS:**
- Never mention technical infrastructure or "MCP"
- Present as professional job market analysis
- State limitations naturally (e.g., "Limited data available")

Provide comprehensive analysis with ONE visual salary chart from returned data.
"""

USAJOBS_AGENT_PROMPT = """
You are a federal job search specialist focusing on government employment data.

**CRITICAL REQUIREMENTS:**
1. Use ONLY data returned from tool calls
2. Do NOT supplement with external knowledge about federal processes
3. Base ALL analysis exclusively on returned responses
4. If no data is returned, state that naturally

Available Tools:
**Job Search:**
- search_usajobs: Search federal positions with filters for agency, location, pay grade, job series
- get_usajobs_details: Detailed federal job posting information including requirements and benefits

**Analysis Areas:**
1. Federal positions based ONLY on search results
2. Job details and requirements from detailed job postings

**OUTPUT REQUIREMENTS:**
- Never mention technical infrastructure
- Present as professional federal employment analysis
- State limitations naturally (e.g., "Limited data available")

Provide federal employment data analysis based exclusively on returned results.
"""



@tool
def adzuna_specialist(query: str) -> str:
    """
    Analyze job markets using Adzuna's comprehensive job search and salary data.
    Specializes in private sector job market intelligence and salary analytics.
    """
    # Create tools list for the agent
    with adzuna_client:
        adzuna_agent = Agent(
            system_prompt=ADZUNA_AGENT_PROMPT,
            tools=adzuna_client.list_tools_sync(),
            model=bedrock_model,
        )
        return str(adzuna_agent(query))

@tool
def usajobs_specialist(query: str) -> str:
    """
    Search and analyze federal government positions using USAJobs.gov data.
    Specializes in federal employment opportunities and government career guidance.
    """
    with usajobs_client:
        usajobs_agent = Agent(
            system_prompt=USAJOBS_AGENT_PROMPT,
            tools=usajobs_client.list_tools_sync(),
            model=bedrock_model,
        )
        return str(usajobs_agent(query))


def create_job_orchestrator_agent():
    """
    Create the main orchestrator agent for comprehensive job search and career planning.
    This orchestrator coordinates specialized job search agents to deliver
    complete employment market analysis.
    """

    JOB_ORCHESTRATOR_PROMPT = """
    You are a Career Strategy Coordinator for job search and career planning.
    
    **CRITICAL REQUIREMENTS:**
    1. Use ONLY data returned from specialist agent calls
    2. Do NOT supplement with external knowledge or general career advice
    3. Base ALL recommendations exclusively on returned data
    4. If servers return insufficient data, state limitations naturally without mentioning technical details
    5. **RESPECT USER SECTOR PREFERENCE**: Only use the specialist that matches user's sector preference
    6. **CALL EACH SPECIALIST ONLY ONCE**: Never make multiple calls to the same specialist
    
    Your role:
    1. Delegate searches to appropriate specialized agents based on user preferences
    2. Synthesize results into data-driven insights
    3. Provide analysis based exclusively on returned data
    
    Available tool agents:
    - adzuna_specialist: For private sector job data
    - usajobs_specialist: For federal job data
    
    **SECTOR SELECTION LOGIC:**
    - If user wants "Private Sector" → call adzuna_specialist ONCE only
    - If user wants "Federal Government" → call usajobs_specialist ONCE only
    - If user wants "Both" → call adzuna_specialist ONCE and usajobs_specialist ONCE
    
    **SINGLE CALL REQUIREMENT:**
    When calling adzuna_specialist, make ONE comprehensive request that includes:
    - Job search with salary filters
    - Visual salary distribution charts
    - Market analysis
    - Company data
    Do NOT make separate calls for different data types.
    
    **LOCATION HANDLING:**
    - Use exact location in server calls
    - Parse location format: "City, Country" → location0='country_code', location1='City'
    - Use specified location - no defaults
    
    **OUTPUT REQUIREMENTS:**
    - Never mention "MCP", "server", or technical infrastructure
    - Present analysis as professional job market insights
    - State data limitations naturally (e.g., "Limited data available for this search")
    
    Provide:
    - Market analysis (with visual charts ONLY when using adzuna_specialist)
    - Recommendations based on results
    - Comparative analysis when using multiple sources
    - Natural statements when data is limited
    
    **CHART GENERATION RULES:**
    - Generate charts ONLY when adzuna_specialist is used
    - Do NOT generate charts for federal-only analysis
    - Charts are exclusive to private sector data
    """

    orchestrator = Agent(
        system_prompt=JOB_ORCHESTRATOR_PROMPT,
        tools=[
            adzuna_specialist,
            usajobs_specialist
        ],
        model=bedrock_model,
    )

    return orchestrator

def create_professional_job_request(user_inputs):
    """
    Generate a professional job search request based on user inputs from Streamlit interface.
    """
    # Parse location for API calls
    location_parts = user_inputs['current_location'].split(',')
    city = location_parts[0].strip()
    
    # Use job title for charts, combined keywords for job search
    chart_keywords = user_inputs['job_title']
    search_keywords = f"{user_inputs['job_title']} {user_inputs['skills']} {user_inputs['focus_areas']}"
    
    # Determine which specialists to use based on sector preference
    sector_pref = user_inputs['sector_preference']
    
    if sector_pref == "Federal Government":
        specialist_instruction = "**MANDATORY: Use ONLY usajobs_specialist for federal analysis**"
        usajobs_params = f"""
        **USAJOBS PARAMETERS:**
        For usajobs_specialist, you MUST use these parameters in search_usajobs:
        - keywords: "{search_keywords}"
        - location: "{user_inputs['current_location']}"
        - clearance_level: "{user_inputs['clearance_status']}"
        """
        adzuna_params = ""
        analysis_req = f"""
        Analysis Requirements:
        1. **MANDATORY**: Use ONLY usajobs_specialist for federal analysis
        2. Search using combined keywords: "{search_keywords}"
        3. Use exact location parameters for federal job searches
        4. Base recommendations EXCLUSIVELY on federal job results
        5. **DO NOT generate any salary charts or call adzuna_specialist**
        6. **NO CHART GENERATION**: Federal analysis does not include visual charts
        """
    elif sector_pref == "Private Sector":
        specialist_instruction = "**MANDATORY: Use ONLY adzuna_specialist for private sector analysis**"
        adzuna_params = f"""
        **ADZUNA PARAMETERS:**
        For adzuna_specialist, you MUST use these parameters in search_adzuna_jobs:
        - keywords: "{search_keywords}"
        - salary_min: {user_inputs['min_salary']}
        - salary_max: {user_inputs['max_salary']}
        - location: "{user_inputs['current_location']}"
        - location0: First level location filter (e.g., 'UK', 'US')
        - location1: Second level location filter (e.g., 'London', 'New York')
        """
        usajobs_params = ""
        analysis_req = f"""
        Analysis Requirements:
        1. **MANDATORY**: Use ONLY adzuna_specialist for private sector analysis
        2. **CRITICAL**: Use salary filters (salary_min={user_inputs['min_salary']}, salary_max={user_inputs['max_salary']})
        3. Search using combined keywords: "{search_keywords}"
        4. Use exact location parameters
        5. Generate visual salary distribution charts
        6. Top hiring companies analysis
        7. Base recommendations EXCLUSIVELY on private sector results
        
        **Chart Requirements:**
        - Create ONE salary distribution chart using get_adzuna_salary_chart
        - Use EXACT job title only: "{chart_keywords}"
        - Use location parameters: location0='us', location1='{city}'
        - Do NOT call get_adzuna_salary_chart more than once
        - Do NOT add skills or keywords to chart generation
        """
    else:  # Both sectors
        specialist_instruction = "**MANDATORY: Use BOTH adzuna_specialist AND usajobs_specialist for comprehensive analysis**"
        adzuna_params = f"""
        **ADZUNA PARAMETERS:**
        For adzuna_specialist, you MUST use these parameters in search_adzuna_jobs:
        - keywords: "{search_keywords}"
        - salary_min: {user_inputs['min_salary']}
        - salary_max: {user_inputs['max_salary']}
        - location: "{user_inputs['current_location']}"
        - location0: First level location filter (e.g., 'UK', 'US')
        - location1: Second level location filter (e.g., 'London', 'New York')
        """
        usajobs_params = f"""
        **USAJOBS PARAMETERS:**
        For usajobs_specialist, you MUST use these parameters in search_usajobs:
        - keywords: "{search_keywords}"
        - location: "{user_inputs['current_location']}"
        - clearance_level: "{user_inputs['clearance_status']}"
        """
        analysis_req = f"""
        Analysis Requirements:
        1. **MANDATORY**: Use BOTH adzuna_specialist AND usajobs_specialist
        2. **CRITICAL**: Use salary filters (salary_min={user_inputs['min_salary']}, salary_max={user_inputs['max_salary']}) for private sector
        3. Search using combined keywords: "{search_keywords}" in both sources
        4. Use exact location parameters for both searches
        5. Generate visual salary distribution charts for private sector
        6. **MANDATORY**: Provide compensation comparison between sectors
        7. Base recommendations on results from both sectors
        8. Top hiring companies analysis for private sector
        9. Federal agency analysis for government sector
        
        **Chart Requirements:**
        - Create ONE salary distribution chart using get_adzuna_salary_chart
        - Use EXACT job title only: "{chart_keywords}"
        - Use location parameters: location0='us', location1='{city}'
        - Do NOT call get_adzuna_salary_chart more than once
        - Do NOT add skills or keywords to chart generation
        """
    
    return f"""
    {specialist_instruction}
    
    {adzuna_params}
    {usajobs_params}
    
    Conduct job search analysis for a {user_inputs['job_title']}:
    
    Professional Background:
    - {user_inputs['experience']} years of experience in {user_inputs['skills']}
    - Currently earning ${user_inputs['current_salary']:,} in {user_inputs['current_location']}
    - Work preferences: {user_inputs['work_preference']}
    - Sector interests: {user_inputs['sector_preference']}
    - Security clearance: {user_inputs['clearance_status']}
    
    Career Requirements:
    - Target salary range: ${user_inputs['min_salary']:,} - ${user_inputs['max_salary']:,}
    - Focus areas: {user_inputs['focus_areas']}
    - Company culture priorities: {user_inputs['company_culture']}
    - Professional development: {user_inputs['growth_priorities']}
    - Work-life balance importance: {user_inputs['work_life_balance']}
    
    {analysis_req}
    """
