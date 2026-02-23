for log_group in "/aws/lambda/blog-multi-agents-classification" "/aws/lambda/blog-multi-agents-orchestrator" "/aws/lambda/blog-multi-agents-customer" "/aws/lambda/blog-multi-agents-routing" "/aws/lambda/blog-multi-agents-extraction"; do
  echo "Cleaning: $log_group"
  aws logs describe-log-streams --log-group-name "$log_group" --profile "genops-profile" --query 'logStreams[*].logStreamName' --output text 2>/dev/null | tr '\t' '\n' | while read stream; do
    [ -n "$stream" ] && aws logs delete-log-stream --log-group-name "$log_group" --profile "genops-profile" --log-stream-name "$stream" 2>/dev/null
  done
done
echo "✅ All log streams cleaned"