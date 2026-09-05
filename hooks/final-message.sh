#!/bin/sh
# post_llm_call: the reply as she will read it.
#
# Everywhere else the server can only see what the agent told it. Here it sees
# what she gets. If a dish died and this message does not say so, the debt is
# not settled - and the next turn opens with every tool that means moving on
# still refused.
set -eu
curl --silent --show-error --max-time 5 \
     --header 'Content-Type: application/json' \
     --data-binary @- \
     "${JACQUINHO_MCP:-http://jacquinho-mcp:8000}/hooks/final-message" 2>/dev/null || echo '{}'
