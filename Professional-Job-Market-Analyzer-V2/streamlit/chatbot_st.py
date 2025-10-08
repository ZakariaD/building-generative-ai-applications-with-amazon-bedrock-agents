import multi_agent_jobs
import streamlit as st
import glob, os
from PIL import Image
import boto3
import io
from botocore.exceptions import ClientError

"""
Professional interface for comprehensive job search analysis.
"""
st.set_page_config(
    page_title="Professional Job Market Analyzer",
    page_icon="💼",
    layout="wide"
)

st.title("🎯 Professional Job Market Analyzer")
st.markdown("*Comprehensive career intelligence powered by Amazon Bedrock Multi-Agents*")

# Sidebar for user inputs
with st.sidebar:
    st.header("📋 Professional Profile")
    
    # Basic Information
    job_title = st.text_input("Target Job Title", value="Senior Software Engineer")
    experience = st.slider("Years of Experience", 0, 30, 5)
    current_salary = st.number_input("Current Salary ($)", min_value=0, value=120000, step=5000)
    current_location = st.selectbox(
        "Current Location",
        ["Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado", "Connecticut", "Delaware", "Florida", "Georgia", "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana", "Maine", "Maryland", "Massachusetts", "Michigan", "Minnesota", "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada", "New Hampshire", "New Jersey", "New Mexico", "New York", "North Carolina", "North Dakota", "Ohio", "Oklahoma", "Oregon", "Pennsylvania", "Rhode Island", "South Carolina", "South Dakota", "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington", "West Virginia", "Wisconsin", "Wyoming"],
        index=31
    )
        
    # Skills and Expertise
    skills = st.text_area("Core Skills & Technologies", 
                            value="Python, AWS, Microservices, Docker, Kubernetes")
    
    # Preferences
    work_preference = st.selectbox(
        "Work Preference",
        ["Remote", "Hybrid", "On-site", "Open to relocation", "Remote or relocation"]
    )
    
    sector_preference = st.multiselect(
        "Sector Interests",
        ["Private Sector", "Federal Government"],
        default=["Private Sector", "Federal Government"]
    )
    
    clearance_status = st.selectbox(
        "Security Clearance",
        ["None", "Eligible", "Secret", "Top Secret", "TS/SCI"]
    )
    
    st.header("💰 Compensation & Culture")
    
    # Salary expectations
    col1, col2 = st.columns(2)
    with col1:
        min_salary = st.number_input("Min Salary ($)", min_value=0, value=130000, step=5000)
    with col2:
        max_salary = st.number_input("Max Salary ($)", min_value=0, value=180000, step=5000)
    
    # Professional priorities
    focus_areas = st.text_area("Focus Areas", 
                                value="Cloud architecture, DevOps, System design")
    
    company_culture = st.text_area("Company Culture Priorities", 
                                    value="Strong engineering culture, Innovation-focused, Collaborative environment")
    
    growth_priorities = st.text_area("Growth & Development", 
                                    value="Learning budget, Conference attendance, Mentorship programs")
    
    work_life_balance = st.selectbox(
        "Work-Life Balance Priority",
        ["Critical", "Very Important", "Important", "Moderate", "Flexible"]
    )

# Main content area
col1, col2 = st.columns([2, 1])

