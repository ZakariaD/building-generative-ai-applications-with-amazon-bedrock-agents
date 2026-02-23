from aws_cdk import (
    Stack, Duration, RemovalPolicy,
    aws_bedrock as bedrock,
    aws_s3 as s3,
    aws_iam as iam,
    aws_lambda as _lambda,
    aws_logs as logs,
    aws_s3_notifications as s3n,
    aws_dynamodb as dynamodb,
    aws_ses as ses,
    aws_sqs as sqs,
    aws_lambda_event_sources as lambda_events,
    aws_cloudwatch as cloudwatch,
    aws_cloudwatch_actions as cw_actions,
    aws_sns as sns,
    CfnOutput
)
import json
from constructs import Construct

class EmailProcessingStack(Stack):
    FOUNDATION_MODEL = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"

    RECIPIENT_EMAILS = ["supplier-invoices@ingestion.company.com"]
    EMAIL_ROUTING = {
        "supplier-invoices@ingestion.company.com": "ap@company.com"
    }
    ALARM_EMAIL = "ap-alerts@company.com"

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

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

        dlq_topic = sns.Topic(self, "DLQAlarmTopic", topic_name=f"{self.stack_name}-dlq-alerts")

        # Allow CloudWatch to publish to SNS topic
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

        # SupplierDirectory table — partition key: email_domain
        supplier_table = dynamodb.Table(self, "SupplierTable",
            table_name=f"{self.stack_name}-supplier-directory",
            partition_key=dynamodb.Attribute(name="email_domain", type=dynamodb.AttributeType.STRING),
            removal_policy=RemovalPolicy.DESTROY)

        bedrock_role = iam.Role(self, "BedrockAgentRole",
            assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com"),
            managed_policies=[iam.ManagedPolicy.from_aws_managed_policy_name("AmazonBedrockFullAccess")])
        bedrock_role.apply_removal_policy(RemovalPolicy.DESTROY)
        email_bucket.grant_read_write(bedrock_role)
        supplier_table.grant_read_data(bedrock_role)

        bedrock_log_group = logs.LogGroup(self, "BedrockAgentLogGroup",
            log_group_name=f"/aws/bedrock/agents/{self.stack_name}",
            retention=logs.RetentionDays.ONE_DAY,
            removal_policy=RemovalPolicy.DESTROY)
        bedrock_role.add_to_policy(iam.PolicyStatement(
            actions=["logs:CreateLogStream", "logs:PutLogEvents"],
            resources=[bedrock_log_group.log_group_arn]))

        lambda_role = iam.Role(self, "LambdaExecutionRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole")])
        lambda_role.apply_removal_policy(RemovalPolicy.DESTROY)
        email_bucket.grant_read_write(lambda_role)
        supplier_table.grant_read_data(lambda_role)
        lambda_role.add_to_policy(iam.PolicyStatement(actions=["ses:SendEmail", "ses:SendRawEmail"], resources=["*"]))
        lambda_role.add_to_policy(iam.PolicyStatement(actions=["bedrock:InvokeModel", "bedrock:InvokeAgent"], resources=["*"]))
        lambda_role.add_to_policy(iam.PolicyStatement(
            actions=["sqs:SendMessage", "sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"],
            resources=[processing_queue.queue_arn, dlq.queue_arn]))

        orchestrator_lambda = _lambda.Function(self, "OrchestratorLambda",
            function_name=f"{self.stack_name}-orchestrator",
            runtime=_lambda.Runtime.PYTHON_3_13,
            handler="index.lambda_handler",
            code=_lambda.Code.from_asset("lambda_functions/orchestrator"),
            role=lambda_role, timeout=Duration.seconds(900), memory_size=512,
            reserved_concurrent_executions=1,
            environment={"EMAIL_BUCKET": email_bucket.bucket_name},
            log_retention=logs.RetentionDays.ONE_DAY)

        orchestrator_lambda.add_event_source(lambda_events.SqsEventSource(
            processing_queue, batch_size=1,
            max_batching_window=Duration.seconds(0),
            report_batch_item_failures=True))

        extraction_lambda = _lambda.Function(self, "ExtractionLambda",
            function_name=f"{self.stack_name}-extraction",
            runtime=_lambda.Runtime.PYTHON_3_13,
            handler="index.lambda_handler",
            code=_lambda.Code.from_asset("lambda_functions/invoice_extraction"),
            role=lambda_role, timeout=Duration.seconds(900), memory_size=1024,
            environment={"EMAIL_BUCKET": email_bucket.bucket_name, "FOUNDATION_MODEL": self.FOUNDATION_MODEL},
            log_retention=logs.RetentionDays.ONE_DAY)

        # agent_customer folder — handles supplier resolution
        customer_lambda = _lambda.Function(self, "CustomerLambda",
            function_name=f"{self.stack_name}-customer",
            runtime=_lambda.Runtime.PYTHON_3_13,
            handler="index.lambda_handler",
            code=_lambda.Code.from_asset("lambda_functions/supplier_resolution"),
            role=lambda_role, timeout=Duration.seconds(900), memory_size=512,
            environment={"SUPPLIER_TABLE": supplier_table.table_name},
            log_retention=logs.RetentionDays.ONE_DAY)

        classification_lambda = _lambda.Function(self, "ClassificationLambda",
            function_name=f"{self.stack_name}-classification",
            runtime=_lambda.Runtime.PYTHON_3_13,
            handler="index.lambda_handler",
            code=_lambda.Code.from_asset("lambda_functions/intent_classification"),
            role=lambda_role, timeout=Duration.seconds(900), memory_size=512,
            environment={"FOUNDATION_MODEL": self.FOUNDATION_MODEL},
            log_retention=logs.RetentionDays.ONE_DAY)

        routing_lambda = _lambda.Function(self, "RoutingLambda",
            function_name=f"{self.stack_name}-routing",
            runtime=_lambda.Runtime.PYTHON_3_13,
            handler="index.lambda_handler",
            code=_lambda.Code.from_asset("lambda_functions/ap_routing"),
            role=lambda_role, timeout=Duration.seconds(900), memory_size=512,
            environment={"EMAIL_ROUTING": json.dumps(self.EMAIL_ROUTING)},
            log_retention=logs.RetentionDays.ONE_DAY)

        # SES saves emails without extension under 'incoming/' prefix
        # Also support manual .eml uploads
        email_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.SqsDestination(processing_queue),
            s3.NotificationKeyFilter(prefix="incoming/"))
        # email_bucket.add_event_notification(
        #     s3.EventType.OBJECT_CREATED,
        #     s3n.SqsDestination(processing_queue),
        #     s3.NotificationKeyFilter(suffix=".eml"))

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

        for fn in [extraction_lambda, customer_lambda, classification_lambda, routing_lambda]:
            fn.grant_invoke(bedrock_role)
            fn.add_permission("AllowBedrockInvoke",
                principal=iam.ServicePrincipal("bedrock.amazonaws.com"),
                action="lambda:InvokeFunction", source_account=self.account)

        extraction_agent = bedrock.CfnAgent(self, "ExtractionAgent",
            agent_name=f"{self.stack_name}-extraction-specialist",
            description="Extracts invoice numbers, PO numbers, supplier info, amounts from email and PDF attachments",
            foundation_model=f"arn:aws:bedrock:{self.region}:{self.account}:inference-profile/{self.FOUNDATION_MODEL}",
            instruction=self._load_instruction("invoice_extraction"),
            agent_resource_role_arn=bedrock_role.role_arn,
            action_groups=[bedrock.CfnAgent.AgentActionGroupProperty(
                action_group_name="extraction-actions", action_group_state="ENABLED",
                action_group_executor=bedrock.CfnAgent.ActionGroupExecutorProperty(lambda_=extraction_lambda.function_arn),
                api_schema=bedrock.CfnAgent.APISchemaProperty(payload=self._load_api_schema("invoice_extraction")))])

        customer_agent = bedrock.CfnAgent(self, "CustomerAgent",
            agent_name=f"{self.stack_name}-supplier-specialist",
            description="Resolves supplier ID and type from DynamoDB SupplierDirectory using email domain",
            foundation_model=f"arn:aws:bedrock:{self.region}:{self.account}:inference-profile/{self.FOUNDATION_MODEL}",
            instruction=self._load_instruction("supplier_resolution"),
            agent_resource_role_arn=bedrock_role.role_arn,
            action_groups=[bedrock.CfnAgent.AgentActionGroupProperty(
                action_group_name="customer-actions", action_group_state="ENABLED",
                action_group_executor=bedrock.CfnAgent.ActionGroupExecutorProperty(lambda_=customer_lambda.function_arn),
                api_schema=bedrock.CfnAgent.APISchemaProperty(payload=self._load_api_schema("supplier_resolution")))])

        classification_agent = bedrock.CfnAgent(self, "ClassificationAgent",
            agent_name=f"{self.stack_name}-classification-specialist",
            description="Classifies invoice email intent: INV, CRN, PAY, DIS, DUP, OTH",
            foundation_model=f"arn:aws:bedrock:{self.region}:{self.account}:inference-profile/{self.FOUNDATION_MODEL}",
            instruction=self._load_instruction("intent_classification"),
            agent_resource_role_arn=bedrock_role.role_arn,
            action_groups=[bedrock.CfnAgent.AgentActionGroupProperty(
                action_group_name="classification-actions", action_group_state="ENABLED",
                action_group_executor=bedrock.CfnAgent.ActionGroupExecutorProperty(lambda_=classification_lambda.function_arn),
                api_schema=bedrock.CfnAgent.APISchemaProperty(payload=self._load_api_schema("intent_classification")))])

        routing_agent = bedrock.CfnAgent(self, "RoutingAgent",
            agent_name=f"{self.stack_name}-routing-specialist",
            description="Formats AP subject lines, splits multi-invoice emails, routes to AP system via SES",
            foundation_model=f"arn:aws:bedrock:{self.region}:{self.account}:inference-profile/{self.FOUNDATION_MODEL}",
            instruction=self._load_instruction("ap_routing"),
            agent_resource_role_arn=bedrock_role.role_arn,
            action_groups=[bedrock.CfnAgent.AgentActionGroupProperty(
                action_group_name="routing-actions", action_group_state="ENABLED",
                action_group_executor=bedrock.CfnAgent.ActionGroupExecutorProperty(lambda_=routing_lambda.function_arn),
                api_schema=bedrock.CfnAgent.APISchemaProperty(payload=self._load_api_schema("ap_routing")))])

        extraction_alias = bedrock.CfnAgentAlias(self, "ExtractionAgentAlias",
            agent_id=extraction_agent.attr_agent_id, agent_alias_name=f"{self.stack_name}-extraction-alias")
        customer_alias = bedrock.CfnAgentAlias(self, "CustomerAgentAlias",
            agent_id=customer_agent.attr_agent_id, agent_alias_name=f"{self.stack_name}-customer-alias")
        classification_alias = bedrock.CfnAgentAlias(self, "ClassificationAgentAlias",
            agent_id=classification_agent.attr_agent_id, agent_alias_name=f"{self.stack_name}-classification-alias")
        routing_alias = bedrock.CfnAgentAlias(self, "RoutingAgentAlias",
            agent_id=routing_agent.attr_agent_id, agent_alias_name=f"{self.stack_name}-routing-alias")

        supervisor_agent = bedrock.CfnAgent(self, "SupervisorAgent",
            agent_name=f"{self.stack_name}-ap-supervisor",
            description="Orchestrates AP invoice processing: extraction → supplier resolution → classification → routing",
            foundation_model=f"arn:aws:bedrock:{self.region}:{self.account}:inference-profile/{self.FOUNDATION_MODEL}",
            instruction=self._load_instruction("supervisor_agent"),
            agent_resource_role_arn=bedrock_role.role_arn,
            agent_collaboration="SUPERVISOR",
            action_groups=[bedrock.CfnAgent.AgentActionGroupProperty(
                action_group_name="enable-agent-user-input",
                action_group_state="ENABLED",
                parent_action_group_signature="AMAZON.UserInput")],
            agent_collaborators=[
                bedrock.CfnAgent.AgentCollaboratorProperty(
                    agent_descriptor=bedrock.CfnAgent.AgentDescriptorProperty(alias_arn=extraction_alias.attr_agent_alias_arn),
                    collaboration_instruction="Extract invoice numbers, PO numbers, supplier info, and amounts from email and PDF attachments",
                    collaborator_name="Extraction-Specialist", relay_conversation_history="TO_COLLABORATOR"),
                bedrock.CfnAgent.AgentCollaboratorProperty(
                    agent_descriptor=bedrock.CfnAgent.AgentDescriptorProperty(alias_arn=customer_alias.attr_agent_alias_arn),
                    collaboration_instruction="Resolve supplier ID and type from DynamoDB SupplierDirectory using email domain",
                    collaborator_name="Supplier-Specialist", relay_conversation_history="TO_COLLABORATOR"),
                bedrock.CfnAgent.AgentCollaboratorProperty(
                    agent_descriptor=bedrock.CfnAgent.AgentDescriptorProperty(alias_arn=classification_alias.attr_agent_alias_arn),
                    collaboration_instruction="Classify invoice intent: INV, CRN, PAY, DIS, DUP, or OTH",
                    collaborator_name="Classification-Specialist", relay_conversation_history="TO_COLLABORATOR"),
                bedrock.CfnAgent.AgentCollaboratorProperty(
                    agent_descriptor=bedrock.CfnAgent.AgentDescriptorProperty(alias_arn=routing_alias.attr_agent_alias_arn),
                    collaboration_instruction="Format AP subject lines and route invoices to AP system via SES",
                    collaborator_name="Routing-Specialist", relay_conversation_history="TO_COLLABORATOR")
            ])

        supervisor_alias = bedrock.CfnAgentAlias(self, "SupervisorAgentAlias",
            agent_id=supervisor_agent.attr_agent_id,
            agent_alias_name=f"{self.stack_name}-supervisor-alias")

        orchestrator_lambda.add_environment("SUPERVISOR_AGENT_ID", supervisor_agent.attr_agent_id)
        orchestrator_lambda.add_environment("SUPERVISOR_AGENT_ALIAS_ID", supervisor_alias.attr_agent_alias_id)

        CfnOutput(self, "EmailBucketName", value=email_bucket.bucket_name)
        CfnOutput(self, "SupplierTableName", value=supplier_table.table_name)
        CfnOutput(self, "ProcessingQueueUrl", value=processing_queue.queue_url)
        CfnOutput(self, "DLQUrl", value=dlq.queue_url)
        CfnOutput(self, "SupervisorAgentId", value=supervisor_agent.attr_agent_id)
        CfnOutput(self, "SupervisorAliasId", value=supervisor_alias.attr_agent_alias_id)

    def _load_instruction(self, name):
        with open(f"instructions/{name}.txt", 'r') as f:
            return f.read().strip()

    def _load_api_schema(self, name) -> str:
        with open(f"api-schemas/{name}.yaml", 'r') as f:
            return f.read()
