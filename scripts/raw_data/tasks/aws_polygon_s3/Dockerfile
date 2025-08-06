FROM python:3.12-slim

WORKDIR /app

# Copy the script
COPY process_polygon.py .

# Install dependencies
RUN pip install --no-cache-dir boto3

# Set environment variables (defaults, can be overridden in ECS task definition)
ENV POLYGON_ENDPOINT=https://files.polygon.io
ENV POLYGON_BUCKET=flatfiles
ENV TARGET_S3_BUCKET=bullseye-cap-polygon-data
ENV MAX_CHUNK_SIZE_BYTES=2147483648
ENV CHECK_INTERVAL_LINES=1000
ENV AWS_DEFAULT_REGION=us-east-1
ENV NUM_WORKERS=4  

# Command to run the script, expecting DATE and NUM_WORKERS as env vars
CMD ["sh", "-c", "python process_polygon.py --date $DATE --num-workers $NUM_WORKERS"]