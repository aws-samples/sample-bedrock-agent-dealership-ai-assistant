import json
import boto3
import uuid
import os
from datetime import datetime

def lambda_handler(event, context):
    agent = event['agent']
    actionGroup = event['actionGroup']
    function = event['function']
    parameters = event.get('parameters', [])

    print(event)
    
    # Extract email address and enquiry from parameters
    email_address = None
    enquiry_text = None
    
    for param in parameters:
        if param['name'] == 'emailAddress':
            email_address = param['value']
        elif param['name'] == 'enquiry':
            enquiry_text = param['value']
    
    # Write to DynamoDB if we have both required fields
    if email_address and enquiry_text:
        try:
            # Initialize DynamoDB client
            dynamodb = boto3.resource('dynamodb')
            table = dynamodb.Table(os.environ['TABLE_NAME'])
            
            # Create item to insert
            timestamp = datetime.utcnow().isoformat()
            item = {
                'enquiryId': str(uuid.uuid4()),  # Generate a unique ID for the enquiry
                'emailAddress': email_address,
                'enquiry': enquiry_text,
                'timestamp': timestamp,
                'agent': agent['name'],
                'actionGroup': actionGroup,
                'function': function
            }
            
            # Write to DynamoDB
            table.put_item(Item=item)
            
            response_message = "The enquiry has been sent successfully! Someone will be in touch within 24 hours."
        except Exception as e:
            print(f"Error writing to DynamoDB: {str(e)}")
            response_message = "We're sorry, there was an issue saving your enquiry. Please try again later."
    else:
        response_message = "Missing required information. Please provide both email address and enquiry."

    # Execute your business logic here. For more information, refer to: https://docs.aws.amazon.com/bedrock/latest/userguide/agents-lambda.html
    responseBody = {
        "TEXT": {
            "body": response_message
        }
    }

    action_response = {
        'actionGroup': actionGroup,
        'function': function,
        'functionResponse': {
            'responseBody': responseBody
        }
    }

    dummy_function_response = {'response': action_response, 'messageVersion': event['messageVersion']}
    print("Response: {}".format(dummy_function_response))

    return dummy_function_response