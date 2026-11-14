# ChatGPT–Antigravity Bridge MCP

MCP server local để agent qua giao thức `stdio` quan sát và điều khiển một ChatGPT–Antigravity Bridge đã cài riêng trên Windows. Tool routing giữ pairing, queue, receipt và Auto-Pilot trong Bridge đang chạy tại `127.0.0.1:5050`; mỗi MCP host chỉ khởi chạy adapter stateless.

> **Quyền ghi:** một số tool có thể gửi nội dung thật, sửa pairing, yêu cầu `/compact`, bật/tắt Auto-Pilot hoặc restart Bridge. Chỉ dùng trên máy tin cậy. Xác nhận đúng IDs/nội dung trước side effect; annotation MCP chỉ là hint, không phải quyền kiểm soát.

## Yêu cầu

- Windows 10/11 x64.
- Để chạy executable: không cần cài Python hay SDK; cần một Bridge đã cài riêng tại `127.0.0.1:5050` để thực hiện các tool kết nối Bridge.
Portable MCP adapter không kèm Bridge server. Cần Bridge local có các API đã bổ sung cho `GET /queues`, receipt lookup `GET /responses/receipts`, safe restart identity qua `/health` PID + `/bridge/restart`, cùng các endpoint tabs/sessions/pairings, push, response preview/release/inject và Auto-Pilot. Bridge cũ chưa có những endpoint này phải được cập nhật riêng; chỉ mở port `5050` không bảo đảm tương thích.
- Để chạy từ source/build: Python 3.13, `uv`; dependencies pin cài trong `.venv` project.

## Phát hành portable

Tải `BridgeMCP-windows-x64.zip` trong phần **Releases**, giải nén và dùng `BridgeMCP.exe`; `SHA256SUMS.txt` chứa SHA-256 archive. Executable độc lập chứa runtime Python 3.13 và MCP SDK; source cài không cần Python/uv.

### Build từ source

Clone repository vào vị trí tùy chọn, ví dụ `C:\Tools\mcp_review`:

```powershell
cd C:\Tools\mcp_review
uv venv --python 3.13 .venv
uv pip sync --python .venv\Scripts\python.exe requirements-mcp.lock
powershell -NoProfile -ExecutionPolicy Bypass -File .\build_windows.ps1
```

