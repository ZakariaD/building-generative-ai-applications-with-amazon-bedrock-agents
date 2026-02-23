import json
import boto3
import os
import email
import re
import base64
import uuid
import logging
from email import policy

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3 = boto3.client('s3')
bedrock_runtime = boto3.client('bedrock-runtime')

def get_named_property(event, name):
    item = next(
        (item for item in
         event['requestBody']['content']['application/json']['properties']
         if item['name'] == name), None)
    if item is None:
        raise ValueError(f"Property '{name}' not found in request")
    return item['value']

def lambda_handler(event, context):
    logger.info(f"=== EXTRACTION AGENT STARTED ===")
    logger.info(f"Event: {json.dumps(event, default=str)}")
    action = event.get('actionGroup')
    api_path = event.get('apiPath')

    try:
        logger.info(f"Processing API path: {api_path}")
        if api_path == '/extract':
            result = extract_email(event)
        else:
            result = {'error': 'Unknown action'}

        logger.info(f"=== EXTRACTION AGENT COMPLETED ===")
        logger.info(f"Result: {json.dumps(result, default=str)}")

        return {
            'messageVersion': '1.0',
            'response': {
                'actionGroup': action,
                'apiPath': api_path,
                'httpMethod': event.get('httpMethod'),
                'httpStatusCode': 200,
                'responseBody': {
                    'application/json': {
                        'body': json.dumps(result)
                    }
                }
            }
        }
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}")
        return {
            'messageVersion': '1.0',
            'response': {
                'actionGroup': action,
                'apiPath': api_path,
                'httpMethod': event.get('httpMethod'),
                'httpStatusCode': 500,
                'responseBody': {
                    'application/json': {
                        'body': json.dumps({'error': str(e)})
                    }
                }
            }
        }

def extract_email(event):
    s3_bucket = get_named_property(event, "s3_bucket")
    s3_object_key = get_named_property(event, "s3_object_key")

    logger.info(f"Extracting email from s3://{s3_bucket}/{s3_object_key}")

    response = s3.get_object(Bucket=s3_bucket, Key=s3_object_key)
    msg = email.message_from_bytes(response['Body'].read(), policy=policy.default)

    sender_raw = msg.get('From', '')
    sender_match = re.search(r'[\w\.\-]+@[\w\.\-]+', sender_raw)
    sender_email = sender_match.group(0) if sender_match else ''
    domain_match = re.search(r'@([\w\.\-]+)', sender_email)
    email_domain = domain_match.group(1) if domain_match else ''

    email_metadata = {
        'email_id': str(uuid.uuid4()),
        'sender_email': sender_email,
        'email_domain': email_domain,
        'to': msg.get('To', ''),
        'recipient_email': msg.get('To', '').split(',')[0].strip(),
        'subject': msg.get('Subject', ''),
        'date': msg.get('Date', ''),
        'email_body': _get_body(msg)
    }

    logger.info(f"Email metadata:")
    logger.info(f"  - sender_email: {sender_email}")
    logger.info(f"  - email_domain: {email_domain}")
    logger.info(f"  - recipient_email: {email_metadata['recipient_email']}")
    logger.info(f"  - subject: {email_metadata['subject']}")

    attachments = []
    invoice_numbers = set()
    po_numbers = set()

    for part in msg.walk():
        if part.get_content_disposition() == 'attachment':
            filename = part.get_filename('')
            if filename.lower().endswith('.pdf'):
                file_data = part.get_payload(decode=True)
                logger.info(f"Processing PDF attachment: {filename}, size: {len(file_data)} bytes")
                try:
                    structured = _extract_with_claude(file_data)
                    logger.info(f"=== EXTRACTED ENTITIES ===")
                    logger.info(f"Invoice Numbers: {structured.get('invoice_numbers', [])}")
                    logger.info(f"PO Numbers: {structured.get('po_numbers', [])}")
                    logger.info(f"Supplier Name: {structured.get('supplier_name')}")
                    logger.info(f"Total Amount: {structured.get('total_amount')}")
                    logger.info(f"Invoice Date: {structured.get('invoice_date')}")
                    logger.info(f"=== END EXTRACTED ENTITIES ===")
                except Exception as e:
                    logger.warning(f"PDF extraction failed for {filename}: {e}")
                    structured = {}

                for inv in structured.get('invoice_numbers', []):
                    invoice_numbers.add(inv)
                for po in structured.get('po_numbers', []):
                    po_numbers.add(po)

                attachments.append({
                    'id': str(uuid.uuid4()),
                    'filename': filename,
                    's3_key': s3_object_key,
                    'content_type': 'application/pdf',
                    'structured_data': structured
                })

    # Fallback: extract from email body if no attachments yielded data
    if not invoice_numbers:
        logger.info("No invoice numbers from PDF, falling back to email body extraction")
        for m in re.findall(r'[A-Z]{2,}-[\d]{3,}', email_metadata['email_body']):
            invoice_numbers.add(m)
    if not po_numbers:
        logger.info("No PO numbers from PDF, falling back to email body extraction")
        for m in re.findall(r'(?:PO|P\.O\.)\s*#?\s*([\d]{5,})', email_metadata['email_body']):
            po_numbers.add(m)

    logger.info(f"Final invoice_numbers: {list(invoice_numbers)}")
    logger.info(f"Final po_numbers: {list(po_numbers)}")

    return {
        'email_metadata': email_metadata,
        'attachments': attachments,
        'invoice_numbers': list(invoice_numbers),
        'po_numbers': list(po_numbers),
        'sender_email': sender_email,
        'email_domain': email_domain,
        'recipient_email': email_metadata['recipient_email']
    }

def _extract_with_claude(pdf_bytes):
    model_id = os.environ.get('FOUNDATION_MODEL', 'us.anthropic.claude-sonnet-4-5-20250929-v1:0')
    logger.info(f"Using model: {model_id}")

    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 2000,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "document", "source": {"type": "base64", "media_type": "application/pdf",
                                                "data": base64.b64encode(pdf_bytes).decode()}},
                {"type": "text", "text": """Extract from this invoice/document:
1. Invoice number(s) (e.g. INV-458921)
2. PO number(s)
3. Supplier name
4. Invoice date
5. Total amount and currency

Return JSON only:
{
  "invoice_numbers": ["list"],
  "po_numbers": ["list"],
  "supplier_name": "name or null",
  "invoice_date": "date or null",
  "total_amount": "amount or null",
  "currency": "USD/EUR/etc or null"
}"""}
            ]
        }]
    }

    response = bedrock_runtime.invoke_model(modelId=model_id, body=json.dumps(body))
    text = json.loads(response['body'].read())['content'][0]['text']
    logger.info(f"Claude response: {text}")

    match = re.search(r'\{.*\}', text, re.DOTALL)
    return json.loads(match.group()) if match else {}

def _get_body(msg):
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == 'text/plain':
                return part.get_payload(decode=True).decode('utf-8', errors='ignore')
    else:
        return msg.get_payload(decode=True).decode('utf-8', errors='ignore')
    return ''
