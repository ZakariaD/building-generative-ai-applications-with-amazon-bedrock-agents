bash helper-scripts/clean-log-streams.sh
export AWS_PROFILE="YOUR_AWS_PROFILE" && python3 helper-scripts/load_customer_data.py
aws s3 cp attachments/intent_PAY.eml s3://EMAIL_BUCKET_NAME/incoming/intent_PAY.eml --profile "YOUR_AWS_PROFILE"
