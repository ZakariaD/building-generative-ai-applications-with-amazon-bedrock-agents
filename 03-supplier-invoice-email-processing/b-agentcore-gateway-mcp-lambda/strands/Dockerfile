FROM public.ecr.aws/docker/library/python:3.12-slim

WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8080

COPY . .

CMD ["opentelemetry-instrument", "python", "multi_agent_invoice.py"]
