import os

import boto3

# No se ponen credenciales aquí. Boto3 las busca solo, en este orden:
#   1. Variables AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY (útil en local)
#   2. ~/.aws/credentials
#   3. El IAM Role de la instancia EC2 (lo que usamos en AWS)
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

s3_client = boto3.client("s3", region_name=AWS_REGION)
