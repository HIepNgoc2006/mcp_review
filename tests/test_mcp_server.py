import anyio
import os
import sys
import unittest
from unittest.mock import patch
from mcp import Client

import mcp_server


class PortableMcpCatalogTests(unittest.TestCase):
    def test_portable_server_exposes_full_profile_independent_catalog(self):
        tools = {tool.name: tool for tool in mcp_server.mcp._tool_manager.list_tools()}
        self.assertEqual(set(tools), {
            "get_bridge_status", "list_chatgpt_tabs", "list_anti_sessions", "list_pairings",
            "list_queues", "pull_chatgpt_reply", "get_delivery_receipt", "pair_chat", "unpair_chat",
            "push_to_chatgpt", "inject_chatgpt_reply", "compact_anti_session", "get_autopilot_status",
            "start_autopilot", "stop_autopilot", "restart_bridge",
        })
        self.assertEqual(tools["list_anti_sessions"].parameters["properties"]["user"]["type"], "string")
        self.assertEqual(tools["pair_chat"].parameters["properties"]["agent"]["enum"], ["agent_1", "agent_2", "agent_3", "agent_4"])
        self.assertTrue(tools["restart_bridge"].annotations.destructive_hint)

    def test_portable_tools_delegate_arbitrary_configured_identity_to_bridge(self):
        with patch.object(mcp_server, "bridge_request", return_value={"status": "ok"}) as bridge:
            mcp_server.list_anti_sessions("workstation-profile")
            mcp_server.pair_chat("chat-1", "workstation-profile", "anti-1", "agent_1")
            mcp_server.compact_anti_session("workstation-profile", "anti-1")
        self.assertEqual(bridge.call_args_list[0].kwargs["query"], {"user": "workstation-profile"})
        self.assertEqual(bridge.call_args_list[1].args[1]["user"], "workstation-profile")
        self.assertEqual(bridge.call_args_list[2].args[1]["user"], "workstation-profile")

    def test_receipt_lookup_uses_exact_safe_bridge_endpoint(self):
        with patch.object(mcp_server, "bridge_request", return_value={"status": "found"}) as bridge:
            result = mcp_server.get_delivery_receipt("chat-1", "response-1")
        self.assertEqual(result, {"status": "found"})
        bridge.assert_called_once_with("/responses/receipts", query={"chat_id": "chat-1", "response_id": "response-1"})

    def test_sdk_in_memory_client_reads_bridge_status(self):
        async def exercise():
            async with Client(mcp_server.mcp) as client:
                result = await client.call_tool("get_bridge_status", {})
                import json
                return json.loads(result.content[0].text)
        health = {"status": "running", "process_count": 1, "listener_count": 1, "pid": 812}
        with patch.object(mcp_server, "bridge_request", return_value=health):
            result = anyio.run(exercise)
        self.assertEqual(result, {"status": "running", "bridge": None, "process_count": 1, "listener_count": 1, "pid": 812})


    def test_stdio_source_smoke_returns_catalog_and_safe_status(self):
        import json
        import os
        import subprocess
        import sys
        root = os.path.dirname(os.path.dirname(__file__))
        result = subprocess.run([sys.executable, "mcp_server.py", "--smoke-test"], cwd=root, capture_output=True, text=True, check=True)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["tool_count"], 16)
        self.assertEqual(payload["health"]["status"], "running")
        self.assertEqual(payload["health"]["pid"], 1)

    def test_stdio_subprocess_negotiates_full_catalog(self):
        from mcp.client.stdio import StdioServerParameters
        async def exercise():
            async with Client(StdioServerParameters(
                command=sys.executable,
                args=[os.path.join(os.path.dirname(os.path.dirname(__file__)), "mcp_server.py")],
                cwd=os.path.dirname(os.path.dirname(__file__)),
            )) as client:
                return await client.list_tools()
        tools = anyio.run(exercise)
        self.assertEqual(len(tools.tools), 16)
        self.assertIn("get_delivery_receipt", {tool.name for tool in tools.tools})

if __name__ == "__main__":
    unittest.main()
