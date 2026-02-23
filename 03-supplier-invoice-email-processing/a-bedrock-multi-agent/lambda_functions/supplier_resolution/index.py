import json
import boto3
import os
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource('dynamodb')

def get_named_property(event, name):
    item = next(
        (item for item in
         event['requestBody']['content']['application/json']['properties']
         if item['name'] == name), None)
    if item is None:
        raise ValueError(f"Property '{name}' not found in request")
    return item['value']

def lambda_handler(event, context):
    logger.info(f"=== SUPPLIER RESOLUTION AGENT STARTED ===")
    logger.info(f"Event: {json.dumps(event, default=str)}")
    action = event.get('actionGroup')
    api_path = event.get('apiPath')

    try:
        logger.info(f"Processing API path: {api_path}")
        if api_path == '/resolve':
            result = resolve_supplier(event)
        else:
            result = {'error': 'Unknown action'}

        logger.info(f"=== SUPPLIER RESOLUTION AGENT COMPLETED ===")
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

def resolve_supplier(event):
    email_domain = get_named_property(event, "email_domain")
    supplier_name = get_named_property(event, "supplier_name") if 'supplier_name' in str(event) else None

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
        'ap_routing_code': 'AP_MANUAL',  # AP = Accounts Payable. AP_MANUAL = route to AP team for manual processing
        'unknown_vendor': True
    }
