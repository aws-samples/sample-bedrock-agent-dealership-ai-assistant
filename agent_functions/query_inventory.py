import json
import os
import uuid
import logging
import boto3
import urllib.request
import urllib.parse
import urllib.error
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Get API Gateway URL from environment variable
API_URL = os.environ.get('API_GATEWAY_URL')
REGION = os.environ.get('AWS_REGION')  

def validate_car_id(car_id):
    """Validate if provided car_id is a valid UUID"""
    try:
        uuid_obj = uuid.UUID(car_id)
        return str(uuid_obj)
    except (ValueError, TypeError):
        return None

def call_api(path, method='GET'):
    """Make a request to the API Gateway endpoint with IAM authentication"""
    url = f"{API_URL.rstrip('/')}/{path.lstrip('/')}"
    api_path = f"/{path.lstrip('/')}"
    
    logger.info(f"Making {method} request to {url}")
    
    try:
        # Create a session with boto3
        session = boto3.Session()
        credentials = session.get_credentials()
        
        # Create a signed request
        request = AWSRequest(
            method=method,
            url=url,
            headers={
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            }
        )
        
        # Sign the request with SigV4
        SigV4Auth(credentials, 'execute-api', REGION).add_auth(request)
        
        # Convert the signed request headers to format expected by urllib
        headers = dict(request.headers)
        
        # Make the API call using urllib
        req = urllib.request.Request(
            url=request.url,
            headers=headers,
            method=request.method
        )
        
        with urllib.request.urlopen(req) as response:
            response_body = response.read().decode('utf-8')
            status_code = response.status
            
            return {
                'statusCode': status_code,
                'apiPath': api_path,
                'httpMethod': method,
                'body': json.loads(response_body) if response_body else {}
            }
            
    except urllib.error.HTTPError as e:
        error_body = {}
        try:
            error_body = json.loads(e.read().decode('utf-8'))
        except Exception as read_error:
            logger.error(f"Error parsing HTTPError response: {str(read_error)}")
            
        return {
            'statusCode': e.code,
            'apiPath': api_path,
            'httpMethod': method,
            'error': str(e),
            'message': error_body.get('message', str(e)),
            'body': error_body
        }
    except Exception as e:
        logger.error(f"Error calling API: {str(e)}")
        return {
            'statusCode': 500,
            'apiPath': api_path,
            'httpMethod': method,
            'error': str(e),
            'message': f"Error calling API: {str(e)}"
        }

def get_all_cars():
    """Retrieve all cars from inventory via API Gateway"""
    return call_api('/cars')

def get_car_by_id(car_id):
    """Retrieve a car by ID via API Gateway"""
    # Validate car_id format
    valid_car_id = validate_car_id(car_id)
    if not valid_car_id:
        return {
            'statusCode': 400,
            'apiPath': '/cars',
            'httpMethod': 'GET',
            'message': f"Invalid car ID format: {car_id}"
        }
    
    return call_api(f'/cars/{valid_car_id}')

def format_bedrock_response(result, event):
    """Format response in the structure expected by Bedrock Agent"""
    # Prepare the response body
    response_body = {}
    
    if 'body' in result:
        # If we have a successful API response
        response_body = result['body']
    elif 'message' in result:
        # If we have an error message
        response_body = {'message': result['message']}
        if 'error' in result:
            response_body['error'] = result['error']

    # Format the complete response structure for Bedrock
    return {
        "messageVersion": "1.0",
        "response": {
            "actionGroup": event['actionGroup'],
            "apiPath": event['apiPath'],
            "httpMethod": result.get('httpMethod', 'GET'),
            "httpStatusCode": result.get('statusCode', 200),
            "responseBody": {
                "application/json": {
                    "body": json.dumps(response_body)
                }
            }
        }
    }

def parse_parameters(event):
    """Parse input parameters from Bedrock Agent request"""
    try:
        # Check if parameters is a list (as in the example payload)
        if 'parameters' in event and isinstance(event['parameters'], list):
            # Convert the list of parameter objects into a dictionary
            param_dict = {}
            for param in event['parameters']:
                if 'name' in param and 'value' in param:
                    param_dict[param['name']] = param['value']
            return param_dict
        
        # Original code for dictionary-based parameters
        if 'parameters' in event and isinstance(event['parameters'], dict):
            return event['parameters']
        
        # Bedrock request body format
        if 'requestBody' in event:
            if isinstance(event['requestBody'], dict) and 'content' in event['requestBody']:
                content = event['requestBody']['content']
                if 'application/json' in content and 'properties' in content['application/json']:
                    return content['application/json']['properties']
                elif 'application/json' in content:
                    body_content = content['application/json']
                    if isinstance(body_content, dict):
                        return body_content
                    elif isinstance(body_content, str):
                        try:
                            return json.loads(body_content)
                        except Exception as e:
                            logger.error(f"Error parsing JSON body content: {str(e)}")
        
        # General fallback for various formats
        for key in ['body', 'payload']:
            if key in event:
                try:
                    body = event[key]
                    if isinstance(body, str):
                        return json.loads(body)
                    elif isinstance(body, dict):
                        return body
                except Exception as e:
                    logger.error(f"Error parsing {key} content: {str(e)}")
                    
        return {}
    except Exception as e:
        logger.error(f"Error parsing parameters: {str(e)}")
        return {}

def lambda_handler(event, context):
    """Lambda handler function for Bedrock Agent action"""
    logger.info(f"Received event: {json.dumps(event)}")
    
    try:
        # Parse parameters
        parameters = parse_parameters(event)
        logger.info(f"Parsed parameters: {json.dumps(parameters)}")
        
        # Check for car_id parameter
        car_id = parameters.get('car_id', None)
        
        # Execute appropriate action based on parameters
        if car_id:
            result = get_car_by_id(car_id)
        else:
            result = get_all_cars()
        
        # Format the response for Bedrock Agent
        response = format_bedrock_response(result, event)
        logger.info(f"Response: {json.dumps(response)}")
        return response
        
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        # Even for errors, we need to maintain the correct response structure
        error_result = {
            'statusCode': 500,
            'apiPath': '/cars',
            'httpMethod': 'GET',
            'message': f'Error processing request: {str(e)}'
        }
        return format_bedrock_response(error_result, event)