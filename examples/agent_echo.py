#!/usr/bin/env python3
"""Fictional protocol demonstration only; never a real resume/search model."""
import json
import sys
request = json.load(sys.stdin)
if request.get('protocol_version') != 1 or request.get('output_schema', {}).get('properties') != {'value': {'type': 'string'}}:
    raise SystemExit('Demo supports only the documented fictional value schema.')
if request.get('task') != 'structured_inference':
    raise SystemExit('Demo has no public search capability.')
print(json.dumps({'protocol_version': 1, 'result': {'value': 'fictional example'}}))
