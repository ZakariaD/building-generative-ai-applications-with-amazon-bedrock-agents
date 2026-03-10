for log_group in "/aws/lambda/email-multi-agents-classification" "/aws/lambda/email-multi-agents-orchestrator" "/aws/lambda/email-multi-agents-customer" "/aws/lambda/email-multi-agents-routing" "/aws/lambda/email-multi-agents-extraction"; do
  echo "Cleaning: $log_group"
  aws logs describe-log-streams --log-group-name "$log_group" --profile "YOUR_AWS_PROFILE" --query 'logStreams[*].logStreamName' --output text 2>/dev/null | tr '\t' '\n' | while read stream; do
    [ -n "$stream" ] && aws logs delete-log-stream --log-group-name "$log_group" --profile "YOUR_AWS_PROFILE" --log-stream-name "$stream" 2>/dev/null
  done
done
echo "✅ All log streams cleaned"