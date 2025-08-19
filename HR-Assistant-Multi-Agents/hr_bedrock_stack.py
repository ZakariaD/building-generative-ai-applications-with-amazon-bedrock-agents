from aws_cdk import (
    Stack, Duration, RemovalPolicy, CustomResource,
    aws_bedrock as bedrock,
    aws_s3 as s3, aws_s3_deployment as s3deploy,
    aws_iam as iam,
    aws_opensearchserverless as oss,
    aws_lambda as _lambda, aws_logs as logs,
    aws_lambda_event_sources as lambda_event_source,
    aws_dynamodb as dynamodb,
    custom_resources as cr,
    CfnOutput,
    aws_ecs as ecs,
    aws_ec2 as ec2,
    aws_ecr_assets as ecr_assets,
    aws_elasticloadbalancingv2 as elbv2,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as cloudfront_origins
)
import json
from constructs import Construct

class HRBedrockStack(Stack):
    # Constants
    EMBEDDING_MODEL = "amazon.titan-embed-text-v1"
    FOUNDATION_MODEL = "us.anthropic.claude-3-7-sonnet-20250219-v1:0"  # Cross-region inference profile

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Knowledge base configurations
        kb_configs = [
            {"name": "compliance-kb", "index": "compliance-index", "construct_id": "ComplianceKB"},
            {"name": "loa-kb", "index": "loa-index", "construct_id": "LOAKB"},
            {"name": "onboarding-kb", "index": "onboarding-index", "construct_id": "OnboardingKB"},
            {"name": "payroll-kb", "index": "payroll-index", "construct_id": "PayrollKB"},
            {"name": "policy-kb", "index": "policy-index", "construct_id": "PolicyKB"}
        ]
        
        # Extract index names for reuse
        index_names = [config["index"] for config in kb_configs]

        # DynamoDB Tables
        employee_data_table = dynamodb.Table(
            self, "EmployeeData",
            table_name=f"{self.stack_name}-EmployeeData",
            partition_key=dynamodb.Attribute(name="employee_id", type=dynamodb.AttributeType.STRING),
            removal_policy=RemovalPolicy.DESTROY
        )

        leave_requests_table = dynamodb.Table(
            self, "LeaveRequests",
            table_name=f"{self.stack_name}-LeaveRequests",
            partition_key=dynamodb.Attribute(name="request_id", type=dynamodb.AttributeType.STRING),
            removal_policy=RemovalPolicy.DESTROY
        )

        payroll_data_table = dynamodb.Table(
            self, "PayrollData",
            table_name=f"{self.stack_name}-PayrollData",
            partition_key=dynamodb.Attribute(name="employee_id", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="pay_period", type=dynamodb.AttributeType.STRING),
            removal_policy=RemovalPolicy.DESTROY
        )

        onboarding_tasks_table = dynamodb.Table(
            self, "OnboardingTasks",
            table_name=f"{self.stack_name}-OnboardingTasks",
            partition_key=dynamodb.Attribute(name="employee_id", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="task_id", type=dynamodb.AttributeType.STRING),
            removal_policy=RemovalPolicy.DESTROY
        )

        # Load sample data from JSON files
        def load_sample_data(file_path):
            with open(file_path, 'r') as f:
                data = json.load(f)
            return data

        def convert_to_dynamodb_format(items):
            dynamodb_items = []
            for item in items:
                dynamodb_item = {}
                for key, value in item.items():
                    if isinstance(value, str):
                        dynamodb_item[key] = {"S": value}
                    elif isinstance(value, (int, float)):
                        dynamodb_item[key] = {"N": str(value)}
                    elif value is None:
                        dynamodb_item[key] = {"NULL": True}
                dynamodb_items.append({"PutRequest": {"Item": dynamodb_item}})
            return dynamodb_items

        employee_data = load_sample_data("sample_data/employee_data.json")
        leave_requests = load_sample_data("sample_data/leave_requests.json")
        payroll_data = load_sample_data("sample_data/payroll_data.json")
        onboarding_tasks = load_sample_data("sample_data/onboarding_tasks.json")

        # Populate DynamoDB tables with sample data
        populate_tables = cr.AwsCustomResource(
            self, "PopulateDynamoDBTables",
            on_create=cr.AwsSdkCall(
                service="dynamodb",
                action="batchWriteItem",
                parameters={
                    "RequestItems": {
                        employee_data_table.table_name: convert_to_dynamodb_format(employee_data),
                        leave_requests_table.table_name: convert_to_dynamodb_format(leave_requests),
                        payroll_data_table.table_name: convert_to_dynamodb_format(payroll_data),
                        onboarding_tasks_table.table_name: convert_to_dynamodb_format(onboarding_tasks)
                    }
                },
                physical_resource_id=cr.PhysicalResourceId.of("populate-dynamodb-tables")
            ),
            policy=cr.AwsCustomResourcePolicy.from_statements([
                iam.PolicyStatement(
                    actions=["dynamodb:BatchWriteItem"],
                    resources=[employee_data_table.table_arn, leave_requests_table.table_arn, payroll_data_table.table_arn, onboarding_tasks_table.table_arn]
                )
            ])
        )

        # S3 bucket for knowledge bases
        kb_bucket = s3.Bucket(
            self, "HRKnowledgeBaseBucket",
            bucket_name=f"{self.stack_name.lower()}-kb-s3b",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True
        )

        # IAM role for Bedrock agents
        bedrock_role = iam.Role(
            self, "BedrockAgentRole",
            assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonBedrockFullAccess")
            ],
            inline_policies={
                "OpenSearchServerlessAccess": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "aoss:APIAccessAll",
                                "aoss:DashboardsAccessAll"
                            ],
                            resources=["*"]
                        )
                    ]
                )
            }
        )

        kb_bucket.grant_read(bedrock_role)

        # OpenSearch Serverless
        aoss_encryption_policy = oss.CfnSecurityPolicy(
            self, "AossEncryptionPolicy",
            name=f"oss-ep-{self.stack_name}",
            type="encryption",
            policy=f'{{"Rules":[{{"ResourceType":"collection","Resource":["collection/oss-{self.stack_name.lower()[:25]}"]}}],"AWSOwnedKey":true}}'
        )
        
        aoss_network_policy = oss.CfnSecurityPolicy(
            self, "AossNetworkPolicy",
            name=f"oss-np-{self.stack_name}",
            type="network",
            policy=f'[{{"Rules":[{{"ResourceType":"collection","Resource":["collection/oss-{self.stack_name.lower()[:25]}"]}},{{"ResourceType":"dashboard","Resource":["collection/oss-{self.stack_name.lower()[:25]}"]}}],"AllowFromPublic":true}}]'
        )
        

        # OpenSearch Serverless collections (created after encryption policies)
        aoss_collection = oss.CfnCollection(
            self, "AossCollection",
            name=f"oss-{self.stack_name.lower()[:25]}",
            type="VECTORSEARCH"
        )
        aoss_collection.add_dependency(aoss_encryption_policy)
        aoss_collection.add_dependency(aoss_network_policy)


        # Custom Resource Provider for AOSS Index Creation (moved up to get role ARN)
        index_provider = cr.Provider(
            self, "AOSSIndexProvider",
            log_retention=logs.RetentionDays.ONE_DAY,
            on_event_handler=_lambda.Function(
                self, "AOSSIndexHandler",
                runtime=_lambda.Runtime.PYTHON_3_13,
                handler="index.on_event",
                timeout=Duration.minutes(15),
                code=_lambda.Code.from_asset("lambda_functions/aoss_index"),
                environment={
                    "BEDROCK_EMBEDDING_MODEL_NAME": f"arn:aws:bedrock:{self.region}::foundation-model/{self.EMBEDDING_MODEL}"
                }
            )
        )

        # Grant permissions to the custom resource handler
        index_provider.on_event_handler.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["aoss:*"],
                resources=["*"]
            )
        )

        # Access policies for OpenSearch collections
        aoss_access_policy = oss.CfnAccessPolicy(
            self, "AossAccessPolicy",
            name="oss-access-policy",
            type="data",
            policy=f'''[
                {{
                    "Rules": [
                        {{
                            "Resource": ["collection/oss-{self.stack_name.lower()[:25]}"],
                            "Permission": ["aoss:CreateCollectionItems", "aoss:DeleteCollectionItems", "aoss:UpdateCollectionItems", "aoss:DescribeCollectionItems"],
                            "ResourceType": "collection"
                        }},
                        {{
                            "Resource": ["index/oss-{self.stack_name.lower()[:25]}/*"],
                            "Permission": ["aoss:CreateIndex", "aoss:DeleteIndex", "aoss:UpdateIndex", "aoss:DescribeIndex", "aoss:ReadDocument", "aoss:WriteDocument"],
                            "ResourceType": "index"
                        }}
                    ],
                    "Principal": ["{bedrock_role.role_arn}", "{index_provider.on_event_handler.role.role_arn}"]
                }}
            ]'''
        )


        # AOSS Collection Index Custom Resource
        aoss_collection_index_cr = CustomResource(
            self, "AossIndexCustomResource",
            service_token=index_provider.service_token,
            properties={
                "CollectionEndpoint": aoss_collection.attr_collection_endpoint,
                "IndexNames": index_names,
                "CollectionName": aoss_collection.name
            }
        )
        aoss_collection_index_cr.node.add_dependency(aoss_collection)
        aoss_collection_index_cr.node.add_dependency(aoss_access_policy)
        aoss_collection_index_cr.node.add_dependency(aoss_network_policy)
        aoss_collection_index_cr.node.add_dependency(aoss_encryption_policy)

        # Wait for both indices to be fully ready
        wait_for_index = cr.AwsCustomResource(
            self, "WaitForIndex",
            function_name=f"{self.stack_name}-WaitForIndex-{self.region}",
            on_create=cr.AwsSdkCall(
                service="sts",
                action="getCallerIdentity",
                physical_resource_id=cr.PhysicalResourceId.of("wait-for-index")
            ),
            timeout=Duration.seconds(120), 
            policy=cr.AwsCustomResourcePolicy.from_statements([
                iam.PolicyStatement(
                    actions=["sts:GetCallerIdentity"],
                    resources=["*"]
                )
            ])
        )
        wait_for_index.node.add_dependency(aoss_collection_index_cr)

        # Create knowledge bases and data sources using loop
        knowledge_bases = {}
        data_sources = {}
        for config in kb_configs:
            # Create knowledge base
            kb = bedrock.CfnKnowledgeBase(
                self, config["construct_id"],
                name=config["name"],
                role_arn=bedrock_role.role_arn,
                knowledge_base_configuration=bedrock.CfnKnowledgeBase.KnowledgeBaseConfigurationProperty(
                    type="VECTOR",
                    vector_knowledge_base_configuration=bedrock.CfnKnowledgeBase.VectorKnowledgeBaseConfigurationProperty(
                        embedding_model_arn=f"arn:aws:bedrock:{self.region}::foundation-model/{self.EMBEDDING_MODEL}"
                    )
                ),
                storage_configuration=bedrock.CfnKnowledgeBase.StorageConfigurationProperty(
                    type="OPENSEARCH_SERVERLESS",
                    opensearch_serverless_configuration=bedrock.CfnKnowledgeBase.OpenSearchServerlessConfigurationProperty(
                        collection_arn=aoss_collection.attr_arn,
                        vector_index_name=config["index"],
                        field_mapping=bedrock.CfnKnowledgeBase.OpenSearchServerlessFieldMappingProperty(
                            vector_field=config["index"]+"-kb-vector",
                            text_field="AMAZON_BEDROCK_TEXT_CHUNK",
                            metadata_field="AMAZON_BEDROCK_METADATA"
                        )
                    )
                )
            )
            kb.node.add_dependency(wait_for_index)
            knowledge_bases[config["name"]] = kb
            
            # Create data source
            ds = bedrock.CfnDataSource(
                self, f"{config['construct_id']}DataSource",
                knowledge_base_id=kb.attr_knowledge_base_id,
                name=f"{config['name']}-datasource",
                data_source_configuration=bedrock.CfnDataSource.DataSourceConfigurationProperty(
                    type="S3",
                    s3_configuration=bedrock.CfnDataSource.S3DataSourceConfigurationProperty(
                        bucket_arn=kb_bucket.bucket_arn,
                        inclusion_prefixes=[f"{config['name']}/"]
                    )
                )
            )
            data_sources[config["name"]] = ds

         # Sync Lambda Role
        sync_lambda_role = iam.Role(
            self, "SyncLambdaFunctionExecutionRole",
            role_name=f"sync-lbd-rol-{self.stack_name}",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            inline_policies={
                f"sync-lbd-rol-pol-{self.stack_name}": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                            resources=[f"arn:{self.partition}:logs:{self.region}:{self.account}:log-group:/aws/lambda/sync-lbd-{self.stack_name}:*"]
                        ),
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "bedrock:StartIngestionJob",
                                "bedrock:GetIngestionJob"
                            ],
                            resources=["*"]
                        )
                    ]
                )
            }
        )
        
        # Sync Lambda Log Group
        sync_lambda_log_group = logs.LogGroup(
            self, "SyncLambdaFunctionCloudWatchLogGroup",
            log_group_name=f"/aws/lambda/sync-lbd-{self.stack_name}",
            retention=logs.RetentionDays.ONE_DAY,
            removal_policy=RemovalPolicy.DESTROY
        )

        # Build KB mapping for sync lambda
        kb_mapping = {}
        for config in kb_configs:
            kb_mapping[config["name"]] = {
                "kb_id": knowledge_bases[config["name"]].attr_knowledge_base_id,
                "ds_id": data_sources[config["name"]].attr_data_source_id
            }
        
        # Lambda function for triggering knowledge base sync
        sync_lambda_code = f"""
import json
import boto3
import urllib.parse

def handler(event, context):
    bedrock = boto3.client('bedrock-agent')
    
    # KB mapping
    kb_mapping = {json.dumps(kb_mapping)}
    
    for record in event['Records']:
        bucket = record['s3']['bucket']['name']
        key = urllib.parse.unquote_plus(record['s3']['object']['key'])
        
        # Determine which knowledge base to sync based on file path
        kb_name = None
        for name in kb_mapping.keys():
            if name in key:
                kb_name = name
                break
        
        if not kb_name:
            continue
            
        try:
            bedrock.start_ingestion_job(
                knowledgeBaseId=kb_mapping[kb_name]['kb_id'],
                dataSourceId=kb_mapping[kb_name]['ds_id']
            )
            print(f'Started sync for KB: {{kb_name}}')
        except Exception as e:
            print(f'Error syncing {{kb_name}}: {{e}}')
    
    return {{'statusCode': 200}}
"""
        
        sync_lambda = _lambda.Function(
            self, "KBSyncFunction",
            function_name=f"sync-lbd-{self.stack_name}",
            runtime=_lambda.Runtime.PYTHON_3_13,
            handler="index.handler",
            timeout=Duration.seconds(60),
            role=sync_lambda_role,
            code=_lambda.Code.from_inline(sync_lambda_code),
            log_group=sync_lambda_log_group
        )

        # S3 event notifications for all knowledge bases
        for config in kb_configs:
            s3_event_source = lambda_event_source.S3EventSource(
                bucket=kb_bucket,
                events=[s3.EventType.OBJECT_CREATED, s3.EventType.OBJECT_REMOVED],
                filters=[s3.NotificationKeyFilter(prefix=f"{config['name']}/")]
            )
            sync_lambda.add_event_source(s3_event_source)
        
        # Wait for event sources to be configured
        wait_for_events = cr.AwsCustomResource(
            self, "WaitForS3EventSources",
            function_name=f"{self.stack_name}-WaitForS3EventSources-{self.region}",
            on_create=cr.AwsSdkCall(
                service="lambda",
                action="getFunction",
                parameters={"FunctionName": sync_lambda.function_name},
                physical_resource_id=cr.PhysicalResourceId.of("wait-for-events")
            ),
            timeout=Duration.seconds(60),
            policy=cr.AwsCustomResourcePolicy.from_statements([
                iam.PolicyStatement(
                    actions=["lambda:GetFunction"],
                    resources=[sync_lambda.function_arn]
                )
            ])
        )
        wait_for_events.node.add_dependency(sync_lambda)
        
        # Upload knowledge base files to S3 for each KB folder
        for i, config in enumerate(kb_configs):
            deployment = s3deploy.BucketDeployment(
                self, f"KnowledgeBaseFiles{i}",
                sources=[s3deploy.Source.asset(f"./knowledge_base_files/{config['name']}")],
                destination_bucket=kb_bucket,
                destination_key_prefix=f"{config['name']}/"
            )
            deployment.node.add_dependency(wait_for_events)

        # Payroll Agent

        # Payroll Agent Lambda Role
        payroll_agent_lambda_role = iam.Role(
            self, "PayrollAgentLambdaFunctionExecutionRole",
            role_name=f"payroll-agent-lbd-rol-{self.stack_name}",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            inline_policies={
                f"payroll-agent-lbd-rol-pol-{self.stack_name}": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                            resources=[f"arn:{self.partition}:logs:{self.region}:{self.account}:log-group:/aws/lambda/payroll-agent-lbd-{self.stack_name}:*"]
                        ),
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=["ses:SendEmail"],
                            resources=["*"]
                        ),
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:DeleteItem", "dynamodb:Query", "dynamodb:Scan"],
                            resources=[
                                employee_data_table.table_arn,
                                payroll_data_table.table_arn
                            ]
                        )
                    ]
                )
            }
        )

        # Payroll Agent Lambda Log Group
        payroll_agent_log_group = logs.LogGroup(
            self, "PayrollAgentLambdaFunctionCloudWatchLogGroup",
            log_group_name=f"/aws/lambda/payroll-agent-lbd-{self.stack_name}",
            retention=logs.RetentionDays.ONE_DAY,
            removal_policy=RemovalPolicy.DESTROY
        )

        # Payroll Agent Lambda Function
        payroll_agent_lambda = _lambda.Function(
            self, "PayrollAgentLambdaFunction",
            function_name=f"payroll-agent-lbd-{self.stack_name}",
            runtime=_lambda.Runtime.PYTHON_3_13,
            handler="index.lambda_handler",
            timeout=Duration.minutes(15),
            role=payroll_agent_lambda_role,
            code=_lambda.Code.from_asset("lambda_functions/payroll_agent"),
            log_group=payroll_agent_log_group,
            environment={
                "EMPLOYEE_TABLE": employee_data_table.table_name,
                "PAYROLL_TABLE": payroll_data_table.table_name
            }
        )

        # Allow Bedrock to invoke Payroll Lambda
        payroll_agent_lambda.add_permission(
            "BedrockInvokePermission",
            principal=iam.ServicePrincipal("bedrock.amazonaws.com"),
            action="lambda:InvokeFunction"
        )
        
        # Payroll Agent
        payroll_agent = bedrock.CfnAgent(
            self, "PayrollAgent",
            agent_name="payroll-specialist",
            foundation_model=f"arn:aws:bedrock:{self.region}:{self.account}:inference-profile/{self.FOUNDATION_MODEL}",
            instruction=self._load_instruction("payroll_agent"),
            agent_resource_role_arn=bedrock_role.role_arn,
            knowledge_bases=[
                bedrock.CfnAgent.AgentKnowledgeBaseProperty(
                    knowledge_base_id=knowledge_bases["payroll-kb"].attr_knowledge_base_id,
                    description="Payroll policies, salary structures, and benefits information"
                )
            ],
            action_groups=[
                bedrock.CfnAgent.AgentActionGroupProperty(
                    action_group_name="payroll-requests-actions",
                    description="Answer the employee request action",
                    action_group_state="ENABLED",
                    action_group_executor=bedrock.CfnAgent.ActionGroupExecutorProperty(
                        lambda_=payroll_agent_lambda.function_arn
                    ),
                    api_schema=bedrock.CfnAgent.APISchemaProperty(
                        payload=self._load_api_schema("payroll_agent")
                    )
                )
            ],
        )

        # Onboarding Agent
               
        # Onboarding Agent Lambda Role
        onboarding_agent_lambda_role = iam.Role(
            self, "OnboardingAgentLambdaFunctionExecutionRole",
            role_name=f"onboarding-agent-lbd-rol-{self.stack_name}",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            inline_policies={
                f"onboarding-agent-lbd-rol-pol-{self.stack_name}": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                            resources=[f"arn:{self.partition}:logs:{self.region}:{self.account}:log-group:/aws/lambda/onboarding-agent-lbd-{self.stack_name}:*"]
                        ),
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=["ses:SendEmail"],
                            resources=["*"]
                        ),
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:DeleteItem", "dynamodb:Query", "dynamodb:Scan"],
                            resources=[
                                employee_data_table.table_arn,
                                onboarding_tasks_table.table_arn
                            ]
                        )
                    ]
                )
            }
        )

        # Onboarding Agent Lambda Log Group
        onboarding_agent_log_group = logs.LogGroup(
            self, "OnboardingAgentLambdaFunctionCloudWatchLogGroup",
            log_group_name=f"/aws/lambda/onboarding-agent-lbd-{self.stack_name}",
            retention=logs.RetentionDays.ONE_DAY,
            removal_policy=RemovalPolicy.DESTROY
        )

        # Onboarding Agent Lambda Function
        onboarding_agent_lambda = _lambda.Function(
            self, "OnboardingAgentLambdaFunction",
            function_name=f"onboarding-agent-lbd-{self.stack_name}",
            runtime=_lambda.Runtime.PYTHON_3_13,
            handler="index.lambda_handler",
            timeout=Duration.minutes(15),
            role=onboarding_agent_lambda_role,
            code=_lambda.Code.from_asset("lambda_functions/onboarding_agent"),
            log_group=onboarding_agent_log_group,
            environment={
                "ONBOARDING_TASKS_TABLE": onboarding_tasks_table.table_name
            }
        )

        # Allow Bedrock to invoke Onboarding Lambda
        onboarding_agent_lambda.add_permission(
            "BedrockInvokePermission",
            principal=iam.ServicePrincipal("bedrock.amazonaws.com"),
            action="lambda:InvokeFunction"
        )

        # Onboarding Agent
        onboarding_agent = bedrock.CfnAgent(
            self, "OnboardingAgent",
            agent_name="onboarding-specialist",
            foundation_model=f"arn:aws:bedrock:{self.region}:{self.account}:inference-profile/{self.FOUNDATION_MODEL}",
            instruction=self._load_instruction("onboarding_agent"),
            agent_resource_role_arn=bedrock_role.role_arn,
            knowledge_bases=[
                bedrock.CfnAgent.AgentKnowledgeBaseProperty(
                    knowledge_base_id=knowledge_bases["onboarding-kb"].attr_knowledge_base_id,
                    description="Onboarding processes, checklists, and new employee resources."
                )
            ],
            action_groups=[
                bedrock.CfnAgent.AgentActionGroupProperty(
                    action_group_name="onboarding-requests-actions",
                    description="Answer the employee onboarding request action",
                    action_group_state="ENABLED",
                    action_group_executor=bedrock.CfnAgent.ActionGroupExecutorProperty(
                        lambda_=onboarding_agent_lambda.function_arn
                    ),
                    api_schema=bedrock.CfnAgent.APISchemaProperty(
                        payload=self._load_api_schema("onboarding_agent")
                    )
                )
            ]
        )

        # LOA Agent

        # LOA Agent Lambda Role
        loa_agent_lambda_role = iam.Role(
            self, "LOAAgentLambdaFunctionExecutionRole",
            role_name=f"loa-agent-lbd-rol-{self.stack_name}",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            inline_policies={
                f"loa-agent-lbd-rol-pol-{self.stack_name}": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                            resources=[f"arn:{self.partition}:logs:{self.region}:{self.account}:log-group:/aws/lambda/loa-agent-lbd-{self.stack_name}:*"]
                        ),
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=["ses:SendEmail"],
                            resources=["*"]
                        ),
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:DeleteItem", "dynamodb:Query", "dynamodb:Scan"],
                            resources=[
                                employee_data_table.table_arn,
                                leave_requests_table.table_arn
                            ]
                        )
                    ]
                )
            }
        )

        # LOA Agent Lambda Log Group
        loa_agent_log_group = logs.LogGroup(
            self, "LOAAgentLambdaFunctionCloudWatchLogGroup",
            log_group_name=f"/aws/lambda/loa-agent-lbd-{self.stack_name}",
            retention=logs.RetentionDays.ONE_DAY,
            removal_policy=RemovalPolicy.DESTROY
        )

        # LOA Agent Lambda Function
        loa_agent_lambda = _lambda.Function(
            self, "LOAAgentLambdaFunction",
            function_name=f"loa-agent-lbd-{self.stack_name}",
            runtime=_lambda.Runtime.PYTHON_3_13,
            handler="index.lambda_handler",
            timeout=Duration.minutes(15),
            role=loa_agent_lambda_role,
            code=_lambda.Code.from_asset("lambda_functions/loa_agent"),
            log_group=loa_agent_log_group,
            environment={
                "EMPLOYEE_TABLE": employee_data_table.table_name,
                "LEAVE_REQUESTS_TABLE": leave_requests_table.table_name
            }
        )

        # Allow Bedrock to invoke LOA Lambda
        loa_agent_lambda.add_permission(
            "BedrockInvokePermission",
            principal=iam.ServicePrincipal("bedrock.amazonaws.com"),
            action="lambda:InvokeFunction"
        )

        # LOA Agent
        loa_agent = bedrock.CfnAgent(
            self, "LOAAgent",
            agent_name="loa-specialist",
            foundation_model=f"arn:aws:bedrock:{self.region}:{self.account}:inference-profile/{self.FOUNDATION_MODEL}",
            instruction=self._load_instruction("loa_agent"),
            agent_resource_role_arn=bedrock_role.role_arn,
            knowledge_bases=[
                bedrock.CfnAgent.AgentKnowledgeBaseProperty(
                    knowledge_base_id=knowledge_bases["loa-kb"].attr_knowledge_base_id,
                    description="Leave policies, request processes, and balance management procedures"
                )
            ],
            action_groups=[
                bedrock.CfnAgent.AgentActionGroupProperty(
                    action_group_name="loa-requests-actions",
                    description="Answer the employee leave request action",
                    action_group_state="ENABLED",
                    action_group_executor=bedrock.CfnAgent.ActionGroupExecutorProperty(
                        lambda_=loa_agent_lambda.function_arn
                    ),
                    api_schema=bedrock.CfnAgent.APISchemaProperty(
                        payload=self._load_api_schema("loa_agent")
                    )
                )
            ]
        )

        # Compliance Agent
        compliance_agent = bedrock.CfnAgent(
            self, "ComplianceAgent",
            agent_name="compliance-specialist",
            foundation_model=f"arn:aws:bedrock:{self.region}:{self.account}:inference-profile/{self.FOUNDATION_MODEL}",
            instruction=self._load_instruction("compliance_agent"),
            agent_resource_role_arn=bedrock_role.role_arn,
            knowledge_bases=[
                bedrock.CfnAgent.AgentKnowledgeBaseProperty(
                    knowledge_base_id=knowledge_bases["compliance-kb"].attr_knowledge_base_id,
                    description="Employment law, regulatory requirements, and compliance procedures"
                )
            ]
        )

        # Policy Agent
        policy_agent = bedrock.CfnAgent(
            self, "PolicyAgent",
            agent_name="policy-specialist",
            foundation_model=f"arn:aws:bedrock:{self.region}:{self.account}:inference-profile/{self.FOUNDATION_MODEL}",
            instruction=self._load_instruction("policy_agent"),
            agent_resource_role_arn=bedrock_role.role_arn,
            knowledge_bases=[
                bedrock.CfnAgent.AgentKnowledgeBaseProperty(
                    knowledge_base_id=knowledge_bases["policy-kb"].attr_knowledge_base_id,
                    description="Company policies, procedures, and workplace guidelines"
                )
            ]
        )

        # Create agent aliases
        payroll_alias = bedrock.CfnAgentAlias(
            self, "PayrollAgentAlias",
            agent_id=payroll_agent.attr_agent_id,
            agent_alias_name="payroll-alias"
        )

        onboarding_alias = bedrock.CfnAgentAlias(
            self, "OnboardingAgentAlias",
            agent_id=onboarding_agent.attr_agent_id,
            agent_alias_name="onboarding-alias"
        )

        loa_alias = bedrock.CfnAgentAlias(
            self, "LOAAgentAlias",
            agent_id=loa_agent.attr_agent_id,
            agent_alias_name="loa-alias"
        )

        compliance_alias = bedrock.CfnAgentAlias(
            self, "ComplianceAgentAlias",
            agent_id=compliance_agent.attr_agent_id,
            agent_alias_name="compliance-alias"
        )

        policy_alias = bedrock.CfnAgentAlias(
            self, "PolicyAgentAlias",
            agent_id=policy_agent.attr_agent_id,
            agent_alias_name="policy-alias"
        )

        # Orchestrator Agent
        orchestrator_agent = bedrock.CfnAgent(
            self, "OrchestratorAgent",
            agent_name="hr-orchestrator",
            foundation_model=f"arn:aws:bedrock:{self.region}:{self.account}:inference-profile/{self.FOUNDATION_MODEL}",
            instruction=self._load_instruction("orchestrator_agent"),
            agent_resource_role_arn=bedrock_role.role_arn,
            agent_collaboration="SUPERVISOR",
            action_groups=[
                bedrock.CfnAgent.AgentActionGroupProperty(
                    action_group_name="enable-agent-user-input",
                    action_group_state="ENABLED",
                    parent_action_group_signature="AMAZON.UserInput"
                )
            ],
            agent_collaborators=[
                bedrock.CfnAgent.AgentCollaboratorProperty(
                    agent_descriptor=bedrock.CfnAgent.AgentDescriptorProperty(
                        alias_arn=payroll_alias.attr_agent_alias_arn
                    ),
                    collaboration_instruction="Handle salary calculations, payroll processing, benefits, and compensation",
                    collaborator_name="Payroll-Specialist",
                    relay_conversation_history="TO_COLLABORATOR"
                ),
                bedrock.CfnAgent.AgentCollaboratorProperty(
                    agent_descriptor=bedrock.CfnAgent.AgentDescriptorProperty(
                        alias_arn=onboarding_alias.attr_agent_alias_arn
                    ),
                    collaboration_instruction="Handle new employee onboarding, documentation, and integration",
                    collaborator_name="Onboarding-Specialist",
                    relay_conversation_history="TO_COLLABORATOR"
                ),
                bedrock.CfnAgent.AgentCollaboratorProperty(
                    agent_descriptor=bedrock.CfnAgent.AgentDescriptorProperty(
                        alias_arn=compliance_alias.attr_agent_alias_arn
                    ),
                    collaboration_instruction="Handle legal compliance, regulations, and employment law",
                    collaborator_name="Compliance-Specialist",
                    relay_conversation_history="TO_COLLABORATOR"
                ),
                bedrock.CfnAgent.AgentCollaboratorProperty(
                    agent_descriptor=bedrock.CfnAgent.AgentDescriptorProperty(
                        alias_arn=loa_alias.attr_agent_alias_arn
                    ),
                    collaboration_instruction="Handle leave requests, PTO, FMLA, and absence management",
                    collaborator_name="LOA-Specialist",
                    relay_conversation_history="TO_COLLABORATOR"
                ),
                bedrock.CfnAgent.AgentCollaboratorProperty(
                    agent_descriptor=bedrock.CfnAgent.AgentDescriptorProperty(
                        alias_arn=policy_alias.attr_agent_alias_arn
                    ),
                    collaboration_instruction="Handle company policies, procedures, and career advancement",
                    collaborator_name="Policy-Specialist",
                    relay_conversation_history="TO_COLLABORATOR"
                )
            ]
        )

        orchestrator_alias = bedrock.CfnAgentAlias(
            self, "OrchestratorAgentAlias",
            agent_id=orchestrator_agent.attr_agent_id,
            agent_alias_name="orchestrator-alias"
        )

        # VPC
        vpc = ec2.Vpc(self, "StreamlitVpc", max_azs=2)
                      

        # ECS Cluster
        cluster = ecs.Cluster(self, "StreamlitCluster", vpc=vpc)

        # Docker Image
        docker_image = ecr_assets.DockerImageAsset(
            self, "StreamlitImage",
            directory="./streamlit",
            platform=ecr_assets.Platform.LINUX_AMD64
        )

        # Task Role
        task_role = iam.Role(
            self, "StreamlitTaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonBedrockFullAccess")
            ]
        )

        # Task Definition
        task_definition = ecs.FargateTaskDefinition(
            self, "StreamlitTaskDef",
            memory_limit_mib=2048,
            cpu=1024,
            task_role=task_role
        )

        # Container
        container = task_definition.add_container(
            "StreamlitContainer",
            image=ecs.ContainerImage.from_docker_image_asset(docker_image),
            port_mappings=[ecs.PortMapping(container_port=8501)],
            logging=ecs.LogDrivers.aws_logs(stream_prefix=f"ecs-log-{self.stack_name.lower()}"),
            environment={
                "ORCHESTRATOR_AGENT_ID": orchestrator_agent.attr_agent_id,
                "AWS_REGION": self.region
            }
        )

        # ALB
        alb = elbv2.ApplicationLoadBalancer(
            self, "StreamlitALB",
            vpc=vpc,
            internet_facing=True
        )

        # ECS Service
        service = ecs.FargateService(
            self, "StreamlitService",
            cluster=cluster,
            task_definition=task_definition,
            desired_count=2,
            assign_public_ip=True
        )
        
        # Auto Scaling
        scaling = service.auto_scale_task_count(
            min_capacity=2,
            max_capacity=10
        )
        
        scaling.scale_on_cpu_utilization(
            "CpuScaling",
            target_utilization_percent=70,
            scale_in_cooldown=Duration.minutes(5),
            scale_out_cooldown=Duration.minutes(2)
        )

        # Target Group
        target_group = elbv2.ApplicationTargetGroup(
            self, "StreamlitTargetGroup",
            port=8501,
            protocol=elbv2.ApplicationProtocol.HTTP,
            vpc=vpc,
            target_type=elbv2.TargetType.IP,
            health_check=elbv2.HealthCheck(
                enabled=True,
                path="/",
                port="traffic-port",
                protocol=elbv2.Protocol.HTTP,
                healthy_threshold_count=5,
                unhealthy_threshold_count=2,
                timeout=Duration.seconds(5),
                interval=Duration.seconds(30)
            )
        )

        # Listener
        alb.add_listener(
            "StreamlitListener",
            port=80,
            default_target_groups=[target_group]
        )

        # Connect service to target group
        service.attach_to_application_target_group(target_group)

        # CloudFront Distribution
        cloudfront_distribution = cloudfront.Distribution(
            self, "StreamlitDistribution",
            comment=f"cloudfront distribution for Streamlit WebApp {self.stack_name}",
            price_class=cloudfront.PriceClass.PRICE_CLASS_100,
            default_behavior=cloudfront.BehaviorOptions(
                origin=cloudfront_origins.HttpOrigin(
                    alb.load_balancer_dns_name,
                    http_port=80,
                    protocol_policy=cloudfront.OriginProtocolPolicy.HTTP_ONLY
                ),
                allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
                cached_methods=cloudfront.CachedMethods.CACHE_GET_HEAD,
                compress=True,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
                origin_request_policy=cloudfront.OriginRequestPolicy.ALL_VIEWER
            )
        )

        # Output URLs
        CfnOutput(
            self, "StreamlitURL",
            value=f"https://{cloudfront_distribution.distribution_domain_name}",
            description="Streamlit Application URL (CloudFront)"
        )

    def _load_instruction(self, agent_name):
        with open(f"instructions/{agent_name}.txt", 'r') as f:
            return f.read().strip()
    
    def _load_api_schema(self, agent_name) -> str:
        """Load API schema from external file"""
        with open(f"api-schemas/{agent_name}.yaml", 'r') as f:
            return f.read()
