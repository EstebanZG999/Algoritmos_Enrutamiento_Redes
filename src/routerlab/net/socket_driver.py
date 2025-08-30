# Transporte TCP local
import asyncio, json
from typing import AsyncIterator, Dict, Any
from routerlab.net.transport import Transport

class SocketDriver(Transport):
    def __init__(self, node: str, port: int, names_path: str):
        self._node = node
        self._port = port
        self._names = self._load_names(names_path)
        self._queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()

    def _load_names(self, path: str) -> dict[str, str]:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data.get("type") == "names"
        return data["config"]

    def me(self) -> str:
        return self._node

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            data = await reader.readuntil(separator=b"\n")
            msg = json.loads(data.decode("utf-8").strip())
            await self._queue.put(msg)
        except asyncio.IncompleteReadError:
            pass
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def _server(self):
        server = await asyncio.start_server(self._handle_client, host="127.0.0.1", port=self._port)
        async with server:
            await server.serve_forever()

    async def run(self) -> AsyncIterator[Dict[str, Any]]:
        asyncio.create_task(self._server())
        while True:
            msg = await self._queue.get()
            yield msg

    async def send(self, to: str, message: Dict[str, Any]) -> None:
        host_port = self._names.get(to)
        if not host_port:
            return
        host, port_str = host_port.split(":")
        reader, writer = await asyncio.open_connection(host=host, port=int(port_str))
        wire = (json.dumps(message) + "\n").encode("utf-8")
        writer.write(wire)
        await writer.drain()
        writer.close()
        await writer.wait_closed()
