# AI-Driven Supplier Invoice Email Processing & AP Routing - Bedrock Multi-Agent Collaboration

[![AWS](https://img.shields.io/badge/AWS-CDK-orange)](https://aws.amazon.com/cdk/)
[![Python](https://img.shields.io/badge/Python-3.13+-blue)](https://python.org)
[![Bedrock](https://img.shields.io/badge/Amazon-Bedrock-purple)](https://aws.amazon.com/bedrock/)
[![Lambda](https://img.shields.io/badge/AWS-Lambda-yellow)](https://aws.amazon.com/lambda/)
[![Multi-Agent](https://img.shields.io/badge/Bedrock-Multi--Agent-green)](https://aws.amazon.com/bedrock/)
[![S3](https://img.shields.io/badge/AWS-S3-red)](https://aws.amazon.com/s3/)

> AI-powered supplier invoice email processing system using AWS Bedrock Multi-Agent Collaboration to automatically ingest supplier emails, extract invoice data, resolve supplier identities, classify intent, and route to the Accounts Payable (AP) inbox with minimal manual intervention.

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

- **Multi-Agent Orchestration** - Supervisor agent coordinates specialized processing agents
- **Event-Driven Architecture** - SES → S3 → SQS → Lambda with DLQ and retry logic
- **Intelligent Extraction** - LLM-powered PDF invoice parsing and invoice number detection
- **Supplier Resolution** - DynamoDB supplier lookup with name fallback
- **Intent Classification** - Claude Sonnet email intent analysis with confidence scoring
- **Smart Routing** - Automatic email splitting for multiple invoices with dynamic routing
- **Audit Trail** - DynamoDB tracking with SNS alerts for failures
- **Centralized Configuration** - Single source for emails, routing, and model settings
- **AP Integration** - Formatted delivery with intent and supplier codes

## Project Structure

```
├── api-schemas/                    # API specifications for agents
│   ├── invoice_extraction.yaml     # Extraction agent API
│   ├── supplier_resolution.yaml    # Supplier resolution API
│   ├── intent_classification.yaml  # Classification agent API
│   └── ap_routing.yaml             # Routing agent API
├── Architecture/                   # Architecture diagrams
│   └── Architecture.png            # System architecture diagram
├── attachments/                    # Sample test files (one per intent)
│   ├── intent_INV.eml              # Invoice submission sample
│   ├── intent_CRN.eml              # Credit note sample
│   ├── intent_PAY.eml              # Payment inquiry sample
│   ├── intent_DIS.eml              # Dispute sample
│   ├── intent_DUP.eml              # Duplicate invoice sample
│   └── intent_OTH.eml              # Other intent sample
├── instructions/                   # Agent instruction files
│   ├── supervisor_agent.txt        # Supervisor orchestrator instructions
│   ├── invoice_extraction.txt      # Extraction specialist instructions
│   ├── supplier_resolution.txt     # Supplier specialist instructions
│   ├── intent_classification.txt   # Classification specialist instructions
│   └── ap_routing.txt              # Routing specialist instructions
├── lambda_functions/               # AWS Lambda functions
│   ├── orchestrator/               # SQS trigger handler
│   │   └── index.py
│   ├── invoice_extraction/         # Email & PDF parsing with LLM
│   │   └── index.py
│   ├── supplier_resolution/        # DynamoDB supplier lookup
│   │   └── index.py
│   ├── intent_classification/      # Intent classification
│   │   └── index.py
│   └── ap_routing/                 # Email formatting & SES
│       └── index.py
├── helper-scripts/                 # Utility scripts
│   ├── init.sh                     # Initialize and test system
│   ├── clean-log-streams.sh        # Clean CloudWatch logs
│   └── load_customer_data.py       # Load suppliers to DynamoDB
├── sample_data/                    # Sample data files
│   └── supplier_data.json          # Supplier records for DynamoDB
├── app.py                          # CDK application entry point
├── email_processing_stack.py       # CDK stack definition
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
                    S3 email upload 
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
                             │
                             ▼
                  ┌─────────────────────┐
                  │ Supervisor Agent    │ ◄── Receives prompt & coordinates
                  │ (Bedrock)           │
                  └──────────┬──────────┘
                             │
                             ▼
            ┌────────────────────────────────────────────┐
            │        Multi-Agent Workflow                │
            ├────────────────────────────────────────────┤
            │  Agent 1: Invoice Extraction               │
            │            (Claude + PDF parsing)          │
            │            ↓                               │
            │  Agent 2: Supplier Resolution              │
            │            (DynamoDB lookup)               │
            │            ↓                               │
            │  Agent 3: Intent Classification            │
            │            (Bedrock LLM)                   │
            │            ↓                               │
            │  Agent 4: AP Routing & Email Send          │
            │            (SES)                           │
            └────────────────────────────────────────────┘
                             ↓
                 Email sent to AP inbox
                 (with intent & supplier codes)
                             ↓
                 AP team routes to appropriate queue
```

The system uses a hierarchical multi-agent architecture:

- **Supervisor Agent** - Orchestrates workflow and coordinates responses (Claude Sonnet)
- **Agent 1 (Invoice Extraction)** - Parses emails and extracts invoice data from PDFs using LLM
- **Agent 2 (Supplier Resolution)** - Resolves supplier codes from DynamoDB
- **Agent 3 (Intent Classification)** - Classifies email intent with confidence scoring
- **Agent 4 (AP Routing)** - Formats and sends emails to AP inbox via SES

## Core Components

### 1. SES Email Receiving → S3 → SQS → Lambda Event-Driven Architecture
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
  - Lambda parses SQS message to extract S3 bucket/key
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
  - FOUNDATION_MODEL: Configurable via environment variable
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

### 2. Supervisor Agent (Bedrock Multi-Agent Orchestrator)
- **Model**: Claude Sonnet
- **Role**: Coordinate multi-agent workflow and decision-making
- **Responsibilities**:
  - Receive initial prompt from Lambda
  - Delegate tasks to specialized agents
  - Aggregate results from sub-agents
  - Handle error recovery and retries

### 3. Agent 1: Invoice Extraction
- **Technology**: Bedrock Claude (PDF document support)
- **Input**: Email file from S3
- **Tasks**:
  - Extract email body, subject, sender
  - Extract recipient email from `To` header for routing
  - Parse PDF attachments
  - Extract invoice number(s), PO number(s), supplier name, date, amount
  - Fallback extraction from email body if no PDF
- **Output**: Structured invoice data, recipient_email, invoice numbers, email metadata

### 4. Agent 2: Supplier Resolution
- **Technology**: DynamoDB SupplierDirectory table
- **Input**: Email domain, supplier name
- **Tasks**:
  - Query DynamoDB by email_domain (partition key)
  - Fallback: scan by supplier name
  - Determine supplier type: STANDARD / STRATEGIC / ONE_TIME
- **Output**: supplier_id, supplier_type, ap_routing_code (`AP_INBOX` or `AP_MANUAL`), or `UNKNOWN_VENDOR`

### 5. Agent 3: Intent Classification
- **Technology**: Bedrock LLM (Claude)
- **Input**: Email body, subject, extracted invoice data
- **Tasks**:
  - Analyze email intent using NLP
  - Classify into intent codes (INV, CRN, PAY, DIS, DUP, OTH)
  - Return confidence score (0-100) and reasoning
- **Output**: intent_code, confidence, confidence_level (high/medium/low), manual_review_required

### 6. Agent 4: AP Routing & Email Send
- **Technology**: Amazon SES / DynamoDB
- **Input**: supplier_id, invoice numbers, intent_code, original email, recipient_email
- **Tasks**:
  - Determine AP destination email based on recipient_email
  - Split email if multiple invoices detected
  - Format subject line: `Original Subject >> Invoice# INV-458921 | Vendor V12345 | INV <<`
  - Send via SES to AP inbox
  - Write processing results to DynamoDB for audit trail
- **Output**: Emails delivered to AP inbox, results stored in DynamoDB

## Getting Started

### Prerequisites

**Required AWS Services Access:**

- **AWS Account** with appropriate permissions
  - IAM permissions for Bedrock, Lambda, S3, DynamoDB, SES
  - Account ID required for CDK deployment
- **AWS CDK v2** installed and configured
- **Amazon Bedrock** access enabled in us-east-1 region
  - Foundation model: Claude Sonnet (us.anthropic.claude-sonnet-4-5-20250929-v1:0)
- **Bedrock Multi-Agent Collaboration** access enabled
- **Node.js 18+** for CDK
- **AWS CLI** configured with credentials
- **Python 3.13+**

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
INGESTION_DOMAIN = "ingestion.company.com"
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

#### 3. Deployment Outputs

After deployment, CDK will output:
- **EmailBucketName** - S3 bucket for email uploads
- **SupervisorAgentId** - Bedrock Supervisor Agent ID
- **SupervisorAliasId** - Bedrock Agent Alias ID
- **SupplierTableName** - DynamoDB supplier table name
- **ProcessingQueueUrl** - SQS queue URL
- **DLQUrl** - Dead letter queue URL

### Infrastructure Components

The CDK stack deploys:

- **S3 Bucket** - Email storage with event notifications (incoming/ prefix)
- **SQS Queue** - Event queue with DLQ for failed messages
- **SNS Topic** - DLQ alerts via email
- **CloudWatch Alarm** - Monitors DLQ message count
- **Lambda Functions** - Orchestrator and 4 specialized agent action groups
- **Bedrock Agents** - Supervisor and 4 sub-agents
- **DynamoDB Table** - Supplier directory
- **SES Configuration** - Email sending service
- **IAM Roles** - Least privilege access policies
- **CloudWatch Logs** - Centralized logging

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
aws logs tail /aws/lambda/<ORCHESTRATOR_LAMBDA_NAME> --follow
```

## Agent Configuration

### Agent Instructions

All agent instructions are in the `instructions/` folder and can be modified:
- `supervisor_agent.txt` - Main orchestration logic
- `invoice_extraction.txt` - Email & PDF parsing rules
- `supplier_resolution.txt` - Supplier lookup logic
- `intent_classification.txt` - Intent classification rules
- `ap_routing.txt` - Email formatting rules

### API Schemas

API schemas define the action group interfaces in `api-schemas/`:
- `invoice_extraction.yaml` - Extraction API specification
- `supplier_resolution.yaml` - Supplier resolution API
- `intent_classification.yaml` - Classification API
- `ap_routing.yaml` - Routing API

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
2. Lambda invokes Supervisor Agent with prompt
3. Supervisor delegates to Agent 1 (Invoice Extraction)
   → Extracts: sender, subject, body, invoice data from PDF
4. Supervisor delegates to Agent 2 (Supplier Resolution)
   → Queries DynamoDB by email domain
   → Returns: "V12345" (STANDARD - AP_INBOX)
5. Supervisor delegates to Agent 3 (Intent Classification)
   → Returns: "INV" (confidence: 95, high)
6. Supervisor delegates to Agent 4 (AP Routing)
   → Formats: "Invoice INV-458921 >> Invoice# INV-458921 | Vendor V12345 | INV <<"
   → Sends to ap@company.com
7. Workflow complete
```

### Multi-Invoice Email Processing (Automatic Splitting)

```
1. Supplier email with 3 invoices saved to S3 → SQS → Lambda triggered
2. Lambda invokes Supervisor Agent with prompt
3. Supervisor delegates to Agent 1 (Invoice Extraction)
   → Identifies 3 invoice numbers: INV-001, INV-002, INV-003
4. Supervisor delegates to Agent 2 (Supplier Resolution)
   → Returns: "V12345" (STANDARD - AP_INBOX)
5. Supervisor delegates to Agent 3 (Intent Classification)
   → Returns: "INV" (confidence: 95, high)
6. Supervisor delegates to Agent 4 (AP Routing)
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

- **CloudWatch Logs**: All Lambda functions log to CloudWatch
- **CloudWatch Metrics**: Monitor Lambda invocations, errors, duration
- **Bedrock Metrics**: Track agent invocations and token usage
- **SQS Metrics**: Monitor queue depth and DLQ messages
- **SNS Alerts**: Email notifications for DLQ failures (`ap-alerts@company.com`)

## Cleanup

```bash
cdk destroy
```

## Troubleshooting

### Lambda timeout errors
- Increase timeout in `email_processing_stack.py`
- Check CloudWatch Logs for specific errors

### Bedrock agent not found
- Verify agent ID and alias ID in environment variables
- Ensure agent is in the same region (us-east-1)

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

### Low confidence classification
- Review intent classification prompts in `instructions/intent_classification.txt`
- Check `manual_review_required=True` emails in AP inbox
- Confidence < 70 triggers manual review flag

## Support

For issues or questions:
1. Check CloudWatch Logs
2. Review agent instructions in `instructions/`
3. Verify IAM permissions
4. Test each Lambda function independently

## Glossary

| Term | Meaning |
|------|---------|
| AP | Account Payable — the finance team responsible for processing supplier invoices and payments |
| AP_INBOX | Routing code: supplier is known, email is automatically routed to the AP inbox |
| AP_MANUAL | Routing code: supplier is unknown (`UNKNOWN_VENDOR`), requires manual review by the AP team |
