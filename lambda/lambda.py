import json
import os
import re
import urllib.parse
import boto3
from pypdf import PdfReader
import io

# Initialize AWS Clients
s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
comprehend = boto3.client('comprehend')

# Environment Variables
DYNAMODB_TABLE_NAME = os.environ.get('DYNAMODB_TABLE', 'ats-cv-records')

def lambda_handler(event, context):
    try:
        # 1. Parse S3 Event
        record = event['Records'][0]
        bucket_name = record['s3']['bucket']['name']
        file_key = urllib.parse.unquote_plus(record['s3']['object']['key'])
        
        cv_id = os.path.basename(file_key).split('.')[0]
        
        print(f"Processing CV file: {file_key} from bucket: {bucket_name}")
        
        # 2. Fetch PDF File from S3
        s3_response = s3_client.get_object(Bucket=bucket_name, Key=file_key)
        pdf_file_obj = s3_response['Body'].read()
        
        # Extract metadata (Job Description) if stored in S3 metadata
        job_description = s3_response.get('Metadata', {}).get('job-description', '')
        
        # 3. Extract Text from PDF using PyPDF Layer
        pdf_reader = PdfReader(io.BytesIO(pdf_file_obj))
        extracted_text = ""
        for page in pdf_reader.pages:
            page_text = page.extract_text()
            if page_text:
                extracted_text += page_text + "\n"
        
        if not extracted_text.strip():
            raise ValueError("No text could be extracted from the provided PDF.")

        # 4. Extract Entities / Key Phrases using Amazon Comprehend
        comprehend_response = comprehend.detect_key_phrases(
            Text=extracted_text[:4000],  # Comprehend byte limit handling
            LanguageCode='en'
        )
        
        cv_keywords = set(
            phrase['Text'].lower() 
            for phrase in comprehend_response.get('KeyPhrases', [])
        )

        # 5. Calculate ATS Match Score
        # Process Job Description Keywords
        jd_keywords = set(re.findall(r'\b\w+\b', job_description.lower())) if job_description else set()
        
        if jd_keywords:
            matched_keywords = cv_keywords.intersection(jd_keywords)
            missing_keywords = list(jd_keywords - cv_keywords)
            match_score = int((len(matched_keywords) / len(jd_keywords)) * 100)
        else:
            # Fallback score if no JD is passed in metadata
            missing_keywords = ["None - Perfect match"]
            match_score = 100

        # 6. Save Results into Amazon DynamoDB
        table = dynamodb.Table(DYNAMODB_TABLE_NAME)
        table.put_item(
            Item={
                'cv_id': cv_id,
                'file_name': file_key,
                'match_score': match_score,
                'missing_keywords': missing_keywords,
                'status': 'COMPLETED'
            }
        )

        print(f"Successfully analyzed CV {cv_id}. Match score: {match_score}%")

        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Analysis completed successfully',
                'cv_id': cv_id,
                'match_score': match_score,
                'missing_keywords': missing_keywords
            })
        }

    except Exception as e:
        print(f"Error processing CV: {str(e)}")
        
        # Log failure status to DynamoDB if cv_id is available
        if 'cv_id' in locals():
            table = dynamodb.Table(DYNAMODB_TABLE_NAME)
            table.put_item(
                Item={
                    'cv_id': cv_id,
                    'match_score': 0,
                    'missing_keywords': [f"Processing Failed: {str(e)}"],
                    'status': 'FAILED'
                }
            )

        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }