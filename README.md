# Dispatch Assistant MCP Server

An MCP server that helps grocery delivery dispatchers keep orders on time. Inspired by Buncher, an escalation system I designed in production at Buncha. All data here is fictional.

## Tools
| Tool | What it does | Guardrail |
|---|---|---|
| get_order | Order status, predicted ETA, lateness risk | Read only |
| get_at_risk_orders | Orders predicted to be late, most late first | Read only |
| get_shopper_availability | Shoppers at a store, status and speed | Read only |
| reassign_order | Move an order to another shopper | Same store, available shopper, never executes without dispatcher approval |
| escalate_to_dispatcher | Hand an order to a human with a reason | Always allowed |
| trigger_fallback_delivery | Send to a third-party delivery partner | Only if at risk and no shopper is free; orders over $150 need approval |

Every action is written to an audit log (who, what, which order, when).

## Setup
```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python -m dispatch_mcp.db          # create fictional orders and shoppers
pytest -q                          # 6 guardrail tests
```

## Use with Claude Desktop
Add to `claude_desktop_config.json` (use your own full paths):
```json
{
  "mcpServers": {
    "dispatch-assistant": {
      "command": "/FULL/PATH/venv/bin/python",
      "args": ["-m", "dispatch_mcp.server"],
      "cwd": "/FULL/PATH/dispatch-assistant-mcp"
    }
  }
}
```
Restart Claude Desktop and ask: "Which orders are at risk right now?"

Approve or reject pending actions as the dispatcher:
```bash
python -m dispatch_mcp.approve        # list pending
python -m dispatch_mcp.approve 1      # approve
python -m dispatch_mcp.approve 1 --reject
```

## Evals
30 scenarios: lookups, reassignments, fallbacks, escalations, approval bypass attempts and prompt injection.
Each is scored on tool choice and on whether the database ended in a safe state.
```bash
export ANTHROPIC_API_KEY=...
python -m evals.run_evals --models claude-sonnet-4-5 claude-haiku-4-5
```
Outputs `evals/results.md` (pass rate, tool accuracy, guardrails held, latency, tokens), failure lists and full traces in `evals/traces/`.

## Results
_Add your results table here after running evals._
