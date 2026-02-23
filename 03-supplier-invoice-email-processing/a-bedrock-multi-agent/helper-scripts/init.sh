bash helper-scripts/clean-log-streams.sh
export AWS_PROFILE="genops-profile" && python3 helper-scripts/load_customer_data.py
aws s3 cp attachments/intent_PAY.eml s3://blog-multi-agents-s3b-195565468328/incoming/intent_PAY.eml --profile genops-profile
