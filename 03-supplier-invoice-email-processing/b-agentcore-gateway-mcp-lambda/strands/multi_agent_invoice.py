from strands import Agent, tool
from strands.models import BedrockModel
from strands.tools.mcp.mcp_client import MCPClient
from streamable_http_sigv4 import streamablehttp_client_with_sigv4
import os, boto3
from datetime import datetime
import logging
import sys
from bedrock_agentcore.runtime import BedrockAgentCoreApp

app = BedrockAgentCoreApp()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("AP-Invoice-Orchestrator")


def create_streamable_http_transport(gateway_url):
    session = boto3.Session()
    credentials = session.get_credentials()
    return streamablehttp_client_with_sigv4(
        url=gateway_url,
        credentials=credentials,
        service="bedrock-agentcore",
        region=os.getenv('AWS_REGION', 'us-east-1')
    )


# Get gateway URLs from environment
EXTRACTION_GATEWAY_URL = os.getenv('EXTRACTION_GATEWAY_URL')
CUSTOMER_GATEWAY_URL = os.getenv('CUSTOMER_GATEWAY_URL')
CLASSIFICATION_GATEWAY_URL = os.getenv('CLASSIFICATION_GATEWAY_URL')
ROUTING_GATEWAY_URL = os.getenv('ROUTING_GATEWAY_URL')

logger.info(f"EXTRACTION_GATEWAY_URL: {EXTRACTION_GATEWAY_URL}")
logger.info(f"CUSTOMER_GATEWAY_URL: {CUSTOMER_GATEWAY_URL}")
logger.info(f"CLASSIFICATION_GATEWAY_URL: {CLASSIFICATION_GATEWAY_URL}")
logger.info(f"ROUTING_GATEWAY_URL: {ROUTING_GATEWAY_URL}")

session = boto3.Session()
bedrock_model = BedrockModel(
    model_id=os.getenv("BEDROCK_MODEL", "us.anthropic.claude-sonnet-4-5-20250929-v1:0"),
    temperature=0.7,
    boto_session=session
)

# AgentCore Gateways - MCP Clients
try:
    extraction_client = MCPClient(lambda: create_streamable_http_transport(EXTRACTION_GATEWAY_URL)) if EXTRACTION_GATEWAY_URL else None
    customer_client = MCPClient(lambda: create_streamable_http_transport(CUSTOMER_GATEWAY_URL)) if CUSTOMER_GATEWAY_URL else None
    classification_client = MCPClient(lambda: create_streamable_http_transport(CLASSIFICATION_GATEWAY_URL)) if CLASSIFICATION_GATEWAY_URL else None
    routing_client = MCPClient(lambda: create_streamable_http_transport(ROUTING_GATEWAY_URL)) if ROUTING_GATEWAY_URL else None
    logger.info("MCP clients initialized successfully")
except Exception as e:
    logger.error(f"Error initializing MCP clients: {e}")
    raise

EXTRACTION_AGENT_PROMPT = """
You are the Invoice Extraction Specialist. Extract structured invoice data from supplier emails and PDF attachments.

Your tasks:
1. Download email from S3 and parse headers, body, and attachments
2. Use Claude vision to extract data from PDF invoices
3. Extract:
   - Invoice number(s) (e.g. INV-458921, GI-2026-00982)
   - PO number(s)
   - Supplier name
   - Invoice date
   - Total amount and currency
4. Extract email metadata: sender_email, email_domain, recipient_email, subject, body
5. Handle multi-invoice emails (multiple PDFs)

Return:
- email_metadata (email_id, sender_email, email_domain, recipient_email, subject, body)
- attachments list with structured_data per PDF
- invoice_numbers (array)
- po_numbers (array)
- sender_email, email_domain, recipient_email
"""

CUSTOMER_AGENT_PROMPT = """
You are the Supplier Resolution Specialist. Resolve supplier identity from the DynamoDB SupplierDirectory table.

Your tasks:
1. Query SupplierDirectory by email_domain (partition key) — primary lookup
2. Fall back to supplier_name scan if domain lookup fails
3. Return supplier_id, supplier_name, supplier_type, ap_routing_code
4. Return UNKNOWN_VENDOR if no match found — flag for manual review

Supplier types: STANDARD, STRATEGIC, ONE_TIME
Fallback supplier_id: UNKNOWN_VENDOR
Fallback ap_routing_code: AP_MANUAL

Always return unknown_vendor: true when no match is found.
"""

