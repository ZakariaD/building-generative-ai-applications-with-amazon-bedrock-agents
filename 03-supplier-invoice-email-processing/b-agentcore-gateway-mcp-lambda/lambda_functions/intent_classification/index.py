import json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    logger.info(f"=== CLASSIFICATION AGENT STARTED ===")

    try:
        tool_name = context.client_context.custom['bedrockAgentCoreToolName']
        delimiter = "___"
        if delimiter in tool_name:
            tool_name = tool_name[tool_name.index(delimiter) + len(delimiter):]

        if tool_name == 'classify':
            result = get_email_content(event)
        else:
            result = {'error': 'Unknown tool'}

        logger.info(f"=== CLASSIFICATION AGENT COMPLETED ===")
        return {'statusCode': 200, 'body': json.dumps(result)}
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return {'statusCode': 500, 'body': json.dumps({'error': str(e)})}


def get_email_content(params):
    """Return the raw email content for the orchestrator agent to classify directly."""
    subject = params.get('subject', '')
    body = params.get('body', '')
    structured_data = params.get('structured_data', '{}')

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
