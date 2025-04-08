from aws_cdk import (
    Stack,
    CfnOutput,
    RemovalPolicy,
    Duration,
    aws_dynamodb as dynamodb,
    aws_lambda as lambda_,
    aws_apigateway as apigateway,
    aws_iam as iam,
    aws_s3 as s3,
    aws_s3_notifications as s3_notifications,
    aws_bedrock as bedrock_cdk,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_s3_deployment as s3deploy,
    custom_resources as cr,
    aws_cloudfront as cloudfront,
    aws_cognito as cognito,
    aws_logs as logs
)

from cdklabs.generative_ai_cdk_constructs import (
    bedrock,
)

from constructs import Construct
import json


class DealershipAiCdkStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        #---------------------------------------------------------------------------
        # Cognito User Pool for Authentication
        #---------------------------------------------------------------------------
        
        user_pool = cognito.UserPool(
            self, "DealershipUserPool",
            self_sign_up_enabled=True,
            auto_verify=cognito.AutoVerifiedAttrs(email=True),  
            standard_attributes=cognito.StandardAttributes(
                email=cognito.StandardAttribute(
                    required=True,
                    mutable=False
                )
            ),
            password_policy=cognito.PasswordPolicy(
                min_length=8,
                require_digits=True,
                require_lowercase=True,
                require_uppercase=True,
                require_symbols=True
            ),
            account_recovery=cognito.AccountRecovery.EMAIL_ONLY,
            removal_policy=RemovalPolicy.DESTROY  # For demo only; use RETAIN for production
        )
        
        # Create domain for the Cognito hosted UI
        domain_prefix = f"dealership-{self.account}-{self.region}"
        user_pool_domain = user_pool.add_domain(
            "DealershipDomain",
            cognito_domain=cognito.CognitoDomainOptions(
                domain_prefix=domain_prefix
            )
        )
        
        # Client for website
        website_client = user_pool.add_client(
            "WebsiteClient",
            generate_secret=True,
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(
                    authorization_code_grant=True,
                    implicit_code_grant=True
                ),
                scopes=[
                    cognito.OAuthScope.EMAIL,
                    cognito.OAuthScope.OPENID,
                    cognito.OAuthScope.PROFILE,
                    cognito.OAuthScope.COGNITO_ADMIN
                ],
                callback_urls=[
                    "http://localhost:8080/",  # Local development
                    "http://localhost:8080/callback.html",  # Local development callback
                ],
                logout_urls=[
                    "http://localhost:8080/",  # Local development
                ]
            )
        )
        
        # Identity pool for federated identities
        identity_pool = cognito.CfnIdentityPool(
            self, "DealershipIdentityPool",
            allow_unauthenticated_identities=False,
            cognito_identity_providers=[
                cognito.CfnIdentityPool.CognitoIdentityProviderProperty(
                    client_id=website_client.user_pool_client_id,
                    provider_name=user_pool.user_pool_provider_name
                )
            ]
        )
        
        # IAM roles for authenticated users
        authenticated_role = iam.Role(
            self, "AuthenticatedRole",
            assumed_by=iam.FederatedPrincipal(
                "cognito-identity.amazonaws.com",
                conditions={
                    "StringEquals": {
                        "cognito-identity.amazonaws.com:aud": identity_pool.ref
                    },
                    "ForAnyValue:StringLike": {
                        "cognito-identity.amazonaws.com:amr": "authenticated"
                    }
                },
                assume_role_action="sts:AssumeRoleWithWebIdentity"
            )
        )
        
        # Attach policies to the authenticated role
        authenticated_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "execute-api:Invoke"
                ],
                resources=["*"]  # Scope this down in production
            )
        )
        
        # Set up identity pool roles
        cognito.CfnIdentityPoolRoleAttachment(
            self, "IdentityPoolRoleAttachment",
            identity_pool_id=identity_pool.ref,
            roles={
                "authenticated": authenticated_role.role_arn
            }
        )

        #---------------------------------------------------------------------------
        # Vehicle Inventory API
        #---------------------------------------------------------------------------

        # DynamoDB Table for Car Inventory
        car_inventory_table = dynamodb.Table(
            self, "car-inventory",
            partition_key=dynamodb.Attribute(
                name="id",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # Create CloudWatch Log Group for the inventory API
        inventory_api_logs = logs.LogGroup(
            self, "CarInventoryApiLogs",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY
        )

        # Create an API Gateway account resource to set up the CloudWatch role
        api_gateway_account = apigateway.CfnAccount(
            self, "ApiGatewayAccount",
            cloud_watch_role_arn=iam.Role(
                self, "ApiGatewayLoggingRole",
                assumed_by=iam.ServicePrincipal("apigateway.amazonaws.com"),
                managed_policies=[
                    iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AmazonAPIGatewayPushToCloudWatchLogs")
                ]
            ).role_arn
        )

        # Create API Gateway with Cognito Authorizer
        api = apigateway.RestApi(
            self, "CarInventoryApi",
            rest_api_name="Car Inventory API",
            description="Car Dealership Inventory API",
            deploy_options=apigateway.StageOptions(
                stage_name="prod",
                data_trace_enabled=True,
                logging_level=apigateway.MethodLoggingLevel.INFO,
                access_log_destination=apigateway.LogGroupLogDestination(inventory_api_logs),
                access_log_format=apigateway.AccessLogFormat.json_with_standard_fields(
                    caller=True,
                    http_method=True,
                    ip=True,
                    protocol=True,
                    request_time=True,
                    resource_path=True,
                    response_length=True,
                    status=True,
                    user=True
                )
            ),
            default_cors_preflight_options=apigateway.CorsOptions(
                allow_origins=["*"],
                allow_methods=["GET"],
                allow_headers=["Content-Type", "Authorization"]
            )
        )
        

        # Lambda Functions with API Gateway Integrations
        get_cars_function = lambda_.Function(
            self, "GetCarsFunction",
            handler="get_vehicle_inventory.lambda_handler",
            runtime=lambda_.Runtime.PYTHON_3_13,
            code= lambda_.Code.from_asset("functions/"),
            environment={
                "TABLE_NAME": car_inventory_table.table_name
            }
        )
        car_inventory_table.grant_read_data(get_cars_function)
        
        # Create API Gateway resources with IAM auth
        cars_resource = api.root.add_resource("cars")
        cars_resource.add_method(
            "GET",
            apigateway.LambdaIntegration(get_cars_function),
            authorization_type=apigateway.AuthorizationType.IAM
        )
        
        car_resource = cars_resource.add_resource("{car_id}")
        car_resource.add_method(
            "GET",
            apigateway.LambdaIntegration(get_cars_function),
            authorization_type=apigateway.AuthorizationType.IAM
        )

        # Load sample data from JSON file
        with open('./inventory_seed/inventory.json', 'r') as file:
            items = json.load(file)
        
        # Create IAM policy for DynamoDB access
        policy_statement = iam.PolicyStatement(
            actions=['dynamodb:BatchWriteItem'],
            resources=[car_inventory_table.table_arn]
        )
        
        # DynamoDB BatchWriteItem can process up to 25 items at once
        # Split items into batches of 25
        batch_size = 25
        batches = [items[i:i + batch_size] for i in range(0, len(items), batch_size)]
        
        for batch_index, batch in enumerate(batches):
            # Prepare the batch write request
            request_items = {
                car_inventory_table.table_name: [
                    {
                        "PutRequest": {
                            "Item": item
                        }
                    }
                    for item in batch
                ]
            }
            
            # Create an AwsCustomResource for each batch
            cr.AwsCustomResource(
                self, f"SeedDynamoDbBatch{batch_index}",
                on_create=cr.AwsSdkCall(
                    service="DynamoDB",
                    action="batchWriteItem",
                    parameters={
                        "RequestItems": request_items
                    },
                    physical_resource_id=cr.PhysicalResourceId.of(f"batch-{batch_index}")
                ),
                policy=cr.AwsCustomResourcePolicy.from_statements([policy_statement]),
                removal_policy=RemovalPolicy.DESTROY
            )

        

    #---------------------------------------------------------------------------
    # Bedrock Knowledge Base with Opensearch serverless
    #---------------------------------------------------------------------------

        # Create an S3 bucket to store knowledge base documents
        documents_bucket = s3.Bucket(
            self, "dealership-kb-bucket",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            enforce_ssl=True,
        )

        # Deploy website content to the S3 bucket for indexing
        s3deploy.BucketDeployment(
            self, "DealerWebsiteDeploymentIndexing",
            sources=[
                s3deploy.Source.asset("./website")
                     ],
            destination_bucket=documents_bucket,
        )

        kb = bedrock.VectorKnowledgeBase(self, 'dealership-ai-knowledgebase', 
            embeddings_model= bedrock.BedrockFoundationModel.TITAN_EMBED_TEXT_V2_1024,
            instruction=  'This knowledge base contains information about the dealership, for example locations, opening times and how to book test drives.' ,
            description= 'This knowledge base contains information about the dealership, for example locations, opening times and how to book test drives.',                    
        )

        kb_data_source = kb.add_s3_data_source(
            data_source_name='car-dealership-documents',
            bucket= documents_bucket,
        )

        # Create a Lambda function to trigger knowledge base ingestion when S3 bucket content changes
        kb_ingestion_function = lambda_.Function(
            self, "KnowledgeBaseIngestionFunction",
            runtime=lambda_.Runtime.PYTHON_3_13,
            handler="kb_ingestion.lambda_handler",
            code=lambda_.Code.from_asset("functions/"),
            environment={
                "KNOWLEDGE_BASE_ID": kb.knowledge_base_id,
                "DATA_SOURCE_ID": kb_data_source.data_source_id
            },
            timeout=Duration.seconds(30)
        )
        
        # Grant the Lambda function permissions to call the Bedrock StartIngestionJob API
        kb_ingestion_function.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock:StartIngestionJob",
                    "bedrock:GetIngestionJob"
                ],
                resources=[
                    f"arn:aws:bedrock:{self.region}:{self.account}:knowledge-base/{kb.knowledge_base_id}",
                    f"arn:aws:bedrock:{self.region}:{self.account}:knowledge-base/{kb.knowledge_base_id}/data-source/{kb_data_source.data_source_id}"
                ]
            )
        )
        
        # Add S3 event notification to trigger the Lambda function when objects are created/updated/deleted
        documents_bucket.add_event_notification(
            event=s3.EventType.OBJECT_CREATED, 
            dest=s3_notifications.LambdaDestination(kb_ingestion_function)
        )
        documents_bucket.add_event_notification(
            event=s3.EventType.OBJECT_REMOVED, 
            dest=s3_notifications.LambdaDestination(kb_ingestion_function)
        )

    #---------------------------------------------------------------------------
    # Bedrock Agent
    #---------------------------------------------------------------------------
   
        test_drive_booking_table = dynamodb.Table(
            self, "test-drive-bookings",
            partition_key=dynamodb.Attribute(
                name="bookingId",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,

        )

    
        action_group_book_test_drive_function = lambda_.Function(
             self, "BookTestDrive",
             handler="book_test_drive.lambda_handler",
             runtime=lambda_.Runtime.PYTHON_3_13,
             code=lambda_.Code.from_asset("agent_functions/"),
             environment={
                 "TABLE_NAME": test_drive_booking_table.table_name
             }
         )  
        
        test_drive_booking_table.grant_read_write_data(action_group_book_test_drive_function)
         
        ag_book_test_drive = bedrock.AgentActionGroup(
                name='book_test_drive',
                description= 'Get available test drive appointments and book them.',
                executor=bedrock.ActionGroupExecutor.fromlambda_function(
                  action_group_book_test_drive_function,
                ),
                enabled= True,
                api_schema= bedrock.ApiSchema.from_local_asset("agent_action_schemas/book_test_drive.yaml")
                ) 
        

        action_group_query_inventory_function = lambda_.Function(
            self, "QueryInventory",
            handler="query_inventory.lambda_handler",
            runtime=lambda_.Runtime.PYTHON_3_13,
            code=lambda_.Code.from_asset("agent_functions/"),
            environment={
                "API_GATEWAY_URL": api.url
            }
        )

        # Grant the Lambda function permission to invoke the API using IAM auth
        # This creates the appropriate IAM policy for the Lambda execution role
        action_group_query_inventory_function.add_to_role_policy(
            iam.PolicyStatement(
                actions=["execute-api:Invoke"],
                resources=[f"arn:aws:execute-api:{self.region}:{self.account}:{api.rest_api_id}/*/{method}/{path}"
                        for method, path in [("GET", "cars"), ("GET", "cars/*")]]  # Add all paths and methods you need
            )
        )
        

        ag_query_inventory = bedrock.AgentActionGroup(
                name='query_vehicle_inventory',
                description= 'Gets vehicle details from the inventory API.',
                executor=bedrock.ActionGroupExecutor.fromlambda_function(
                  action_group_query_inventory_function,
                ),
                enabled= True,
                api_schema= bedrock.ApiSchema.from_local_asset("agent_action_schemas/query_inventory.yaml")
                ) 

        enquiries_table = dynamodb.Table(
            self, "dealership-enquiries",
            partition_key=dynamodb.Attribute(
                name="enquiryId",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
        )

              

        action_group_capture_enquiry_function = lambda_.Function(
             self, "CaptureEnquiry",
             handler="capture_enquiry.lambda_handler",
             runtime=lambda_.Runtime.PYTHON_3_13,
             code=lambda_.Code.from_asset("agent_functions/"),
             environment={
                 "TABLE_NAME": enquiries_table.table_name
             }
         )
        
        enquiries_table.grant_read_write_data(action_group_capture_enquiry_function)
        
        ag_capture_enquiry = bedrock.AgentActionGroup(
                name='capture_enquiry',
                description= 'Capture an enquiry or lead from the user for a human follow up.',
                executor=bedrock.ActionGroupExecutor.fromlambda_function(
                  action_group_capture_enquiry_function,
                ),
                enabled= True,
                function_schema=bedrock_cdk.CfnAgent.FunctionSchemaProperty(
                    functions=[bedrock_cdk.CfnAgent.FunctionProperty(
                        name="capture_enquiry_for_follow_up",

                        parameters={
                            "emailAddress": bedrock_cdk.CfnAgent.ParameterDetailProperty(
                                type="string",

                                # the properties below are optional
                                description="Users email address",
                                required=True
                            ),
                            "enquiry": bedrock_cdk.CfnAgent.ParameterDetailProperty(
                                type="string",

                                # the properties below are optional
                                description="The enquiry or lead for a human to follow up on",
                                required=True
                            )
                        }
                    )]
                )
        ) 


        action_group_get_todays_date_function = lambda_.Function(
             self, "GetTodaysDate",
             handler="get_todays_date.lambda_handler",
             runtime=lambda_.Runtime.PYTHON_3_13,
             code=lambda_.Code.from_asset("agent_functions/"),
         )
        
        ag_get_todays_date = bedrock.AgentActionGroup(
                name='get_todays_date',
                description= 'Gets the current date and time.',
                executor=bedrock.ActionGroupExecutor.fromlambda_function(
                    action_group_get_todays_date_function,
                ),
                enabled= True,
                function_schema=bedrock_cdk.CfnAgent.FunctionSchemaProperty(
                    functions=[bedrock_cdk.CfnAgent.FunctionProperty(
                        name="get_current_date"
                    )]
                ) 
        )

        orchestration = open('prompts/orchestration.txt', encoding="utf-8").read()

        agent = bedrock.Agent(
            self,
            "DealerAIAgent",
            instruction="You are an AI assistant for a car dealership website called \"AnyCompany Auto\" that sells new and used cars. You help customers find vehicles using the stock inventory, and answer questions about the vehicles. You can also answer questions about the dealership itself such as location, opening hours and booking test drives. You should capture any sales leads or enquiries for a human to follow up on where required. Do not answer questions that are not about vehicles or the car dealership. Do not recommend vehicles that are not sold by this dealership. ",
            knowledge_bases=[kb],
            user_input_enabled= True,
            should_prepare_agent=True,
            foundation_model=bedrock.BedrockFoundationModel.ANTHROPIC_CLAUDE_3_5_SONNET_V2_0,
            prompt_override_configuration= bedrock.PromptOverrideConfiguration.from_steps(
                steps=[
                    bedrock.PromptStepConfiguration(
                        step_type=bedrock.AgentStepType.ORCHESTRATION,
                        step_enabled= True,
                        custom_prompt_template= orchestration,
                        inference_config=bedrock.InferenceConfiguration(
                            temperature=0.0,
                            top_k=250,
                            top_p=1,
                            maximum_length=2048,
                            stop_sequences=['</invoke>', '</answer>', '</error>'],
                        ),
                    ),
                ]
            ),

            )
        
        agent.add_action_group(ag_book_test_drive)  
        agent.add_action_group(ag_query_inventory)   
        agent.add_action_group(ag_capture_enquiry)
        agent.add_action_group(ag_get_todays_date)

        agent_alias= bedrock.AgentAlias(self, 
                                        'PrdAlias',
                                        description='Live production alias for agent.',
                                        agent=agent)


    #---------------------------------------------------------------------------
    # Agent Invoker API
    #---------------------------------------------------------------------------

        # Create CloudWatch Log Group for the agent invoker API
        agent_api_logs = logs.LogGroup(
            self, "AgentInvokerApiLogs",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY
        )


        # Create API Gateway with Cognito Authorizer
        agent_api = apigateway.RestApi(
            self, "AgentInvokerApi",
            rest_api_name="Bedrock Agent Invoker",
            description="Car Dealership Amazon Bedrock Agent API",
            deploy_options=apigateway.StageOptions(
                stage_name="prod",
                data_trace_enabled=True,
                logging_level=apigateway.MethodLoggingLevel.INFO,
                access_log_destination=apigateway.LogGroupLogDestination(agent_api_logs),
                access_log_format=apigateway.AccessLogFormat.json_with_standard_fields(
                    caller=True,
                    http_method=True,
                    ip=True,
                    protocol=True,
                    request_time=True,
                    resource_path=True,
                    response_length=True,
                    status=True,
                    user=True
                )
            ),
            default_cors_preflight_options=apigateway.CorsOptions(
                allow_origins=["*"],
                allow_methods=["POST"],
                allow_headers=["Content-Type", "Authorization"]
            )
        )
        
        # Add Cognito authorizer to the Agent API Gateway
        agent_auth = apigateway.CognitoUserPoolsAuthorizer(
            self, "AgentInvokerApiAuthorizer",
            cognito_user_pools=[user_pool],
            identity_source="method.request.header.Authorization"
        )

        # Lambda Functions with API Gateway Integrations
        invoke_agent_function = lambda_.Function(
            self, "InvokeAgentFunction",
            handler="agent_invoker.lambda_handler",
            runtime=lambda_.Runtime.PYTHON_3_13,
            code= lambda_.Code.from_asset("functions/"),
            environment={
                "AGENT_ID": agent.agent_id,
                "AGENT_ALIAS": agent_alias.alias_id
            },
            timeout=Duration.seconds(30)
        )
        
        agent_resource = agent_api.root.add_resource("agent")
        agent_resource.add_method(
            "POST",
            apigateway.LambdaIntegration(invoke_agent_function),
            authorizer=agent_auth,
            authorization_type=apigateway.AuthorizationType.COGNITO
        )
        
        agent_alias.grant_invoke(invoke_agent_function)

    #---------------------------------------------------------------------------
    # Dealership Website
    #---------------------------------------------------------------------------
        # Create an S3 bucket to store the website content
        website_bucket = s3.Bucket(
            self, "DealershipWebsiteBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,  # For demo purposes; use RETAIN in production
            auto_delete_objects=True,  # For demo purposes; be careful in production
            encryption=s3.BucketEncryption.S3_MANAGED,
            object_ownership=s3.ObjectOwnership.BUCKET_OWNER_ENFORCED, # Recommended for OAC,
            enforce_ssl=True,
        )

        # Create an S3 bucket for CloudFront access logs
        cloudfront_logs_bucket = s3.Bucket(
            self, "CloudFrontLogsBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.DESTROY,  # For demo purposes; use RETAIN in production
            auto_delete_objects=True,  # For demo purposes; be careful in production
            object_ownership=s3.ObjectOwnership.OBJECT_WRITER,  # Enable ACLs
            access_control=s3.BucketAccessControl.LOG_DELIVERY_WRITE  # Grant log delivery write permissions
        )
        
        # Create CloudFront distribution with OAC
        distribution = cloudfront.Distribution(
            self, "DealershipWebsiteDistribution",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(
                    website_bucket,
                    origin_access_levels=[cloudfront.AccessLevel.READ]
                ),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
                origin_request_policy=cloudfront.OriginRequestPolicy.CORS_S3_ORIGIN,
            ),
            default_root_object="index.html",
            minimum_protocol_version=cloudfront.SecurityPolicyProtocol.TLS_V1_2_2021,
            enable_logging=True,  # Enable logging
            log_bucket=cloudfront_logs_bucket,  # Specify log bucket
        )

        # Update configuration for CloudFront URLs for the Cognito client
        website_client.node.default_child.add_property_override(
            "CallbackURLs", [
                f"https://{distribution.domain_name}/",
                f"https://{distribution.domain_name}/callback.html"
            ]
        )
        
        website_client.node.default_child.add_property_override(
            "LogoutURLs", [
                f"https://{distribution.domain_name}/"
            ]
        )

        # Update website config to include the API endpoint, Cognito details and auth info
        config_js_content = f"""
        window.API_ENDPOINT = "{agent_api.url}";
        window.COGNITO_USER_POOL_ID = "{user_pool.user_pool_id}";
        window.COGNITO_CLIENT_ID = "{website_client.user_pool_client_id}";
        window.COGNITO_IDENTITY_POOL_ID = "{identity_pool.ref}";
        window.COGNITO_DOMAIN = "{domain_prefix}.auth.{self.region}.amazoncognito.com";
        window.API_URL = "{api.url}";
        window.REGION = "{self.region}";
        """
        
        # Deploy website content to the S3 bucket
        s3deploy.BucketDeployment(
            self, "DealerWebsiteDeployment",
            sources=[
                s3deploy.Source.asset("./website"),
                s3deploy.Source.data("config.js", config_js_content)
                     ],
            destination_bucket=website_bucket,
        )
        
        # CloudFormation Outputs
        CfnOutput(self, 'DealershipWebsite', value=f"https://{distribution.domain_name}", description="Car Dealership Website URL")
        CfnOutput(self, 'KnowledgeBaseId', value=kb.knowledge_base_id, description="Bedrock Knowledge Base ID")
        CfnOutput(self, 'S3DataSourceId', value=kb_data_source.data_source_id, description="Bedrock Knowledge Base data source Id")
        CfnOutput(self, 'DealershipKBDocsBucket', value= documents_bucket.bucket_name, description="Bedrock Knowledge Base - Documents S3 Bucket")
        CfnOutput(self, 'InventoryApiUrl', value= api.url, description="Vehicle Inventory API URL")
        CfnOutput(self, 'AgentInvokerApiUrl', value= agent_api.url, description="Agent Invoker API URL")
