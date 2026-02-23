#!/usr/bin/env python3
import json
import boto3

with open('sample_data/supplier_data.json', 'r') as f:
    suppliers = json.load(f)

dynamodb = boto3.client('dynamodb', region_name='us-east-1')
table_name = 'blog-multi-agents-supplier-directory'

print(f"Loading {len(suppliers)} suppliers into {table_name}...")

for i in range(0, len(suppliers), 25):
    batch = suppliers[i:i+25]
    items = [{'PutRequest': {'Item': {k: {'S': str(v)} for k, v in s.items()}}} for s in batch]
    dynamodb.batch_write_item(RequestItems={table_name: items})
    print(f"Batch {i//25 + 1}: uploaded {len(batch)} suppliers")

print(f"Done. Total: {len(suppliers)} suppliers loaded.")
