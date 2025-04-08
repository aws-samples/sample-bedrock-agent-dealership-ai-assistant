import json
import boto3
import uuid
import logging
import os
from datetime import datetime, timedelta

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['TABLE_NAME'])

# Sample availability slots (9 AM to 5 PM, every hour)
def generate_available_slots(days_ahead=7):
    available_slots = {}
    today = datetime.now()
    
    for day in range(1, days_ahead + 1):
        current_date = today + timedelta(days=day)
        date_str = current_date.strftime("%Y-%m-%d")
        available_slots[date_str] = []
        
        for hour in range(9, 17):  # 9 AM to 4 PM
            time_slot = f"{hour:02d}:00"
            available_slots[date_str].append(time_slot)
    
    return available_slots

# Mock appointments database (would be a real database in production)
AVAILABLE_APPOINTMENTS = generate_available_slots()
BOOKED_APPOINTMENTS = {}

def lambda_handler(event, context):
    """
    Lambda handler for the Amazon Bedrock agent to handle vehicle test drive bookings
    """
    try:
        logger.info(f"Event received: {json.dumps(event)}")
        
        # Extract API path from the event
        api_path = event.get('apiPath', '')
        
        # Process based on the API path
        if api_path == '/get-available-appointments':
            return get_available_appointments(event)
        elif api_path == '/book-appointment':
            return book_appointment(event)
        else:
            return {
                'messageVersion': '1.0',
                'response': {
                    'actionGroup': event.get('actionGroup', ''),
                    'apiPath': api_path,
                    'httpMethod': event.get('httpMethod', ''),
                    'httpStatusCode': 400,
                    'responseBody': {
                        'content': {
                            'application/json': {
                                'body': {
                                    'message': f'Unsupported API path: {api_path}'
                                }
                            }
                        }
                    }
                }
            }
            
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return {
            'messageVersion': '1.0',
            'response': {
                'actionGroup': event.get('actionGroup', ''),
                'apiPath': event.get('apiPath', ''),
                'httpMethod': event.get('httpMethod', ''),
                'httpStatusCode': 500,
                'responseBody': {
                    'content': {
                        'application/json': {
                            'body': {
                                'message': f'Error processing request: {str(e)}'
                            }
                        }
                    }
                }
            }
        }

def extract_parameters(event):
    """
    Extract parameters from the Bedrock agent event
    """
    parameters = {}
    
    # Extract from parameters array if present
    if 'parameters' in event and event['parameters']:
        for param in event['parameters']:
            parameters[param.get('name')] = param.get('value')
            
    # Extract from request body if present
    if 'requestBody' in event and 'content' in event['requestBody']:
        for content_type, content in event['requestBody']['content'].items():
            if 'properties' in content:
                for prop in content['properties']:
                    parameters[prop.get('name')] = prop.get('value')
                    
    return parameters

def get_available_appointments(event):
    """
    Get available appointment slots based on vehicle type and date range
    """
    parameters = extract_parameters(event)
    
    start_date = parameters.get('startDate')
    end_date = parameters.get('endDate')
    
    # Filter appointments by date if provided
    available_dates = {}
    
    for date, slots in AVAILABLE_APPOINTMENTS.items():
        if ((not start_date or date >= start_date) and 
            (not end_date or date <= end_date) and
            slots):  # Only include dates with available slots
            available_dates[date] = slots
    
    # Return the available vehicles and appointment slots
    response_body = {
        'availableAppointments': available_dates
    }
    
    return {
        'messageVersion': '1.0',
        'response': {
            'actionGroup': event.get('actionGroup', ''),
            'apiPath': event.get('apiPath', ''),
            'httpMethod': event.get('httpMethod', ''),
            'httpStatusCode': 200,
            'responseBody': {
                'content': {
                    'application/json': {
                        'body': response_body
                    }
                }
            }
        }
    }

