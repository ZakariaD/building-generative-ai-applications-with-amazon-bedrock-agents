from aws_cdk import (
    Stack, SecretValue,
    aws_ec2 as ec2,
    RemovalPolicy,
    CfnOutput,
    aws_iam as iam,
    Stack,
    aws_logs as logs,
    aws_ecs as ecs,
    aws_ecr_assets as ecr_assets,
    Fn,    
    aws_elasticloadbalancingv2 as elbv2,
    aws_secretsmanager as secretsmanager,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as cloudfront_origins,
    aws_s3 as s3
)
from constructs import Construct
import json


class BedrockMCPStack(Stack):
    # Constants
    FOUNDATION_MODEL = "us.anthropic.claude-3-7-sonnet-20250219-v1:0"  # Cross-region inference profile

    def _load_secret_file(self, service_name):
        """Load API secrets from service-specific file"""
        with open(f"secrets/{service_name}.json", 'r') as f:
            return json.load(f)    

    ### Network ###

    def create_vpc(self, project_name, vpc_name, cidr_range="10.0.0.0/16"):
        # Create VPC with two private subnets
        vpc = ec2.Vpc(self, f"{project_name}-{vpc_name}",
            ip_addresses=ec2.IpAddresses.cidr(cidr_range),
            max_azs=2
        )
        vpc.apply_removal_policy(RemovalPolicy.DESTROY)
        
        return vpc
        
    
    ### VPC Endpoints ###
    
    def create_default_vpc_endpoints(self, project_name, vpc, vpc_name):
        # Create Security Group - VPC Endpoint
        sg_vpc_endpoint = ec2.SecurityGroup(
            self, f"{project_name}-{vpc_name}-endpoint-security-group",
            security_group_name=f"{project_name}-vpc-endpoint-security-group",
            vpc=vpc,
        )
        sg_vpc_endpoint.apply_removal_policy(RemovalPolicy.DESTROY)
        sg_vpc_endpoint.add_ingress_rule(ec2.Peer.ipv4(vpc.vpc_cidr_block), connection=ec2.Port.tcp(443))
        
        # Create VPC Interface Endpoints for Bedrock Runtime
        bedrock_interface_vpc_endpoint = ec2.InterfaceVpcEndpoint(self, f"{project_name}-{vpc_name}-BedrockInterfaceVpcEndpoint",
            vpc=vpc,
            service=ec2.InterfaceVpcEndpointService(f"com.amazonaws.{self.region}.bedrock-runtime", 443),
            private_dns_enabled=True,
            security_groups=[sg_vpc_endpoint]
        )
        bedrock_interface_vpc_endpoint.apply_removal_policy(RemovalPolicy.DESTROY)
        
        # Create VPC Interface Endpoints for Bedrock Runtime
        bedrock_agent_interface_vpc_endpoint = ec2.InterfaceVpcEndpoint(self, f"{project_name}-{vpc_name}-BedrockAgentInterfaceVpcEndpoint",
            vpc=vpc,
            service=ec2.InterfaceVpcEndpointService(f"com.amazonaws.{self.region}.bedrock-agent-runtime", 443),
            private_dns_enabled=True,
            security_groups=[sg_vpc_endpoint]
        )
        bedrock_agent_interface_vpc_endpoint.apply_removal_policy(RemovalPolicy.DESTROY)

        # Create VPC Interface Endpoints for ECR API
        ecr_api_interface_vpc_endpoint = ec2.InterfaceVpcEndpoint(self, f"{project_name}-{vpc_name}-ecr.api",
            vpc=vpc,
            service=ec2.InterfaceVpcEndpointService(f"com.amazonaws.{self.region}.ecr.api", 443),
            private_dns_enabled=True,
            security_groups=[sg_vpc_endpoint]
        )
        ecr_api_interface_vpc_endpoint.apply_removal_policy(RemovalPolicy.DESTROY)

        # Create VPC Interface Endpoints for ECR DKR
        ecr_dkr_interface_vpc_endpoint = ec2.InterfaceVpcEndpoint(self, f"{project_name}-{vpc_name}-ecr.dkr",
            vpc=vpc,
            service=ec2.InterfaceVpcEndpointService(f"com.amazonaws.{self.region}.ecr.dkr", 443),
            private_dns_enabled=True,
            security_groups=[sg_vpc_endpoint]
        )
        ecr_dkr_interface_vpc_endpoint.apply_removal_policy(RemovalPolicy.DESTROY)

        # Create VPC Interface Endpoints for Cloudwatch Logs
        logs_interface_vpc_endpoint = ec2.InterfaceVpcEndpoint(self, f"{project_name}-{vpc_name}-logs",
            vpc=vpc,
            service=ec2.InterfaceVpcEndpointService(f"com.amazonaws.{self.region}.logs", 443),
            private_dns_enabled=True,
            security_groups=[sg_vpc_endpoint]
        )
        logs_interface_vpc_endpoint.apply_removal_policy(RemovalPolicy.DESTROY)
        
        # Create VPC Interface Endpoints for Secrets Manager
        secretsmanager_interface_vpc_endpoint = ec2.InterfaceVpcEndpoint(self, f"{project_name}-{vpc_name}-secretsmanager",
            vpc=vpc,
            service=ec2.InterfaceVpcEndpointService(f"com.amazonaws.{self.region}.secretsmanager", 443),
            private_dns_enabled=True,
            security_groups=[sg_vpc_endpoint]
        )
        secretsmanager_interface_vpc_endpoint.apply_removal_policy(RemovalPolicy.DESTROY)

        # Create VPC Gateway Endpoint for S3 (required for ECR image layers)
        s3_gateway_vpc_endpoint = ec2.GatewayVpcEndpoint(self, f"{project_name}-{vpc_name}-s3",
            vpc=vpc,
            service=ec2.GatewayVpcEndpointAwsService.S3
        )
        s3_gateway_vpc_endpoint.apply_removal_policy(RemovalPolicy.DESTROY)



    ### ECS Clusters ###

    def create_ecs_cluster(self, project_name, vpc, vpc_name, internet_facing):
        # Create ECS Cluster
        cluster = ecs.Cluster(self, f"{project_name}-{vpc_name}-ecs-cluster", 
            cluster_name=f"{project_name}-{vpc_name}-ecs-cluster", 
            vpc=vpc, 
            container_insights=True
        )
        cluster.apply_removal_policy(RemovalPolicy.DESTROY)
        
        
        # Create an Internet-facing Network Load Balancer
        nlb = elbv2.NetworkLoadBalancer(
            self, f"{project_name}-{vpc_name}-nlb",
            load_balancer_name=f"{project_name}-{vpc_name}-nlb",
            vpc=vpc,
            internet_facing=internet_facing,
            deletion_protection=False
        )
        nlb.apply_removal_policy(RemovalPolicy.DESTROY)
        
        return cluster, nlb

        
    ### ECS Services ###

    def create_ecs_service(self, 
                          project_name, 
                          vpc,
                          vpc_name,
                          cluster,
                          nlb,
                          service_name,                          
                          directory, 
                          source_port, 
                          target_port,
                          environ={},
                          secret_arn=None,
                          s3_bucket=None                
                          ):
        # Build Docker images and push to ECR
        image = ecr_assets.DockerImageAsset(self, 
            f"{project_name}-{vpc_name}-{service_name}", 
            directory=directory,
            platform=ecr_assets.Platform.LINUX_AMD64
        )
        
        # Create Security Group - VPC Endpoint
        service_security_group = ec2.SecurityGroup(
            self, f"{project_name}-{vpc_name}-{service_name}-security-group",
            security_group_name=f"{project_name}-{vpc_name}-{service_name}-security-group",
            vpc=vpc,
        )
        service_security_group.apply_removal_policy(RemovalPolicy.DESTROY)
        service_security_group.add_ingress_rule(ec2.Peer.ipv4(vpc.vpc_cidr_block), connection=ec2.Port.tcp(target_port))
        
        # Create Log Group for ECS Task
        service_log_group = logs.LogGroup(self, f"{project_name}-{vpc_name}-{service_name}-loggroup", 
            log_group_name=f"/aws/ecs/{project_name}-{vpc_name}-{service_name}-loggroup",
            removal_policy=RemovalPolicy.DESTROY,
        )

        # Define Task Definitions for both services
        task_definition = ecs.FargateTaskDefinition(
            self, f"{project_name}-{vpc_name}-{service_name}-taskdef",
            memory_limit_mib=8192,
            cpu=4096,
        )
        task_definition.add_to_task_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["bedrock:InvokeModel", 
                         "bedrock:InvokeModelWithResponseStream", 
                         "bedrock:CreateInferenceProfile",
                         "bedrock:GetInferenceProfile",
                         "bedrock:ListInferenceProfiles",
                         "bedrock:DeleteInferenceProfile"
                         ],
                resources=[
                    f"arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-7-sonnet-20250219-v1:0", 
                    f"arn:aws:bedrock:us-east-2::foundation-model/anthropic.claude-3-7-sonnet-20250219-v1:0", 
                    f"arn:aws:bedrock:us-west-2::foundation-model/anthropic.claude-3-7-sonnet-20250219-v1:0", 
                    f"arn:aws:bedrock:{self.region}:{self.account}:inference-profile/{self.FOUNDATION_MODEL}"
                ]
            )
        )
        if secret_arn: 
            task_definition.add_to_task_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["secretsmanager:GetSecretValue"],
                resources=[secret_arn]
            )
        )
        
        if s3_bucket:
            task_definition.add_to_task_role_policy(
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
                    resources=[f"{s3_bucket.bucket_arn}/*"]
                )
            )
            task_definition.add_to_task_role_policy(
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["s3:ListBucket"],
                    resources=[s3_bucket.bucket_arn]
                )
            )
        
        container = task_definition.add_container(
            f"{project_name}-{vpc_name}-{service_name}-container",
            image=ecs.ContainerImage.from_docker_image_asset(image),
            logging=ecs.LogDriver.aws_logs(stream_prefix=project_name, log_group=service_log_group),
            environment=environ
        )
        container.add_port_mappings(ecs.PortMapping(container_port=target_port))
        container.add_to_execution_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["logs:CreateLogGroup"],
                resources=[f"arn:aws:logs:*:{self.account}:log-group:*"]
            )
        )
        container.add_to_execution_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                resources=[f"arn:aws:logs:*:{self.account}:log-group:*:log-stream:*"]
            )
        )
        
        # Create ECS Services with Auto Scaling enabled
        service = ecs.FargateService(
            self, f"{project_name}-{vpc_name}-{service_name}-service",
            cluster=cluster,
            task_definition=task_definition,
            desired_count=1,
            min_healthy_percent=100,
            security_groups=[service_security_group],
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS)
        )
        service.auto_scale_task_count(
            min_capacity=1,
            max_capacity=5
        ).scale_on_cpu_utilization(f"{project_name}-{vpc_name}-{service_name}-service-scaling", target_utilization_percent=50)
        service.apply_removal_policy(RemovalPolicy.DESTROY)

        # Add listeners and target groups for both services
        listener = nlb.add_listener(f"{project_name}-{vpc_name}-{service_name}-listener-{source_port}", port=source_port)
        listener.add_targets(f"{project_name}-{vpc_name}-{service_name}-targetgroup-service",
                              port=target_port,
                              targets=[service])
        listener.apply_removal_policy(RemovalPolicy.DESTROY)

    ### MCP Secrets ### 

    def create_mcp_secrets(self, project_name, service_name, api_id, api_key):
        
         # Load secrets from separate files
        mcp_creds = self._load_secret_file(service_name)
        
        mcp_secret = secretsmanager.Secret(
            self, f"{project_name}-{service_name}-secrets",
            description=f"{service_name} API credentials",
            secret_object_value={
                "API_ID": SecretValue.unsafe_plain_text(mcp_creds[api_id]),
                "API_KEY": SecretValue.unsafe_plain_text(mcp_creds[api_key])
            }
        )

        mcp_secret.apply_removal_policy(RemovalPolicy.DESTROY)

        return mcp_secret


    ### Init ###

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        project_name = self.stack_name
        
        # Define MCP servers across various business domain
        mcp_servers = [
            { "name": "adzuna-mcp-server", "description": "ADZUNA JOBS API", "directory": "./mcp_servers/adzuna", "source_port": 8001, "target_port": 8000 },
            { "name": "usajobs-mcp-server", "description": "USA JOBS API", "directory": "./mcp_servers/usajobs", "source_port": 8002, "target_port": 8000 },
        ]

        mcp_server_clusters = [mcp_servers]
        
        
        # Create VPCs
        mcp_server_hub_vpc_name = "mcp-hub-vpc" 
        mcp_server_hub_vpc = self.create_vpc(project_name, mcp_server_hub_vpc_name, "10.1.0.0/16")
        agentic_app_vpc_name = "agentic-app-vpc"
        agentic_app_vpc = self.create_vpc(project_name, agentic_app_vpc_name, "10.2.0.0/16")
        
        # Create VPC Endpoints        
        self.create_default_vpc_endpoints(project_name, mcp_server_hub_vpc, mcp_server_hub_vpc_name)
        self.create_default_vpc_endpoints(project_name, agentic_app_vpc, agentic_app_vpc_name)

        # Create S3 bucket for chart storage
        charts_bucket = s3.Bucket(
            self, f"{project_name}-charts-bucket",
            bucket_name=f"{project_name.lower()}-charts-{self.account}-{self.region}",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            public_read_access=False,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL
        )
        


        # Create MCP Server Registry
        adzuna_secret = self.create_mcp_secrets(project_name, "adzuna", "ADZUNA_APP_ID", "ADZUNA_APP_KEY")
        usajobs_secret = self.create_mcp_secrets(project_name, "usajobs", "USAJOBS_EMAIL", "USAJOBS_API_KEY")

                                     
        # Create MCP Infra - Cluster + NLB        
        mcp_cluster, mcp_nlb = self.create_ecs_cluster(project_name, mcp_server_hub_vpc, mcp_server_hub_vpc_name, False) # False for non Internet facing nlb
        
        # Create App infra
        app_cluster, app_nlb = self.create_ecs_cluster(project_name, agentic_app_vpc, agentic_app_vpc_name, True)
        
        endpoint_service = ec2.VpcEndpointService(
            self, f"{project_name}-mcp-vpcendpointservice",
            vpc_endpoint_service_load_balancers=[mcp_nlb],
            acceptance_required=False,
            allowed_principals=[iam.ArnPrincipal(f"arn:aws:iam::{self.account}:root")],
        )
        
        # Create Security Group - VPC Endpoint
        sg_mcp_vpc_endpoint = ec2.SecurityGroup(
            self, f"{project_name}-{agentic_app_vpc_name}-endpoint-mcp-security-group",
            security_group_name=f"{project_name}-vpc-endpoint-mcp-security-group",
            vpc=agentic_app_vpc,
        )
        sg_mcp_vpc_endpoint.apply_removal_policy(RemovalPolicy.DESTROY)
        sg_mcp_vpc_endpoint.add_ingress_rule(ec2.Peer.ipv4(agentic_app_vpc.vpc_cidr_block), connection=ec2.Port.all_traffic())

        
        # Create Interface VPC Endpoint to access PrivateLink to NLB
        interface_endpoint = ec2.InterfaceVpcEndpoint(
            self, f"{project_name}-mcp-interfaceendpoint",
            vpc=agentic_app_vpc,
            service=ec2.InterfaceVpcEndpointService(endpoint_service.vpc_endpoint_service_name, 443),
            private_dns_enabled=False,
            security_groups=[sg_mcp_vpc_endpoint],
            subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS)
        )        
        # vpce_dns = Fn.select(0,interface_endpoint.vpc_endpoint_dns_entries)
        
        # Create MCP Servers
        for mcp_server_cluster in mcp_server_clusters:
            for mcp_server in mcp_server_cluster:
                # Select appropriate secret based on service name
                secret = adzuna_secret if "adzuna" in mcp_server["name"] else usajobs_secret
                
                env_vars = {
                    "AWS_REGION": self.region,
                    "MCP_SECRET_NAME": secret.secret_name
                }
                
                # Add S3 bucket name for Adzuna server
                if "adzuna" in mcp_server["name"]:
                    env_vars["CHARTS_BUCKET_NAME"] = charts_bucket.bucket_name
                
                s3_bucket_param = charts_bucket if "adzuna" in mcp_server["name"] else None
                
                self.create_ecs_service(
                                  project_name,
                                  mcp_server_hub_vpc,
                                  mcp_server_hub_vpc_name,
                                  mcp_cluster,
                                  mcp_nlb,
                                  mcp_server["name"],
                                  mcp_server["directory"],
                                  mcp_server["source_port"],
                                  mcp_server["target_port"],
                                  env_vars,
                                  secret.secret_arn,
                                  s3_bucket_param

                )
        
        # Create App service - streamlit
        self.create_ecs_service(
            project_name,
            agentic_app_vpc,
            agentic_app_vpc_name,
            app_cluster,
            app_nlb,
            "streamlit",
            "./streamlit",
            80,
            8501,
            {
                "BEDROCK_MODEL": self.FOUNDATION_MODEL,
                "AWS_REGION": self.region,
                "ADZUNA_MCP_ENDPOINT": f"http://{Fn.select(1, Fn.split(':', Fn.select(0, interface_endpoint.vpc_endpoint_dns_entries)))}:8001/mcp",
                "USAJOBS_MCP_ENDPOINT": f"http://{Fn.select(1, Fn.split(':', Fn.select(0, interface_endpoint.vpc_endpoint_dns_entries)))}:8002/mcp",
                "CHARTS_BUCKET_NAME": charts_bucket.bucket_name
            },
            None,
            charts_bucket
        )

        # CloudFront Distribution
        cloudfront_distribution = cloudfront.Distribution(
            self, "AgenticAppDistribution",
            comment=f"cloudfront distribution for Agentic App {self.stack_name}",
            price_class=cloudfront.PriceClass.PRICE_CLASS_100,
            default_behavior=cloudfront.BehaviorOptions(
                origin=cloudfront_origins.HttpOrigin(
                    app_nlb.load_balancer_dns_name,
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
        cloudfront_distribution.apply_removal_policy(RemovalPolicy.DESTROY)


        ### Outputs ### 

        CfnOutput(
            self, "AgenticAppURL",
            value=f"https://{cloudfront_distribution.distribution_domain_name}",
            description="Streamlit Application URL (CloudFront)"
        )
        