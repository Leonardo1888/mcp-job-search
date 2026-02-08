import asyncio
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    server_params = StdioServerParameters(
        command="python",
        args=["server.py"],
        env=None
    )
    
    # Questo cattura stderr del server
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            result = await session.call_tool(
                "extract_skills_from_cv",
                arguments={
                    "cv_filename": "cv.txt",
                    "confidence_threshold": 0.6
                }
            )
            
            print(result.content[0].text)

asyncio.run(main())