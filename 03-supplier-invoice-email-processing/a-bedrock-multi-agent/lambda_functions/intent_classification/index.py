import json
import boto3
import os
import re
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

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
    logger.info(f"=== CLASSIFICATION AGENT STARTED ===")
    logger.info(f"Event: {json.dumps(event, default=str)}")
    action = event.get('actionGroup')
    api_path = event.get('apiPath')

    try:
        logger.info(f"Processing API path: {api_path}")
        if api_path == '/classify':
            result = classify_invoice(event)
        else:
            result = {'error': 'Unknown action'}

        logger.info(f"=== CLASSIFICATION AGENT COMPLETED ===")
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

def classify_invoice(event):
    subject = get_named_property(event, "subject")
    body = get_named_property(event, "body")
    structured_data = get_named_property(event, "structured_data") if 'structured_data' in str(event) else '{}'

    logger.info(f"Classifying invoice email:")
    logger.info(f"  - Subject: {subject}")
    logger.info(f"  - Body length: {len(body)} chars")

    try:
        structured = json.loads(structured_data) if isinstance(structured_data, str) else structured_data
        logger.info(f"  - Structured data: {json.dumps(structured, default=str)}")
    except Exception:
        structured = {}
        logger.warning("Failed to parse structured_data")

    prompt = f"""Classify this supplier invoice email into ONE intent code.

Subject: {subject}
Body: {body}
Invoice data: amount={structured.get('total_amount')}, date={structured.get('invoice_date')}

Codes:
- INV: Supplier submitting an invoice for payment
- CRN: Credit note or credit memo
- PAY: Payment status inquiry or remittance
- DIS: Dispute, discrepancy, or complaint
- DUP: Duplicate invoice submission
- OTH: Other / unclear

Return JSON only:
{{"intent_code": "INV|CRN|PAY|DIS|DUP|OTH", "confidence": 0-100, "reasoning": "Brief explanation"}}"""

    model_id = os.environ.get('FOUNDATION_MODEL', 'us.anthropic.claude-sonnet-4-5-20250929-v1:0')
    logger.info(f"Using model: {model_id}")
    logger.info("Invoking Bedrock Claude...")

    response = bedrock_runtime.invoke_model(
        modelId=model_id,
        body=json.dumps({
            'anthropic_version': 'bedrock-2023-05-31',
            'max_tokens': 300,
            'messages': [{'role': 'user', 'content': prompt}]
        })
    )

    text = json.loads(response['body'].read())['content'][0]['text']
    logger.info(f"Claude response: {text}")
    logger.info("Parsing classification JSON...")

    try:
        result = json.loads(text)
        logger.info("Direct JSON parse successful")
    except json.JSONDecodeError:
        logger.info("Direct JSON parse failed, trying extraction...")
        match = re.search(r'\{.*\}', text, re.DOTALL)
        result = json.loads(match.group()) if match else {'intent_code': 'OTH', 'confidence': 0, 'reasoning': 'parse error'}

    logger.info(f"Intent code: {result['intent_code']}")
    logger.info(f"Confidence: {result['confidence']}%")
    logger.info(f"Reasoning: {result['reasoning']}")

    return {
        'intent_code': result['intent_code'],
        'confidence': result['confidence'],
        'confidence_level': get_confidence_level(result['confidence']),
        'reasoning': result['reasoning'],
        'manual_review_required': result['confidence'] < 70
    }

def get_confidence_level(confidence):
    if confidence >= 90:
        return 'high'
    elif confidence >= 70:
        return 'medium'
    else:
        return 'low'
