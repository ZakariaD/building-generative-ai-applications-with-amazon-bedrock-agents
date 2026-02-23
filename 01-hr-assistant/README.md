# HR Assistant

AI-powered HR automation solutions using Amazon Bedrock Agents.

## 📁 Implementations

### [a-bedrock-single-agent](./a-bedrock-single-agent/)
Single agent implementation with knowledge base integration.

**Features:**
- CloudFormation deployment
- Employee handbook processing with vector search
- DynamoDB employee data storage
- SES email notifications
- Streamlit web interface

**Use Case:** Simple HR queries, policy lookups, leave requests

**Deployment:** CloudFormation template

---

### [b-bedrock-multi-agent](./b-bedrock-multi-agent/)
Multi-agent orchestration system with specialized HR agents.

**Features:**
- Orchestrator + 5 specialized agents (LOA, Onboarding, Payroll, Compliance, Policy)
- Lambda action groups for each agent
- Dedicated knowledge base per agent
- OpenSearch Serverless for vector storage
- CDK infrastructure as code

**Use Case:** Complex HR workflows requiring multiple specialized agents

**Deployment:** AWS CDK

---

## 🚀 Quick Start

Choose the implementation that fits your needs:

- **Single Agent**: Start here for simple HR automation
- **Multi-Agent**: Use for enterprise-scale HR operations with complex workflows

Each folder contains detailed README with setup instructions and architecture diagrams.
