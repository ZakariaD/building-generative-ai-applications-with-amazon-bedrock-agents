# AI-Driven Supplier Invoice Email Processing & AP Routing - AgentCore Gateway + MCP + Lambda

[![AWS](https://img.shields.io/badge/AWS-CDK-orange)](https://aws.amazon.com/cdk/)
[![Python](https://img.shields.io/badge/Python-3.12+-blue)](https://python.org)
[![Bedrock](https://img.shields.io/badge/Amazon-Bedrock-purple)](https://aws.amazon.com/bedrock/)
[![AgentCore](https://img.shields.io/badge/Bedrock-AgentCore-green)](https://aws.amazon.com/bedrock/)
[![Lambda](https://img.shields.io/badge/AWS-Lambda-yellow)](https://aws.amazon.com/lambda/)
[![S3](https://img.shields.io/badge/AWS-S3-red)](https://aws.amazon.com/s3/)

> AI-powered supplier invoice email processing system using Bedrock AgentCore with MCP Gateways and Strands multi-agent orchestration to automatically ingest supplier emails, extract invoice data, resolve supplier identities, classify intent, and route to the Accounts Payable (AP) inbox with minimal manual intervention.

## 📋 Table of Contents

- [Features](#features)
- [Project Structure](#project-structure)
- [Architecture](#architecture)
- [Core Components](#core-components)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Configuration](#configuration)
- [Deployment](#deployment)
- [Post-Deployment](#post-deployment)
- [Agent Configuration](#agent-configuration)
- [Data Flow](#data-flow)
- [Monitoring](#monitoring)
- [Troubleshooting](#troubleshooting)

## Features

- **Multi-Agent Orchestration** - Strands orchestrator coordinates specialized agents via MCP Gateways
- **Event-Driven Architecture** - SES → S3 → SQS → Lambda with DLQ and retry logic
- **Intelligent Extraction** - LLM-powered PDF invoice parsing and invoice number detection
- **Supplier Resolution** - DynamoDB supplier lookup with name fallback
- **Intent Classification** - Agent LLM-powered email intent analysis with confidence scoring
- **Smart Routing** - Automatic email splitting for multiple invoices with dynamic routing
- **AgentCore Runtime** - Containerized Strands orchestrator for scalable agent execution
- **MCP Gateways** - Model Context Protocol gateways exposing Lambda tools to agents
- **Centralized Configuration** - Single source for emails, routing, and model settings
- **AP Integration** - Formatted delivery with intent and supplier codes

## Project Structure

```
├── Architecture/                   # Architecture diagrams
│   └── Architecture.png            # System architecture diagram
├── attachments/                    # Sample test files (one per intent)
│   ├── intent_INV.eml              # Invoice submission sample
│   ├── intent_CRN.eml              # Credit note sample
│   ├── intent_PAY.eml              # Payment inquiry sample
│   ├── intent_DIS.eml              # Dispute sample
│   ├── intent_DUP.eml              # Duplicate invoice sample
│   └── intent_OTH.eml              # Other intent sample
├── lambda_functions/               # AWS Lambda functions (MCP-compatible)
│   ├── orchestrator/               # SQS trigger → AgentCore Runtime
│   │   └── index.py
│   ├── invoice_extraction/         # Email & PDF parsing with LLM
│   │   └── index.py
│   ├── supplier_resolution/        # DynamoDB supplier lookup
│   │   └── index.py
│   ├── intent_classification/      # Returns email data for agent LLM classification
│   │   └── index.py
│   └── ap_routing/                 # Email formatting & SES
│       └── index.py
├── strands/                        # Strands orchestrator (Docker → AgentCore Runtime)
│   ├── multi_agent_invoice.py      # Strands agent definitions & prompts
│   ├── streamable_http_sigv4.py    # SigV4 MCP transport for gateway auth
│   ├── Dockerfile
│   └── requirements.txt
├── helper-scripts/                 # Utility scripts
│   ├── init.sh                     # Initialize and test system
│   ├── clean-log-streams.sh        # Clean CloudWatch logs
│   └── load_customer_data.py       # Load suppliers to DynamoDB
├── sample_data/                    # Sample data files
│   └── supplier_data.json          # Supplier records for DynamoDB
├── app.py                          # CDK application entry point
├── email_processing_stack.py      # CDK stack definition
├── cdk.json                        # CDK configuration
├── requirements.txt                # CDK dependencies
└── README.md                       # This documentation
```

## Architecture

> **📥 Download**: [Architecture Diagram](Architecture/Architecture.zip)

![Architecture Diagram](./Architecture/Architecture.png)

```
                    Supplier Email 
                              ↓
                    SES Receipt Rule
                              ↓
                    S3 email upload (incoming/)
                              ↓
                  ┌─────────────────────┐
                  │    SQS Queue        │ ◄── S3 event notification
                  │  (with DLQ)         │     (decoupled architecture)
                  └──────────┬──────────┘
                             │ (polls queue)
                             ▼
                  ┌─────────────────────┐
                  │  Lambda Function    │ ◄── Triggered by SQS
                  │  (Orchestrator)     │     
                  └──────────┬──────────┘
                             │ invoke_agent_runtime
                             ▼
                  ┌─────────────────────┐
                  │  AgentCore Runtime  │ ◄── Strands orchestrator (Docker)
                  │  (Strands Agent)    │
                  └──────────┬──────────┘
                             │ MCP Gateway calls
                             ▼
            ┌────────────────────────────────────────────┐
            │     MCP Gateway Multi-Agent Workflow       │
            ├────────────────────────────────────────────┤
            │  Gateway 1: Invoice Extraction              │
            │            (Claude Vision + PDF parsing)    │
            │            ↓                                │
            │  Gateway 2: Supplier Resolution              │
            │            (DynamoDB lookup)                 │
            │            ↓                                │
            │  Gateway 3: Intent Classification            │
            │            (Agent LLM classification)       │
            │            ↓                                │
            │  Gateway 4: AP Routing & Email Send          │
            │            (SES)                            │
            └────────────────────────────────────────────┘
                             ↓
                 Email sent to AP inbox
                 (with intent & supplier codes)
                             ↓
                 AP team routes to appropriate queue
```

The system uses a Strands multi-agent architecture with AgentCore MCP Gateways:

- **Orchestrator Agent (Strands)** - Coordinates workflow via @tool functions (Claude Sonnet)
- **Agent 1 (Invoice Extraction)** - Strands sub-agent → MCP Gateway → Lambda (PDF parsing with Claude Vision)
- **Agent 2 (Supplier Resolution)** - Strands sub-agent → MCP Gateway → Lambda (DynamoDB lookup)
- **Agent 3 (Intent Classification)** - Strands sub-agent with LLM → MCP Gateway → Lambda (returns raw data, agent LLM classifies)
- **Agent 4 (AP Routing)** - Strands sub-agent → MCP Gateway → Lambda (SES email send)

### Key Differences from Bedrock Multi-Agent (a-bedrock-multi-agent)

| Aspect | a-bedrock-multi-agent | b-agentcore-gateway-mcp-lambda |
|--------|----------------------|-------------------------------|
| Orchestration | Bedrock Supervisor Agent | Strands Agent (AgentCore Runtime) |
| Agent Communication | Bedrock Action Groups + API schemas | MCP Gateways → Lambda |
| Agent Definitions | CfnAgent + instruction .txt files | Strands @tool + system prompts in Python |
| Runtime | Bedrock-managed | AgentCore Runtime (Docker container) |
| Trigger | SQS → Lambda → Bedrock invoke_agent | SQS → Lambda → AgentCore invoke_agent_runtime |

## Core Components

### 1. SES Email Receiving → S3 → SQS → Lambda → AgentCore Runtime
- **Purpose**: Automated email ingestion and reliable processing workflow
- **Email Ingestion**:
  - Domain: ingestion.company.com (verified in SES)
  - Recipient: supplier-invoices@ingestion.company.com
  - SES receives emails via MX record and saves to S3 (no file extension)
  - Spam/virus scanning enabled
  - TLS encryption required
- **Dynamic Email Routing**:
  - Extraction Agent extracts recipient email from `To` header
  - Routing Agent determines AP destination based on ingestion recipient
  - `supplier-invoices@ingestion.company.com` → routes to `ap@company.com`
  - No default fallback - fails if recipient not configured
- **Configuration**:
  - S3 triggers SQS on any file upload under `incoming/` prefix (covers all formats)
  - SQS triggers Lambda with batch_size=1 (one message per invocation)
  - Dead Letter Queue (DLQ) captures failed messages after 3 retries
  - CloudWatch Alarm sends email alert when messages enter DLQ
  - Lambda invokes AgentCore Runtime endpoint with S3 bucket/key payload
  - Reserved concurrency controls parallel processing
- **SQS Settings**:
  - Retention: 14 days (maximum)
  - Visibility timeout: 900 seconds (matches Lambda timeout)
  - Encryption: SQS-managed
  - DLQ retention: 14 days
  - max_receive_count: 3 (retries before DLQ)
- **Lambda Settings**:
  - batch_size=1: Each Lambda processes 1 email
  - max_batching_window=0: Immediate processing (no delay)
  - report_batch_item_failures=True: Granular retry (only failed messages)
  - reserved_concurrent_executions: 1 (testing), 5 (production)
- **Benefits**:
  - Automatic email ingestion from SES
  - SES receipt rule filters recipients (only allowed emails saved to S3)
  - Automatic retry mechanism (3 attempts)
  - Message persistence (14-day retention)
  - Decoupled components for better reliability
  - Partial batch failure support
  - No event loss (messages wait in queue)
  - Email alerts for failed processing
- **Input**: S3 bucket name, object key (email file)

### 2. AgentCore Runtime (Strands Orchestrator)
- **Model**: Claude Sonnet
- **Technology**: Strands multi-agent framework running in Docker container on AgentCore Runtime
- **Role**: Coordinate multi-agent workflow via @tool functions and MCP Gateway calls
- **Responsibilities**:
  - Receive payload from orchestrator Lambda (S3 bucket/key)
  - Delegate tasks to specialist agents via @tool decorators
  - Each specialist creates a Strands sub-agent with its own system prompt and MCP tools
  - Aggregate results from sub-agents
  - Handle error recovery and retries

### 3. Agent 1: Invoice Extraction (MCP Gateway → Lambda)
- **Technology**: Bedrock Claude Vision (PDF document support) in Lambda + Strands sub-agent
- **Input**: Email file from S3
- **Tasks**:
  - Extract email body, subject, sender
  - Extract recipient email from `To` header for routing
  - Parse PDF attachments using Claude Vision (base64 PDF → invoke_model)
  - Extract invoice number(s), PO number(s), supplier name, date, amount
  - Fallback extraction from email body if no PDF
- **Output**: Structured invoice data, recipient_email, invoice numbers, email metadata
- **Note**: Lambda retains the Bedrock invoke_model call because Claude Vision requires raw PDF bytes — the agent LLM cannot process binary documents

### 4. Agent 2: Supplier Resolution (MCP Gateway → Lambda)
- **Technology**: DynamoDB SupplierDirectory table
- **Input**: Email domain, supplier name
- **Tasks**:
  - Query DynamoDB by email_domain (partition key)
  - Fallback: scan by supplier name
  - Determine supplier type: STANDARD / STRATEGIC / ONE_TIME
- **Output**: supplier_id, supplier_type, ap_routing_code (`AP_INBOX` or `AP_MANUAL`), or `UNKNOWN_VENDOR`

### 5. Agent 3: Intent Classification (MCP Gateway → Lambda + Agent LLM)
- **Technology**: Strands sub-agent LLM (no Bedrock call in Lambda)
- **Input**: Email body, subject, extracted invoice data
- **Tasks**:
  - Lambda returns raw email content (subject, body, invoice amount/date) — no LLM call
  - Strands classification agent's own LLM analyzes the content using its system prompt
  - Classifies into intent codes (INV, CRN, PAY, DIS, DUP, OTH)
  - Returns confidence score (0-100) and reasoning
- **Output**: intent_code, confidence, confidence_level (high/medium/low), manual_review_required
- **Note**: The agent's LLM handles classification — the Lambda is a pure data retrieval tool

### 6. Agent 4: AP Routing & Email Send (MCP Gateway → Lambda)
- **Technology**: Amazon SES
- **Input**: supplier_id, invoice numbers, intent_code, original email, recipient_email
- **Tasks**:
  - Determine AP destination email based on recipient_email via EMAIL_ROUTING
  - Split email if multiple invoices detected
  - Format subject line: `Original Subject >> Invoice# INV-458921 | Vendor V12345 | INV <<`
  - Send via SES to AP inbox with HTML metadata section
- **Output**: Emails delivered to AP inbox with email_id, invoice_number, subject per email

## Getting Started

### Prerequisites

**Required AWS Services Access:**

- **AWS Account** with appropriate permissions
  - IAM permissions for Bedrock, AgentCore, Lambda, S3, DynamoDB, SES, ECR
  - Account ID required for CDK deployment
- **AWS CDK v2** installed and configured
- **Amazon Bedrock** access enabled in us-east-1 region
  - Foundation model: Claude Sonnet (us.anthropic.claude-sonnet-4-5-20250929-v1:0)
- **Bedrock AgentCore** access enabled
- **Docker** installed (for building Strands container image)
- **Node.js 18+** for CDK
- **AWS CLI** configured with credentials
- **Python 3.12+**

### Configuration

#### 1. Environment Setup

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

#### 2. Configure AWS Account

```bash
export CDK_DEFAULT_ACCOUNT=123456789012  # Replace with your account ID
export CDK_DEFAULT_REGION=us-east-1

# Bootstrap CDK (first time only)
cdk bootstrap aws://$CDK_DEFAULT_ACCOUNT/$CDK_DEFAULT_REGION
```

#### 3. Email Configuration (Centralized)
All email addresses configured as class-level constants in `email_processing_stack.py`:

```python
RECIPIENT_EMAILS = ["supplier-invoices@ingestion.company.com"]
EMAIL_ROUTING = {
    "supplier-invoices@ingestion.company.com": "ap@company.com"
}
ALARM_EMAIL = "ap-alerts@company.com"
```

**Dynamic Email Routing**: System automatically routes emails based on ingestion recipient:
- Emails to `supplier-invoices@ingestion.company.com` → Sent to `ap@company.com`

#### 4. Model Configuration
Foundation model configured as constant (easy to update):

```python
FOUNDATION_MODEL = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
```

To change model: Update constant and redeploy. All agents automatically use new model.

## Deployment

#### 1. Synthesize CloudFormation Template

```bash
cdk synth
```

#### 2. Deploy Infrastructure

```bash
cdk deploy
```

#### 3. Note Deployment Outputs

After deployment, CDK will output:
- **EmailBucketName** - S3 bucket for email uploads
- **SupplierTableName** - DynamoDB supplier table name
- **ProcessingQueueUrl** - SQS queue URL
- **DLQUrl** - Dead letter queue URL
- **StrandsRuntimeArn** - AgentCore Runtime ARN
- **StrandsEndpointArn** - AgentCore Runtime Endpoint ARN
- **StrandsImageUri** - Docker image URI for Strands orchestrator
- **ExtractionGatewayUrl** - MCP Gateway URL for extraction
- **CustomerGatewayUrl** - MCP Gateway URL for supplier resolution
- **ClassificationGatewayUrl** - MCP Gateway URL for classification
- **RoutingGatewayUrl** - MCP Gateway URL for routing

### Infrastructure Components

The CDK stack deploys:

- **S3 Bucket** - Email storage with event notifications (incoming/ prefix)
- **SQS Queue** - Event queue with DLQ for failed messages
- **SNS Topic** - DLQ alerts via email
- **CloudWatch Alarm** - Monitors DLQ message count
- **Lambda Functions** - Orchestrator and 4 specialist MCP tool handlers
- **MCP Gateways** - 4 AgentCore gateways with Lambda targets and tool schemas
- **AgentCore Runtime** - Strands orchestrator container with runtime endpoint
- **DynamoDB Table** - Supplier directory
- **SES Configuration** - Email receiving and sending
- **IAM Roles** - Lambda role, Gateway role, Runtime role
- **CloudWatch Logs** - Centralized logging for all components
- **X-Ray** - Transaction search configuration

## Post-Deployment

### 1. Load Supplier Data

```bash
python helper-scripts/load_customer_data.py
```

**To add a supplier manually:**

```bash
aws dynamodb put-item \
  --table-name <SUPPLIER_TABLE_NAME> \
  --item '{
    "email_domain": {"S": "example.com"},
    "supplier_id": {"S": "V12345"},
    "supplier_name": {"S": "Example Corp"},
    "supplier_type": {"S": "STANDARD"},
    "default_currency": {"S": "USD"},
    "ap_routing_code": {"S": "AP_INBOX"}
  }'
```

### 2. Configure SES

```bash
# Verify sender email
aws ses verify-email-identity --email-address supplier-invoices@ingestion.company.com

# Verify AP recipient (if in sandbox)
aws ses verify-email-identity --email-address ap@company.com
```

### 3. Test the System

**Using Helper Scripts:**

```bash
bash helper-scripts/init.sh
```

**Manual Testing — upload a sample email to S3:**

```bash
aws s3 cp attachments/intent_INV.eml \
  s3://<EMAIL_BUCKET_NAME>/incoming/intent_INV.eml
```

**Monitor CloudWatch Logs:**

```bash
# Orchestrator Lambda logs
aws logs tail /aws/lambda/<STACK_NAME>-orchestrator --follow

# AgentCore Runtime logs (Strands orchestrator + sub-agents)
aws logs tail /aws/bedrock-agentcore/<STACK_NAME>-runtime --follow

# Individual agent Lambda logs
aws logs tail /aws/lambda/<STACK_NAME>-extraction --follow
aws logs tail /aws/lambda/<STACK_NAME>-customer --follow
aws logs tail /aws/lambda/<STACK_NAME>-classification --follow
aws logs tail /aws/lambda/<STACK_NAME>-routing --follow
```

## Agent Configuration

### Strands Agent Prompts

All agent system prompts are defined in `strands/multi_agent_invoice.py`:
- `ORCHESTRATOR_PROMPT` - Main orchestration logic and workflow coordination
- `EXTRACTION_AGENT_PROMPT` - Email & PDF parsing rules
- `CUSTOMER_AGENT_PROMPT` - Supplier lookup logic
- `CLASSIFICATION_AGENT_PROMPT` - Intent classification rules (agent LLM does the reasoning)
- `ROUTING_AGENT_PROMPT` - Email formatting and SES routing rules

### MCP Gateway Tool Schemas

Tool schemas are defined inline in `email_processing_stack.py` as `ToolDefinitionProperty`:
- `extract_invoice_email` - Extraction tool (s3_bucket, s3_object_key)
- `resolve_supplier` - Supplier resolution tool (email_domain, supplier_name)
- `get_email_content` - Classification data retrieval tool (subject, body, structured_data)
- `route_to_ap` - AP routing tool (original_subject, original_body, supplier_id, intent_code, invoice_numbers, recipient_email)

### Intent Classification Codes

| Code | Meaning | Keywords |
|------|---------|---------|
| INV | Invoice submission | invoice, attached, payment due, amount owed |
| CRN | Credit note / credit memo | credit, credit note, credit memo, adjustment |
| PAY | Payment status inquiry | payment status, remittance, paid, confirmation |
| DIS | Dispute or discrepancy | dispute, incorrect, wrong amount, overcharged |
| DUP | Duplicate submission | duplicate, resending, resubmit, already sent |
| OTH | Other / unclear | — |

## Data Flow

### Single Invoice Email Processing

```
1. Supplier email saved to S3 → SQS → Lambda triggered
2. Lambda invokes AgentCore Runtime endpoint with S3 bucket/key
3. Strands orchestrator delegates to extraction_specialist (@tool)
   → Sub-agent calls MCP Gateway → Lambda extracts email + PDF data
   → Returns: sender, subject, body, invoice data from PDF
4. Strands orchestrator delegates to supplier_specialist (@tool)
   → Sub-agent calls MCP Gateway → Lambda queries DynamoDB by email domain
   → Returns: "V12345" (STANDARD - AP_INBOX)
5. Strands orchestrator delegates to classification_specialist (@tool)
   → Sub-agent calls MCP Gateway → Lambda returns raw email content
   → Sub-agent's LLM classifies intent
   → Returns: "INV" (confidence: 95, high)
6. Strands orchestrator delegates to routing_specialist (@tool)
   → Sub-agent calls MCP Gateway → Lambda formats and sends via SES
   → Formats: "Invoice INV-458921 >> Invoice# INV-458921 | Vendor V12345 | INV <<"
   → Sends to ap@company.com
7. Workflow complete
```

### Multi-Invoice Email Processing (Automatic Splitting)

```
1. Supplier email with 3 invoices saved to S3 → SQS → Lambda triggered
2. Lambda invokes AgentCore Runtime endpoint with S3 bucket/key
3. Strands orchestrator delegates to extraction_specialist
   → Identifies 3 invoice numbers: INV-001, INV-002, INV-003
4. Strands orchestrator delegates to supplier_specialist
   → Returns: "V12345" (STANDARD - AP_INBOX)
5. Strands orchestrator delegates to classification_specialist
   → Returns: "INV" (confidence: 95, high)
6. Strands orchestrator delegates to routing_specialist
   → Detects multiple invoices (3)
   → Automatically splits into 3 separate emails:

   Email 1: "Invoices >> Invoice# INV-001 | Vendor V12345 | INV <<"
   Email 2: "Invoices >> Invoice# INV-002 | Vendor V12345 | INV <<"
   Email 3: "Invoices >> Invoice# INV-003 | Vendor V12345 | INV <<"

   → Sends 3 emails to ap@company.com
7. Workflow complete - 3 emails delivered for independent tracking
```

**Why Split Emails?**
- Each invoice tracked independently in AP system
- Separate processing workflows per invoice
- Individual status updates per invoice
- Prevents confusion when one invoice has issues

## Monitoring

- **CloudWatch Logs**: All Lambda functions and AgentCore Runtime log to CloudWatch
- **CloudWatch Metrics**: Monitor Lambda invocations, errors, duration
- **AgentCore Runtime Logs**: Strands orchestrator and sub-agent execution in `/aws/bedrock-agentcore/<STACK_NAME>-runtime`
- **SQS Metrics**: Monitor queue depth and DLQ messages
- **SNS Alerts**: Email notifications for DLQ failures (`ap-alerts@company.com`)
- **X-Ray**: Transaction search for end-to-end tracing

## Cleanup

```bash
cdk destroy
```

## Troubleshooting

### Lambda timeout errors
- Increase timeout in `email_processing_stack.py`
- Check CloudWatch Logs for specific errors

### AgentCore Runtime not responding
- Check Runtime logs: `/aws/bedrock-agentcore/<STACK_NAME>-runtime`
- Verify Docker image built successfully (check ECR)
- Verify Runtime endpoint ARN in orchestrator Lambda environment
- Check Runtime role permissions for Bedrock and Gateway access

### MCP Gateway errors
- Verify gateway URLs in Runtime environment variables
- Check gateway role has lambda:InvokeFunction permission
- Review individual Lambda logs for tool execution errors

### SES sending failures
- Verify email addresses in SES console
- Check SES sandbox status
- Review SES sending limits

### DynamoDB query errors
- Verify table name and region
- Check Lambda IAM permissions for DynamoDB
- Verify supplier data exists in table

### SQS/DLQ issues
- Check DLQ for failed messages
- Review CloudWatch Alarms
- Verify SQS permissions

### s3:TestEvent errors in orchestrator
- This is harmless — S3 sends a test event when the SQS notification is first created
- The orchestrator skips these automatically (no `Records` key in the message)

### Low confidence classification
- Review classification prompt in `strands/multi_agent_invoice.py` (`CLASSIFICATION_AGENT_PROMPT`)
- Check `manual_review_required=True` emails in AP inbox
- Confidence < 70 triggers manual review flag

## Support

For issues or questions:
1. Check CloudWatch Logs (Lambda + AgentCore Runtime)
2. Review agent prompts in `strands/multi_agent_invoice.py`
3. Verify IAM permissions (Lambda role, Gateway role, Runtime role)
4. Test each Lambda function independently via MCP Gateway
