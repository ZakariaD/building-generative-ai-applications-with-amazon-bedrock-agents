#!/usr/bin/env python3
import os
import aws_cdk as cdk
from email_processing_stack import EmailProcessingStack

app = cdk.App()
env = cdk.Environment(
    account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
    region=os.environ.get("CDK_DEFAULT_REGION", "us-east-1")
)

EmailProcessingStack(app, "EmailProcessingStack", stack_name="ap-agentcore", env=env)

app.synth()
