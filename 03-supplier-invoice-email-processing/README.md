# Supplier Invoice Email Processing

Automated invoice processing system using Amazon Bedrock Multi-Agent Collaboration.

## 📁 Implementations

### [a-bedrock-multi-agent](./a-bedrock-multi-agent/)
Multi-agent invoice workflow with event-driven architecture.

**Features:**
- SES → S3 → SQS → Lambda event pipeline
- Supervisor agent + 4 specialized agents
- Intent classification (INV, CRN, PAY, DIS, DUP, OTH)
- Invoice extraction from PDF attachments
- Supplier resolution via DynamoDB
- Automatic AP routing with email splitting
- Dead Letter Queue with SNS alerts

**Agents:**
1. **Invoice Extraction** - Parses emails and PDFs
2. **Supplier Resolution** - DynamoDB supplier lookup
3. **Intent Classification** - Email intent analysis
4. **AP Routing** - Formats and sends to AP inbox

**Use Case:** Automated supplier invoice ingestion and routing

**Deployment:** AWS CDK

---

### [b-agentcore-gateway-mcp-lambda](./b-agentcore-gateway-mcp-lambda/)
**Status:** Coming soon

Serverless MCP-based Lambda invoice processing.

---

## 🚀 Quick Start

**Current Implementation:** Multi-Agent (a-bedrock-multi-agent)

1. Configure SES domain for email receiving
2. Deploy CDK stack
3. Load supplier data to DynamoDB
4. Test with sample invoices

## 📧 Email Flow

```
Supplier Email → SES → S3 → SQS → Lambda → Bedrock Agents → AP Inbox
```

## 🎯 Key Features

- **Automatic Email Splitting**: Multiple invoices → separate emails
- **Intent Classification**: 6 intent types with confidence scoring
- **Supplier Resolution**: Automatic supplier identification
- **Error Handling**: DLQ with SNS alerts for failures

Each folder contains detailed README with setup instructions and architecture diagrams.
