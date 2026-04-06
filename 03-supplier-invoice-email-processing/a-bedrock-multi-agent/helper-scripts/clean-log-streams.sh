for log_group in "/aws/lambda/<STACK_NAME>-classification" "/aws/lambda/<STACK_NAME>-orchestrator" "/aws/lambda/<STACK_NAME>-customer" "/aws/lambda/<STACK_NAME>-routing" "/aws/lambda/<STACK_NAME>-extraction"; do
  echo "Cleaning: $log_group"
  aws logs describe-log-streams --log-group-name "$log_group" --profile "YOUR_AWS_PROFILE" --query 'logStreams[*].logStreamName' --output text 2>/dev/null | tr '\t' '\n' | while read stream; do
    [ -n "$stream" ] && aws logs delete-log-stream --log-group-name "$log_group" --profile "YOUR_AWS_PROFILE" --log-stream-name "$stream" 2>/dev/null
  done
done
echo "✅ All log streams cleaned"