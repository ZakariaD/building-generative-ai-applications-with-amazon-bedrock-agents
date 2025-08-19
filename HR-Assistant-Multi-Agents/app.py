#!/usr/bin/env python3
import os
import aws_cdk as cdk
from hr_bedrock_stack import HRBedrockStack

app = cdk.App()
env = cdk.Environment(
    account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
    region=os.environ.get("CDK_DEFAULT_REGION", "us-east-1")
)

HRBedrockStack(app, "HRBedrockStack", stack_name="hr-multi-agent-poc", env=env)

app.synth()
