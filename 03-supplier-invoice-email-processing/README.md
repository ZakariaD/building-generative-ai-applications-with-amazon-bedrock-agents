# Supplier Invoice Email Processing

Automated invoice processing system using Amazon Bedrock agents — two implementations showcasing different orchestration patterns.

## 📁 Implementations

### [a-bedrock-multi-agent](./a-bedrock-multi-agent/)
Multi-agent invoice workflow using native Bedrock Multi-Agent Collaboration.

**Features:**
- SES → S3 → SQS → Lambda event pipeline
- Supervisor agent + 4 specialized Bedrock agents
- Intent classification (INV, CRN, PAY, DIS, DUP, OTH)
- Invoice extraction from PDF attachments (Claude Vision)
- Supplier resolution via DynamoDB
- Automatic AP routing with email splitting
- Dead Letter Queue with SNS alerts

**Agents:**
1. **Invoice Extraction** - Parses emails and PDFs
2. **Supplier Resolution** - DynamoDB supplier lookup
3. **Intent Classification** - Email intent analysis (agent LLM)
4. **AP Routing** - Formats and sends to AP inbox

**Deployment:** AWS CDK

---

### [b-agentcore-gateway-mcp-lambda](./b-agentcore-gateway-mcp-lambda/)
Same invoice workflow re-architected using Bedrock AgentCore with MCP Gateways and Strands multi-agent orchestration.

**Features:**
- SES → S3 → SQS → Lambda → AgentCore Runtime event pipeline
- Strands orchestrator + 4 specialist agents via MCP Gateways
- Same intent classification codes (INV, CRN, PAY, DIS, DUP, OTH)
- Same invoice extraction from PDF attachments (Claude Vision)
- Same supplier resolution via DynamoDB
- Same automatic AP routing with email splitting
- Dead Letter Queue with SNS alerts

**What Changed:**
- Bedrock Supervisor Agent → Strands Agent on AgentCore Runtime (Docker)
- Bedrock Action Groups + API schemas → MCP Gateways + inline tool schemas
- Agent instructions in .txt files → System prompts in Python code
- `invoke_agent` → `invoke_agent_runtime`

**Agents:**
1. **Invoice Extraction** - MCP Gateway → Lambda (Claude Vision for PDFs)
2. **Supplier Resolution** - MCP Gateway → Lambda (DynamoDB lookup)
3. **Intent Classification** - MCP Gateway → Lambda (data retrieval) + agent LLM (classification)
4. **AP Routing** - MCP Gateway → Lambda (SES email send)

**Deployment:** AWS CDK

---

## 🚀 Quick Start

1. Choose an implementation folder
2. Configure SES domain for email receiving
3. Deploy CDK stack
4. Load supplier data to DynamoDB
5. Test with sample invoices

## 📧 Email Flow

**a-bedrock-multi-agent:**
```
Supplier Email → SES → S3 → SQS → Lambda → Bedrock Supervisor → Agents → AP Inbox
```

**b-agentcore-gateway-mcp-lambda:**
```
Supplier Email → SES → S3 → SQS → Lambda → AgentCore Runtime (Strands) → MCP Gateways → Lambdas → AP Inbox
```

## 🎯 Key Features (Both Implementations)

- **Automatic Email Splitting**: Multiple invoices → separate emails
- **Intent Classification**: 6 intent types with confidence scoring
- **Supplier Resolution**: Automatic supplier identification via DynamoDB
- **Error Handling**: DLQ with SNS alerts for failures

Each folder contains detailed README with setup instructions and architecture diagrams.