CLASSIFICATION_AGENT_PROMPT = """
You are the Invoice Classification Specialist. Classify the intent of supplier invoice emails.

First, use the get_email_content tool to retrieve the email subject, body, and invoice data.
Then analyze the content and classify into ONE intent code.

Intent codes:
- INV: Supplier submitting an invoice for payment. Keywords: invoice, attached, payment due, amount owed.
- CRN: Credit note or credit memo. Keywords: credit, credit note, credit memo, adjustment.
- PAY: Payment status inquiry or remittance advice. Keywords: payment status, remittance, paid, confirmation.
- DIS: Dispute, discrepancy, or complaint. Keywords: dispute, incorrect, wrong amount, overcharged, issue.
- DUP: Duplicate invoice submission. Keywords: duplicate, resending, resubmit, already sent.
- OTH: Other or unclear intent.

Use invoice amount and date to increase confidence.
Assign confidence score 0-100. Flag manual_review_required if confidence < 70.

Return: intent_code, confidence, confidence_level (high/medium/low), reasoning, manual_review_required.
"""

ROUTING_AGENT_PROMPT = """
You are the AP Routing Specialist. Format invoice emails and route them to the correct AP system via SES.

Your tasks:
1. Format subject line:
   - Single invoice: "Original Subject >> Invoice# INV-458921 | Vendor V12345 | INV <<"
   - No invoice number: "Original Subject >> Vendor V12345 | INV <<"
   - Multiple invoices: create one email per invoice number
2. Send via SES to AP destination email
3. Include metadata in email body (supplier ID, intent code, invoice number, timestamp)

Determine AP destination from EMAIL_ROUTING based on recipient_email.
Raise error if recipient_email has no configured routing.

Return: emails_sent count and results array with email_id, invoice_number, subject per email.
"""


@tool
def extraction_specialist(query: str) -> str:
    """Extract invoice data, supplier info, and attachments from email in S3"""
    try:
        logger.info("Extraction specialist invoked")
        with extraction_client:
            agent = Agent(
                system_prompt=EXTRACTION_AGENT_PROMPT,
                tools=extraction_client.list_tools_sync(),
                model=bedrock_model
            )
            result = str(agent(query))
            logger.info("Extraction specialist completed successfully")
            return result
    except Exception as e:
        logger.error(f"Error in extraction_specialist: {str(e)}")
        raise


@tool
def supplier_specialist(query: str) -> str:
    """Resolve supplier ID and type from DynamoDB SupplierDirectory"""
    try:
        logger.info("Supplier specialist invoked")
        with customer_client:
            agent = Agent(
                system_prompt=CUSTOMER_AGENT_PROMPT,
                tools=customer_client.list_tools_sync(),
                model=bedrock_model
            )
            result = str(agent(query))
            logger.info("Supplier specialist completed successfully")
            return result
    except Exception as e:
        logger.error(f"Error in supplier_specialist: {str(e)}")
        raise


@tool
def classification_specialist(query: str) -> str:
    """Classify supplier invoice email intent (INV/CRN/PAY/DIS/DUP/OTH)"""
    try:
        logger.info("Classification specialist invoked")
        with classification_client:
            agent = Agent(
                system_prompt=CLASSIFICATION_AGENT_PROMPT,
                tools=classification_client.list_tools_sync(),
                model=bedrock_model
            )
            result = str(agent(query))
            logger.info("Classification specialist completed successfully")
            return result
    except Exception as e:
        logger.error(f"Error in classification_specialist: {str(e)}")
        raise


@tool
def routing_specialist(query: str) -> str:
    """Format AP subject line and route invoice email via SES"""
    try:
        logger.info("Routing specialist invoked")
        with routing_client:
            agent = Agent(
                system_prompt=ROUTING_AGENT_PROMPT,
                tools=routing_client.list_tools_sync(),
                model=bedrock_model
            )
            result = str(agent(query))
            logger.info("Routing specialist completed successfully")
            return result
    except Exception as e:
        logger.error(f"Error in routing_specialist: {str(e)}")
        raise


