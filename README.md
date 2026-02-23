# Building Generative AI Applications with Amazon Bedrock Agents

A collection of production-ready examples demonstrating Amazon Bedrock Agents capabilities for enterprise use cases.

## 📁 Projects

### 1. [HR Assistant](./01-hr-assistant/)
AI-powered HR automation solutions using Bedrock Agents.

- **[a-bedrock-single-agent](./01-hr-assistant/a-bedrock-single-agent/)** - Single agent implementation with knowledge base integration
  - CloudFormation deployment
  - Employee handbook processing
  - Streamlit UI

- **[b-bedrock-multi-agent](./01-hr-assistant/b-bedrock-multi-agent/)** - Multi-agent orchestration system
  - Orchestrator + specialized agents (LOA, Onboarding, Payroll, Compliance, Policy)
  - Lambda action groups
  - CDK infrastructure
  - Knowledge base per agent

### 2. [Job Market Analyzer](./02-job-market-analyzer/)
Intelligent job market analysis using Bedrock Agents with MCP integration.

- **[a-ecs-single-vpc-mcp](./02-job-market-analyzer/a-ecs-single-vpc-mcp/)** - ECS-based deployment with MCP servers
  - Single VPC architecture
  - Adzuna & USAJobs API integration
  - Streamlit interface

- **[b-ecs-multi-vpc-mcp-privatelink](./02-job-market-analyzer/b-ecs-multi-vpc-mcp-privatelink/)** - Multi-VPC with PrivateLink
  - Enhanced security with VPC isolation
  - Dedicated MCP servers per VPC
  - PrivateLink connectivity

- **[c-agentcore-gateway-mcp-lambda](./02-job-market-analyzer/c-agentcore-gateway-mcp-lambda/)** - Serverless Lambda-based MCP
  - API Gateway integration
  - Lambda MCP servers
  - SigV4 authentication

### 3. [Supplier Invoice Email Processing](./03-supplier-invoice-email-processing/)
Automated invoice processing with multi-agent collaboration.

- **[a-bedrock-multi-agent](./03-supplier-invoice-email-processing/a-bedrock-multi-agent/)** - Multi-agent invoice workflow
  - Intent classification
  - Invoice extraction
  - Supplier resolution
  - AP routing
  - Email attachment processing

- **[b-agentcore-gateway-mcp-lambda](./03-supplier-invoice-email-processing/b-agentcore-gateway-mcp-lambda/)** - Coming soon

## 🚀 Getting Started

Each project contains its own README with detailed setup instructions, architecture diagrams, and deployment guides.