with col2:
    st.header("🚀 Analysis Controls")
    
    if st.button("🔍 Start Comprehensive Analysis", type="primary", use_container_width=True):
        # Map sector preferences (only 2 possible values)
        mapped_sector = (
            "Both" if len(sector_preference) == 2 else
            "Federal Government" if "Federal Government" in sector_preference else
            "Private Sector"
        )
        
        # Collect user inputs
        user_inputs = {
            'job_title': job_title,
            'experience': experience,
            'current_salary': current_salary,
            'current_location': current_location,
            'skills': skills,
            'work_preference': work_preference,
            'sector_preference': mapped_sector,
            'clearance_status': clearance_status,
            'min_salary': min_salary,
            'max_salary': max_salary,
            'focus_areas': focus_areas,
            'company_culture': company_culture,
            'growth_priorities': growth_priorities,
            'work_life_balance': work_life_balance
        }
        
        # Generate professional job request
        job_request = multi_agent_jobs.create_professional_job_request(user_inputs)
        
        # Create progress indicators
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        with col1:
            st.header("📊 Analysis Results")
            
            try:
                # Initialize orchestrator
                status_text.text("🤖 Initializing AI job market analysts...")
                progress_bar.progress(20)
                
                orchestrator = multi_agent_jobs.create_job_orchestrator_agent()
                
                # Execute analysis
                status_text.text("🔍 Analyzing job markets and salary data...")
                progress_bar.progress(60)
                
                result = orchestrator(job_request)
                
                # Display results
                status_text.text("✅ Analysis complete!")
                progress_bar.progress(100)
                
                # Results display
                st.success("🎉 Comprehensive job market analysis completed!")

                # Display salary charts only for private sector analysis
                if mapped_sector in ["Private Sector", "Both"]:
                    # Check for charts in S3 first, then fallback to local
                    bucket_name = os.getenv('CHARTS_BUCKET_NAME')
                    chart_found = False
                    
                    if bucket_name:
                        try:
                            s3_client = boto3.client('s3')
                            # List objects in the bucket
                            response = s3_client.list_objects_v2(Bucket=bucket_name)
                            
                            if 'Contents' in response:
                                with st.expander("📊 Salary Distribution Charts", expanded=True):
                                    for obj in response['Contents']:
                                        key = obj['Key']
                                        if key.lower().endswith(('.png', '.jpg', '.jpeg')) and ('salary' in key.lower() or 'chart' in key.lower()):
                                            try:
                                                # Download image from S3
                                                image_obj = s3_client.get_object(Bucket=bucket_name, Key=key)
                                                image_data = image_obj['Body'].read()
                                                image = Image.open(io.BytesIO(image_data))
                                                
                                                # Map supported country codes to readable names
                                                country_map = {
                                                    "us": "US", "gb": "UK", "at": "Austria", 
                                                    "au": "Australia", "be": "Belgium", "br": "Brazil", 
                                                    "ca": "Canada", "ch": "Switzerland", "de": "Germany", 
                                                    "es": "Spain", "fr": "France", "in": "India", 
                                                    "it": "Italy", "mx": "Mexico", "nl": "Netherlands", 
                                                    "nz": "New Zealand", "pl": "Poland", "sg": "Singapore", 
                                                    "za": "South Africa"
                                                }
                                                
                                                # Extract country from filename if present
                                                country_display = "US"  # Default
                                                for code, name in country_map.items():
                                                    if f"_{code}_" in key:
                                                        country_display = name
                                                        break
                                                
                                                chart_caption = f"Salary Chart: {job_title} {country_display} - {current_location}"
                                                st.image(image, caption=chart_caption, use_container_width=True)
                                                chart_found = True
                                                
                                                # Delete the chart from S3 after displaying
                                                s3_client.delete_object(Bucket=bucket_name, Key=key)
                                            except Exception as e:
                                                st.error(f"Could not display chart {key}: {str(e)}")
                        except ClientError as e:
                            st.warning(f"Could not access S3 bucket: {e}")
                    
                    if not chart_found:
                        st.info("No salary charts were generated. Charts may take a moment to appear or the API may not have returned histogram data.")
                elif mapped_sector == "Federal Government":
                    st.info("📊 Salary charts are only displayed for private sector analysis. Federal positions are analyzed through job postings and requirements.")
                
                # Create expandable sections for results
                with st.expander("📈 Complete Analysis Report", expanded=True):
                    st.markdown(result)
                
                # Additional metrics
                with st.expander("📊 Analysis Summary"):
                    st.info(f"""
                    **Analysis Parameters:**
                    - Target Role: {job_title}
                    - Experience Level: {experience} years
                    - Salary Range: ${min_salary:,} - ${max_salary:,}
                    - Location: {current_location}
                    - Work Preference: {work_preference}
                    - Sectors: {', '.join(sector_preference)}
                    """)
                
            except Exception as e:
                st.error(f"❌ Analysis failed: {str(e)}")
                st.info("Please check your inputs and try again.")
            finally:
                # Clean up local chart files only (S3 files are managed separately)
                import time
                time.sleep(2)  # Brief pause for display
                
                for chart_file in glob.glob("/app/charts/*.png") + glob.glob("/app/charts/*.jpg") + glob.glob("/app/charts/*.jpeg"):
                    if "salary" in chart_file.lower() or "chart" in chart_file.lower():
                        try:
                            if os.path.exists(chart_file):
                                os.remove(chart_file)
                        except:
                            pass

with col1:
    if 'result' not in locals():
        st.header("👋 Welcome to Professional Job Market Analysis")
        st.markdown("""
        This advanced tool provides comprehensive job market intelligence by:
        
        🔍 **Multi-Source Analysis**
        - Private sector opportunities via [Adzuna](https://www.adzuna.com/)
        - Federal positions through [USAJobs](https://www.usajobs.gov/)
        - Salary benchmarking and market trends
        
        📊 **Data-Driven Insights**
        - Visual salary distribution charts
        - Company hiring volume analysis
        - Market demand forecasting
        
        🎯 **Personalized Recommendations**
        - Tailored application strategies
        - Career progression pathways
        - Sector comparison analysis
        
        **Get started by filling out your profile in the sidebar and clicking 'Start Analysis'**
        """)