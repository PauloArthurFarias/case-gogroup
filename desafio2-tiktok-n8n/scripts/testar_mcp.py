"""Cliente MCP de teste: lista as ferramentas do servidor MCP do n8n e cria um post.
Uso: python scripts/testar_mcp.py ["tema"]
"""
import asyncio
import json
import sys

import mcp.client.streamable_http as sh
from mcp import ClientSession

URL = "http://localhost:5678/mcp/tiktok"
cliente_http = getattr(sh, "streamable_http_client", None) or getattr(sh, "streamablehttp_client")


async def main(tema: str) -> None:
    async with cliente_http(URL) as conn:
        leitura, escrita = conn[0], conn[1]
        async with ClientSession(leitura, escrita) as s:
            await s.initialize()
            tools = (await s.list_tools()).tools
            print("Ferramentas:", [t.name for t in tools])
            print(f"Chamando criar_post_tiktok(tema={tema!r})...")
            res = await s.call_tool("criar_post_tiktok", {"tema": tema})
            for c in res.content:
                print(getattr(c, "text", c))
            hist = await s.call_tool("historico_publicacoes", {})
            print("Histórico:", hist.content[0].text[:600] if hist.content else hist)


if __name__ == "__main__":
    if sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "golpe do boleto"))
