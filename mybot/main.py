"""
mybot 主程序

这是 ErisPulse 自动生成的主程序文件
"""
import asyncio
from ErisPulse import sdk

async def main():
    await sdk.run(keep_running=True)

if __name__ == "__main__":
    asyncio.run(main())
