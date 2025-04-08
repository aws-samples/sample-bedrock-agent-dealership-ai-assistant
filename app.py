#!/usr/bin/env python3
import os

import aws_cdk as cdk

from dealership_ai_cdk.dealership_ai_cdk_stack import DealershipAiCdkStack

from cdk_nag import ( AwsSolutionsChecks, NagSuppressions )


app = cdk.App()
cdk.Aspects.of(app).add(AwsSolutionsChecks())
stack = DealershipAiCdkStack(app, "DealershipAiCdkStack",
    # If you don't specify 'env', this stack will be environment-agnostic.
    # Account/Region-dependent features and context lookups will not work,
    # but a single synthesized template can be deployed anywhere.

    # Uncomment the next line to specialize this stack for the AWS Account
    # and Region that are implied by the current CLI configuration.

    #env=cdk.Environment(account=os.getenv('CDK_DEFAULT_ACCOUNT'), region=os.getenv('CDK_DEFAULT_REGION')),

    # Uncomment the next line if you know exactly what Account and Region you
    # want to deploy the stack to. */

    env=cdk.Environment(region='us-west-2'),

    # For more information, see https://docs.aws.amazon.com/cdk/latest/guide/environments.html
    )

NagSuppressions.add_stack_suppressions(stack, [{"id":"AwsSolutions-IAM4", "reason":"AWSLambdaBasicExecutionRole used for Lambda function logging"}])
NagSuppressions.add_stack_suppressions(stack, [{"id":"AwsSolutions-IAM5", "reason":"Confirmed use of wildcard is by design or part of S3 deployment construct"}])
NagSuppressions.add_stack_suppressions(stack, [{"id":"AwsSolutions-COG3", "reason":"AdvancedSecurityMode not required for demo"}])
NagSuppressions.add_stack_suppressions(stack, [{"id":"AwsSolutions-S1", "reason":"S3 server access logs not required for demo"}])
NagSuppressions.add_stack_suppressions(stack, [{"id":"AwsSolutions-L1", "reason":"Older Lambda runtime in managed constructs"}])
NagSuppressions.add_stack_suppressions(stack, [{"id":"AwsSolutions-APIG2", "reason":"Request validation not required for demo"}])
NagSuppressions.add_stack_suppressions(stack, [{"id":"AwsSolutions-CFR4", "reason":"Using default CloudFront certificate for demo"}])
NagSuppressions.add_stack_suppressions(stack, [{"id":"AwsSolutions-COG4", "reason":"Using IAM auth for service to service API"}])

app.synth()
