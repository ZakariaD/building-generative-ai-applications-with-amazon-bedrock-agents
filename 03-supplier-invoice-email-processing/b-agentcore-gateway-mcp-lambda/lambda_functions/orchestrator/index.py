import boto3
import json
import os
import logging
from datetime import datetime
from urllib.parse import unquote_plus
import traceback

logger = logging.getLogger()
logger.setLevel(logging.INFO)

bedrock_agentcore = boto3.client('bedrock-agentcore')


def lambda_handler(event, context):
    logger.info("=== ORCHESTRATOR LAMBDA STARTED ===")
    logger.info(f"Event: {json.dumps(event, default=str)}")

    batch_item_failures = []

    for record in event['Records']:
        message_id = record['messageId']
        try:
            s3_event = json.loads(record['body'])
            # When S3 → SQS notification is first created,
            # S3 sends an s3:TestEvent to verify the connection. This test message
            # lacks the 'Records' key that real S3 upload events have, so we skip it.
            if 'Records' not in s3_event:
                logger.info(f"Skipping s3:TestEvent — When S3-SQS notification is first created, S3 sends a test message that lacks the Records key. Body: {record['body'][:200]}")
                continue
            s3_record = s3_event['Records'][0]['s3']
            s3_bucket = s3_record['bucket']['name']
            s3_object_key = unquote_plus(s3_record['object']['key'])

            # Skip SES setup notification — SES drops this file when receipt rules
            # are first activated to confirm it has write access to the bucket.
            if s3_object_key.endswith('AMAZON_SES_SETUP_NOTIFICATION'):
                logger.info(f"Skipping AMAZON_SES_SETUP_NOTIFICATION: {s3_object_key}")
                continue

            upload_timestamp = datetime.utcnow().isoformat() + 'Z'

            logger.info(f"Processing SQS Message ID: {message_id}")
            logger.info(f"S3 Trigger Details:")
            logger.info(f"  - Bucket: {s3_bucket}")
            logger.info(f"  - Key: {s3_object_key}")
            logger.info(f"  - Timestamp: {upload_timestamp}")

            runtime_endpoint_arn = os.environ['RUNTIME_ENDPOINT_ARN']
            logger.info(f"Runtime Endpoint ARN: {runtime_endpoint_arn}")

            runtime_arn = runtime_endpoint_arn.split('/runtime-endpoint/')[0]
            endpoint_name = runtime_endpoint_arn.split('/runtime-endpoint/')[1]

            payload = {
                "s3_bucket": s3_bucket,
                "s3_object_key": s3_object_key
            }

            session_id = f"session-{s3_object_key.replace('/', '-')}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            payload_json = json.dumps(payload)

            logger.info(f"Calling bedrock_agentcore.invoke_agent_runtime...")
            logger.info(f"  agentRuntimeArn: {runtime_arn}")
            logger.info(f"  runtimeSessionId: {session_id}")

            response = bedrock_agentcore.invoke_agent_runtime(
                agentRuntimeArn=runtime_arn,
                runtimeSessionId=session_id,
                payload=payload_json
            )

            logger.info("invoke_agent_runtime call succeeded")
            response_body = response['response'].read()
            logger.info(f"Response body (first 500 chars): {response_body[:500]}")

            response_data = json.loads(response_body)
            logger.info(f"Response: {json.dumps(response_data, indent=2)}")

            logger.info(f"=== INVOICE PROCESSING SUMMARY ===")
            logger.info(f"  - S3 Bucket: {s3_bucket}")
            logger.info(f"  - S3 Object Key: {s3_object_key}")
            logger.info(f"  - Timestamp: {upload_timestamp}")
            logger.info(f"Successfully processed message: {message_id}")
            logger.info(f"=== END INVOICE PROCESSING SUMMARY ===")

        except Exception as e:
            logger.error(f"Failed to process message {message_id}")
            logger.error(f"Error: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            batch_item_failures.append({"itemIdentifier": message_id})

    logger.info("=== ORCHESTRATOR LAMBDA COMPLETED ===")
    return {'batchItemFailures': batch_item_failures}
