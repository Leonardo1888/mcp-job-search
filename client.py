import asyncio
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

server_params = StdioServerParameters(
    command="python",
    args=["server.py"],
    env=None
)

async def TestExtract_skills_from_cv():
    print("Testing extract_skills_from_cv...")
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

async def TestGet_skill_details():
    print("Testing get_skill_details tool...")
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "get_skill_details",
                arguments={
                    "skill_ids": ["KS125LS6N7WP4S6SFTCK", "KSUK6OFU4EA534NO9T4D"]
                }
            )
            print(result.content[0].text)

async def TestFind_related_skills_for_cv():
    print("Testing find_related_skills_for_cv tool...")
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "find_related_skills_for_cv",
                arguments={
                    "cv_filename": "cv.txt",
                    "limit_per_skill": 5
                }
            )
            print(result.content[0].text)

async def TestAnalyze_cv_complete():
    print("Testing analyze_cv_complete tool...")
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "analyze_cv_complete",
                arguments={
                    "cv_filename": "cv.txt"
                }
            )
            print(result.content[0].text)

async def main():
    """Esegue tutti i test in sequenza"""
    try:
        #await TestExtract_skills_from_cv()
        #print("\n" + "="*50 + "\n")
        
        #await TestGet_skill_details()
        #print("\n" + "="*50 + "\n")
        
        #await TestFind_related_skills_for_cv()
        #print("\n" + "="*50 + "\n")
        
        await TestAnalyze_cv_complete()
        
    except Exception as e:
        print(f"Errore durante i test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Esegui la funzione main asincrona
    asyncio.run(main())