import json
import boto3
import os
from datetime import datetime
import logging


logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource('dynamodb')

tasks_table = dynamodb.Table(os.environ.get('ONBOARDING_TASKS_TABLE'))

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
    action = event.get('actionGroup')
    api_path = event.get('apiPath')

    print("DEBUG: Lambda event ", str(event))
    print("DEBUG: Lambda context ", str(context))
    
    try:
        if api_path == '/onboarding-tasks':
            result = get_onboarding_tasks(event)
        elif api_path == '/onboarding-task-update':
            result = update_task_status(event)
        else:
            result = {'error': 'Unknown action'}
        
        return {
            'messageVersion': '1.0',
            'response': {
                'actionGroup': action,
                'apiPath': api_path,
                'httpMethod': event.get('httpMethod'),
                'httpStatusCode': 200,
                'responseBody': {
                    'application/json': {
                        'body': json.dumps(result, default=str)
                    }
                }
            }
        }
    except Exception as e:
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

def get_onboarding_tasks(event):
    employee_id = get_named_parameter(event, "employee_id")
    
    try:
        response = tasks_table.query(
            KeyConditionExpression='employee_id = :emp_id',
            ExpressionAttributeValues={':emp_id': employee_id}
        )
        return response.get('Items', [])
    except Exception as e:
        logger.error(f"Error querying tasks for employee {employee_id}: {str(e)}")
        return []

def update_task_status(event):
    
    employee_id = get_named_property(event, "employee_id")
    task_id     = get_named_property(event, "task_id")
    status      = get_named_property(event, "status")
        
    update_expression = 'SET #status = :status'
    expression_attribute_names = {'#status': 'status'}
    expression_attribute_values = {':status': status}
    
    if status == 'completed':
        update_expression += ', completed_date = :completed_date'
        expression_attribute_values[':completed_date'] = datetime.now().isoformat()
    
    tasks_table.update_item(
        Key={'employee_id': employee_id, 'task_id': task_id},
        UpdateExpression=update_expression,
        ExpressionAttributeNames=expression_attribute_names,
        ExpressionAttributeValues=expression_attribute_values
    )
    
    return {'message': 'Task updated successfully'}