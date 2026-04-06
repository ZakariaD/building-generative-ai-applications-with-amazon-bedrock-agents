from aws_cdk import (
    Stack, Duration, RemovalPolicy, CfnOutput,
    aws_iam as iam,
    aws_lambda as _lambda,
    aws_logs as logs,
    aws_bedrockagentcore as bedrockagentcore,
    aws_s3 as s3,
    aws_s3_notifications as s3_notifications,
    aws_dynamodb as dynamodb,
    aws_ecr_assets as ecr_assets,
    aws_ses as ses,
    aws_sqs as sqs,
    aws_sns as sns,
    aws_cloudwatch as cloudwatch,
    aws_cloudwatch_actions as cw_actions,
    aws_lambda_event_sources as lambda_events,
    CfnResource
)
from constructs import Construct
import json


class EmailProcessingStack(Stack):
    FOUNDATION_MODEL = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"

    RECIPIENT_EMAILS = ["supplier-invoices@ingestion.company.com"]
    EMAIL_ROUTING = {
        "supplier-invoices@ingestion.company.com": "ap@company.com"
    }
    ALARM_EMAIL = "ap-alerts@company.com"

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ── S3 Bucket for email files ──
        email_bucket = s3.Bucket(
            self, "EmailBucket",
            bucket_name=f"{self.stack_name.lower()}-s3b-{self.account}",
            encryption=s3.BucketEncryption.S3_MANAGED,
            versioned=True,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True
        )
        email_bucket.add_to_resource_policy(iam.PolicyStatement(
            sid="AllowSESPuts", effect=iam.Effect.ALLOW,
            principals=[iam.ServicePrincipal("ses.amazonaws.com")],
            actions=["s3:PutObject"],
            resources=[f"{email_bucket.bucket_arn}/*"],
            conditions={"StringEquals": {"AWS:SourceAccount": self.account}}
        ))

        # ── SQS Queues (DLQ + Processing) ──
        dlq = sqs.Queue(self, "EmailProcessingDLQ",
            queue_name=f"{self.stack_name}-dlq",
            retention_period=Duration.days(14),
            encryption=sqs.QueueEncryption.SQS_MANAGED)

        processing_queue = sqs.Queue(self, "EmailProcessingQueue",
            queue_name=f"{self.stack_name}-queue",
            visibility_timeout=Duration.seconds(900),
            retention_period=Duration.days(14),
            encryption=sqs.QueueEncryption.SQS_MANAGED,
            dead_letter_queue=sqs.DeadLetterQueue(max_receive_count=3, queue=dlq))

        # ── SNS DLQ Alarm ──
        dlq_topic = sns.Topic(self, "DLQAlarmTopic", topic_name=f"{self.stack_name}-dlq-alerts")
        dlq_topic.add_to_resource_policy(iam.PolicyStatement(
            principals=[iam.ServicePrincipal("cloudwatch.amazonaws.com")],
            actions=["sns:Publish"],
            resources=[dlq_topic.topic_arn]
        ))
        sns.Subscription(self, "DLQAlarmEmail", topic=dlq_topic,
                         protocol=sns.SubscriptionProtocol.EMAIL, endpoint=self.ALARM_EMAIL)

        dlq_alarm = cloudwatch.Alarm(self, "DLQAlarm",
            alarm_name=f"{self.stack_name}-dlq-messages",
            metric=dlq.metric_approximate_number_of_messages_visible(),
            threshold=1, evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING)
        dlq_alarm.add_alarm_action(cw_actions.SnsAction(dlq_topic))

        # ── DynamoDB Supplier Directory ──
        supplier_table = dynamodb.Table(
            self, "SupplierTable",
            table_name=f"{self.stack_name}-supplier-directory",
            partition_key=dynamodb.Attribute(name="email_domain", type=dynamodb.AttributeType.STRING),
            removal_policy=RemovalPolicy.DESTROY
        )

        # ── Lambda Execution Role ──
        lambda_role = iam.Role(
            self, "LambdaExecutionRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole")
            ]
        )
        email_bucket.grant_read_write(lambda_role)
        supplier_table.grant_read_data(lambda_role)
        lambda_role.add_to_policy(iam.PolicyStatement(
            actions=["ses:SendEmail", "ses:SendRawEmail"],
            resources=["*"]
        ))
        lambda_role.add_to_policy(iam.PolicyStatement(
            actions=["bedrock:InvokeModel"],
            resources=[
                "arn:aws:bedrock:*::foundation-model/*",
                f"arn:aws:bedrock:*:{self.account}:inference-profile/*"
            ]
        ))

        # ── CloudWatch Log Groups ──
        extraction_log_group = logs.LogGroup(
            self, "ExtractionLogGroup",
            log_group_name=f"/aws/lambda/{self.stack_name}-extraction",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY
        )
        customer_log_group = logs.LogGroup(
            self, "CustomerLogGroup",
            log_group_name=f"/aws/lambda/{self.stack_name}-customer",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY
        )
        classification_log_group = logs.LogGroup(
            self, "ClassificationLogGroup",
            log_group_name=f"/aws/lambda/{self.stack_name}-classification",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY
        )
        routing_log_group = logs.LogGroup(
            self, "RoutingLogGroup",
            log_group_name=f"/aws/lambda/{self.stack_name}-routing",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY
        )

        # ── Lambda Functions (Agent Specialists) ──
        extraction_lambda = _lambda.Function(
            self, "ExtractionLambda",
            function_name=f"{self.stack_name}-extraction",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="index.lambda_handler",
            code=_lambda.Code.from_asset("./lambda_functions/invoice_extraction"),
            timeout=Duration.minutes(15),
            memory_size=1024,
            role=lambda_role,
            environment={
                "EMAIL_BUCKET": email_bucket.bucket_name,
                "FOUNDATION_MODEL": self.FOUNDATION_MODEL
            },
            log_group=extraction_log_group
        )

        customer_lambda = _lambda.Function(
            self, "CustomerLambda",
            function_name=f"{self.stack_name}-customer",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="index.lambda_handler",
            code=_lambda.Code.from_asset("./lambda_functions/supplier_resolution"),
            timeout=Duration.minutes(15),
            memory_size=512,
            role=lambda_role,
            environment={"SUPPLIER_TABLE": supplier_table.table_name},
            log_group=customer_log_group
        )

        classification_lambda = _lambda.Function(
            self, "ClassificationLambda",
            function_name=f"{self.stack_name}-classification",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="index.lambda_handler",
            code=_lambda.Code.from_asset("./lambda_functions/intent_classification"),
            timeout=Duration.minutes(15),
            memory_size=256,
            role=lambda_role,
            log_group=classification_log_group
        )

        routing_lambda = _lambda.Function(
            self, "RoutingLambda",
            function_name=f"{self.stack_name}-routing",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="index.lambda_handler",
            code=_lambda.Code.from_asset("./lambda_functions/ap_routing"),
            timeout=Duration.minutes(15),
            memory_size=512,
            role=lambda_role,
            environment={"EMAIL_ROUTING": json.dumps(self.EMAIL_ROUTING)},
            log_group=routing_log_group
        )

        # Grant Bedrock AgentCore permission to invoke Lambda functions
        for lambda_fn in [extraction_lambda, customer_lambda, classification_lambda, routing_lambda]:
            lambda_fn.add_permission(
                "BedrockAgentCoreInvoke",
                principal=iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
                action="lambda:InvokeFunction",
                source_account=self.account
            )

        # ── AgentCore Gateway Role ──
        gateway_role = iam.Role(
            self, "GatewayRole",
            role_name=f"{self.stack_name}-gateway-role",
            assumed_by=iam.ServicePrincipal(
                "bedrock-agentcore.amazonaws.com",
                conditions={
                    "StringEquals": {"aws:SourceAccount": self.account},
                    "ArnLike": {"aws:SourceArn": f"arn:aws:bedrock-agentcore:{self.region}:{self.account}:gateway/{self.stack_name}-*"}
                }
            ),
            inline_policies={
                "GatewayPolicy": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            actions=["lambda:InvokeFunction"],
                            resources=[
                                extraction_lambda.function_arn,
                                customer_lambda.function_arn,
                                classification_lambda.function_arn,
                                routing_lambda.function_arn
                            ]
                        )
                    ]
                )
            }
        )

        # ── MCP Gateways ──
        extraction_gateway = bedrockagentcore.CfnGateway(
            self, "ExtractionGateway",
            authorizer_type="AWS_IAM",
            name=f"{self.stack_name}-extraction-gateway",
            protocol_type="MCP",
            role_arn=gateway_role.role_arn
        )

        customer_gateway = bedrockagentcore.CfnGateway(
            self, "CustomerGateway",
            authorizer_type="AWS_IAM",
            name=f"{self.stack_name}-customer-gateway",
            protocol_type="MCP",
            role_arn=gateway_role.role_arn
        )

        classification_gateway = bedrockagentcore.CfnGateway(
            self, "ClassificationGateway",
            authorizer_type="AWS_IAM",
            name=f"{self.stack_name}-classification-gateway",
            protocol_type="MCP",
            role_arn=gateway_role.role_arn
        )

        routing_gateway = bedrockagentcore.CfnGateway(
            self, "RoutingGateway",
            authorizer_type="AWS_IAM",
            name=f"{self.stack_name}-routing-gateway",
            protocol_type="MCP",
            role_arn=gateway_role.role_arn
        )

        # ── Gateway Targets ──
        extraction_target = bedrockagentcore.CfnGatewayTarget(
            self, "ExtractionTarget",
            gateway_identifier=extraction_gateway.attr_gateway_identifier,
            name=f"{self.stack_name}-extraction-target",
            credential_provider_configurations=[
                bedrockagentcore.CfnGatewayTarget.CredentialProviderConfigurationProperty(
                    credential_provider_type="GATEWAY_IAM_ROLE"
                )
            ],
            target_configuration=bedrockagentcore.CfnGatewayTarget.TargetConfigurationProperty(
                mcp=bedrockagentcore.CfnGatewayTarget.McpTargetConfigurationProperty(
                    lambda_=bedrockagentcore.CfnGatewayTarget.McpLambdaTargetConfigurationProperty(
                        lambda_arn=extraction_lambda.function_arn,
                        tool_schema=bedrockagentcore.CfnGatewayTarget.ToolSchemaProperty(
                            inline_payload=[
                                bedrockagentcore.CfnGatewayTarget.ToolDefinitionProperty(
                                    name="extract",
                                    description="Extract invoice data from email — invoice numbers, PO numbers, supplier info and amounts from S3 email",
                                    input_schema=bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                        type="object",
                                        properties={
                                            "s3_bucket": bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="S3 bucket name"
                                            ),
                                            "s3_object_key": bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="S3 object key"
                                            )
                                        },
                                        required=["s3_bucket", "s3_object_key"]
                                    )
                                )
                            ]
                        )
                    )
                )
            )
        )

        customer_target = bedrockagentcore.CfnGatewayTarget(
            self, "CustomerTarget",
            gateway_identifier=customer_gateway.attr_gateway_identifier,
            name=f"{self.stack_name}-customer-target",
            credential_provider_configurations=[
                bedrockagentcore.CfnGatewayTarget.CredentialProviderConfigurationProperty(
                    credential_provider_type="GATEWAY_IAM_ROLE"
                )
            ],
            target_configuration=bedrockagentcore.CfnGatewayTarget.TargetConfigurationProperty(
                mcp=bedrockagentcore.CfnGatewayTarget.McpTargetConfigurationProperty(
                    lambda_=bedrockagentcore.CfnGatewayTarget.McpLambdaTargetConfigurationProperty(
                        lambda_arn=customer_lambda.function_arn,
                        tool_schema=bedrockagentcore.CfnGatewayTarget.ToolSchemaProperty(
                            inline_payload=[
                                bedrockagentcore.CfnGatewayTarget.ToolDefinitionProperty(
                                    name="resolve",
                                    description="Query DynamoDB SupplierDirectory to resolve supplier ID and type",
                                    input_schema=bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                        type="object",
                                        properties={
                                            "email_domain": bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="Sender email domain"
                                            ),
                                            "supplier_name": bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="Supplier name from invoice"
                                            )
                                        },
                                        required=["email_domain"]
                                    )
                                )
                            ]
                        )
                    )
                )
            )
        )

        classification_target = bedrockagentcore.CfnGatewayTarget(
            self, "ClassificationTarget",
            gateway_identifier=classification_gateway.attr_gateway_identifier,
            name=f"{self.stack_name}-classification-target",
            credential_provider_configurations=[
                bedrockagentcore.CfnGatewayTarget.CredentialProviderConfigurationProperty(
                    credential_provider_type="GATEWAY_IAM_ROLE"
                )
            ],
            target_configuration=bedrockagentcore.CfnGatewayTarget.TargetConfigurationProperty(
                mcp=bedrockagentcore.CfnGatewayTarget.McpTargetConfigurationProperty(
                    lambda_=bedrockagentcore.CfnGatewayTarget.McpLambdaTargetConfigurationProperty(
                        lambda_arn=classification_lambda.function_arn,
                        tool_schema=bedrockagentcore.CfnGatewayTarget.ToolSchemaProperty(
                            inline_payload=[
                                bedrockagentcore.CfnGatewayTarget.ToolDefinitionProperty(
                                    name="classify",
                                    description="Analyze email and classify intent as INV, CRN, PAY, DIS, DUP or OTH",
                                    input_schema=bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                        type="object",
                                        properties={
                                            "subject": bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="Email subject"
                                            ),
                                            "body": bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="Email body text"
                                            ),
                                            "structured_data": bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="JSON string of extracted invoice data (amounts, dates)"
                                            )
                                        },
                                        required=["subject", "body"]
                                    )
                                )
                            ]
                        )
                    )
                )
            )
        )

        routing_target = bedrockagentcore.CfnGatewayTarget(
            self, "RoutingTarget",
            gateway_identifier=routing_gateway.attr_gateway_identifier,
            name=f"{self.stack_name}-routing-target",
            credential_provider_configurations=[
                bedrockagentcore.CfnGatewayTarget.CredentialProviderConfigurationProperty(
                    credential_provider_type="GATEWAY_IAM_ROLE"
                )
            ],
            target_configuration=bedrockagentcore.CfnGatewayTarget.TargetConfigurationProperty(
                mcp=bedrockagentcore.CfnGatewayTarget.McpTargetConfigurationProperty(
                    lambda_=bedrockagentcore.CfnGatewayTarget.McpLambdaTargetConfigurationProperty(
                        lambda_arn=routing_lambda.function_arn,
                        tool_schema=bedrockagentcore.CfnGatewayTarget.ToolSchemaProperty(
                            inline_payload=[
                                bedrockagentcore.CfnGatewayTarget.ToolDefinitionProperty(
                                    name="route",
                                    description="Format subject line and send invoice email to AP inbox via SES",
                                    input_schema=bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                        type="object",
                                        properties={
                                            "original_subject": bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="Original email subject"
                                            ),
                                            "original_body": bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="Original email body"
                                            ),
                                            "supplier_id": bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="Resolved supplier ID"
                                            ),
                                            "intent_code": bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="Intent classification code"
                                            ),
                                            "invoice_numbers": bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="JSON array of invoice numbers"
                                            ),
                                            "recipient_email": bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="Original recipient email for routing lookup"
                                            )
                                        },
                                        required=["original_subject", "original_body", "supplier_id", "intent_code", "recipient_email"]
                                    )
                                )
                            ]
                        )
                    )
                )
            )
        )

        # Add dependencies for Gateway Targets
        extraction_target.node.add_dependency(extraction_gateway)
        extraction_target.node.add_dependency(extraction_lambda)
        customer_target.node.add_dependency(customer_gateway)
        customer_target.node.add_dependency(customer_lambda)
        classification_target.node.add_dependency(classification_gateway)
        classification_target.node.add_dependency(classification_lambda)
        routing_target.node.add_dependency(routing_gateway)
        routing_target.node.add_dependency(routing_lambda)

        # ── Strands Orchestrator — AgentCore Runtime ──
        strands_image = ecr_assets.DockerImageAsset(
            self, "StrandsImage",
            directory="./strands",
            platform=ecr_assets.Platform.LINUX_ARM64
        )

        runtime_role = iam.Role(
            self, "RuntimeRole",
            assumed_by=iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
            inline_policies={
                "RuntimePolicy": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
                            resources=[
                                "arn:aws:bedrock:*::foundation-model/*",
                                f"arn:aws:bedrock:*:{self.account}:inference-profile/*"
                            ]
                        ),
                        iam.PolicyStatement(
                            actions=["bedrock-agentcore:InvokeGateway"],
                            resources=["*"]
                        ),
                        iam.PolicyStatement(
                            actions=["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
                            resources=[
                                f"arn:aws:logs:{self.region}:{self.account}:log-group:/aws/bedrock-agentcore/{self.stack_name}-runtime:*"
                            ]
                        )
                    ]
                )
            }
        )
        strands_image.repository.grant_pull(runtime_role)

        runtime_log_group = logs.LogGroup(
            self, "RuntimeLogGroup",
            log_group_name=f"/aws/bedrock-agentcore/{self.stack_name}-runtime",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY
        )

        runtime = bedrockagentcore.CfnRuntime(
            self, "StrandsRuntime",
            agent_runtime_name=f"{self.stack_name.replace('-', '_')}_strands",
            agent_runtime_artifact=bedrockagentcore.CfnRuntime.AgentRuntimeArtifactProperty(
                container_configuration=bedrockagentcore.CfnRuntime.ContainerConfigurationProperty(
                    container_uri=strands_image.image_uri
                )
            ),
            network_configuration=bedrockagentcore.CfnRuntime.NetworkConfigurationProperty(
                network_mode="PUBLIC"
            ),
            protocol_configuration="HTTP",
            role_arn=runtime_role.role_arn,
            environment_variables={
                "EXTRACTION_GATEWAY_URL": extraction_gateway.attr_gateway_url,
                "CUSTOMER_GATEWAY_URL": customer_gateway.attr_gateway_url,
                "CLASSIFICATION_GATEWAY_URL": classification_gateway.attr_gateway_url,
                "ROUTING_GATEWAY_URL": routing_gateway.attr_gateway_url,
                "BEDROCK_MODEL": self.FOUNDATION_MODEL,
                "AWS_REGION": self.region
            }
        )

        endpoint = bedrockagentcore.CfnRuntimeEndpoint(
            self, "StrandsEndpoint",
            name=f"{self.stack_name.replace('-', '_')}_endpoint",
            agent_runtime_id=runtime.ref
        )

        # ── Orchestrator Lambda (SQS trigger → AgentCore Runtime) ──
        orchestrator_log_group = logs.LogGroup(
            self, "OrchestratorLogGroup",
            log_group_name=f"/aws/lambda/{self.stack_name}-orchestrator",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY
        )

        orchestrator_lambda = _lambda.Function(
            self, "OrchestratorLambda",
            function_name=f"{self.stack_name}-orchestrator",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="index.lambda_handler",
            code=_lambda.Code.from_asset("./lambda_functions/orchestrator"),
            timeout=Duration.minutes(15),
            memory_size=512,
            reserved_concurrent_executions=1,
            environment={"RUNTIME_ENDPOINT_ARN": endpoint.attr_agent_runtime_endpoint_arn},
            log_group=orchestrator_log_group
        )

        orchestrator_lambda.add_to_role_policy(iam.PolicyStatement(
            actions=["bedrock-agentcore:InvokeRuntimeEndpoint", "bedrock-agentcore:InvokeAgentRuntime"],
            resources=[
                runtime.attr_agent_runtime_arn,
                f"{runtime.attr_agent_runtime_arn}/*",
                endpoint.attr_agent_runtime_endpoint_arn,
            ]
        ))

        # SQS trigger for orchestrator (from S3 → SQS → Lambda)
        orchestrator_lambda.add_event_source(lambda_events.SqsEventSource(
            processing_queue, batch_size=1,
            max_batching_window=Duration.seconds(0),
            report_batch_item_failures=True))

        # S3 → SQS notification (incoming/ prefix for SES emails)
        email_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3_notifications.SqsDestination(processing_queue),
            s3.NotificationKeyFilter(prefix="incoming/"))

        # ── SES Receipt Rule ──
        receipt_rule_set = ses.CfnReceiptRuleSet(self, "EmailReceiptRuleSet",
            rule_set_name=f"{self.stack_name}-receipt-rules")
        receipt_rule = ses.CfnReceiptRule(self, "EmailReceiptRule",
            rule_set_name=receipt_rule_set.rule_set_name,
            rule=ses.CfnReceiptRule.RuleProperty(
                name="save-to-s3-rule", enabled=True, scan_enabled=True, tls_policy="Require",
                recipients=self.RECIPIENT_EMAILS,
                actions=[ses.CfnReceiptRule.ActionProperty(
                    s3_action=ses.CfnReceiptRule.S3ActionProperty(
                        bucket_name=email_bucket.bucket_name,
                        object_key_prefix="incoming/", topic_arn=None))]))
        receipt_rule.add_dependency(receipt_rule_set)
        receipt_rule.node.add_dependency(email_bucket)

        # ── Outputs ──
        CfnOutput(self, "EmailBucketName", value=email_bucket.bucket_name)
        CfnOutput(self, "SupplierTableName", value=supplier_table.table_name)
        CfnOutput(self, "ProcessingQueueUrl", value=processing_queue.queue_url)
        CfnOutput(self, "DLQUrl", value=dlq.queue_url)
        CfnOutput(self, "StrandsRuntimeArn", value=runtime.attr_agent_runtime_arn)
        CfnOutput(self, "StrandsEndpointArn", value=endpoint.attr_agent_runtime_endpoint_arn)
        CfnOutput(self, "StrandsImageUri", value=strands_image.image_uri)
        CfnOutput(self, "ExtractionGatewayUrl", value=extraction_gateway.attr_gateway_url)
        CfnOutput(self, "CustomerGatewayUrl", value=customer_gateway.attr_gateway_url)
        CfnOutput(self, "ClassificationGatewayUrl", value=classification_gateway.attr_gateway_url)
        CfnOutput(self, "RoutingGatewayUrl", value=routing_gateway.attr_gateway_url)

        # ── X-Ray Transaction Search Configuration ──
        policy_doc = {
            "Version": "2012-10-17",
            "Statement": [{
                "Sid": "TransactionSearchXRayAccess",
                "Effect": "Allow",
                "Principal": {"Service": "xray.amazonaws.com"},
                "Action": "logs:PutLogEvents",
                "Resource": [
                    f"arn:aws:logs:{self.region}:{self.account}:log-group:aws/spans:*",
                    f"arn:aws:logs:{self.region}:{self.account}:log-group:/aws/application-signals/data:*"
                ],
                "Condition": {
                    "ArnLike": {"aws:SourceArn": f"arn:aws:xray:{self.region}:{self.account}:*"},
                    "StringEquals": {"aws:SourceAccount": self.account}
                }
            }]
        }

        logs_resource_policy = CfnResource(
            self, "LogsResourcePolicy",
            type="AWS::Logs::ResourcePolicy",
            properties={
                "PolicyName": "TransactionSearchAccessPolicy",
                "PolicyDocument": json.dumps(policy_doc)
            }
        )

        xray_config = CfnResource(
            self, "XRayTransactionSearchConfig",
            type="AWS::XRay::TransactionSearchConfig",
            properties={"IndexingPercentage": 1}
        )
        xray_config.node.add_dependency(logs_resource_policy)
