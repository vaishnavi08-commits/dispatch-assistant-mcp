"""MCP server exposing the dispatch tools. Run: python -m dispatch_mcp.server"""
from mcp.server.fastmcp import FastMCP
from .tools import TOOLS
from .db import DB_PATH, seed

mcp = FastMCP("dispatch-assistant")
for fn in TOOLS:
    mcp.tool()(fn)


def main():
    if not DB_PATH.exists():
        seed()
    mcp.run()


if __name__ == "__main__":
    main()
