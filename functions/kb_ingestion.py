import json
import boto3
import os
import uuid
import logging
import time

logger = logging.getLogger()
logger.setLevel(logging.INFO)

bedrock_agent = boto3.client('bedrock-agent')

def lambda_handler(event, context):
    knowledge_base_id = os.environ.get('KNOWLEDGE_BASE_ID')
    data_source_id = os.environ.get('DATA_SOURCE_ID')
    
    if not knowledge_base_id or not data_source_id:
        logger.error("Missing required environment variables: KNOWLEDGE_BASE_ID or DATA_SOURCE_ID")
        return {
            'statusCode': 500,
            'body': json.dumps('Missing required environment variables')
        }
    
    logger.info(f"Processing S3 event for knowledge base {knowledge_base_id}, data source {data_source_id}")
    logger.info(f"Event details: {json.dumps(event)}")
    
    try:
        # Wait a short time to allow multiple changes to coalesce (reduces multiple ingestion jobs)
        time.sleep(2)
        
        # Start the ingestion job
        response = bedrock_agent.start_ingestion_job(
            dataSourceId=data_source_id,
            knowledgeBaseId=knowledge_base_id,
            description=f"Auto-triggered ingestion job from S3 event at {time.strftime('%Y-%m-%d %H:%M:%S')}",
            clientToken=str(uuid.uuid4())
        )
        
        ingestion_job_id = response['ingestionJob']['ingestionJobId']
        logger.info(f"Started ingestion job with ID: {ingestion_job_id}")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Successfully initiated knowledge base ingestion',
                'ingestionJobId': ingestion_job_id
            })
        }
        
    except Exception as e:
        logger.error(f"Error starting ingestion job: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps(f'Error initiating knowledge base ingestion: {str(e)}')
        }