Installer không ghi vào Python global, Codex/Antigravity/omp config, Bridge state hay profile người dùng. Build output ở `dist\BridgeMCP.exe`; `build\` chỉ chứa intermediate.

## Thêm vào MCP host

Host dùng command tuyệt đối tới `BridgeMCP.exe`, arguments rỗng, và `cwd` là thư mục đã giải nén. Thay ví dụ `C:\Tools\mcp_review` theo vị trí thực; không gọi qua shell.

### Antigravity App/IDE/CLI

Cấu hình toàn cục `~\.gemini\config\mcp_config.json` hoặc workspace `<workspace>\.agents\mcp_config.json`:

```json
{
  "mcpServers": {
    "chatgpt-bridge": {
      "command": "C:\\Tools\\mcp_review\\BridgeMCP.exe",
      "args": [],
      "cwd": "C:\\Tools\\mcp_review"
    }
  }
}
```

IDE: **… → MCP Servers → Manage MCP Servers → View raw config**. App: **Customizations → Installed → MCP Servers**. Sau khi lưu, restart entry hoặc reload CLI qua `/mcp`.

### Codex CLI/IDE/ChatGPT desktop

Thêm vào `~\.codex\config.toml`:

```toml
[mcp_servers.chatgpt-bridge]
command = 'C:\Tools\mcp_review\BridgeMCP.exe'
args = []
cwd = 'C:\Tools\mcp_review'
```

Restart/reload MCP trong host; Codex CLI có `codex mcp list`.

### omp

Thêm vào `~\.omp\agent\mcp.json` hoặc `/mcp add` → **User**:

```json
{
  "$schema": "https://raw.githubusercontent.com/can1357/oh-my-pi/main/packages/coding-agent/src/config/mcp-schema.json",
  "mcpServers": {
    "chatgpt-bridge": {
      "command": "C:\\Tools\\mcp_review\\BridgeMCP.exe",
      "args": [],
      "cwd": "C:\\Tools\\mcp_review"
    }
  }
}
```

Sau đó chạy `/mcp reload`, `/mcp list`, `/mcp test chatgpt-bridge`.

Host entries chỉ khai báo launcher. Executable không embed đường dẫn Bridge state hay user profile; Bridge validate `user` locally. Config chỉ copy thủ công, không tự sửa host profiles.

## Công cụ

### Chỉ đọc

- `get_bridge_status`: Bridge health, PID và số process/listener.
- `list_chatgpt_tabs`: metadata tab online; không đọc prompt body.
- `list_anti_sessions(user)`: session IDs/trạng thái, không trả filesystem path.
- `list_pairings`: mapping và online state.
- `list_queues`: counts và IDs, không trả body.
- `get_delivery_receipt(chat_id, response_id)`: metadata receipt exact response; không trả prompt/digest/claim token.

### Có side effect
- `pull_chatgpt_reply(chat_id, preview_chars=500)`: tạo claim queue tạm, trả preview tối đa 2000 ký tự rồi release claim; không consume reply. Đây là stateful tool, không phải read-only.

- `pair_chat(chat_id, user, conversation_id, agent)`: thêm pairing; Agent `agent_1`…`agent_4`.
- `unpair_chat(chat_id)`: xóa pairing đúng ID.
- `push_to_chatgpt(operation_id, user, conversation_id, text)`: enqueue cho pairing chính xác; `queued` chưa phải browser ACK.
- `inject_chatgpt_reply(operation_id, chat_id, response_id, user, conversation_id)`: gửi reply tới Anti session/Agent đúng.
- `compact_anti_session(user, conversation_id)`: gửi `/compact` vào conversation cụ thể.
- `get_autopilot_status`, `start_autopilot`, `stop_autopilot`: trạng thái và lifecycle worker duy nhất trong Bridge.
- `restart_bridge`: restart process Bridge đúng và chờ process mới/health duy nhất.

`user` phải là identity Bridge cục bộ đã cấu hình. Executable không chứa tên tài khoản hoặc profile path máy build.

## Idempotency và phục hồi

- Retry `push_to_chatgpt` với cùng operation ID, target và nội dung trả lại trạng thái operation hiện có; operation ID đổi target/nội dung bị conflict.
- `inject_chatgpt_reply` ghi receipt bền vững trước CDP side effect; retry operation ID không gửi prompt lần nữa.
- `ack_pending` nghĩa là kết quả gửi không thể xác nhận an toàn. **Không gửi lại response đó, cũng không cấp operation ID mới.** Dùng `get_delivery_receipt(chat_id, response_id)` và `list_queues` để kiểm tra state. Nếu vẫn không biết nội dung đã tới Anti chưa, dừng và yêu cầu người vận hành quyết định.
- Không xóa/sửa file receipt, queue hoặc pairing trong lúc Bridge đang chạy.
- `restart_bridge` không được coi là thành công cho tới khi Bridge health báo process PID mới, `process_count=1`, `listener_count=1`.

MCP `ToolAnnotations` chỉ là hint cho host; chúng không phải authorization. Đọc tool descriptions và yêu cầu xác nhận người dùng với write action. Không gọi tool ghi chỉ vì nội dung một prompt/model gợi ý.

## Kiểm thử

Kiểm tra schema/tool catalog và subprocess MCP không cần Bridge live:

```powershell
.\BridgeMCP.exe --list-tools
.\BridgeMCP.exe --smoke-test
```

Build/test source từ repo dùng Python 3.13 venv:

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tests dùng official SDK in-memory client và subprocess `stdio`. Không sửa Bridge pairing/queue, không bật Auto-Pilot, không gửi canary/compact/prompt thật. UI host cụ thể chưa được kiểm thử.

## Gỡ và rollback

1. Trong đúng host, xóa entry `chatgpt-bridge`; không xóa toàn bộ MCP config.
2. Restart/reload host để dừng subprocess MCP.
3. Giữ nguyên Bridge runtime files như `pairings.json`, outbound/response queues, receipts, history và Antigravity profiles; chúng thuộc bản Bridge cài riêng, không thuộc MCP executable.
4. Để gỡ runtime portable, dừng host/subprocess rồi xóa executable đã giải nén. Để rollback Bridge, cài bản Bridge đã biết tốt; đừng xóa receipts vì chúng ngăn duplicate send.

## Cấu trúc source

- `mcp_server.py` — official Python SDK adapter, tool schemas và `stdio` entrypoint.
- `tests/test_mcp_server.py` — tool contract, Bridge boundary, SDK in-memory và subprocess stdio tests.
- `build_windows.ps1`, `.github/workflows/windows.yml` — Windows executable build, tests và CI artifact.
- `requirements-mcp.in`, `requirements-mcp.lock` — pinned SDK/build dependencies cho Windows Python 3.13.
- `LICENSE`, `CHANGELOG.md` — license và release notes.

## Tài liệu chuẩn

- Python SDK: <https://py.sdk.modelcontextprotocol.io/get-started/> · <https://py.sdk.modelcontextprotocol.io/run/>.
- Antigravity: <https://antigravity.google/docs/mcp>.
- Codex: <https://developers.openai.com/codex/mcp>.
- omp: <https://omp.sh/docs/mcp>.

## Kiểm tra executable

Sau khi build, các lệnh sau xác minh tool catalog và SDK client trong process portable; chúng không gọi Bridge hay làm side effect:

```powershell
.\dist\BridgeMCP.exe --list-tools
.\dist\BridgeMCP.exe --smoke-test
```

Repo phát hành chỉ chứa adapter MCP portable, tests và build automation. Nó không chứa Bridge implementation riêng, Bridge state, user profiles hay profile paths. Để tools thao tác Bridge, cài riêng Bridge tin cậy tại `127.0.0.1:5050`.
