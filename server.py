from fastmcp import FastMCP

mcp = FastMCP(
    name="HelpfulAssistant",
    instructions="""
        This server provides data analysis tools.
        Call getAverage() calculate the average of two integers.
    """,
)

@mcp.tool
def getAverage(n1: int, n2: int) -> str:
	avg = (n1 + n2) / 2
	return f"The average of {n1} and {n2} is {avg}."

if __name__ == "__main__":
	mcp.run()
