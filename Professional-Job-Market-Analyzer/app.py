#!/usr/bin/env python3
import os
import aws_cdk as cdk
from bedrock_mcp_stack import BedrockMCPStack

app = cdk.App()
env = cdk.Environment(
    account= os.environ.get("CDK_DEFAULT_ACCOUNT"),
    region=os.environ.get("CDK_DEFAULT_REGION", "us-east-1")
)

BedrockMCPStack(app, "BedrockMCPStack", stack_name="multi-agent-mcp-jobs", env=env)

app.synth()
