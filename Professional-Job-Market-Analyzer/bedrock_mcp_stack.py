from aws_cdk import (
    Stack, Duration, RemovalPolicy, CfnOutput, SecretValue,
    aws_iam as iam,
    aws_ecs as ecs,
    aws_ec2 as ec2,
    aws_ecr_assets as ecr_assets,
    aws_elasticloadbalancingv2 as elbv2,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as cloudfront_origins,
    aws_secretsmanager as secretsmanager,
    aws_logs as logs
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
        agentic_app_vpc = ec2.Vpc(self, "AgenticAppVpc", max_azs=2)
       
        agentic_app_vpc.apply_removal_policy(RemovalPolicy.DESTROY)
        
        # Create Security Group - VPC Endpoint (Agentic App VPC)
        sg_vpc_endpoint = ec2.SecurityGroup(
            self, "endpoint-security-group",
            security_group_name="vpc-endpoint-security-group",
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
            security_groups=[sg_vpc_endpoint]
        )
        bedrock_interface_vpc_endpoint.apply_removal_policy(RemovalPolicy.DESTROY)
        
        # Create VPC Interface Endpoints for Bedrock Runtime (Agentic App VPC)
        bedrock_agent_interface_vpc_endpoint = ec2.InterfaceVpcEndpoint(self, "BedrockAgentInterfaceVpcEndpoint",
            vpc=agentic_app_vpc,
            service=ec2.InterfaceVpcEndpointService(f"com.amazonaws.{self.region}.bedrock-agent-runtime", 443),
            private_dns_enabled=True,
            security_groups=[sg_vpc_endpoint]
        )
        bedrock_agent_interface_vpc_endpoint.apply_removal_policy(RemovalPolicy.DESTROY)

        # Create VPC Interface Endpoints for ECR API (Agentic App VPC)
        ecr_api_interface_vpc_endpoint = ec2.InterfaceVpcEndpoint(self, "ecr.api",
            vpc=agentic_app_vpc,
            service=ec2.InterfaceVpcEndpointService(f"com.amazonaws.{self.region}.ecr.api", 443),
            private_dns_enabled=True,
            security_groups=[sg_vpc_endpoint]
        )
        ecr_api_interface_vpc_endpoint.apply_removal_policy(RemovalPolicy.DESTROY)

        # Create VPC Interface Endpoints for ECR DKR (Agentic App VPC)
        ecr_dkr_interface_vpc_endpoint = ec2.InterfaceVpcEndpoint(self, "ecr.dkr",
            vpc=agentic_app_vpc,
            service=ec2.InterfaceVpcEndpointService(f"com.amazonaws.{self.region}.ecr.dkr", 443),
            private_dns_enabled=True,
            security_groups=[sg_vpc_endpoint]
        )
        ecr_dkr_interface_vpc_endpoint.apply_removal_policy(RemovalPolicy.DESTROY)

         # Create VPC Interface Endpoints for Secrets Manager (Agentic App VPC)
        mcp_secretsmanager_interface_vpc_endpoint = ec2.InterfaceVpcEndpoint(self, "mcp-secretsmanager",
            vpc=agentic_app_vpc,
            service=ec2.InterfaceVpcEndpointService(f"com.amazonaws.{self.region}.secretsmanager", 443),
            private_dns_enabled=True,
            security_groups=[sg_vpc_endpoint]
        )
        mcp_secretsmanager_interface_vpc_endpoint.apply_removal_policy(RemovalPolicy.DESTROY)
        
        # Create VPC Interface Endpoints for CloudWatch Logs (Agentic App VPC)
        logs_vpc_endpoint = ec2.InterfaceVpcEndpoint(self, "CloudWatchLogs",
            vpc=agentic_app_vpc,
            service=ec2.InterfaceVpcEndpointService(f"com.amazonaws.{self.region}.logs", 443),
            private_dns_enabled=True,
            security_groups=[sg_vpc_endpoint]
        )
        logs_vpc_endpoint.apply_removal_policy(RemovalPolicy.DESTROY)
        

        # =============================================================================
        # Agentic APP-MCP INFRASTRUCTURE
        # =============================================================================

        # CloudWatch Log Group for Agentic App
        agentic_app_log_group = logs.LogGroup(
            self, "AgenticAppLogGroup",
            log_group_name=f"/ecs/agentic-app-{self.stack_name.lower()}",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY
        )
        
        agentic_app_task_role = iam.Role(
            self, "AgenticAppTaskRole",
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
                )
            }
        )

        # Load secrets from separate files
        adzuna_creds = self._load_secret_file("adzuna")
        usajobs_creds = self._load_secret_file("usajobs")
        
        # Secrets Manager - API Credentials
        adzuna_secret = secretsmanager.Secret(
            self, "AdzunaAPICredentials",
            description="Adzuna API credentials",
            secret_object_value={
                "ADZUNA_APP_ID": SecretValue.unsafe_plain_text(adzuna_creds["ADZUNA_APP_ID"]),
                "ADZUNA_APP_KEY": SecretValue.unsafe_plain_text(adzuna_creds["ADZUNA_APP_KEY"])
            }
        )
        
        usajobs_secret = secretsmanager.Secret(
            self, "USAJobsAPICredentials",
            description="USAJobs API credentials",
            secret_object_value={
                "USAJOBS_EMAIL": SecretValue.unsafe_plain_text(usajobs_creds["USAJOBS_EMAIL"]),
                "USAJOBS_API_KEY": SecretValue.unsafe_plain_text(usajobs_creds["USAJOBS_API_KEY"])
            }
        )

        # Grant read access to secrets
        adzuna_secret.grant_read(agentic_app_task_role)
        usajobs_secret.grant_read(agentic_app_task_role)

         # ECS Clusters (Agentic APP)
        agentic_app_cluster = ecs.Cluster(
            self, "AgenticAppCluster", 
            vpc=agentic_app_vpc,
            container_insights=True
        )

        # Docker Image
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
                "ADZUNA_SECRET_NAME": adzuna_secret.secret_name,
                "USAJOBS_SECRET_NAME": usajobs_secret.secret_name,
            }
        )

        # ALB
        agentic_app_alb = elbv2.ApplicationLoadBalancer(
            self, "AgenticAppALB",
            vpc=agentic_app_vpc,
            internet_facing=True
        )

        # ECS Service
        agentic_app_service = ecs.FargateService(
            self, "AgenticAppService",
            cluster=agentic_app_cluster,
            task_definition=agentic_app_task_definition,
            desired_count=2,
            assign_public_ip=True,
            min_healthy_percent=100
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
    