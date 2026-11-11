# AG-UI — Kết Nối Parlant Với Giao Diện Frontend AG-UI / CopilotKit

## Tổng quan

[AG-UI](https://docs.ag-ui.com) (Agent-User Interaction Protocol) là một giao thức mở, hướng sự kiện, kết nối giữa agent backend và frontend. Nó chuẩn hóa luồng dữ liệu mà một giao diện người dùng cần — truyền phát chat trực tiếp (streaming chat), các lệnh gọi tool, chia sẻ trạng thái và generative UI — giúp bất kỳ frontend nào tương thích với AG-UI (chẳng hạn như các component React của [CopilotKit](https://www.copilotkit.ai)) có thể giao tiếp với bất kỳ backend nào tương thích với AG-UI. Đây là mảnh ghép tương đương ở phía frontend so với MCP (giao tiếp agent-với-tool) và A2A (giao tiếp agent-với-agent).

Quy trình hoạt động: Client gửi một **`RunAgentInput`** (chứa thread id, run id, danh sách tin nhắn, trạng thái dùng chung và các frontend tools), và agent phản hồi bằng một **luồng sự kiện có định kiểu (stream of typed events)** thông qua Server-Sent Events (SSE): vòng đời lượt chạy (`RUN_STARTED`, `RUN_FINISHED`, `RUN_ERROR`), văn bản (`TEXT_MESSAGE_START` / `_CONTENT` / `_END`), gọi tool (`TOOL_CALL_START` / `_ARGS` / `_END` / `_RESULT`), trạng thái (`STATE_SNAPSHOT` / `STATE_DELTA`), và các sự kiện mở rộng (`CUSTOM`, `RAW`).

Bản thân Parlant vốn đã là một agent backend phát luồng sự kiện: một phiên hội thoại có một nhật ký sự kiện, và các client đọc nó qua SSE. Do đó, việc hỗ trợ AG-UI **không đòi hỏi** bất kỳ thay đổi nào đối với Parlant — bạn chỉ cần viết một **adapter** nhỏ gọn để chuyển đổi cấu trúc sự kiện phiên của Parlant thành sự kiện AG-UI. Parlant tiếp tục làm chủ phần *hành vi* (các quy tắc rules, tools, khớp điều kiện, tính tuân thủ); AG-UI / CopilotKit làm chủ phần *trải nghiệm UX* (hiển thị giao diện, generative UI, các components).

Tài liệu này hướng dẫn cách xây dựng adapter đó. Adapter là một dịch vụ chuyển đổi mỏng do bạn tự viết và lưu trữ trong mã nguồn của bạn, chứ không nằm trong mã nguồn của Parlant.

## Động lực thiết kế

Các đội ngũ xây dựng giải pháp trên Parlant muốn có một agent được kiểm soát chặt chẽ, tuân thủ chính sách, nhưng thường không muốn mất thời gian xây dựng giao diện chat, xử lý streaming và render generative-UI từ con số không. AG-UI là tiêu chuẩn giúp họ tận dụng các frontend sẵn có (CopilotKit và các giải pháp khác).

Sự kết hợp này mang lại sự phân chia trách nhiệm rõ ràng:

- **Parlant** quyết định *agent làm những gì* — rule nào được khớp, tool nào được chạy, agent được phép nói gì — với tất cả các bảo đảm an toàn nguyên vẹn.
- **AG-UI / CopilotKit** quyết định *giao diện trông như thế nào* — bong bóng chat trực tiếp, hiển thị thẻ widget/tool, các thành phần dựng sẵn.

Bởi vì cầu nối này chỉ là một adapter phía trên API HTTP/SSE hiện có của Parlant, nên hoàn toàn không cần can thiệp hay chỉnh sửa mã nguồn Parlant.

## Kiến trúc hệ thống

Adapter vận hành như một dịch vụ HTTP độc lập nằm giữa frontend và server Parlant thông thường:

```
CopilotKit / AG-UI client  ──POST /agui (RunAgentInput)──▶  Adapter  ──REST + SSE──▶  Parlant server
                           ◀────── AG-UI event stream ─────           ◀── session events ──
```

Adapter bao gồm ba thành phần:

1. **Translator (Bộ chuyển đổi):** Một hàm thuần túy chuyển đổi từ một sự kiện Parlant thành danh sách các sự kiện AG-UI.
2. **Source (Nguồn cấp dữ liệu):** Điều khiển phiên Parlant thông qua API HTTP/SSE và phát ra các sự kiện của lượt tương tác.
3. **Server:** Endpoint `POST /agui` đóng gói lượt chạy và truyền luồng sự kiện AG-UI đã mã hóa.

Cài đặt các thư viện cần thiết trong môi trường của adapter:

```bash
pip install ag-ui-protocol fastapi uvicorn httpx
```

## Bước 1 — Translator (Chuyển đổi sự kiện Parlant → AG-UI)

Luồng sự kiện của Parlant trả về các đối tượng JSON với `kind` (`message`/`tool`/`status`/`custom`), `source`, `id`, `trace_id` và `data`. Translator ánh xạ từng sự kiện sang các sự kiện AG-UI tương ứng.

```python
# translator.py
from __future__ import annotations

import json
from typing import Any

from ag_ui.core import (
    BaseEvent,
    CustomEvent,
    EventType,
    RunErrorEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
    ToolCallArgsEvent,
    ToolCallEndEvent,
    ToolCallResultEvent,
    ToolCallStartEvent,
)


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


class ParlantToAGUITranslator:
    """Ánh xạ các sự kiện của một lượt tương tác Parlant thành các sự kiện AG-UI."""

    def __init__(self) -> None:
        self._started: set[str] = set()
        self._emitted: dict[str, int] = {}
        self._ended: set[str] = set()
        self._seen_calls: set[str] = set()

    def translate(self, event: dict[str, Any]) -> list[BaseEvent]:
        kind, source = event.get("kind"), event.get("source")
        if kind == "message" and source == "ai_agent":
            return self._message(event)
        if kind == "tool":
            return self._tool(event)
        if kind == "status":
            return self._status(event)
        if kind == "custom":
            return [CustomEvent(type=EventType.CUSTOM, name="parlant.custom", value=event.get("data"))]
        return []  # bỏ qua các sự kiện từ khách hàng, UI hoặc nhân viên hỗ trợ

    def _message(self, event: dict[str, Any]) -> list[BaseEvent]:
        out: list[BaseEvent] = []
        mid = str(event["id"])
        data = event.get("data") or {}
        chunks = data.get("chunks")

        if mid not in self._started:
            self._started.add(mid)
            self._emitted[mid] = 0
            out.append(TextMessageStartEvent(type=EventType.TEXT_MESSAGE_START, message_id=mid, role="assistant"))

        if chunks is not None:  # chế độ streaming: danh sách các đoạn văn bản, kết thúc bằng None
            content = [c for c in chunks if c is not None]
            for delta in content[self._emitted[mid]:]:
                out.append(TextMessageContentEvent(type=EventType.TEXT_MESSAGE_CONTENT, message_id=mid, delta=delta))
            self._emitted[mid] = len(content)
            if chunks and chunks[-1] is None and mid not in self._ended:
                self._ended.add(mid)
                out.append(TextMessageEndEvent(type=EventType.TEXT_MESSAGE_END, message_id=mid))
        else:  # chế độ block: nhận toàn bộ tin nhắn cùng lúc
            message = data.get("message") or ""
            if self._emitted[mid] == 0 and message:
                out.append(TextMessageContentEvent(type=EventType.TEXT_MESSAGE_CONTENT, message_id=mid, delta=message))
                self._emitted[mid] = 1
            if mid not in self._ended:
                self._ended.add(mid)
                out.append(TextMessageEndEvent(type=EventType.TEXT_MESSAGE_END, message_id=mid))
        return out

    def _tool(self, event: dict[str, Any]) -> list[BaseEvent]:
        out: list[BaseEvent] = []
        for index, call in enumerate((event.get("data") or {}).get("tool_calls", [])):
            # Parlant không có id riêng theo từng lệnh gọi; tổng hợp id ổn định:
            call_id = f"{event['id']}:{index}"
            if call_id in self._seen_calls:
                continue
            self._seen_calls.add(call_id)
            result = call.get("result") or {}

            out.append(ToolCallStartEvent(type=EventType.TOOL_CALL_START, tool_call_id=call_id, tool_call_name=call.get("tool_id", "")))
            out.append(ToolCallArgsEvent(type=EventType.TOOL_CALL_ARGS, tool_call_id=call_id, delta=json.dumps(call.get("arguments", {}), ensure_ascii=False, sort_keys=True)))
            out.append(ToolCallEndEvent(type=EventType.TOOL_CALL_END, tool_call_id=call_id))
            out.append(ToolCallResultEvent(type=EventType.TOOL_CALL_RESULT, message_id=f"{call_id}:result", tool_call_id=call_id, content=_stringify(result.get("data"))))

            # Dữ liệu giao diện đa phương tiện (file, widget) nằm trong result.metadata
            if metadata := result.get("metadata"):
                out.append(CustomEvent(type=EventType.CUSTOM, name="parlant.tool_result_metadata", value={"tool_call_id": call_id, "metadata": metadata}))
        return out

    def _status(self, event: dict[str, Any]) -> list[BaseEvent]:
        data = event.get("data") or {}
        if data.get("status") == "error":
            return [RunErrorEvent(type=EventType.RUN_ERROR, message=_stringify(data.get("data") or data.get("message") or "error"))]
        if data.get("message"):  # thông điệp narration của agent
            return [CustomEvent(type=EventType.CUSTOM, name="parlant.status", value=data)]
        return []
```

## Bước 2 — Source (Điều khiển phiên Parlant)

Source nhận `RunAgentInput`, tạo hoặc tiếp tục session trên Parlant, gửi tin nhắn của người dùng và đọc luồng SSE:

```python
# source.py
from __future__ import annotations

import json
from typing import Any, AsyncIterator

import httpx
from ag_ui.core import RunAgentInput


def latest_user_message(run_input: RunAgentInput) -> str:
    for message in reversed(run_input.messages):
        if getattr(message, "role", None) == "user":
            content = getattr(message, "content", None)
            return content if isinstance(content, str) else str(content or "")
    return ""


class ParlantSource:
    def __init__(self, base_url: str, agent_id: str, *, customer_id: str | None = None, turn_timeout: float = 60.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._agent_id = agent_id
        self._customer_id = customer_id
        self._turn_timeout = turn_timeout
        self._sessions: dict[str, str] = {}  # Ánh xạ AG-UI threadId -> Parlant session id

    async def run(self, run_input: RunAgentInput) -> AsyncIterator[dict[str, Any]]:
        message = latest_user_message(run_input)
        async with httpx.AsyncClient(base_url=self._base_url, timeout=self._turn_timeout) as http:
            session_id = self._sessions.get(run_input.thread_id)
            if session_id is None:
                session = (await http.post(
                    "/sessions",
                    params={"allow_greeting": "false"},
                    json={"agent_id": self._agent_id, "customer_id": self._customer_id},
                )).raise_for_status().json()
                session_id = session["id"]
                self._sessions[run_input.thread_id] = session_id

            posted = (await http.post(
                f"/sessions/{session_id}/events",
                json={"kind": "message", "source": "customer", "message": message},
            )).raise_for_status().json()
            min_offset = posted["offset"] + 1

            async with http.stream(
                "GET",
                f"/sessions/{session_id}/events",
                params={"min_offset": min_offset, "sse": "true", "wait_for_data": int(self._turn_timeout)},
            ) as response:
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    event = json.loads(line[len("data:"):].strip())
                    yield event
                    # Dừng lại khi tin nhắn của agent cho lượt này đã hoàn tất
                    data = event.get("data") or {}
                    if event.get("kind") == "message" and event.get("source") == "ai_agent":
                        chunks = data.get("chunks")
                        if chunks is None or (chunks and chunks[-1] is None):
                            return
                    if event.get("kind") == "status" and data.get("status") in ("ready", "error"):
                        return
```

## Bước 3 — Server (`POST /agui`)

```python
# server.py
from __future__ import annotations

import os
from typing import AsyncIterator

from ag_ui.core import (
    EventType, RunAgentInput, RunErrorEvent, RunFinishedEvent, RunStartedEvent, StateSnapshotEvent,
)
from ag_ui.encoder import EventEncoder
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

from source import ParlantSource
from translator import ParlantToAGUITranslator

app = FastAPI(title="Parlant AG-UI adapter")

source = ParlantSource(
    base_url=os.environ.get("PARLANT_URL", "http://localhost:8800"),
    agent_id=os.environ["PARLANT_AGENT_ID"],
)


@app.post("/agui")
async def run_agent(request: Request) -> StreamingResponse:
    run_input = RunAgentInput.model_validate(await request.json())

    async def stream() -> AsyncIterator[str]:
        encoder = EventEncoder()
        translator = ParlantToAGUITranslator()

        yield encoder.encode(RunStartedEvent(type=EventType.RUN_STARTED, thread_id=run_input.thread_id, run_id=run_input.run_id))
        if run_input.state not in (None, {}):
            yield encoder.encode(StateSnapshotEvent(type=EventType.STATE_SNAPSHOT, snapshot=run_input.state))

        errored = False
        try:
            async for parlant_event in source.run(run_input):
                for ag_event in translator.translate(parlant_event):
                    yield encoder.encode(ag_event)
                    if isinstance(ag_event, RunErrorEvent):
                        errored = True
                if errored:
                    break
        except Exception as exc:
            yield encoder.encode(RunErrorEvent(type=EventType.RUN_ERROR, message=str(exc)))
            errored = True

        if not errored:
            yield encoder.encode(RunFinishedEvent(type=EventType.RUN_FINISHED, thread_id=run_input.thread_id, run_id=run_input.run_id))

    return StreamingResponse(stream(), media_type="text/event-stream")
```

Khởi chạy server adapter:

```bash
PARLANT_URL=http://localhost:8800 PARLANT_AGENT_ID=<agent_id> uvicorn server:app --port 9000
```

## Bảng ánh xạ đối chiếu giữa Parlant và AG-UI

| Parlant | AG-UI |
|---|---|
| Một lượt tương tác trong session (turn) | Một lượt chạy run (`RUN_STARTED` … `RUN_FINISHED`) |
| Session ID / `trace_id` theo lượt | `threadId` / `runId` |
| Sự kiện tin nhắn `message` của agent (streaming `chunks`) | `TEXT_MESSAGE_START` → `TEXT_MESSAGE_CONTENT`* → `TEXT_MESSAGE_END` |
| Sự kiện `tool` (`tool_calls[]`) | `TOOL_CALL_START` → `TOOL_CALL_ARGS` → `TOOL_CALL_END` → `TOOL_CALL_RESULT` |
| `result.metadata` của tool (files, widgets) | Sự kiện `CUSTOM` (`name="parlant.tool_result_metadata"`) |
| `status` = error | `RUN_ERROR` |
| `status` có thông điệp narration | Sự kiện `CUSTOM` (`name="parlant.status"`) |
| Sự kiện `custom` | Sự kiện `CUSTOM` (`name="parlant.custom"`) |
| Dữ liệu đầu vào `RunAgentInput.state` | `STATE_SNAPSHOT` (phản hồi lại lúc bắt đầu run) |
