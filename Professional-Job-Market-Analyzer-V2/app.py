#!/usr/bin/env python3
import os
import aws_cdk as cdk
from bedrock_mcp_stack import BedrockMCPStack

app = cdk.App()
env = cdk.Environment(
    account= os.environ.get("CDK_DEFAULT_ACCOUNT"),
    region=os.environ.get("CDK_DEFAULT_REGION", "us-east-1")
)

# Note: Keep stack_name short (max 15 chars) to avoid 32-char limit on load balancer names
BedrockMCPStack(app, "BedrockMCPStack", stack_name="job-market", env=env)


app.synth()
