import json
import boto3
import os
from decimal import Decimal
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource('dynamodb')

# Get employee data

employee_table = dynamodb.Table(os.environ.get('EMPLOYEE_TABLE'))
payroll_table = dynamodb.Table(os.environ.get('PAYROLL_TABLE'))

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
        if api_path == '/payroll-calculate':
            result = calculate_payroll(event)
        elif api_path == '/payroll-history':
            result = get_payroll_history(event)
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
                        'body': json.dumps(result, default=str)
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

def calculate_payroll(event):
    employee_id = get_named_property(event, "employee_id")
    pay_period = get_named_property(event, "pay_period")
    
    employee = employee_table.get_item(Key={'employee_id': employee_id})
    if 'Item' not in employee:
        raise Exception(f'Employee {employee_id} not found')
    
    gross_pay = float(employee['Item']['salary']) / 26
    
    # Calculate deductions
    federal_tax = gross_pay * 0.15
    state_tax = gross_pay * 0.04
    social_security = gross_pay * 0.062
    medicare = gross_pay * 0.0145
    health_insurance = 150.0
    dental_insurance = 25.0
    retirement_401k = gross_pay * 0.06
    
    total_deductions = federal_tax + state_tax + social_security + medicare + health_insurance + dental_insurance + retirement_401k
    net_pay = gross_pay - total_deductions
    
    payroll_data = {
        'employee_id': employee_id,
        'pay_period': pay_period,
        'gross_pay': Decimal(str(gross_pay)),
        'federal_tax': Decimal(str(federal_tax)),
        'state_tax': Decimal(str(state_tax)),
        'social_security': Decimal(str(social_security)),
        'medicare': Decimal(str(medicare)),
        'health_insurance': Decimal(str(health_insurance)),
        'dental_insurance': Decimal(str(dental_insurance)),
        'retirement_401k': Decimal(str(retirement_401k)),
        'net_pay': Decimal(str(net_pay)),
        'overtime_hours': Decimal('0'),
        'overtime_pay': Decimal('0')
    }
    
    payroll_table.put_item(Item=payroll_data)
    
    return {
        'employee_id': employee_id,
        'pay_period': pay_period,
        'gross_pay': gross_pay,
        'net_pay': net_pay,
        'deductions': {
            'federal_tax': federal_tax,
            'state_tax': state_tax,
            'social_security': social_security,
            'medicare': medicare,
            'health_insurance': health_insurance,
            'retirement_401k': retirement_401k
        }
    }

def get_payroll_history(event):
    
    employee_id = get_named_parameter(event, "employee_id")
    
    logger.info(f"Using employee_id: {employee_id}")
    
    logger.info(f"Querying payroll history for employee: {employee_id}")
    
    try:
        response = payroll_table.query(
            KeyConditionExpression='employee_id = :emp_id',
            ExpressionAttributeValues={':emp_id': employee_id}
        )
        logger.info(f"Payroll records found: {len(response.get('Items', []))}")
        return response['Items']
    except Exception as e:
        logger.error(f"Error querying payroll history: {str(e)}")
        raise