import json
import boto3
import os
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import logging
import uuid

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ses = boto3.client('ses')

def get_named_property(event, name):
    item = next(
        (item for item in
         event['requestBody']['content']['application/json']['properties']
         if item['name'] == name), None)
    if item is None:
        raise ValueError(f"Property '{name}' not found in request")
    return item['value']

def lambda_handler(event, context):
    logger.info(f"=== AP ROUTING AGENT STARTED ===")
    logger.info(f"Event: {json.dumps(event, default=str)}")
    action = event.get('actionGroup')
    api_path = event.get('apiPath')

    try:
        logger.info(f"Processing API path: {api_path}")
        if api_path == '/route':
            result = route_invoice(event)
        else:
            result = {'error': 'Unknown action'}

        logger.info(f"=== AP ROUTING AGENT COMPLETED ===")
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

def route_invoice(event):
    original_subject = get_named_property(event, "original_subject")
    original_body = get_named_property(event, "original_body")
    supplier_id = get_named_property(event, "supplier_id")
    intent_code = get_named_property(event, "intent_code")
    recipient_email = get_named_property(event, "recipient_email")

    logger.info(f"Routing invoice:")
    logger.info(f"  - Subject: {original_subject}")
    logger.info(f"  - Supplier ID: {supplier_id}")
    logger.info(f"  - Intent code: {intent_code}")
    logger.info(f"  - Recipient email: {recipient_email}")

    invoice_numbers_str = get_named_property(event, "invoice_numbers") if 'invoice_numbers' in str(event) else '[]'
    logger.info(f"  - Invoice numbers string: {invoice_numbers_str}")

    try:
        invoice_numbers = json.loads(invoice_numbers_str) if isinstance(invoice_numbers_str, str) else invoice_numbers_str
        logger.info(f"  - Parsed invoice numbers: {invoice_numbers}")
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse invoice numbers: {e}. Using empty list.")
        invoice_numbers = []

    email_routing = json.loads(os.environ.get('EMAIL_ROUTING', '{}'))
    if recipient_email not in email_routing:
        raise ValueError(f"No routing configured for recipient: {recipient_email}")

    ap_email = email_routing[recipient_email]
    from_email = ap_email
    logger.info(f"  - From: {from_email}, To: {ap_email}")

    emails_sent = []

    if len(invoice_numbers) <= 1:
        logger.info("Single invoice - sending one email")
        invoice_number = invoice_numbers[0] if invoice_numbers else ''
        email_id = send_email(from_email, ap_email, original_subject, original_body,
                              supplier_id, invoice_number, intent_code)
        emails_sent.append({
            'email_id': email_id,
            'invoice_number': invoice_number,
            'subject': format_subject(original_subject, supplier_id, invoice_number, intent_code)
        })
    else:
        logger.info(f"Multiple invoices ({len(invoice_numbers)}) - splitting into separate emails")
        for idx, invoice_number in enumerate(invoice_numbers, 1):
            logger.info(f"Sending email {idx}/{len(invoice_numbers)} for invoice: {invoice_number}")
            email_id = send_email(from_email, ap_email, original_subject, original_body,
                                  supplier_id, invoice_number, intent_code)
            emails_sent.append({
                'email_id': email_id,
                'invoice_number': invoice_number,
                'subject': format_subject(original_subject, supplier_id, invoice_number, intent_code)
            })

    logger.info(f"Total emails sent: {len(emails_sent)}")
    return {'emails_sent': len(emails_sent), 'results': emails_sent}

def format_subject(original_subject, supplier_id, invoice_number, intent_code):
    inv_part = f"Invoice# {invoice_number} | " if invoice_number else ""
    return f"{original_subject} >> {inv_part}Vendor {supplier_id} | {intent_code} <<"

def send_email(from_email, to_email, subject, body, supplier_id, invoice_number, intent_code):
    formatted_subject = format_subject(subject, supplier_id, invoice_number, intent_code)
    logger.info(f"Sending email with subject: {formatted_subject}")

    processing_time_utc = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')

    body_text = f"""{body}

---
Processed by AP Invoice Routing System
Supplier ID: {supplier_id}
Invoice Number: {invoice_number if invoice_number else 'N/A'}
Intent Code: {intent_code}
Processing Timestamp: {datetime.utcnow().isoformat()}Z
"""

    body_html = f"""<html>
<head>
  <style>
    body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; color: #333; background: #f5f5f5; }}
    .email-content {{ background: #ffffff; padding: 20px; margin-bottom: 20px; color: #333; }}
    .metadata-section {{ background: #2c3e50; color: #ffffff; padding: 25px; border-radius: 8px; margin-top: 20px; border: 2px solid #34495e; }}
    .metadata-title {{ font-size: 18px; font-weight: bold; margin-bottom: 15px; border-bottom: 2px solid #3498db; padding-bottom: 10px; color: #ffffff; }}
    .metadata-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-top: 15px; }}
    .metadata-item {{ background: #34495e; padding: 12px; border-radius: 6px; border-left: 4px solid #f39c12; }}
    .metadata-label {{ font-size: 11px; text-transform: uppercase; letter-spacing: 1px; color: #ecf0f1; margin-bottom: 5px; font-weight: 600; }}
    .metadata-value {{ font-size: 16px; font-weight: bold; color: #ffffff; }}
    .highlight {{ background: #f39c12; color: #000; padding: 3px 10px; border-radius: 4px; font-weight: bold; }}
    .footer {{ margin-top: 20px; font-size: 12px; color: #bdc3c7; text-align: center; }}
  </style>
</head>
<body>
  <div class="email-content">
    <p>{body.replace(chr(10), '<br>')}</p>
  </div>
  <div class="metadata-section">
    <div class="metadata-title">🤖 AP Invoice Metadata</div>
    <div class="metadata-grid">
      <div class="metadata-item">
        <div class="metadata-label">Supplier ID</div>
        <div class="metadata-value"><span class="highlight">{supplier_id}</span></div>
      </div>
      <div class="metadata-item">
        <div class="metadata-label">Intent Code</div>
        <div class="metadata-value"><strong>{intent_code}</strong></div>
      </div>
      <div class="metadata-item">
        <div class="metadata-label">Invoice Number</div>
        <div class="metadata-value"><strong>{invoice_number if invoice_number else 'N/A'}</strong></div>
      </div>
      <div class="metadata-item">
        <div class="metadata-label">Processing Time</div>
        <div class="metadata-value">{processing_time_utc}</div>
      </div>
    </div>
    <div class="footer">
      ⚡ Powered by Amazon Bedrock Multi-Agent Collaboration | AP Invoice Routing System
    </div>
  </div>
</body>
</html>
"""

    msg = MIMEMultipart('alternative')
    msg['Subject'] = formatted_subject
    msg['From'] = from_email
    msg['To'] = to_email

    msg.attach(MIMEText(body_text, 'plain', 'UTF-8'))
    msg.attach(MIMEText(body_html, 'html', 'UTF-8'))

    logger.info(f"Calling SES send_raw_email...")
    response = ses.send_raw_email(
        Source=from_email,
        Destinations=[to_email],
        RawMessage={'Data': msg.as_string()}
    )

    message_id = response['MessageId']
    logger.info(f"Email sent successfully. MessageId: {message_id}")
    return message_id
