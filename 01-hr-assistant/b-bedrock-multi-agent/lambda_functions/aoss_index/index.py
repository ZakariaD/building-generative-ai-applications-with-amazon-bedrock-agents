import boto3
import os
import sys
import subprocess
import json
import urllib3
import time

subprocess.call('pip install opensearch-py -t /tmp/ --no-cache-dir'.split(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
sys.path.insert(1, '/tmp/')

from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth

# Model dimension mapping
DIMENSION_MAP = {
    'amazon.titan-embed-text-v1': 1536,
    'amazon.titan-embed-text-v2:0': 1536,
    'cohere.embed-english-v3': 1024,
    'cohere.embed-multilingual-v3': 1024
}

def send_response(event, context, response_status, response_data=None, physical_resource_id=None, reason=None):
    """Send response to CloudFormation"""
    response_data = response_data or {}
    physical_resource_id = physical_resource_id or context.log_stream_name
    
    response_body = {
        'Status': response_status,
        'Reason': reason or f'See CloudWatch Log Stream: {context.log_stream_name}',
        'PhysicalResourceId': physical_resource_id,
        'StackId': event['StackId'],
        'RequestId': event['RequestId'],
        'LogicalResourceId': event['LogicalResourceId'],
        'Data': response_data
    }
    
    json_response_body = json.dumps(response_body)
    
    headers = {
        'content-type': '',
        'content-length': str(len(json_response_body))
    }
    
    try:
        http = urllib3.PoolManager()
        response = http.request('PUT', event['ResponseURL'], body=json_response_body, headers=headers)
        print(f"Status code: {response.status}")
    except Exception as e:
        print(f"Failed to send response: {e}")

def create_index(collection_endpoint, index_name):
    """Create OpenSearch index"""
    session = boto3.Session()
    region = session.region_name
    credentials = session.get_credentials()
    
    # Extract host from endpoint
    host = collection_endpoint.replace('https://', '')
    
    client = OpenSearch(
        hosts=[{'host': host, 'port': 443}],
        http_auth=AWSV4SignerAuth(credentials, region, 'aoss'),
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection
    )
    
    model = os.environ['BEDROCK_EMBEDDING_MODEL_NAME']
    dimension = DIMENSION_MAP.get(model.split('/')[-1], 1536)
    
    index_body = {
        'settings': {'index': {'knn.algo_param': {'ef_search': 512}, 'knn': True}},
        'mappings': {
            'properties': {
                'AMAZON_BEDROCK_METADATA': {'type': 'text'},
                'AMAZON_BEDROCK_TEXT_CHUNK': {'type': 'text'},
                index_name+'-kb-vector': {
                    'type': 'knn_vector',
                    'dimension': dimension,
                    'method': {
                        'engine': 'faiss',
                        'name': 'hnsw',
                        'space_type': 'l2',
                        'parameters': {'ef_construction': 512, 'm': 16}
                    }
                }
            }
        }
    }
    
    response = client.indices.create(index=index_name, body=index_body)
    return response

# def delete_index(collection_endpoint, index_name):
#     """Delete OpenSearch index"""
#     session = boto3.Session()
#     region = session.region_name
#     credentials = session.get_credentials()
    
#     host = collection_endpoint.replace('https://', '')
    
#     client = OpenSearch(
#         hosts=[{'host': host, 'port': 443}],
#         http_auth=AWSV4SignerAuth(credentials, region, 'aoss'),
#         use_ssl=True,
#         verify_certs=True,
#         connection_class=RequestsHttpConnection
#     )
    
#     try:
#         response = client.indices.delete(index=index_name)
#         return response
#     except Exception as e:
#         print(f"Index {index_name} may not exist: {e}")
#         return None

def on_event(event, context):
    """Custom resource handler"""
    print(f"Received event: {json.dumps(event)}")
    
    request_type = event['RequestType']
    properties = event['ResourceProperties']
    collection_endpoint = properties['CollectionEndpoint']
    index_names = properties['IndexNames']
    collection_name = properties['CollectionName']
    
    # physical_resource_id = f"{collection_name}-{index_name}"
    
    try:
        if request_type == 'Create':
            for index_name in index_names:
                print(f"Creating index {index_name} for collection {collection_name}")
                response = create_index(collection_endpoint, index_name)
                print(f"Index created successfully: {response}")

                physical_resource_id = f"{collection_name}-{index_name}"
                
                send_response(event, context, 'SUCCESS', 
                            {'IndexName': index_name, 'Status': 'Created'}, 
                            physical_resource_id, 
                            f"Index {index_name} created successfully")
            
        # elif request_type == 'Update':
        #     print(f"Update not supported for index {index_name}")
        #     send_response(event, context, 'SUCCESS', 
        #                  {'IndexName': index_name, 'Status': 'No changes'}, 
        #                  physical_resource_id, 
        #                  "Update operation completed")
            
        # elif request_type == 'Delete':
        #     print(f"Deleting index {index_name} for collection {collection_name}")
        #     delete_index(collection_endpoint, index_name)
        #     print(f"Index deleted successfully")
            
        #     send_response(event, context, 'SUCCESS', 
        #                  {'IndexName': index_name, 'Status': 'Deleted'}, 
        #                  physical_resource_id, 
        #                  f"Index {index_name} deleted successfully")
            
    except Exception as e:
        for index_name in index_names:
            error_message = f"Error processing {request_type} request: {str(e)}"
            print(error_message)
            physical_resource_id = f"{collection_name}-{index_name}"
            send_response(event, context, 'FAILED', {}, 
                        physical_resource_id, error_message)

# Keep the original lambda_handler for backward compatibility
def lambda_handler(event, context):
    """Original handler - now delegates to on_event"""
    return on_event(event, context)