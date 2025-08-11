FROM python:3.12-slim

WORKDIR /app

# Copy the script
COPY process_polygon.py .

# Install dependencies
RUN pip install --no-cache-dir boto3 requests

# Set environment variables (defaults, can be overridden in Batch job)
ENV POLYGON_API_ENDPOINT=https://api.polygon.io
ENV TARGET_S3_BUCKET=bullseye-cap-polygon-data
ENV MAX_CHUNK_SIZE_BYTES=4294967296
ENV AWS_DEFAULT_REGION=us-east-1

# Command to run the script, expecting DATE and CHUNK_INDEX
CMD ["sh", "-c", "python process_polygon.py --date $DATE --chunk-index $CHUNK_INDEX"]