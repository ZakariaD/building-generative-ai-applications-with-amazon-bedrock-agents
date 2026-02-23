import boto3
import json
import os
import logging
from datetime import datetime
from urllib.parse import unquote_plus

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    logger.info("=== ORCHESTRATOR LAMBDA STARTED ===")
    logger.info(f"Event: {json.dumps(event, default=str)}")

    batch_item_failures = []

    for record in event['Records']:
        message_id = record['messageId']
        try:
            s3_event = json.loads(record['body'])
            s3_record = s3_event['Records'][0]['s3']
            s3_bucket = s3_record['bucket']['name']
            s3_object_key = unquote_plus(s3_record['object']['key'])
            upload_timestamp = datetime.utcnow().isoformat() + 'Z'

            logger.info(f"Processing SQS Message ID: {message_id}")
            logger.info(f"S3 Trigger Details:")
            logger.info(f"  - Bucket: {s3_bucket}")
            logger.info(f"  - Key: {s3_object_key}")
            logger.info(f"  - Timestamp: {upload_timestamp}")

            supervisor_prompt = f"""Process the supplier invoice email uploaded to S3 and route to the AP inbox.

Email Details:
- S3 Bucket: {s3_bucket}
- S3 Object Key: {s3_object_key}
- Upload Timestamp: {upload_timestamp}

Workflow Steps:
1. Extract invoice data and supplier info using Extraction-Specialist
2. Resolve supplier identity using Supplier-Specialist
3. Classify invoice intent using Classification-Specialist
4. Format subject and route to AP inbox using Routing-Specialist

Provide a summary including supplier ID, invoice number(s), intent code, and number of emails routed."""

            supervisor_agent_id = os.environ['SUPERVISOR_AGENT_ID']
            supervisor_agent_alias_id = os.environ['SUPERVISOR_AGENT_ALIAS_ID']
            session_id = f"session-{s3_object_key.replace('/', '-')}"

            logger.info(f"Bedrock Agent Configuration:")
            logger.info(f"  - Agent ID: {supervisor_agent_id}")
            logger.info(f"  - Alias ID: {supervisor_agent_alias_id}")
            logger.info(f"  - Session ID: {session_id}")
            logger.info(f"Invoking Supervisor Agent...")

            config = boto3.session.Config(read_timeout=600, connect_timeout=60, retries={'max_attempts': 3})
            bedrock_agent = boto3.client('bedrock-agent-runtime', config=config)

            response = bedrock_agent.invoke_agent(
                agentId=supervisor_agent_id,
                agentAliasId=supervisor_agent_alias_id,
                sessionId=session_id,
                inputText=supervisor_prompt,
                enableTrace=True
            )

            logger.info("Supervisor Agent invoked successfully")
            logger.info("Processing response stream...")

            completion = ""
            chunk_count = 0
            for evt in response.get('completion', []):
                if 'chunk' in evt and 'bytes' in evt['chunk']:
                    chunk_count += 1
                    completion += evt['chunk']['bytes'].decode('utf-8')

            logger.info(f"Received {chunk_count} chunks from Supervisor")
            logger.info(f"Supervisor response: {completion}")
            logger.info(f"")
            logger.info(f"=== INVOICE PROCESSING SUMMARY ===")
            logger.info(f"📧 Email Source:")
            logger.info(f"  - S3 Bucket: {s3_bucket}")
            logger.info(f"  - S3 Object Key: {s3_object_key}")
            logger.info(f"  - Upload Timestamp: {upload_timestamp}")
            logger.info(f"✅ Successfully processed message: {message_id}")
            logger.info(f"=== END INVOICE PROCESSING SUMMARY ===")

        except Exception as e:
            logger.error(f"Failed to process message {message_id}")
            logger.error(f"Error: {str(e)}")
            logger.error(f"Error type: {type(e).__name__}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            batch_item_failures.append({"itemIdentifier": message_id})

    logger.info("=== ORCHESTRATOR LAMBDA COMPLETED ===")
    return {'batchItemFailures': batch_item_failures}