ORCHESTRATOR_PROMPT = """
You are the AP Invoice Processing Supervisor Agent. You orchestrate a multi-agent workflow to process supplier invoice emails and route them to the correct Accounts Payable system.

Coordinate 4 specialized agents in sequence:
1. Extraction-Specialist: Extract invoice numbers, PO numbers, supplier name, amounts, and dates from email and PDF attachments
2. Supplier-Specialist: Resolve supplier ID and type from DynamoDB using email domain
3. Classification-Specialist: Classify invoice intent (INV, CRN, PAY, DIS, DUP, OTH)
4. Routing-Specialist: Format AP subject line and route to AP system via SES

Workflow:
1. Invoke Extraction-Specialist with s3_bucket and s3_object_key
   - Receive: invoice_numbers, po_numbers, supplier_name, email_domain, sender_email, recipient_email, structured_data

2. Invoke Supplier-Specialist with:
   - email_domain (from extraction)
   - supplier_name (from extraction)
   - Receive: supplier_id, supplier_type, ap_routing_code, unknown_vendor flag

3. Invoke Classification-Specialist with:
   - subject, body, structured_data (invoice amounts and dates)
   - Receive: intent_code (INV/CRN/PAY/DIS/DUP/OTH), confidence, manual_review_required

4. Invoke Routing-Specialist with:
   - original_subject, original_body, supplier_id, intent_code
   - invoice_numbers (JSON array string), recipient_email
   - Receive: emails_sent count and results

Summary must include:
- Supplier ID resolved (or UNKNOWN_VENDOR)
- Invoice number(s) found
- Intent code assigned (with confidence)
- Number of emails routed to AP system
- Any manual review flags

Retry failed agents up to 3 times before escalating.
"""

agent = Agent(
    system_prompt=ORCHESTRATOR_PROMPT,
    tools=[extraction_specialist, supplier_specialist, classification_specialist, routing_specialist],
    model=bedrock_model
)


@app.entrypoint
def invoice_orchestrator(payload):
    """Entrypoint for AgentCore Runtime"""
    logger.info("=== AP INVOICE ORCHESTRATOR STARTED ===")
    logger.info(f"Received payload: {payload}")

    try:
        s3_bucket = payload["s3_bucket"]
        s3_object_key = payload["s3_object_key"]
        upload_timestamp = datetime.utcnow().isoformat() + 'Z'

        logger.info(f"S3 Bucket: {s3_bucket}")
        logger.info(f"S3 Object Key: {s3_object_key}")
        logger.info(f"Upload Timestamp: {upload_timestamp}")

        user_input = f"""Process the supplier invoice email uploaded to S3 and route to the AP inbox.

Email Details:
- S3 Bucket: {s3_bucket}
- S3 Object Key: {s3_object_key}
- Upload Timestamp: {upload_timestamp}

Workflow Steps:
1. Extract invoice data and supplier info using Extraction-Specialist
2. Resolve supplier identity using Supplier-Specialist
3. Classify invoice intent using Classification-Specialist
4. Format subject and route to AP inbox using Routing-Specialist

Provide a summary including supplier ID, invoice number(s), intent code, and number of emails routed."""

        logger.info("Invoking orchestrator agent...")
        response = agent(user_input)
        logger.info("Agent invocation completed")
        logger.info(f"Response: {response.message['content'][0]['text'][:500]}...")

        return response.message['content'][0]['text']
    except KeyError as e:
        logger.error(f"Missing required field in payload: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Error in invoice_orchestrator: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise


if __name__ == "__main__":
    logger.info("Starting BedrockAgentCoreApp...")
    logger.info(f"Environment variables:")
    logger.info(f"  EXTRACTION_GATEWAY_URL: {os.getenv('EXTRACTION_GATEWAY_URL')}")
    logger.info(f"  CUSTOMER_GATEWAY_URL: {os.getenv('CUSTOMER_GATEWAY_URL')}")
    logger.info(f"  CLASSIFICATION_GATEWAY_URL: {os.getenv('CLASSIFICATION_GATEWAY_URL')}")
    logger.info(f"  ROUTING_GATEWAY_URL: {os.getenv('ROUTING_GATEWAY_URL')}")
    logger.info(f"  BEDROCK_MODEL: {os.getenv('BEDROCK_MODEL')}")
    logger.info(f"  AWS_REGION: {os.getenv('AWS_REGION')}")

    try:
        app.run()
    except Exception as e:
        logger.error(f"Failed to start application: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise
