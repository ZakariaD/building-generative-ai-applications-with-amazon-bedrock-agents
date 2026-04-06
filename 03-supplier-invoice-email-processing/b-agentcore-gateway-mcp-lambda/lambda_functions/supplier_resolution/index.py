import json
import boto3
import os
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource('dynamodb')


def lambda_handler(event, context):
    logger.info(f"=== SUPPLIER RESOLUTION AGENT STARTED ===")

    try:
        tool_name = context.client_context.custom['bedrockAgentCoreToolName']
        delimiter = "___"
        if delimiter in tool_name:
            tool_name = tool_name[tool_name.index(delimiter) + len(delimiter):]

        if tool_name == 'resolve':
            result = resolve_supplier(event)
        else:
            result = {'error': 'Unknown tool'}

        logger.info(f"=== SUPPLIER RESOLUTION AGENT COMPLETED ===")
        return {'statusCode': 200, 'body': json.dumps(result)}
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return {'statusCode': 500, 'body': json.dumps({'error': str(e)})}


def resolve_supplier(params):
    email_domain = params.get('email_domain')
    supplier_name = params.get('supplier_name')

    logger.info(f"Resolving supplier:")
    logger.info(f"  - email_domain: {email_domain}")
    logger.info(f"  - supplier_name: {supplier_name}")

    table_name = os.environ['SUPPLIER_TABLE']
    table = dynamodb.Table(table_name)
    logger.info(f"Querying DynamoDB table: {table_name}")

    # Priority 1: exact email_domain match (partition key)
    logger.info(f"Strategy 1: Exact email_domain match for '{email_domain}'")
    response = table.get_item(Key={'email_domain': email_domain})
    item = response.get('Item')

    if item:
        logger.info(f"Match found via email_domain")
    else:
        logger.info(f"No match via email_domain")

    # Priority 2: supplier name scan fallback
    if not item and supplier_name:
        logger.info(f"Strategy 2: Supplier name scan for '{supplier_name}'")
        scan = table.scan(
            FilterExpression='contains(supplier_name, :name)',
            ExpressionAttributeValues={':name': supplier_name}
        )
        item = scan['Items'][0] if scan['Items'] else None
        if item:
            logger.info(f"Match found via supplier_name scan")
        else:
            logger.info(f"No match via supplier_name scan")

    if item:
        logger.info(f"Supplier resolved: {item['supplier_id']} ({item['supplier_type']})")
        return {
            'supplier_id': item['supplier_id'],
            'supplier_name': item['supplier_name'],
            'supplier_type': item['supplier_type'],
            'default_currency': item.get('default_currency', 'USD'),
            'ap_routing_code': item['ap_routing_code'],
            'unknown_vendor': False
        }

    logger.warning(f"No supplier found for domain={email_domain}. Returning UNKNOWN_VENDOR.")
    return {
        'supplier_id': 'UNKNOWN_VENDOR',
        'supplier_name': None,
        'supplier_type': 'UNKNOWN',
        'default_currency': None,
        'ap_routing_code': 'AP_MANUAL',
        'unknown_vendor': True
    }
