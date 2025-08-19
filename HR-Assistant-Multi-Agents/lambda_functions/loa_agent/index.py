import json
import boto3
import os
from datetime import datetime
import uuid
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource('dynamodb')

leave_table = dynamodb.Table(os.environ.get('LEAVE_REQUESTS_TABLE'))
employee_table = dynamodb.Table(os.environ.get('EMPLOYEE_TABLE'))


def get_named_parameter(event, name):
  return next(item for item in event['parameters'] if item['name'] == name)['value']

def get_named_property(event, name):
  item = next(
      (item for item in
       event['requestBody']['content']['application/json']['properties']
       if item['name'] == name), None)
  if item is None:
    raise ValueError(f"Property '{name}' not found in request")
  return item['value']

def lambda_handler(event, context):
    logger.info(f"Received event: {json.dumps(event)}")
    action = event.get('actionGroup')
    api_path = event.get('apiPath')

    print("DEBUG: Lambda event ", str(event))
    print("DEBUG: Lambda context ", str(context))
    
    try:
        logger.info(f"Processing API path: {api_path}")
        if api_path == '/leave-request':
            result = submit_leave_request(event)
        elif api_path == '/leave-balance':
            result = get_leave_balance(event)
        else:
            result = {'error': 'Unknown action'}
        
        logger.info(f"Function result: {json.dumps(result, default=str)}")
        
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

def submit_leave_request(event):
   
    employee_id = get_named_property(event, "employee_id")
    leave_type  = get_named_property(event, "leave_type")
    start_date  = get_named_property(event, "start_date")
    end_date    = get_named_property(event, "end_date")
    reason      = get_named_property(event, "reason")
    
    # Calculate days requested
    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d')
    days_requested = (end - start).days + 1
    
    # Get manager ID from employee table
    employee_response = employee_table.get_item(Key={'employee_id': employee_id})
    manager_id = employee_response.get('Item', {}).get('manager_id', 'null')
    
    # Generate request ID following REQ00X pattern
    response = leave_table.scan(ProjectionExpression='request_id')
    existing_ids = [item['request_id'] for item in response.get('Items', []) if item['request_id'].startswith('REQ')]
    next_num = len([id for id in existing_ids if id.startswith('REQ')]) + 1
    request_id = f'REQ{next_num:03d}'
    
    leave_table.put_item(
        Item={
            'request_id': request_id,
            'employee_id': employee_id,
            'leave_type': leave_type,
            'start_date': start_date,
            'end_date': end_date,
            'days_requested': days_requested,
            'reason': reason,
            'status': 'pending',
            'approved_by': manager_id,
            'submitted_date': datetime.now().isoformat()
        }
    )
    
    return {
        'message': 'Leave request submitted successfully',
        'request_id': request_id
    }

def get_leave_balance(event):
    employee_id = get_named_parameter(event, "employee_id")
    
    try:
        employee_response = employee_table.get_item(Key={'employee_id': employee_id})
        employee_data = employee_response.get('Item')
        pto_balance = float(employee_data.get('pto_balance'))
        sick_balance = float(employee_data.get('sick_balance'))

        return {
            'employee_id': employee_id,
            'pto_balance': pto_balance,
            'sick_balance': sick_balance
        }
    except Exception as e:
        logger.error(f"Error getting employee data for {employee_id}: {str(e)}")
        return []    
    