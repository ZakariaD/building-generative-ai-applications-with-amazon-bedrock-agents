# Job Market Analyzer

Intelligent job market analysis using Amazon Bedrock Agents with Model Context Protocol (MCP) integration.

## 📁 Implementations

### [a-ecs-single-vpc-mcp](./a-ecs-single-vpc-mcp/)
ECS-based deployment with MCP servers in a single VPC.

**Features:**
- Single VPC architecture with private subnets
- ECS Fargate for containerized MCP servers
- Adzuna & USAJobs API integration
- Application Load Balancer + CloudFront
- Streamlit interface with salary analytics

**Use Case:** Standard deployment with simplified networking

**Deployment:** AWS CDK

---

### [b-ecs-multi-vpc-mcp-privatelink](./b-ecs-multi-vpc-mcp-privatelink/)
Multi-VPC architecture with PrivateLink for enhanced security.

**Features:**
- VPC isolation for each MCP server
- AWS PrivateLink connectivity
- Dedicated ECS clusters per VPC
- Enhanced security with network segmentation
- Same job search capabilities as single-VPC

**Use Case:** Enterprise environments requiring strict network isolation

**Deployment:** AWS CDK

---

### [c-agentcore-gateway-mcp-lambda](./c-agentcore-gateway-mcp-lambda/)
Serverless Lambda-based MCP implementation.

**Features:**
- API Gateway integration
- Lambda functions as MCP servers
- SigV4 authentication
- Fully serverless architecture
- Cost-optimized for variable workloads

**Use Case:** Serverless deployments with pay-per-use pricing

**Deployment:** AWS CDK

---

## 🚀 Quick Start

Choose the implementation based on your requirements:

- **Single VPC**: Simplest deployment, good for most use cases
- **Multi-VPC + PrivateLink**: Maximum security and isolation
- **Lambda**: Serverless, cost-effective for variable workloads

## 🔑 Prerequisites

All implementations require:
- Adzuna API credentials (https://developer.adzuna.com/)
- USAJobs API credentials (https://developer.usajobs.gov/)
- Amazon Bedrock access (Claude 3.7 Sonnet)

Each folder contains detailed README with setup instructions and architecture diagrams.
