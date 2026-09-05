#!/bin/sh
# pre_llm_call: her message, before the model reads it.
#
# This is the only copy of what she said that the model did not write. The
# server checks quotes against it, so a confirmed answer stops being something
# the agent can assert about her and becomes something it has to have heard.
#
# Fails open on purpose: a consultation must not stop because a hook could not
# reach the server. What is lost is a verification, and the server says so.
set -eu
curl --silent --show-error --max-time 5 \
     --header 'Content-Type: application/json' \
     --data-binary @- \
     "${JACQUINHO_MCP:-http://jacquinho-mcp:8000}/hooks/her-message" 2>/dev/null || echo '{}'
