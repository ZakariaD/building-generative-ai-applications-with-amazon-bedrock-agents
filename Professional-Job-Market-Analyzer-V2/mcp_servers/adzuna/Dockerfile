FROM python:3.11-slim

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Expose the port
EXPOSE 8000

# Start the MCP server
CMD ["python3.11", "index.py"]

