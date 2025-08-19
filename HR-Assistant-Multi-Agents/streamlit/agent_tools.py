import io
import os
import random
from botocore.config import Config

import boto3
import streamlit as st

AGENT_ID = os.environ.get("ORCHESTRATOR_AGENT_ID")
REGION = os.environ.get("AWS_REGION", "us-east-1")

# Use default credentials (IAM role in ECS)

config = Config(
    read_timeout=300,
    connect_timeout=60,
    retries={'max_attempts': 3}
)

bedrock_agent_runtime = boto3.client("bedrock-agent-runtime", region_name=REGION, config=config)


def generate_random_15digit():
    number = ""

    for _ in range(15):
        number += str(random.randint(0, 9))

    return number


def invoke_bedrock_agent(inputText, sessionId, endSession=False):
    response = bedrock_agent_runtime.invoke_agent(
        agentAliasId="TSTALIASID",
        agentId=AGENT_ID,
        sessionId=sessionId,
        inputText=inputText,
        endSession=endSession,
        enableTrace=False,
    )

    event_stream = response["completion"]
    model_response = {"text": "", "images": [], "traces": []}

    for event in event_stream:
        if "chunk" in event:
            chunk = event["chunk"]
            if "bytes" in chunk:
                text = chunk["bytes"].decode("utf-8")
                model_response["text"] += text
    
    return model_response
