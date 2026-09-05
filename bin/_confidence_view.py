"""Formats the confidence log for a human watching beside the chat.

Reads the JSON lines the MCP server writes after every evidence-bearing tool
call, and prints one legible line each. Kept out of the shell script because
ANSI escapes inside nested quoting are a losing game.
"""

import json
import sys

COLOUR = {'alta': '\033[32m', 'média': '\033[33m', 'baixa': '\033[31m'}
DIM = '\033[90m'
RED = '\033[31m'
OFF = '\033[0m'

for line in sys.stdin:
    if ' ' not in line:
        continue
    try:
        entry = json.loads(line.split(' ', 1)[1])
    except (ValueError, IndexError):
        continue
    colour = COLOUR.get(entry.get('band', ''), '')
    score = entry.get('score')
    # A call that did not touch the evidence still gets a line, dimmed: seeing
    # the agent work while the score stands still is the point.
    if not entry.get('moved', True):
        print(f'{DIM}     {entry["after"]:<36} {score:.2f}{OFF}')
        sys.stdout.flush()
        continue
    # The number is for whoever is watching the run, not for Dona Maria: the
    # badge stays wordless so a heuristic is not quoted at her as a decimal.
    shown = f'{score:.2f}' if isinstance(score, (int, float)) else '  - '
    print(f'{DIM}após{OFF} {entry["after"]:<36} '
          f'{colour}{shown}{OFF}  {colour}{entry["badge"]}{OFF}')
    for issue in entry.get('blocking_issues', []):
        print(f'      {RED}! {issue}{OFF}')
    sys.stdout.flush()
