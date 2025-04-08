import json
import boto3
import logging
import os
from botocore.exceptions import ClientError

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize the Bedrock Agent Runtime client
bedrock_agent_runtime = boto3.client(
    service_name='bedrock-agent-runtime'
)

def lambda_handler(event, context):
    """
    AWS Lambda handler for invoking an Amazon Bedrock Agent.
    
    :param event: Event data from API Gateway
    :param context: Lambda context
    :return: API Gateway response
    """
    logger.info(f"Received event: {json.dumps(event)}")
    
    # Set CORS headers for browser requests
    headers = {
        'Access-Control-Allow-Origin': '*',  # Replace with your website domain in production
        'Access-Control-Allow-Headers': 'Content-Type,Authorization',
        'Access-Control-Allow-Methods': 'POST,OPTIONS'
    }
    
    # Handle OPTIONS request (preflight)
    if event.get('httpMethod') == 'OPTIONS':
        logger.info("Handling OPTIONS preflight request")
        return {
            'statusCode': 200,
            'headers': headers,
            'body': json.dumps({})
        }
    
    try:
        logger.info("Processing POST request")
        
        # Check if event body exists
        if 'body' not in event:
            logger.error("Request body is missing")
            return {
                'statusCode': 400,
                'headers': headers,
                'body': json.dumps({'error': 'Request body is missing'})
            }
        
        # Log the raw body type and value
        body_type = type(event['body']).__name__
        logger.info(f"Raw body type: {body_type}")
        logger.info(f"Raw body value: {event['body']}")
        
        # Parse request body with error handling
        try:
            # If body is already a dict, use it directly, otherwise parse JSON
            if isinstance(event['body'], dict):
                body = event['body']
            else:
                body = json.loads(event['body'])
            
            logger.info(f"Parsed request body: {json.dumps(body)}")
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse request body: {str(e)}")
            
            # Get a preview of the received body if it's a string
            received_body = event['body'][:100] if isinstance(event['body'], str) else 'Not a string'
            
            return {
                'statusCode': 400,
                'headers': headers,
                'body': json.dumps({
                    'error': 'Invalid JSON in request body',
                    'details': str(e),
                    'receivedBody': received_body
                })
            }
        
        # Check if body is empty or not a dict
        if not body or not isinstance(body, dict):
            logger.error("Request body is not a valid JSON object")
            return {
                'statusCode': 400,
                'headers': headers,
                'body': json.dumps({'error': 'Request body is not a valid JSON object'})
            }
        
        # Extract and validate parameters
        prompt = body.get('prompt')
        session_id = body.get('sessionId')
        
        if not prompt:
            logger.error("Missing required parameter: prompt")
            return {
                'statusCode': 400,
                'headers': headers,
                'body': json.dumps({'error': 'Missing required parameter: prompt'})
            }
        
        if not session_id:
            logger.error("Missing required parameter: sessionId")
            return {
                'statusCode': 400,
                'headers': headers,
                'body': json.dumps({'error': 'Missing required parameter: sessionId'})
            }
        
        logger.info(f"Processing request with sessionId: {session_id}")
        logger.info(f"User prompt: \"{prompt}\"")
        
        # Agent configuration
        agent_id = os.environ['AGENT_ID']
        agent_alias_id = os.environ['AGENT_ALIAS']
        
        logger.info(f"Invoking Bedrock Agent: agentId={agent_id}, agentAliasId={agent_alias_id}")
        
        # Invoke the Bedrock Agent
        completion = invoke_agent(agent_id, agent_alias_id, session_id, prompt)
        
        # Return successful response
        logger.info("Sending successful response back to client")
        return {
            'statusCode': 200,
            'headers': headers,
            'body': json.dumps({
                'sessionId': session_id,
                'completion': completion
            })
        }
        
    except ClientError as e:
        logger.error(f"AWS service error: {str(e)}")
        return {
            'statusCode': 500,
            'headers': headers,
            'body': json.dumps({
                'error': 'Failed to invoke Bedrock Agent',
                'message': str(e)
            })
        }
    except Exception as e:
        logger.error(f"Unhandled error: {str(e)}")
        return {
            'statusCode': 500,
            'headers': headers,
            'body': json.dumps({
                'error': 'Failed to process request',
                'message': str(e)
            })
        }

def invoke_agent(agent_id, agent_alias_id, session_id, prompt):
    """
    Sends a prompt for the agent to process and respond to.
    
    :param agent_id: The unique identifier of the agent to use.
    :param agent_alias_id: The alias of the agent to use.
    :param session_id: The unique identifier of the session.
    :param prompt: The prompt that you want the Agent to complete.
    :return: Completion text from the agent.
    """
    try:
        logger.info("Sending request to Bedrock Agent")
        import time
        start_time = time.time()
        
        response = bedrock_agent_runtime.invoke_agent(
            agentId=agent_id,
            agentAliasId=agent_alias_id,
            sessionId=session_id,
            inputText=prompt
        )
        
        end_time = time.time()
        logger.info(f"Received initial response from Bedrock Agent after {(end_time - start_time) * 1000:.2f}ms")
        
        # Process streaming response
        logger.info("Processing streaming response...")
        completion = ""
        chunk_count = 0
        
        for event in response.get("completion", []):
            chunk_count += 1
            
            if "chunk" not in event:
                logger.warning(f"Received event without chunk at position {chunk_count}")
                continue
                
            chunk = event["chunk"]
            
            if "bytes" not in chunk:
                logger.warning(f"Chunk at position {chunk_count} has no bytes property")
                continue
                
            completion += chunk["bytes"].decode('utf-8')
            
            # Log every few chunks to avoid excessive logging
            if chunk_count % 5 == 0:
                logger.info(f"Processed {chunk_count} chunks so far")
        
        logger.info(f"Completed streaming response. Received {chunk_count} chunks.")
        logger.info(f"Total response length: {len(completion)} characters")
        
        # Log a preview of the response (first 100 chars)
        preview_text = completion[:100] + "..." if len(completion) > 100 else completion
        logger.info(f"Response preview: \"{preview_text}\"")
        
        return completion
        
    except ClientError as e:
        logger.error(f"Couldn't invoke agent: {str(e)}")
        raise