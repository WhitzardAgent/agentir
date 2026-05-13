# Loss Report

Target: sharegpt  
Status: lossy

## Summary

- Records processed: 1
- Exact: 0
- Lossy: 1
- Partial: 0
- Unsupported: 0

## Losses

### warning LOWER004

Field: tool_call  
Event: evt_0002  
Message: Structured tool call was downgraded to inline text because ShareGPT has no native tool-call field.  
Suggestion: Use target `openai-tools` or `hermes-xml` when tool structure matters.
