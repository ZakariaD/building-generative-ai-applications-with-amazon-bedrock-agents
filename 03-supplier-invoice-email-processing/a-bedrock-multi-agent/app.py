#!/usr/bin/env python3
import os
import aws_cdk as cdk
from email_processing_stack import EmailProcessingStack

app = cdk.App()
env = cdk.Environment(
    account="195565468328", #os.environ.get("CDK_DEFAULT_ACCOUNT"),
    region="us-east-1" #os.environ.get("CDK_DEFAULT_REGION", "us-east-1")
)
EmailProcessingStack(app, "EmailProcessingStack", stack_name="blog-multi-agents", env=env)

app.synth()
