import os
import unittest

import anyio
from mcp.client.stdio import StdioServerParameters
from mcp import Client


class PackagedMcpProtocolTests(unittest.TestCase):
    def test_portable_executable_negotiates_the_complete_catalog(self):
        root = os.path.dirname(os.path.dirname(__file__))
        executable = os.path.join(root, "dist", "BridgeMCP.exe")
        if not os.path.isfile(executable):
            self.skipTest("Build the portable executable before packaged-protocol validation")

        async def list_tools():
            async with Client(StdioServerParameters(command=executable, args=[], cwd=root)) as client:
                return await client.list_tools()

        catalog = anyio.run(list_tools)
        tools = {tool.name: tool for tool in catalog.tools}
        self.assertEqual(len(tools), 16)
        self.assertEqual(tools["pair_chat"].input_schema["properties"]["agent"]["enum"], [
            "agent_1", "agent_2", "agent_3", "agent_4",
        ])
        self.assertTrue(tools["restart_bridge"].annotations.destructive_hint)


if __name__ == "__main__":
    unittest.main()
