from fastmcp import FastMCP

mcp = FastMCP("My MCP Server")

@mcp.tool
def greet(name: str) -> str:
	return f"Hello, i hope you are fine {name}!"

if __name__ == "__main__":
	mcp.run()
