import json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)


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
            result = get_email_content(event)
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


def get_email_content(event):
    """Return raw email content for the Bedrock agent's LLM to classify."""
    subject = get_named_property(event, "subject")
    body = get_named_property(event, "body")
    structured_data = get_named_property(event, "structured_data") if 'structured_data' in str(event) else '{}'

    logger.info(f"Returning email content for classification:")
    logger.info(f"  - Subject: {subject}")
    logger.info(f"  - Body length: {len(body)} chars")

    try:
        structured = json.loads(structured_data) if isinstance(structured_data, str) else structured_data
    except Exception:
        structured = {}
        logger.warning("Failed to parse structured_data")

    return {
        'subject': subject,
        'body': body,
        'invoice_amount': structured.get('total_amount'),
        'invoice_date': structured.get('invoice_date'),
        'currency': structured.get('currency')
    }
