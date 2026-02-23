from aws_cdk import (
    Stack, Duration, RemovalPolicy, CfnOutput, SecretValue,
    aws_iam as iam,
    aws_ecs as ecs,
    aws_ec2 as ec2,
    aws_ecr_assets as ecr_assets,
    aws_elasticloadbalancingv2 as elbv2,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as cloudfront_origins,
    aws_logs as logs,
    aws_lambda as _lambda,
    aws_bedrockagentcore as bedrockagentcore,
    aws_secretsmanager as secretsmanager,
    aws_s3 as s3
)
from constructs import Construct
import json

class BedrockMCPStack(Stack):
    # Constants
    FOUNDATION_MODEL = "anthropic.claude-3-7-sonnet-20250219-v1:0"  # Base foundation model
    INFERENCE_PROFILE_ID = "us.anthropic.claude-3-7-sonnet-20250219-v1:0"  # Cross-region inference profile

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create VPC
        agentic_app_vpc = ec2.Vpc(
            self, "AgenticAppVpc",
            vpc_name=f"{self.stack_name}-agentic-app-vpc",
            max_azs=2
        )
       
        agentic_app_vpc.apply_removal_policy(RemovalPolicy.DESTROY)
        
        # Create Security Group - VPC Endpoint (Agentic App VPC)
        sg_vpc_endpoint = ec2.SecurityGroup(
            self, "endpoint-security-group",
            security_group_name=f"{self.stack_name}-vpc-endpoint-sg",
            vpc=agentic_app_vpc,
        )
        sg_vpc_endpoint.apply_removal_policy(RemovalPolicy.DESTROY)
        sg_vpc_endpoint.add_ingress_rule(ec2.Peer.ipv4(agentic_app_vpc.vpc_cidr_block), connection=ec2.Port.tcp(443))
        
        
        # VPC Endpoints

        # Create VPC Interface Endpoints for Bedrock Runtime (Agentic App VPC)
        bedrock_interface_vpc_endpoint = ec2.InterfaceVpcEndpoint(self, "BedrockInterfaceVpcEndpoint",
            vpc=agentic_app_vpc,
            service=ec2.InterfaceVpcEndpointService(f"com.amazonaws.{self.region}.bedrock-runtime", 443),
            private_dns_enabled=True,
            security_groups=[sg_vpc_endpoint],
            subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS)
        )
        bedrock_interface_vpc_endpoint.apply_removal_policy(RemovalPolicy.DESTROY)
        
        # Create VPC Interface Endpoints for Bedrock Runtime (Agentic App VPC)
        bedrock_agent_interface_vpc_endpoint = ec2.InterfaceVpcEndpoint(self, "BedrockAgentInterfaceVpcEndpoint",
            vpc=agentic_app_vpc,
            service=ec2.InterfaceVpcEndpointService(f"com.amazonaws.{self.region}.bedrock-agent-runtime", 443),
            private_dns_enabled=True,
            security_groups=[sg_vpc_endpoint],
            subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS)
        )
        bedrock_agent_interface_vpc_endpoint.apply_removal_policy(RemovalPolicy.DESTROY)

        # Create VPC Interface Endpoints for Bedrock Agent Core (Agentic App VPC)
        bedrock_agentcore_interface_vpc_endpoint = ec2.InterfaceVpcEndpoint(self, f"BedrockAgentCoreInterfaceVpcEndpoint",
            vpc=agentic_app_vpc,
            service=ec2.InterfaceVpcEndpointService(f"com.amazonaws.{self.region}.bedrock-agentcore.gateway", 443),
            private_dns_enabled=True,
            security_groups=[sg_vpc_endpoint],
            subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS)
        )
        bedrock_agentcore_interface_vpc_endpoint.apply_removal_policy(RemovalPolicy.DESTROY)

        # Create VPC Interface Endpoints for ECR API (Agentic App VPC)
        ecr_api_interface_vpc_endpoint = ec2.InterfaceVpcEndpoint(self, "EcrApiInterfaceVpcEndpoint",
            vpc=agentic_app_vpc,
            service=ec2.InterfaceVpcEndpointService(f"com.amazonaws.{self.region}.ecr.api", 443),
            private_dns_enabled=True,
            security_groups=[sg_vpc_endpoint],
            subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS)
        )
        ecr_api_interface_vpc_endpoint.apply_removal_policy(RemovalPolicy.DESTROY)

        # Create VPC Interface Endpoints for ECR DKR (Agentic App VPC)
        ecr_dkr_interface_vpc_endpoint = ec2.InterfaceVpcEndpoint(self, "EcrDkrInterfaceVpcEndpoint",
            vpc=agentic_app_vpc,
            service=ec2.InterfaceVpcEndpointService(f"com.amazonaws.{self.region}.ecr.dkr", 443),
            private_dns_enabled=True,
            security_groups=[sg_vpc_endpoint],
            subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS)
        )
        ecr_dkr_interface_vpc_endpoint.apply_removal_policy(RemovalPolicy.DESTROY)
        
        # Create VPC Interface Endpoints for CloudWatch Logs (Agentic App VPC)
        logs_vpc_endpoint = ec2.InterfaceVpcEndpoint(self, "CloudWatchLogsInterfaceVpcEndpoint",
            vpc=agentic_app_vpc,
            service=ec2.InterfaceVpcEndpointService(f"com.amazonaws.{self.region}.logs", 443),
            private_dns_enabled=True,
            security_groups=[sg_vpc_endpoint],
            subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS)
        )
        logs_vpc_endpoint.apply_removal_policy(RemovalPolicy.DESTROY)

        # Create VPC Gateway Endpoint for S3 (required for ECR image layers) (Agentic App VPC)
        s3_gateway_vpc_endpoint = ec2.GatewayVpcEndpoint(self, f"s3GatewayVpcEndpoint",
            vpc=agentic_app_vpc,
            service=ec2.GatewayVpcEndpointAwsService.S3
        )
        s3_gateway_vpc_endpoint.apply_removal_policy(RemovalPolicy.DESTROY)
        

        # =============================================================================
        # SECRETS MANAGER
        # =============================================================================
        
        # Load secrets from separate files
        adzuna_creds = self._load_secret_file("adzuna")
        usajobs_creds = self._load_secret_file("usajobs")
        
        # Secrets Manager - API Credentials
        adzuna_secret = secretsmanager.Secret(
            self, "AdzunaAPICredentials",
            description="Adzuna API credentials",
            secret_object_value={
                "API_ID": SecretValue.unsafe_plain_text(adzuna_creds["ADZUNA_APP_ID"]),
                "API_KEY": SecretValue.unsafe_plain_text(adzuna_creds["ADZUNA_APP_KEY"])
            }
        )
        
        usajobs_secret = secretsmanager.Secret(
            self, "USAJobsAPICredentials",
            description="USAJobs API credentials",
            secret_object_value={
                "API_ID": SecretValue.unsafe_plain_text(usajobs_creds["USAJOBS_EMAIL"]),
                "API_KEY": SecretValue.unsafe_plain_text(usajobs_creds["USAJOBS_API_KEY"])
            }
        )

        # =============================================================================
        # S3 BUCKET FOR CHART STORAGE
        # =============================================================================
        
        # Create S3 bucket for chart storage
        charts_bucket = s3.Bucket(
            self, "ChartsStorageBucket",
            bucket_name=f"{self.stack_name.lower()}-charts-{self.account}-{self.region}",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            public_read_access=False,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL
        )

        # =============================================================================
        # Bedrock AgentCore Gateway INFRASTRUCTURE
        # =============================================================================

        # CloudWatch Log Groups for Lambda Functions
        adzuna_lambda_log_group = logs.LogGroup(
            self, "AdzunaLambdaLogGroup",
            log_group_name=f"/aws/lambda/{self.stack_name}-adzuna-lambda",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY
        )
        
        usajobs_lambda_log_group = logs.LogGroup(
            self, "UsajobsLambdaLogGroup",
            log_group_name=f"/aws/lambda/{self.stack_name}-usajobs-lambda",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY
        )

        # Lambda Functions using ECR
        adzuna_docker_image = ecr_assets.DockerImageAsset(
            self, "AdzunaLambdaImage",
            directory="./lambda_functions/adzuna_lambda",
            platform=ecr_assets.Platform.LINUX_AMD64
        )
        
        adzuna_lambda = _lambda.Function(
            self, "AdzunaLambda",
            function_name=f"{self.stack_name}-adzuna-lambda",
            code=_lambda.Code.from_ecr_image(
                repository=adzuna_docker_image.repository,
                tag_or_digest=adzuna_docker_image.image_tag
            ),
            handler=_lambda.Handler.FROM_IMAGE,
            runtime=_lambda.Runtime.FROM_IMAGE,
            timeout=Duration.minutes(5),
            memory_size=1024,
            environment={
                "MCP_SECRET_NAME": adzuna_secret.secret_name,
                "CHARTS_BUCKET_NAME": charts_bucket.bucket_name
            },
            log_group=adzuna_lambda_log_group
        )
        
        # USAJobs Lambda Function using ECR
        usajobs_docker_image = ecr_assets.DockerImageAsset(
            self, "UsajobsLambdaImage",
            directory="./lambda_functions/usajobs_lambda",
            platform=ecr_assets.Platform.LINUX_AMD64
        )
        
        usajobs_lambda = _lambda.Function(
            self, "UsajobsLambda",
            function_name=f"{self.stack_name}-usajobs-lambda",
            code=_lambda.Code.from_ecr_image(
                repository=usajobs_docker_image.repository,
                tag_or_digest=usajobs_docker_image.image_tag
            ),
            handler=_lambda.Handler.FROM_IMAGE,
            runtime=_lambda.Runtime.FROM_IMAGE,
            timeout=Duration.minutes(5),
            memory_size=512,
            environment={
                "MCP_SECRET_NAME": usajobs_secret.secret_name,
                "CHARTS_BUCKET_NAME": charts_bucket.bucket_name
            },
            log_group=usajobs_lambda_log_group
        )
        
        # Grant Lambda access to their respective secrets
        adzuna_secret.grant_read(adzuna_lambda)
        usajobs_secret.grant_read(usajobs_lambda)
        
        # Grant Lambda functions access to S3 bucket for chart storage
        charts_bucket.grant_read_write(adzuna_lambda)
        charts_bucket.grant_read_write(usajobs_lambda)
        
        # Grant Bedrock Agent Core permission to invoke Lambda functions
        adzuna_lambda.add_permission(
            "BedrockAgentCoreInvoke",
            principal=iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
            action="lambda:InvokeFunction",
            source_account=self.account
        )
        
        usajobs_lambda.add_permission(
            "BedrockAgentCoreInvoke",
            principal=iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
            action="lambda:InvokeFunction",
            source_account=self.account
        )

        # Agent Core Gateway Role
        agent_core_gateway_role = iam.Role(
            self, "AgentCoreGatewayRole",
            role_name=f"{self.stack_name}-agent-core-gateway-role",
            assumed_by=iam.ServicePrincipal(
                "bedrock-agentcore.amazonaws.com",
                conditions={
                    "StringEquals": {"aws:SourceAccount": self.account},
                    "ArnLike": {"aws:SourceArn": [
                        f"arn:aws:bedrock-agentcore:{self.region}:{self.account}:gateway/{self.stack_name}-adzuna-mcp-gateway-*",
                        f"arn:aws:bedrock-agentcore:{self.region}:{self.account}:gateway/{self.stack_name}-usajobs-mcp-gateway-*"
                    ]}
                }
            ),
            inline_policies={
                "AgentCoreGatewayPolicy": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            actions=["lambda:InvokeFunction"],
                            resources=[adzuna_lambda.function_arn, usajobs_lambda.function_arn]
                        )
                    ]
                )
            }
        )
        
        # Adzuna MCP Gateway
        adzuna_cfn_gateway = bedrockagentcore.CfnGateway(
            self, "AdzunaMcpGateway",
            authorizer_type="AWS_IAM",
            name=f"{self.stack_name}-adzuna-mcp-gateway",
            protocol_type="MCP",
            role_arn=agent_core_gateway_role.role_arn
        )
        
        # USAJobs MCP Gateway
        usajobs_cfn_gateway = bedrockagentcore.CfnGateway(
            self, "UsajobsMcpGateway",
            authorizer_type="AWS_IAM",
            name=f"{self.stack_name}-usajobs-mcp-gateway",
            protocol_type="MCP",
            role_arn=agent_core_gateway_role.role_arn
        )
        
        
        # Adzuna Lambda Gateway Target
        adzuna_gateway_target = bedrockagentcore.CfnGatewayTarget(
            self, "AdzunaGatewayTarget",
            gateway_identifier=adzuna_cfn_gateway.attr_gateway_identifier,
            name=f"{self.stack_name}-adzuna-lambda-target",
            credential_provider_configurations=[
                bedrockagentcore.CfnGatewayTarget.CredentialProviderConfigurationProperty(
                    credential_provider_type="GATEWAY_IAM_ROLE"
                )
            ],
            target_configuration=bedrockagentcore.CfnGatewayTarget.TargetConfigurationProperty(
                mcp=bedrockagentcore.CfnGatewayTarget.McpTargetConfigurationProperty(
                    lambda_=bedrockagentcore.CfnGatewayTarget.McpLambdaTargetConfigurationProperty(
                        lambda_arn=adzuna_lambda.function_arn,
                        tool_schema=bedrockagentcore.CfnGatewayTarget.ToolSchemaProperty(
                            inline_payload=[
                                bedrockagentcore.CfnGatewayTarget.ToolDefinitionProperty(
                                    name="search_adzuna_jobs",
                                    description="Search for jobs using Adzuna API with filters",
                                    input_schema=bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                        type="object",
                                        properties={
                                            "keywords": bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="Job search keywords"
                                            ),
                                            "location": bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="Country code (us, gb, au, etc.)"
                                            ),
                                            "limit": bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="integer",
                                                description="Number of results (max 50)"
                                            ),
                                            "salary_min": bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="integer",
                                                description="Minimum salary filter"
                                            ),
                                            "salary_max": bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="integer",
                                                description="Maximum salary filter"
                                            ),
                                            "company": bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="Company name filter"
                                            ),
                                            "full_time": bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="boolean",
                                                description="Filter for full-time jobs only"
                                            )
                                        },
                                        required=["keywords"]
                                    )
                                ),
                                bedrockagentcore.CfnGatewayTarget.ToolDefinitionProperty(
                                    name="get_adzuna_salary_stats",
                                    description="Get salary statistics for a job title/keyword",
                                    input_schema=bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                        type="object",
                                        properties={
                                            "keywords": bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="Job search keywords"
                                            ),
                                            "location": bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="Country code (us, gb, au, etc.)"
                                            )
                                        },
                                        required=["keywords"]
                                    )
                                ),
                                bedrockagentcore.CfnGatewayTarget.ToolDefinitionProperty(
                                    name="get_adzuna_job_categories",
                                    description="Get available job categories and their job counts",
                                    input_schema=bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                        type="object",
                                        properties={
                                            "location": bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="Country code (us, gb, au, etc.)"
                                            )
                                        }
                                    )
                                ),
                                bedrockagentcore.CfnGatewayTarget.ToolDefinitionProperty(
                                    name="get_adzuna_top_companies",
                                    description="Get top companies by job count",
                                    input_schema=bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                        type="object",
                                        properties={
                                            "location": bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="Country code (us, gb, au, etc.)"
                                            ),
                                            "limit": bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="integer",
                                                description="Number of companies to return"
                                            )
                                        }
                                    )
                                ),
                                bedrockagentcore.CfnGatewayTarget.ToolDefinitionProperty(
                                    name="search_adzuna_by_location",
                                    description="Search jobs by specific location (city, state, etc.)",
                                    input_schema=bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                        type="object",
                                        properties={
                                            "keywords": bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="Job search keywords"
                                            ),
                                            "where": bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="Specific location (e.g., 'New York', 'San Francisco')"
                                            ),
                                            "location": bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="Country code (us, gb, au, etc.)"
                                            ),
                                            "limit": bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="integer",
                                                description="Number of results"
                                            )
                                        },
                                        required=["keywords", "where"]
                                    )
                                ),
                                bedrockagentcore.CfnGatewayTarget.ToolDefinitionProperty(
                                    name="get_adzuna_job_details",
                                    description="Get detailed information about a specific job posting",
                                    input_schema=bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                        type="object",
                                        properties={
                                            "job_id": bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="Unique job identifier"
                                            ),
                                            "location": bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="Country code (us, gb, au, etc.)"
                                            )
                                        },
                                        required=["job_id"]
                                    )
                                ),
                                bedrockagentcore.CfnGatewayTarget.ToolDefinitionProperty(
                                    name="search_adzuna_geodata",
                                    description="Search for location data and get geographic job market info",
                                    input_schema=bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                        type="object",
                                        properties={
                                            "location_query": bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="Location search term"
                                            ),
                                            "location": bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="Country code (us, gb, au, etc.)"
                                            )
                                        },
                                        required=["location_query"]
                                    )
                                ),
                                bedrockagentcore.CfnGatewayTarget.ToolDefinitionProperty(
                                    name="get_adzuna_salary_chart",
                                    description="Generate a visual salary histogram chart for a job title/keyword",
                                    input_schema=bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                        type="object",
                                        properties={
                                            "keywords": bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="Job search keywords"
                                            ),
                                            "location": bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="Country code (us, gb, au, etc.)"
                                            ),
                                            "save_path": bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="Optional path to save the chart image"
                                            )
                                        },
                                        required=["keywords"]
                                    )
                                )
                            ]
                        )
                    )
                )
            )
        )
        
        # USAJobs Lambda Gateway Target
        usajobs_gateway_target = bedrockagentcore.CfnGatewayTarget(
            self, "UsajobsGatewayTarget",
            gateway_identifier=usajobs_cfn_gateway.attr_gateway_identifier,
            name=f"{self.stack_name}-usajobs-lambda-target",
            credential_provider_configurations=[
                bedrockagentcore.CfnGatewayTarget.CredentialProviderConfigurationProperty(
                    credential_provider_type="GATEWAY_IAM_ROLE"
                )
            ],
            target_configuration=bedrockagentcore.CfnGatewayTarget.TargetConfigurationProperty(
                mcp=bedrockagentcore.CfnGatewayTarget.McpTargetConfigurationProperty(
                    lambda_=bedrockagentcore.CfnGatewayTarget.McpLambdaTargetConfigurationProperty(
                        lambda_arn=usajobs_lambda.function_arn,
                        tool_schema=bedrockagentcore.CfnGatewayTarget.ToolSchemaProperty(
                            inline_payload=[
                                bedrockagentcore.CfnGatewayTarget.ToolDefinitionProperty(
                                    name="search_usajobs",
                                    description="Search US government jobs using USAJobs API with advanced filters",
                                    input_schema=bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                        type="object",
                                        properties={
                                            "keywords": bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="Job search keywords"
                                            ),
                                            "location": bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="Location filter"
                                            ),
                                            "limit": bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="integer",
                                                description="Number of results (max 500)"
                                            ),
                                            "organization": bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="Federal agency or organization filter"
                                            ),
                                            "pay_grade_low": bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="Minimum pay grade (e.g., 'GS-12')"
                                            ),
                                            "pay_grade_high": bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="Maximum pay grade (e.g., 'GS-15')"
                                            ),
                                            "job_category_code": bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="Job category code filter"
                                            ),
                                            "position_schedule_type_code": bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="Position schedule type (1=Full-time, 2=Part-time, etc.)"
                                            ),
                                            "position_offering_type_code": bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="Position offering type (15317=Permanent, 15323=Temporary, etc.)"
                                            )
                                        },
                                        required=["keywords"]
                                    )
                                ),
                                bedrockagentcore.CfnGatewayTarget.ToolDefinitionProperty(
                                    name="get_usajobs_job_details",
                                    description="Get detailed information about a specific USAJobs posting",
                                    input_schema=bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                        type="object",
                                        properties={
                                            "control_number": bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                                type="string",
                                                description="USAJobs control number for the job posting"
                                            )
                                        },
                                        required=["control_number"]
                                    )
                                ),
                                bedrockagentcore.CfnGatewayTarget.ToolDefinitionProperty(
                                    name="get_usajobs_agencies",
                                    description="Get list of federal agencies that post jobs",
                                    input_schema=bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                        type="object",
                                        properties={}
                                    )
                                ),
                                bedrockagentcore.CfnGatewayTarget.ToolDefinitionProperty(
                                    name="get_usajobs_occupational_series",
                                    description="Get list of occupational series codes",
                                    input_schema=bedrockagentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                                        type="object",
                                        properties={}
                                    )
                                )
                            ]
                        )
                    )
                )
            )
        )
        
        # Add dependencies
        adzuna_gateway_target.node.add_dependency(adzuna_cfn_gateway)
        adzuna_gateway_target.node.add_dependency(adzuna_lambda)
        usajobs_gateway_target.node.add_dependency(usajobs_cfn_gateway)
        usajobs_gateway_target.node.add_dependency(usajobs_lambda)
        
        # Apply removal policies for proper cleanup
        agent_core_gateway_role.apply_removal_policy(RemovalPolicy.DESTROY)
        adzuna_cfn_gateway.apply_removal_policy(RemovalPolicy.DESTROY)
        usajobs_cfn_gateway.apply_removal_policy(RemovalPolicy.DESTROY)
        adzuna_lambda.apply_removal_policy(RemovalPolicy.DESTROY)
        usajobs_lambda.apply_removal_policy(RemovalPolicy.DESTROY)
        adzuna_gateway_target.apply_removal_policy(RemovalPolicy.DESTROY)
        usajobs_gateway_target.apply_removal_policy(RemovalPolicy.DESTROY)
        adzuna_secret.apply_removal_policy(RemovalPolicy.DESTROY)
        usajobs_secret.apply_removal_policy(RemovalPolicy.DESTROY)
        charts_bucket.apply_removal_policy(RemovalPolicy.DESTROY)
        
        # =============================================================================
        # Agentic APP-MCP INFRASTRUCTURE
        # =============================================================================

        # CloudWatch Log Group for Agentic App
        agentic_app_log_group = logs.LogGroup(
            self, "AgenticAppLogGroup",
            log_group_name=f"/ecs/{self.stack_name}-agentic-app",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY
        )
        
        agentic_app_task_role = iam.Role(
            self, "AgenticAppTaskRole",
            role_name=f"{self.stack_name}-agentic-app-task-role",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            inline_policies={
                "BedrockInvokePolicy": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "bedrock:InvokeModel",
                                "bedrock:InvokeModelWithResponseStream",
                                "bedrock:UseInferenceProfile"
                            ],
                            resources=[
                                f"arn:aws:bedrock:{self.region}:{self.account}:inference-profile/{self.INFERENCE_PROFILE_ID}",
                                # Anthropic Claude 3.7 Sonnet in us-east-1, us-east-2 and us-west-2
                                f"arn:aws:bedrock:us-east-1::foundation-model/{self.FOUNDATION_MODEL}",
                                f"arn:aws:bedrock:us-east-2::foundation-model/{self.FOUNDATION_MODEL}",
                                f"arn:aws:bedrock:us-west-2::foundation-model/{self.FOUNDATION_MODEL}" 
                            ]
                        )
                    ]
                ),
                "CloudWatchLogsPolicy": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "logs:CreateLogStream",
                                "logs:PutLogEvents"
                            ],
                            resources=[agentic_app_log_group.log_group_arn + ":*"]
                        )
                    ]
                ),
                "S3ChartsAccessPolicy": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
                            resources=[f"{charts_bucket.bucket_arn}/*"]
                        ),
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=["s3:ListBucket"],
                            resources=[charts_bucket.bucket_arn]
                        )
                    ]
                ),
                "BedrockAgentCoreGatewayPolicy": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=["bedrock-agentcore:InvokeGateway"],
                            resources=[
                                f"arn:aws:bedrock-agentcore:{self.region}:{self.account}:gateway/{adzuna_cfn_gateway.attr_gateway_identifier}",
                                f"arn:aws:bedrock-agentcore:{self.region}:{self.account}:gateway/{usajobs_cfn_gateway.attr_gateway_identifier}"
                            ]
                        )
                    ]
                )
            }
        )

        # ECS Clusters (Agentic APP)
        agentic_app_cluster = ecs.Cluster(
            self, "AgenticAppCluster",
            cluster_name=f"{self.stack_name}-agentic-app-cluster",
            vpc=agentic_app_vpc,
            container_insights=True
        )

        # Agentic App Docker Image
        agentic_app_docker_image = ecr_assets.DockerImageAsset(
            self, "AgenticAppImage",
            directory="./streamlit",
            platform=ecr_assets.Platform.LINUX_AMD64
        )
        

        # Task Definition
        agentic_app_task_definition = ecs.FargateTaskDefinition(
            self, "AgenticAppTaskDef",
            memory_limit_mib=2048,
            cpu=1024,
            task_role=agentic_app_task_role
        )

        # Container
        agentic_app_container = agentic_app_task_definition.add_container(
            "AgenticAppContainer",
            image=ecs.ContainerImage.from_docker_image_asset(agentic_app_docker_image),
            port_mappings=[ecs.PortMapping(container_port=8501)],
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="agentic-app",
                log_group=agentic_app_log_group
            ),
            environment={
                "BEDROCK_MODEL": self.INFERENCE_PROFILE_ID,
                "AWS_REGION": self.region,
                "ADZUNA_GATEWAY_NAME": adzuna_cfn_gateway.name,
                "USAJOBS_GATEWAY_NAME": usajobs_cfn_gateway.name,
                "ADZUNA_GATEWAY_URL": f"https://{adzuna_cfn_gateway.attr_gateway_identifier}.gateway.bedrock-agentcore.{self.region}.amazonaws.com/mcp",
                "USAJOBS_GATEWAY_URL": f"https://{usajobs_cfn_gateway.attr_gateway_identifier}.gateway.bedrock-agentcore.{self.region}.amazonaws.com/mcp",
                "CHARTS_BUCKET_NAME": charts_bucket.bucket_name
            }
        )

        # ALB
        agentic_app_alb = elbv2.ApplicationLoadBalancer(
            self, "AgenticAppALB",
            load_balancer_name=f"{self.stack_name}-alb",
            vpc=agentic_app_vpc,
            internet_facing=True,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC)
        )

        # ECS Service
        agentic_app_service = ecs.FargateService(
            self, "AgenticAppService",
            cluster=agentic_app_cluster,
            task_definition=agentic_app_task_definition,
            desired_count=2,
            assign_public_ip=False,
            min_healthy_percent=100,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS)
        )
        
        # Auto Scaling
        agentic_app_scaling = agentic_app_service.auto_scale_task_count(
            min_capacity=2,
            max_capacity=10
        )
        
        agentic_app_scaling.scale_on_cpu_utilization(
            "CpuScaling",
            target_utilization_percent=70,
            scale_in_cooldown=Duration.minutes(5),
            scale_out_cooldown=Duration.minutes(2)
        )

        # Target Group
        agentic_app_target_group = elbv2.ApplicationTargetGroup(
            self, "AgenticAppTargetGroup",
            target_group_name=f"{self.stack_name}-alb-tg",
            port=8501,
            protocol=elbv2.ApplicationProtocol.HTTP,
            vpc=agentic_app_vpc,
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
        agentic_app_alb.add_listener(
            "AgenticAppListener",
            port=80,
            default_target_groups=[agentic_app_target_group]
        )

        # Connect service to target group
        agentic_app_service.attach_to_application_target_group(agentic_app_target_group)

        # CloudFront Distribution
        cloudfront_distribution = cloudfront.Distribution(
            self, "AgenticAppDistribution",
            comment=f"cloudfront distribution for Agentic App {self.stack_name}",
            price_class=cloudfront.PriceClass.PRICE_CLASS_100,
            default_behavior=cloudfront.BehaviorOptions(
                origin=cloudfront_origins.HttpOrigin(
                    agentic_app_alb.load_balancer_dns_name,
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
            self, "AgenticAppURL",
            value=f"https://{cloudfront_distribution.distribution_domain_name}",
            description="Streamlit Application URL (CloudFront)"
        )
        

    def _load_secret_file(self, service_name):
        """Load API secrets from service-specific file"""
        with open(f"secrets/{service_name}.json", 'r') as f:
            return json.load(f)
    