# HR Bedrock Agent Core Stack

[![AWS](https://img.shields.io/badge/AWS-CDK-orange)](https://aws.amazon.com/cdk/)
[![Python](https://img.shields.io/badge/Python-3.13+-blue)](https://python.org)
[![Bedrock](https://img.shields.io/badge/Amazon-Bedrock-purple)](https://aws.amazon.com/bedrock/)
[![Lambda](https://img.shields.io/badge/AWS-Lambda-yellow)](https://aws.amazon.com/lambda/)
[![Agent Core](https://img.shields.io/badge/Bedrock-Agent%20Core-green)](https://aws.amazon.com/bedrock/)
[![MCP](https://img.shields.io/badge/MCP-Model%20Context%20Protocol-lightblue)](https://modelcontextprotocol.io/)
[![Strands](https://img.shields.io/badge/Strands-Agents-red)](https://strandsagents.com/)

> This project presents the third version of the **Professional Job Market Analyzer**, a cloud-native infrastructure solution built using AWS CDK for deploying multi-agent job search applications with Bedrock Agent Core Gateway integration and Lambda-based MCP tools.

## 📋 Table of Contents

- [Features](#features)
- [Project Structure](#project-structure)
- [Architecture](#architecture)
- [Getting Started](#getting-started)
- [Prerequisites](#prerequisites)
- [Configuration](#configuration)
- [Deployment](#deployment)

## Features

- **Serverless MCP Architecture** - Lambda-based MCP tools with Bedrock Agent Core Gateway
- **Single VPC Design** - Simplified network architecture with VPC endpoints
- **Auto-scaling ECS Fargate** - Serverless container orchestration for Streamlit app
- **CloudFront Distribution** - Global CDN for optimal application performance
- **Secrets Management** - Secure API credential storage with AWS Secrets Manager
- **VPC Endpoints** - Private connectivity to AWS services without internet routing
- **S3 Chart Storage** - Salary visualization chart storage
- **Bedrock Agent Core Gateway** - Native MCP protocol support with Lambda integration

## Project Structure

```
├── Architecture/                # Architecture diagrams
│   ├── Architecture.jpeg        # System architecture diagram
├── lambda_functions/            # Lambda MCP tool implementations
│   ├── adzuna_lambda/           # Adzuna job search Lambda function
│   │   ├── Dockerfile           # Container configuration
│   │   ├── index.py             # Lambda handler implementation
│   │   └── requirements.txt     # Python dependencies
│   └── usajobs_lambda/          # USAJobs Lambda function
│       ├── Dockerfile           # Container configuration
│       ├── index.py             # Lambda handler implementation
│       └── requirements.txt     # Python dependencies
├── secrets/                     # API credentials (gitignored)
│   ├── adzuna.json              # Adzuna API credentials
│   └── usajobs.json             # USAJobs API credentials
├── streamlit/                   # Frontend application
│   ├── chatbot_st.py            # Main Streamlit interface
│   ├── multi_agent_jobs.py      # Multi-agent orchestrator
│   ├── streamable_http_sigv4.py # AWS SigV4 authentication helper
│   ├── Dockerfile               # Container configuration
│   └── requirements.txt         # Application dependencies
├── app.py                       # CDK application entry point
├── bedrock_mcp_stack.py         # Main CDK stack definition
├── cdk.json                     # CDK configuration
├── README.md                    # This documentation
└── requirements.txt             # CDK dependencies
```

## Architecture

> **📥 Download**: [Architecture Diagram](Architecture/Architecture.zip)

![Architecture Diagram](Architecture/Architecture.jpeg)

The system implements a serverless architecture with Bedrock Agent Core Gateway integration:

### Agentic App VPC 
- **ECS Fargate Cluster** - Streamlit application container
- **Application Load Balancer** - Public access on port 80
- **VPC Endpoints** - Bedrock, Bedrock Agent Core, ECR, Secrets Manager, CloudWatch Logs, S3

### Serverless MCP Tools
- **Lambda Functions** - Containerized Adzuna and USAJobs MCP tools
- **Bedrock Agent Core Gateways** - Native MCP protocol support
- **Gateway Targets** - Lambda function integration with tool schemas

### AWS Services Integration
- **Amazon Bedrock** - Claude 3.7 Sonnet for AI model with cross-region inference profile
- **Bedrock Agent Core** - Native MCP gateway and tool orchestration
- **Lambda** - Serverless MCP tool execution
- **ECS Fargate** - Serverless container hosting for Streamlit app
- **CloudFront** - Global content delivery network
- **S3** - Chart storage
- **Secrets Manager** - Secure credential management

## Getting Started

### Prerequisites

- **AWS Account** with appropriate permissions
  - IAM permissions for Bedrock, Lambda, ECS, VPC, CloudFront, Secrets Manager, Bedrock Agent Core
  - Account ID required for CDK deployment
- **AWS CDK v2** installed and configured
- **Amazon Bedrock** access enabled in us-east-1 region
  - Claude 3.7 Sonnet model access required
- **Bedrock Agent Core** access enabled
- **Node.js 18+** for CDK
- **Docker** for containerized deployment
- **AWS CLI** configured with credentials

### Configuration

1. **API Account Creation**
   
   Create developer accounts for the required APIs:
   
   - **Adzuna API**: Register at https://developer.adzuna.com/
   - **USAJobs API**: Register at https://developer.usajobs.gov/

2. **API Credentials Setup**
   
   Create credential files in the `secrets/` directory:
   
   ```bash
   # secrets/adzuna.json
   {
     "ADZUNA_APP_ID": "your_adzuna_app_id",
     "ADZUNA_APP_KEY": "your_adzuna_app_key"
   }
   
   # secrets/usajobs.json
   {
     "USAJOBS_EMAIL": "your_email@example.com",
     "USAJOBS_API_KEY": "your_usajobs_api_key"
   }
   ```

3. **Environment Setup**
   ```bash
   # Create and activate virtual environment
   python -m venv venv
   source venv/bin/activate  
   
   # Install Python dependencies
   pip install -r requirements.txt
   ```

4. **Configure AWS Account**
   ```bash
   # Set your AWS account ID and region
   export CDK_DEFAULT_ACCOUNT=123456789012  # Replace with your account ID
   export CDK_DEFAULT_REGION=us-east-1      # We are using the us-east-1 region
   
   # Bootstrap CDK (first time only)
   cdk bootstrap aws://$CDK_DEFAULT_ACCOUNT/$CDK_DEFAULT_REGION
   ```

## Deployment

### Detailed Deployment Steps

1. **Synthesize CloudFormation Template**
   ```bash
   cdk synth
   ```

2. **Deploy Infrastructure**
   ```bash
   cdk deploy --context account=$CDK_DEFAULT_ACCOUNT --context region=$CDK_DEFAULT_REGION
   ```

3. **Access Application**
   - Application will be available via CloudFront URL (output from CDK)
   - Use the provided URL to access the job search interface

### Infrastructure Components

The CDK stack deploys:

- **VPC Agentic App** - Private network (10.0.0.0/16) for applications
- **VPC Endpoints** - Bedrock, Bedrock Agent Core, ECR, Secrets Manager, CloudWatch Logs, S3
- **Lambda Functions** - Serverless MCP tool execution
- **Bedrock Agent Core Gateways** - Native MCP protocol support with IAM authentication
- **ECS Fargate Cluster** - Serverless container hosting for Streamlit app
- **Auto Scaling** - Dynamic scaling (2-10 instances based on CPU utilization)
- **Application Load Balancer** - External load balancing for Streamlit app
- **CloudFront Distribution** - Global CDN with caching optimization
- **S3 Bucket** - Chart storage management

### VPC Endpoints

The stack includes VPC endpoints for secure AWS service access:
- Bedrock Runtime
- Bedrock Agent Runtime
- Bedrock Agent Core Gateway
- ECR API and DKR
- Secrets Manager
- CloudWatch Logs
- S3

### Lambda MCP Tools
Serverless Model Context Protocol implementations for job search services:
- **Adzuna Lambda**: Private sector job search, salary statistics, company data
- **USAJobs Lambda**: Federal government job opportunities and requirements

### Streamlit Application
Professional job market analyzer with features:
- **Multi-Agent Orchestration** - Coordinated private and federal job search via Bedrock Agent Core
- **Interactive Interface** - Professional profile configuration
- **Real-time Analysis** - Live job market data processing through Lambda tools
- **Salary Visualization** - Automated chart generation and display
- **Personalized Recommendations** - Tailored career intelligence

### Usage Patterns
- **Job Search Queries**: Various search patterns and filters across private and federal sectors
- **Salary Analysis**: Market research and compensation benchmarking with visual charts
- **Company Research**: Employer analysis and hiring trends
- **Career Planning**: Professional development pathways with government and private options

### Screenshots
Application interface examples:
- **Home Page**: Main job search interface
- **Analysis Results**: Job search results and salary analytics

> **📥 Download**: [Screenshot](screenshots/screenshots.zip) (if image not displayed)

![Home Page](screenshots/home-page.png)

![Analysis Results Example 1](screenshots/Analysis-Results-Example-1.png)

![Analysis Results Example 2](screenshots/Analysis-Results-Example-2.png)