def book_appointment(event):
    """
    Book an appointment for a test drive
    """
    parameters = extract_parameters(event)
    
    # Extract booking details
    customer_name = parameters.get('customerName')
    customer_email = parameters.get('customerEmail')
    customer_phone = parameters.get('customerPhone')
    vehicle_model = parameters.get('vehicleModel')
    appointment_date = parameters.get('appointmentDate')
    appointment_time = parameters.get('appointmentTime')
    
    # Validate required fields
    required_fields = {
        'customerName': customer_name,
        'customerEmail': customer_email,
        'customerPhone': customer_phone,
        'vehicleModel': vehicle_model,
        'appointmentDate': appointment_date,
        'appointmentTime': appointment_time
    }
    
    missing_fields = [field for field, value in required_fields.items() if not value]
    
    if missing_fields:
        return {
            'messageVersion': '1.0',
            'response': {
                'actionGroup': event.get('actionGroup', ''),
                'apiPath': event.get('apiPath', ''),
                'httpMethod': event.get('httpMethod', ''),
                'httpStatusCode': 400,
                'responseBody': {
                    'content': {
                        'application/json': {
                            'body': {
                                'message': f'Missing required fields: {", ".join(missing_fields)}'
                            }
                        }
                    }
                }
            }
        }
    
    # Check if the appointment slot is available
    if appointment_date not in AVAILABLE_APPOINTMENTS:
        return {
            'messageVersion': '1.0',
            'response': {
                'actionGroup': event.get('actionGroup', ''),
                'apiPath': event.get('apiPath', ''),
                'httpMethod': event.get('httpMethod', ''),
                'httpStatusCode': 400,
                'responseBody': {
                    'content': {
                        'application/json': {
                            'body': {
                                'message': f'No appointments available on {appointment_date}'
                            }
                        }
                    }
                }
            }
        }
    
    if appointment_time not in AVAILABLE_APPOINTMENTS[appointment_date]:
        return {
            'messageVersion': '1.0',
            'response': {
                'actionGroup': event.get('actionGroup', ''),
                'apiPath': event.get('apiPath', ''),
                'httpMethod': event.get('httpMethod', ''),
                'httpStatusCode': 400,
                'responseBody': {
                    'content': {
                        'application/json': {
                            'body': {
                                'message': f'The requested time slot {appointment_time} on {appointment_date} is not available'
                            }
                        }
                    }
                }
            }
        }
    
    # Book the appointment
    booking_id = str(uuid.uuid4())
    
    # Remove the time slot from available appointments
    AVAILABLE_APPOINTMENTS[appointment_date].remove(appointment_time)
    
    # Add to booked appointments
    if appointment_date not in BOOKED_APPOINTMENTS:
        BOOKED_APPOINTMENTS[appointment_date] = {}
        
    BOOKED_APPOINTMENTS[appointment_date][appointment_time] = {
        'bookingId': booking_id,
        'customerName': customer_name,
        'customerEmail': customer_email,
        'customerPhone': customer_phone,
        'vehicleModel': vehicle_model
    }
    
    # Create booking item for DynamoDB
    booking_item = {
        'bookingId': booking_id,
        'customerName': customer_name,
        'customerEmail': customer_email,
        'customerPhone': customer_phone,
        'vehicleModel': vehicle_model,
        'appointmentDate': appointment_date,
        'appointmentTime': appointment_time,
        'createdAt': datetime.now().isoformat(),
        'status': 'confirmed'
    }
    
    try:
        # Write to DynamoDB
        table.put_item(Item=booking_item)
        logger.info(f"Successfully wrote booking {booking_id} to DynamoDB")
    except Exception as e:
        logger.error(f"Error writing to DynamoDB: {str(e)}")
        # Note: We continue with the booking process even if DynamoDB write fails
        # In a production system, you might want to handle this differently
    
    response_body = {
        'bookingId': booking_id,
        'message': f'Test drive booked successfully for {customer_name} on {appointment_date} at {appointment_time} for {vehicle_model}',
        'bookingDetails': {
            'customer': {
                'name': customer_name,
                'email': customer_email,
                'phone': customer_phone
            },
            'appointment': {
                'date': appointment_date,
                'time': appointment_time,
                'vehicle': vehicle_model
            }
        }
    }
    
    return {
        'messageVersion': '1.0',
        'response': {
            'actionGroup': event.get('actionGroup', ''),
            'apiPath': event.get('apiPath', ''),
            'httpMethod': event.get('httpMethod', ''),
            'httpStatusCode': 200,
            'responseBody': {
                'content': {
                    'application/json': {
                        'body': response_body
                    }
                }
            }
        }
    }
