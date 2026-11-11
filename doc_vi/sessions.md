# Làm việc với các Phiên (Working with Sessions)

Một phiên (session) là một cuộc trò chuyện giữa khách hàng và một agent. Một khách hàng có thể có nhiều phiên với cùng một agent — cuộc trò chuyện hỗ trợ hôm nay và câu hỏi thanh toán tuần trước là các phiên riêng biệt, mỗi phiên có lịch sử và trạng thái riêng.

Một phiên sở hữu nhật ký sự kiện (event log), metadata, nhãn (labels), và công việc xử lý chuyển đổi các tin nhắn của khách hàng thành các phản hồi của agent.

## Mô hình tư duy (The mental model)

**Một phiên là một nhật ký sự kiện (event log).** Mọi điều diễn ra trong cuộc trò chuyện đều được ghi lại dưới dạng một sự kiện (event): tin nhắn của khách hàng, tin nhắn của agent, các lệnh gọi công cụ (tool calls), cập nhật trạng thái (status updates), và các sự kiện tùy chỉnh của ứng dụng (custom events). Các sự kiện hoạt động theo cơ chế chỉ nối thêm (append-only) và được sắp xếp theo `offset`, một số thứ tự vị trí tăng dần thêm một với mỗi sự kiện. Các client đọc cuộc hội thoại bằng cách liên tục tải các sự kiện từ offset đã biết gần nhất trở đi.

**Một lượt (turn) là một nhóm các sự kiện.** Khi khách hàng gửi một tin nhắn, Parlant xử lý nó và phản hồi. Mọi thứ được tạo ra trong quá trình đó — tin nhắn của khách hàng, các cập nhật trạng thái, các lệnh gọi công cụ, và câu trả lời của agent — đều chia sẻ chung một `trace_id`. ID đó là cách bạn kết nối một tin nhắn của agent với các lệnh gọi công cụ đứng đằng sau nó.

**Một phiên có một chế độ (mode).** Ở chế độ `auto` (mặc định), Parlant tự động phản hồi mỗi khi có tin nhắn mới của khách hàng. Ở chế độ `manual`, nó giữ im lặng — các tin nhắn vẫn được ghi lại, nhưng không có phản hồi nào của agent được sinh ra. Chế độ manual là nền tảng cho việc chuyển giao cho con người (human handoff).

**Một phiên mang theo trạng thái ứng dụng.** `metadata` chứa JSON cho ứng dụng của bạn (ID phiếu hỗ trợ CRM, gợi ý định tuyến). `labels` là các thẻ dạng tập hợp (set-like tags) dùng để lọc và phân tích dữ liệu — chúng giúp bạn có thể truy vấn các phiên dựa trên những gì đang diễn ra bên trong chúng.

Có hai cách để làm việc với các session:

- **Python SDK**, trong ngữ cảnh agent/server, khi mã của bạn chạy bên trong ứng dụng Parlant — trong một công cụ, một hook, hoặc một callback khác của engine.
- **HTTP API**, khi frontend, dịch vụ backend khác, hoặc tích hợp bên ngoài làm việc với các session từ xa.

## Python SDK

### Lấy phiên hiện tại (Get the Current Session)

Bên trong một công cụ hoặc engine callback, hãy truy cập session cho tương tác đang hoạt động bằng `Session.current`:

```python
import parlant.sdk as p

session = p.Session.current
```

`Session.current` có phạm vi gắn liền với tác vụ asyncio đang hoạt động. Việc truy cập nó bên ngoài công cụ hoặc engine callback sẽ làm phát sinh `RuntimeError`. Trong mã ứng dụng đã có sẵn ID của session, hãy lấy session thông qua server:

```python
session = await server.get_session(id=session_id)
```

Một session cung cấp các thuộc tính `id`, `interaction`, `customer`, `agent`, `mode`, `title`, `metadata`, `labels`, và `usage`. Bạn có thể cập nhật các thuộc tính cốt lõi và metadata của nó một cách bất đồng bộ:

```python
# Khi chuyển cấp: tạm dừng phiên và ghi lại lý do
await session.update(mode="manual", title=f"Transferred — {session.title}")
await session.metadata.set("handoff_reason", "billing")

# Sau đó, khi vấn đề đã được giải quyết: bàn giao phiên lại cho agent
await session.update(mode="auto")
await session.metadata.delete("handoff_reason")
```

Đọc lại metadata tại bất kỳ nơi nào bạn cần — ví dụ, trong backend của bảng điều khiển người vận hành (operator dashboard):

```python
reason = await session.metadata.get("handoff_reason")
```

**LƯU Ý:** Sử dụng `metadata.get()` khi bạn cần đọc dữ liệu được làm mới trực tiếp từ session store. Việc đọc trực tiếp như `session.metadata["handoff_reason"]` sử dụng khung nhìn cục bộ hiện tại của đối tượng SDK, thường là bản snapshot được chụp tại thời điểm bắt đầu lượt hội thoại.

### Nhãn của phiên (Session Labels)

Một nhãn (label) là một thẻ gắn trên session. Các nhãn tồn tại để trả lời một câu hỏi thực tế: khi bạn vận hành hàng nghìn cuộc hội thoại trực tiếp, làm thế nào để bạn tìm thấy những cuộc hội thoại cần chú ý ngay lúc này? Ví dụ: các phiên cần con người can thiệp, các phiên có chạm đến vấn đề giá cả, hoặc các phiên đến từ một chiến dịch bạn vừa triển khai ngày hôm qua.

Các nhãn giúp các phiên có thể truy vấn được dựa trên những gì đang diễn ra bên trong chúng. Mỗi nhãn trở thành một bộ lọc trên danh sách session (`GET /sessions?labels=needs-human`) và một điểm móc nối cho các thao tác hàng loạt. Điều này hỗ trợ một số nhu cầu phổ biến:

- **Định tuyến và hàng đợi (Routing and queues).** Một công cụ thêm nhãn `needs-human`, và dashboard của người vận hành hiển thị các session khớp với nhãn đó.
- **Phân khúc và phân tích (Segmentation and analytics).** Đếm các session được gắn nhãn `pricing` hoặc `refund-request` là bạn đã có báo cáo chủ đề trực tiếp mà không cần một pipeline phân loại riêng biệt.
- **Quản lý vòng đời (Lifecycle management).** Lưu trữ (archive), xuất dữ liệu, hoặc xóa hàng loạt các session theo nhãn thay vì tự theo dõi các ID.

Các quy tắc (rules) cũng có thể áp dụng các nhãn một cách tự động (xem bên dưới). Khi agent nhận ra một tình huống trong quá trình lập luận thông thường, nó sẽ gắn nhãn phù hợp cho session. Bạn không cần một bước phân loại riêng.

Labels hoạt động như một tập hợp (set): một session hoặc là mang một nhãn hoặc là không, và việc thêm một nhãn hai lần là thao tác vô hại (no-op). Sử dụng `metadata` cho các giá trị theo từng session mà bạn đọc từng session một; sử dụng `labels` cho các đặc điểm bạn muốn truy vấn trên phạm vi nhiều session.

Hãy cẩn thận đừng thêm quá nhiều nhãn. Bởi vì các nhãn cung cấp dữ liệu cho phần phân tích của bạn, mỗi nhãn bạn thêm vào là thêm một dòng trong mọi báo cáo và thêm một bộ lọc cần bận tâm. Một vài nhãn mà bạn thực sự hành động dựa trên chúng sẽ hữu ích hơn hàng chục nhãn mà không ai truy vấn tới. Đừng thêm nhãn theo mặc định "để phòng hờ". Chỉ thêm nhãn khi bạn có kế hoạch rõ ràng để xem nó trong các báo cáo phân tích hoặc hành động dựa trên nó.

### Quản lý nhãn từ một công cụ (Manage Labels from a Tool)

Các thao tác đọc là đồng bộ, trong khi các thay đổi là bất đồng bộ và được lưu trữ bền vững ngay lập tức:

```python
import parlant.sdk as p


@p.tool
async def transfer_to_human(reason: str) -> p.ToolResult:
    session = p.Session.current

    await session.metadata.set("handoff_reason", reason)
    await session.labels.add("needs-human")

    return p.ToolResult(
        data=(
            "Transfer requested. Let the customer know a human agent "
            "will pick the conversation up shortly."
        ),
        control={"mode": "manual"},
    )
```

Mỗi phần của công cụ này thực hiện một nhiệm vụ riêng biệt. Nhãn `needs-human` đưa session vào hàng đợi của nhân viên vận hành — dashboard chính là truy vấn cho nhãn đó. Metadata ghi lại *lý do*, dành cho nhân viên tiếp nhận phiên. `data` cho agent biết cần nói gì trong phản hồi của nó. Và `control={"mode": "manual"}` tạm dừng phiên sau khi phản hồi đó được gửi đi, để agent dừng trả lời cho đến khi một con người bàn giao phiên trở lại.

Sử dụng `label in session.labels` để kiểm tra sự tồn tại và lặp qua `session.labels` để đọc các nhãn hiện tại. `Session.update()` không nhận labels; thay vào đó hãy sử dụng `session.labels.add()` và `session.labels.remove()`.

### Áp dụng nhãn từ các Observation và Policy khớp điều kiện

Các nhãn cũng có thể được gắn một cách khai báo vào các observations và policies. Khi Parlant xác nhận rằng một observation hoặc policy có gắn nhãn khớp với một lượt hội thoại, nó sẽ thêm các nhãn đó vào session:

```python
await agent.create_observation(
    condition="The customer is asking about pricing",
    labels=["pricing-interest"],  # bộ phận kinh doanh muốn đếm các phiên này
)

await agent.create_policy(
    title="High-value refund review",
    content=(
        "When the customer requests a refund above $500, don't process it. "
        "Tell them it needs a manager's review and they'll hear back within "
        "one business day."
    ),
    labels=["manager-review"],  # hàng đợi của quản lý: các phiên chờ xét duyệt
)
```

Các nhãn được thêm vào khi có kết quả khớp đã được xác nhận, chứ không chỉ đơn thuần vì một quy tắc được gợi nhớ như một ứng viên. Chúng tích lũy trong suốt phiên, và Parlant không tự động gỡ bỏ chúng khi observation hoặc policy không còn khớp nữa. Hãy xóa các nhãn tạm thời một cách tường minh từ một công cụ hoặc thông qua HTTP API.

### Xếp hàng một phản hồi chạy nền (Queue a Background Follow-Up)

Sử dụng `Agent.queue_response()` khi công việc chạy nền cần dẫn đến một câu trả lời có thể kết hợp với các kết quả khác hoặc một lượt hội thoại mới hơn của khách hàng. Trước tiên, hãy lưu kết quả đã hoàn thành, sau đó yêu cầu phản hồi:

```python
await session.emit_tool_result(my_tool, result)
await agent.queue_response(session)
```

Khi khởi chạy công việc từ một công cụ hoặc hook, hãy đăng ký coroutine chưa khởi chạy của nó để Parlant biết câu trả lời bị hoãn cần phải chờ đợi điều gì:

```python
session = p.Session.current
agent = p.Agent.current

async def complete_lookup() -> None:
    result = await lookup_in_background()
    await session.emit_tool_result(my_tool, result)

await agent.queue_response(session, after=complete_lookup())
```

Lệnh await ghi nhận việc lập lịch, không phải là việc gửi phản hồi. Coroutine bắt đầu sau khi đăng ký và kế thừa `Session.current` cùng `Agent.current`. Việc gián đoạn lượt hội thoại ban đầu của khách hàng không làm hủy bỏ công việc đã đăng ký. Chỉ câu trả lời bị hoãn mới chờ đợi các tác vụ đã đăng ký; các lượt hội thoại thông thường của khách hàng vẫn duy trì tính phản hồi nhanh. Các tác vụ chưa đăng ký sẽ không hiển thị đối với cơ chế gộp lô (batching). Một tác vụ phát sinh ngoại lệ sẽ được ghi log và loại khỏi lô, không có cơ chế thử lại hoặc câu trả lời tự bịa ra. Hãy bắt các lỗi dự kiến và lưu kết quả lỗi nếu khách hàng cần một lời giải thích.

**Nếu một phản hồi đang trong quá trình xử lý:** nó có thể đáp ứng các yêu cầu đã xếp hàng cho thông tin được đưa vào trong lịch sử đã tải của nó. Các kết quả mới có thể làm mới một phản hồi chưa được xuất bản. Một khi văn bản đã hiển thị, nó sẽ được giữ nguyên; các kết quả chưa được bao hàm sẽ tạo ra một phần tiếp nối tự động trừ khi một lượt mới của khách hàng kết hợp chúng vào trước. Ba yêu cầu được đưa ra trước ranh giới đó sẽ kết hợp thành một phản hồi đang chờ xử lý, chứ không phải mỗi người gọi một phản hồi. Cơ chế này không thể kết hợp công việc chưa được đăng ký.

Việc xóa hoặc cắt bớt lịch sử sẽ loại bỏ các yêu cầu đầu vào đã xếp hàng nhưng đã lỗi thời; các kết quả còn lại vẫn có thể được trả lời. Điều này không hoàn tác các công việc bên ngoài đã bắt đầu. Nếu một tin nhắn mới của khách hàng làm gián đoạn một phản hồi streaming, tiền tố đã được lưu trước đó vẫn giữ nguyên và luồng của nó bị chấm dứt mà không thêm văn bản chưa xuất bản.

Các phản hồi chỉ chạy nền sử dụng responder mà không thực hiện matching hoặc gọi công cụ mới. Chế độ manual sẽ triệt tiêu chúng, bao gồm cả việc chuyển giao xảy ra trong quá trình sinh phản hồi. Việc dừng phản hồi đang hoạt động trong hàng đợi thông qua API hủy cũng sẽ hủy các tác vụ và yêu cầu cục bộ còn lại của nó. `utter(rules=...)` vẫn là thao tác cho một phản hồi được tạo ngay lập tức, độc lập, không có hành vi kết hợp (coalescing) này.

**Giới hạn triển khai:** hàng đợi và các coroutine đã đăng ký nằm trong tiến trình server. Hãy sử dụng tính bám dính định tuyến (routing affinity) cho một session. Lưu lượng truy cập bị phân chia trên các pods vẫn có thể tạo ra các phản hồi cạnh tranh nhau, và việc khởi động lại sẽ làm mất các yêu cầu đang chờ xử lý cùng các tác vụ chưa hoàn thành. Các kết quả công cụ và chi phí đã hoàn thành vẫn được lưu trữ bền vững; không có cơ chế phát lại hoặc phục hồi tự động. Xếp hàng là một API SDK trong nội bộ tiến trình, không phải là một endpoint HTTP mới.

Mỗi câu trả lời được sinh ra sẽ có bản ghi dấu vết (trace) và mức sử dụng (usage) riêng. Một câu trả lời kết hợp sử dụng lượt bắt nguồn của yêu cầu đang chờ xử lý mới nhất khi quá trình sinh bắt đầu; các kết quả công cụ đóng góp giữ nguyên sự quy kết ban đầu của chúng. Một lượt khách hàng đáp ứng yêu cầu sẽ sở hữu mức sử dụng phản hồi thông thường của nó. Chi phí không bao giờ bị sao chép vào từng tác vụ đóng góp. Xem [Báo cáo mức sử dụng (Usage Reports)](usage-reports.md#what-gets-recorded).

## HTTP API

API phiên làm việc tập trung vào hai tài nguyên:

| Tài nguyên | Mục đích |
|---|---|
| `/sessions` | Tạo, liệt kê, cập nhật, và xóa các phiên hội thoại. |
| `/sessions/{session_id}/events` | Thêm nối tiếp, streaming, đọc, cập nhật, và xóa các sự kiện bên trong một phiên. |

Các ví dụ dưới đây giả định rằng `$PARLANT_URL` trỏ tới server của bạn và mọi header `Authorization` cần thiết đã được thiết lập.

### Cách xác thực áp dụng cho các phiên (How Auth Applies to Sessions)

Mỗi request đều phân giải thành một trong bốn loại người gọi, và session là nơi thể hiện sự khác biệt rõ nhất. Tóm lại:

- **Admin** (static API key): toàn quyền truy cập — bất kỳ phiên nào, bất kỳ thao tác nào.
- **Customer** (một JWT mà backend của *bạn* phát hành): phạm vi giới hạn trong các phiên của chính họ. `customer_id` của phiên được lấy từ token, không tin cậy từ request body — một khách hàng không thể tạo hoặc đọc phiên của bất kỳ ai khác.
- **Guest** (một guest token do Parlant phát hành): khi một trình duyệt ẩn danh tạo một phiên, Parlant trả về một guest token trong response header `X-Parlant-Guest-Token`. Token đó sở hữu các phiên mà nó đã tạo — một guest không bao giờ có thể đọc cuộc trò chuyện của một guest khác. Một guest quay lại có thể nhận được token gia hạn cho cùng một định danh trong header đó trên bất kỳ phản hồi nào sau đó; hãy lưu trữ nó thay thế cho token cũ.
- **Anonymous** (không có token): chỉ có thể bắt đầu một cuộc hội thoại guest, và không làm được gì khác. Việc biết ID của một phiên không mang lại quyền truy cập vào phiên đó.

Quyền sở hữu được thực thi trên mọi endpoint session và event: customer và guest chỉ có thể liệt kê, đọc và gửi bài vào các phiên của chính họ. Hai trường sự kiện ngoài ra còn **bị thu gọn (redacted) đối với người gọi không phải admin**: lập luận nội bộ của agent trên các status events, và dữ liệu thô `result.data` trên các tool events. Các sự kiện vẫn đến nơi — trường bị ẩn được thay thế bằng `{"redacted": true}` — do đó giao diện người dùng phía khách hàng vẫn hoạt động mà không làm lộ dữ liệu nội bộ.

Để biết mô hình đầy đủ — định dạng token, kết nối với identity provider của bạn, vòng đời guest, và tùy biến chính sách — xem [Xác thực (Authentication)](auth.md).

### Cấu trúc tài nguyên (Resource Shapes)

#### Sessions

Một phản hồi session có cấu trúc như sau:

```json
{
  "id": "sess_123",
  "agent_id": "agent_123",
  "customer_id": "cust_123",
  "creation_utc": "2026-07-06T12:00:00Z",
  "modified_utc": "2026-07-06T12:00:00Z",
  "title": "Checkout support",
  "mode": "auto",
  "metadata": {"priority": "high"},
  "labels": ["vip"]
}
```

Các trường quan trọng:

| Trường | Ý nghĩa |
|---|---|
| `agent_id` | Agent phụ trách phiên này. |
| `customer_id` | Khách hàng mà phiên này thuộc về. Với xác thực customer hoặc guest, giá trị này được suy ra từ người gọi thay vì tin cậy từ body. |
| `mode` | `auto` hoặc `manual`. Trong chế độ `manual`, Parlant không tự động trả lời các tin nhắn mới của khách hàng. |
| `metadata` | Đối tượng JSON cho trạng thái ứng dụng, gợi ý định tuyến, phân tích dữ liệu, hoặc tích hợp. |
| `labels` | Các thẻ dạng tập hợp dùng để lọc và quản lý vòng đời. |

#### Events

Events là các bản ghi chỉ thêm mới (append-only) trong một phiên. Chúng được sắp xếp theo `offset` và gom nhóm theo `trace_id`.

```json
{
  "id": "evt_123",
  "source": "customer",
  "kind": "message",
  "offset": 0,
  "creation_utc": "2026-07-06T12:00:00Z",
  "modified_utc": "2026-07-06T12:00:00Z",
  "trace_id": "trace_123",
  "data": {
    "message": "Hi, I need help",
    "participant": {"id": "cust_123", "display_name": "Jane"}
  },
  "metadata": {},
  "deleted": false
}
```

Các trường quan trọng:

| Trường | Ý nghĩa |
|---|---|
| `offset` | Vị trí đơn điệu tăng dần trong nhật ký sự kiện của phiên. Sử dụng nó cho các lần đọc tăng dần. |
| `trace_id` | Liên kết các sự kiện có liên quan, thường là một đầu vào của khách hàng cùng các trạng thái, công cụ và tin nhắn của agent phát sinh từ đó. |
| `kind` | Một trong các loại: `message`, `tool`, `status`, hoặc `custom`. |
| `source` | Một trong các nguồn: `customer`, `customer_ui`, `human_agent`, `human_agent_on_behalf_of_ai_agent`, `ai_agent`, hoặc `system`. |
| `metadata` | Đối tượng JSON cấp sự kiện. Chỉ metadata là có thể vá (patch) sau khi tạo. |
| `deleted` | Đánh dấu sự kiện đã bị xóa. Các lệnh gọi danh sách thông thường chỉ trả về các sự kiện chưa bị xóa. |

### Tạo một Phiên (Create a Session)

```http
POST /sessions?allow_greeting=false
Content-Type: application/json

{
  "agent_id": "agent_123",
  "customer_id": "cust_123",
  "title": "Checkout support",
  "metadata": {"cart_id": "cart_789"},
  "labels": ["vip"]
}
```

Các tham số:

| Tham số | Vị trí | Tác dụng |
|---|---|---|
| `agent_id` | body | Bắt buộc. Chọn agent cho phiên. |
| `customer_id` | body | Tùy chọn. Người gọi admin/development có thể thiết lập. Customer token được giới hạn trong khách hàng của chính nó. Người gọi ẩn danh và guest sẽ tạo các phiên guest. |
| `title` | body | Tiêu đề hiển thị tùy chọn. |
| `metadata` | body | Đối tượng JSON tùy chọn được lưu trữ trên phiên. |
| `labels` | body | Các nhãn tùy chọn để lọc và thao tác hàng loạt. |
| `allow_greeting` | query | Nếu `true`, agent bắt đầu một lượt ngay sau khi phiên được tạo, để nó có thể chào khách hàng trước tin nhắn đầu tiên của họ. |

Ví dụ:

```bash
curl -X POST "$PARLANT_URL/sessions?allow_greeting=false" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "agent_123",
    "title": "Support chat",
    "metadata": {"source": "web"},
    "labels": ["vip"]
  }'
```

Nếu xác thực guest ẩn danh được bật, phản hồi có thể bao gồm `X-Parlant-Guest-Token`. Hãy lưu trữ nó và gửi dưới dạng `Authorization: Bearer ...` trong các request tiếp theo. Bất kỳ phản hồi nào sau đó có thể mang một token được gia hạn trong cùng header; hãy thay thế token đã lưu bằng token mới đó.

### Đọc và Liệt kê các Phiên (Read and List Sessions)

Đọc một phiên:

```http
GET /sessions/{session_id}
```

Liệt kê các phiên:

```http
GET /sessions?agent_id=agent_123&customer_id=cust_123&labels=vip&limit=25&sort=desc
```

Bộ lọc và phân trang:

| Query parameter | Tác dụng |
|---|---|
| `agent_id` | Chỉ các phiên dành cho agent này. |
| `customer_id` | Chỉ các phiên dành cho khách hàng này. Người gọi đã xác thực customer luôn bị giới hạn trong khách hàng của chính họ. |
| `labels` | Tham số danh sách có thể lặp lại. Chỉ các phiên khớp với các nhãn được cung cấp mới được trả về. |
| `min_modified_utc` | Chỉ các phiên được sửa đổi tại hoặc sau dấu thời gian UTC này. Hữu ích cho các tác vụ đồng bộ hóa. |
| `limit` | Bật phân trang theo con trỏ (cursor pagination) và giới hạn phản hồi ở mức 1-100 mục. |
| `cursor` | Con trỏ từ phản hồi phân trang trước đó. |
| `sort` | `asc` hoặc `desc`. |

Cấu trúc phản hồi phụ thuộc vào `limit`:

```http
GET /sessions
```

trả về một mảng thuần túy:

```json
[
  {"id": "sess_1", "agent_id": "agent_123", "...": "..."}
]
```

trong khi:

```http
GET /sessions?limit=25
```

trả về một đối tượng có phân trang:

```json
{
  "items": [{"id": "sess_1", "agent_id": "agent_123"}],
  "total_count": 104,
  "has_more": true,
  "next_cursor": "AAAB..."
}
```

### Cập nhật một Phiên (Update a Session)

```http
PATCH /sessions/{session_id}
Content-Type: application/json

{
  "title": "Refund issue",
  "mode": "manual",
  "metadata": {
    "set": {"priority": "high", "handoff_reason": "billing"},
    "unset": ["old_priority"]
  },
  "labels": {
    "upsert": ["needs-human"],
    "remove": ["self-service"]
  }
}
```

Các trường patch:

| Trường | Tác dụng |
|---|---|
| `title` | Thay thế tiêu đề của phiên. |
| `mode` | Đặt `auto` hoặc `manual`. |
| `customer_id` | Gán lại khách hàng của phiên, tùy thuộc vào quyền hạn. |
| `agent_id` | Gán lại agent của phiên. |
| `metadata.set` | Hợp nhất các khóa vào session metadata. |
| `metadata.unset` | Xóa các khóa khỏi session metadata nếu có. |
| `labels.upsert` | Thêm nhãn. Các nhãn hiện có được giữ nguyên. |
| `labels.remove` | Xóa nhãn nếu có. |

Các trường hợp sử dụng phổ biến:

- Định tuyến một cuộc hội thoại sang con người xử lý với `mode: "manual"` và các nhãn như `["needs-human"]`.
- Gắn trạng thái ứng dụng, chẳng hạn như ID phiếu hỗ trợ CRM, bằng cách sử dụng metadata.

### Xóa các Phiên (Delete Sessions)

Xóa một phiên:

```http
DELETE /sessions/{session_id}
```

Xóa hàng loạt phiên:

```http
DELETE /sessions?agent_id=agent_123&customer_id=cust_123
```

Việc xóa hàng loạt chấp nhận các bộ lọc `agent_id` và `customer_id`. Nếu không cung cấp bộ lọc nào, tất cả các phiên hiển thị với người gọi và được phép bởi chính sách phân quyền sẽ bị xóa. Hãy sử dụng endpoint này một cách cẩn trọng.

### Gửi các Sự kiện (Post Events)

Tất cả các thao tác tạo sự kiện đều sử dụng:

```http
POST /sessions/{session_id}/events
Content-Type: application/json
```

Body luôn bao gồm:

| Trường | Ý nghĩa |
|---|---|
| `kind` | Loại sự kiện: `message`, `custom`, hoặc `status` để gửi trực tiếp. |
| `source` | Nguồn sự kiện. Các nguồn được hỗ trợ tùy thuộc vào `kind`. |
| `message` | Văn bản tin nhắn cho các sự kiện tin nhắn chấp nhận văn bản rõ ràng. |
| `data` | Payload JSON cho các sự kiện custom và status. |
| `metadata` | Metadata tùy chọn của sự kiện. |
| `participant` | Chi tiết người tham gia tùy chọn hoặc bắt buộc, tùy thuộc vào nguồn. |
| `rules` | Các chỉ dẫn phát ngôn (utterance instructions) tùy chọn cho các tin nhắn do AI-agent sinh ra. |
| `status` | Bắt buộc đối với các sự kiện trạng thái (status events). |

#### Tin nhắn Khách hàng: Bắt đầu hoặc Tiếp tục một Lượt

```http
POST /sessions/{session_id}/events
Content-Type: application/json

{
  "kind": "message",
  "source": "customer",
  "message": "I need help changing my order"
}
```

Tác dụng:

1. Tạo một sự kiện tin nhắn của khách hàng.
2. Chạy kiểm duyệt theo thiết lập `moderation` của agent (xem [Kiểm duyệt (Moderation)](moderation.md)); kết quả được lưu tại `data.flagged`.
3. Bắt đầu xử lý nền cho phiên.
4. Trả về sự kiện của khách hàng ngay lập tức, không phải phản hồi cuối cùng của agent.

Bạn chỉ có thể ghi đè người tham gia (participant) nếu được phép:

```json
{
  "kind": "message",
  "source": "customer",
  "message": "Hello",
  "participant": {"id": "cust_123", "display_name": "Jane Customer"}
}
```

Bạn có thể đính kèm tham chiếu tệp vào tin nhắn của khách hàng bằng `attachments`. Parlant không lưu trữ byte nào — mỗi mục tham chiếu đến một tệp trong bộ lưu trữ của chính bạn:

```json
{
  "kind": "message",
  "source": "customer",
  "message": "Here's the leak under my sink.",
  "attachments": [
    {"url": "https://cdn.example.com/u/9f3a.jpg", "media_type": "image/jpeg", "caption": "a leaking pipe"}
  ]
}
```

Chỉ có `url` là bắt buộc; `media_type`, `caption`, `filename`, và `metadata` là tùy chọn. Một công cụ đọc các thông tin này thông qua `p.Session.current.interaction`, và caption (hoặc một placeholder) được hiển thị cho agent. Xem [Nội dung phong phú (Rich Content)](rich-content.md) để biết hướng dẫn đầy đủ.

##### Độ trễ xử lý các tin nhắn liên tiếp (Consecutive-Message Processing Delay)

Mỗi tin nhắn của khách hàng bắt đầu quá trình xử lý nền cho phản hồi của agent. Nếu phiên đang được xử lý, lượt chạy hiện tại sẽ bị hủy và được thay thế bằng một lượt chạy nhìn thấy lịch sử tương tác mới nhất. Một số khách hàng có thói quen gửi nhiều tin nhắn ngắn liên tiếp. Việc bắt đầu quá trình matching và làm việc với mô hình tốn kém cho mỗi tin nhắn từng phần sẽ rất lãng phí.

Do đó, Parlant sẽ đợi một chút trước khi xử lý các tin nhắn sau trong một chuỗi tin nhắn dồn dập không bị gián đoạn. Nó gán cho mỗi tin nhắn của khách hàng một chỉ số bắt đầu từ số không, `k`, đếm các tin nhắn liên tiếp của khách hàng kể từ tin nhắn gần nhất của agent:

| `k` | Độ trễ mặc định |
|---:|---:|
| `0` | Không có độ trễ |
| `1` | 1.000 ms |
| `2` hoặc lớn hơn | 3.000 ms |

Một câu trả lời của agent sẽ đặt lại số đếm, vì vậy tin nhắn tiếp theo của khách hàng sẽ lại là `k=0`. Các sự kiện status, tool, và các sự kiện không phải tin nhắn khác không làm gián đoạn chuỗi tin nhắn này. Các phiên ở chế độ manual không bao giờ bị trì hoãn, vì Parlant không tự động xử lý chúng.

Ghi đè `p.CompassOptimizationPolicy.get_process_delay` để điều chỉnh hoặc tắt độ trễ, sau đó liên kết policy thông qua `configure_container`:

```python
import parlant.sdk as p


class MyOptimizationPolicy(p.CompassOptimizationPolicy):
    def get_process_delay(self, k: int) -> int:
        if k == 0:
            return 0
        return 500  # Đợi nửa giây cho mỗi tin nhắn tiếp theo trong chuỗi dồn dập.


async def configure_container(container: p.Container) -> p.Container:
    container[p.CompassOptimizationPolicy] = MyOptimizationPolicy()
    return container


async with p.Server(configure_container=configure_container) as server:
    ...
```

#### Tin nhắn AI-Agent: Buộc Agent phải phản hồi

Để yêu cầu agent xử lý trạng thái phiên hiện tại:

```http
POST /sessions/{session_id}/events
Content-Type: application/json

{
  "kind": "message",
  "source": "ai_agent"
}
```

Lệnh này không nhận `message`, vì agent sẽ tự sinh nội dung. Nếu không có `rules`, lệnh này sẽ bắt đầu quá trình xử lý và trả về status event đầu tiên cho trace xử lý đó. Hãy tiếp tục đọc các sự kiện để nhận tool events, cập nhật trạng thái và tin nhắn cuối cùng của agent.

Để yêu cầu một loại phát ngôn được sinh ra cụ thể, hãy cung cấp `rules`:

```json
{
  "kind": "message",
  "source": "ai_agent",
  "rules": [
    {
      "action": "Tell the customer that you are checking the order status.",
      "rationale": "buy_time"
    }
  ]
}
```

`rationale` có thể là `unspecified`, `buy_time`, hoặc `follow_up`. Với `rules`, endpoint yêu cầu Parlant tạo ra phát ngôn theo yêu cầu và trả về sự kiện tin nhắn đã được sinh ra.

#### Tin nhắn Human-Agent

```json
{
  "kind": "message",
  "source": "human_agent",
  "message": "I will take it from here.",
  "participant": {"id": "agent_456", "display_name": "Alex"}
}
```

Thao tác này tạo một tin nhắn của con người và không kích hoạt xử lý AI. `participant` với `display_name` là bắt buộc.

#### Tin nhắn Human-Agent đại diện cho AI Agent

```json
{
  "kind": "message",
  "source": "human_agent_on_behalf_of_ai_agent",
  "message": "Your refund request has been received."
}
```

Thao tác này ghi lại một tin nhắn với agent của phiên là người tham gia, nhưng với nguồn đánh dấu là do con người soạn thảo thay mặt cho AI.

#### Sự kiện Tùy chỉnh (Custom Event)

```json
{
  "kind": "custom",
  "source": "customer_ui",
  "data": {
    "type": "page_view",
    "url": "/checkout"
  },
  "metadata": {
    "browser_session": "abc"
  }
}
```

Các custom events yêu cầu `data`, chấp nhận bất kỳ đối tượng JSON nào có thể serialize được, và không kích hoạt xử lý AI.

#### Sự kiện Trạng thái (Status Event)

```json
{
  "kind": "status",
  "source": "system",
  "status": "typing",
  "data": {"message": "Typing"}
}
```

Các trạng thái được hỗ trợ:

| Trạng thái | Trường hợp sử dụng điển hình |
|---|---|
| `acknowledged` | Hệ thống đã chấp nhận một lượt hội thoại. |
| `processing` | Agent đang làm việc. |
| `typing` | Agent đang tạo phản hồi. |
| `ready` | Lượt hội thoại đã hoàn thành. |
| `error` | Quá trình xử lý bị lỗi. |
| `cancelled` | Yêu cầu hủy đặc biệt, được mô tả bên dưới. |

Đối với các trạng thái không phải hủy, `data` phải là một đối tượng JSON. Sự kiện được tạo trực tiếp và không kích hoạt xử lý của agent.

### Hủy xử lý đang chạy (Cancel In-Flight Processing)

Việc hủy bỏ được thể hiện dưới dạng một yêu cầu sự kiện trạng thái:

```http
POST /sessions/{session_id}/events
Content-Type: application/json

{
  "kind": "status",
  "source": "customer",
  "status": "cancelled"
}
```

`source` là bắt buộc theo schema của sự kiện nhưng **không** được dùng cho việc hủy: yêu cầu chỉ dựa duy nhất vào `status: "cancelled"`, và sự kiện hủy trả về do Parlant tự biên soạn. Hãy gửi định danh của chính người gọi — ví dụ `customer` khi một khách hàng tự ngắt lượt của mình.

Endpoint này không chỉ đơn thuần nối thêm sự kiện được cung cấp. Thay vào đó, nó:

1. Tìm tác vụ xử lý đang hoạt động cho phiên.
2. Hủy tác vụ đó.
3. Chờ cho đến khi Parlant phát ra một sự kiện trạng thái `cancelled` cho trace đang hoạt động.
4. Trả về sự kiện đã phát ra đó.

Các kết quả:

| Mã trạng thái | Ý nghĩa |
|---|---|
| `201` | Quá trình xử lý đã bị hủy và một sự kiện hủy đã được phát ra. |
| `409` | Không có tác vụ xử lý nào đang hoạt động cho phiên. |
| `504` | Tác vụ đã bị hủy, nhưng không có sự kiện hủy nào xuất hiện trước khi timeout. |

Sau khi hủy, Parlant cũng phát ra một trạng thái `ready` kết thúc cho cùng trace đó để các client có thể xóa giao diện "đang suy nghĩ".

### Đọc các Sự kiện (Read Events)

Liệt kê các sự kiện:

```http
GET /sessions/{session_id}/events?min_offset=0&wait_for_data=0
```

Các tham số truy vấn:

| Query parameter | Tác dụng |
|---|---|
| `min_offset` | Trả về các sự kiện có `offset >= min_offset`. Mặc định là `0`. |
| `source` | Lọc theo một nguồn, ví dụ `customer` hoặc `ai_agent`. |
| `kinds` | Các loại sự kiện cách nhau bởi dấu phẩy, ví dụ `message,status`. |
| `trace_id` | Chỉ trả về các sự kiện thuộc về một trace. |
| `wait_for_data` | Thời gian timeout cho long-polling tính bằng giây. Mặc định `60`. |
| `sse` | Nếu `true`, stream các sự kiện khớp dưới dạng Server-Sent Events. |

#### Đọc ngay lập tức (Immediate Read)

Sử dụng `wait_for_data=0` để trả về ngay lập tức:

```bash
curl "$PARLANT_URL/sessions/$SESSION_ID/events?min_offset=0&wait_for_data=0"
```

#### Thăm dò dài (Long Polling)

Sử dụng `min_offset` kết hợp với `wait_for_data` để chờ các sự kiện mới:

```bash
curl "$PARLANT_URL/sessions/$SESSION_ID/events?min_offset=12&wait_for_data=30"
```

Hành vi:

- Nếu các sự kiện khớp đã tồn tại, trả về ngay lập tức.
- Nếu không có sự kiện khớp nào tồn tại, đợi tối đa `wait_for_data` giây.
- Nếu không có sự kiện nào đến trước khi hết thời gian chờ, trả về `504`.

Vòng lặp phía client:

```javascript
let offset = 0;

while (true) {
  const res = await fetch(
    `${PARLANT_URL}/sessions/${sessionId}/events?min_offset=${offset}&wait_for_data=30`,
  );

  if (res.status === 504) continue;
  const events = await res.json();

  for (const event of events) {
    render(event);
    offset = Math.max(offset, event.offset + 1);
  }
}
```

#### Server-Sent Events (SSE)

Sử dụng `sse=true` để nhận luồng dữ liệu stream:

```javascript
const source = new EventSource(
  `${PARLANT_URL}/sessions/${sessionId}/events?min_offset=0&sse=true&wait_for_data=60`,
);

source.onmessage = (message) => {
  const event = JSON.parse(message.data);
  render(event);
};
```

Luồng stream gửi mỗi sự kiện khớp dưới dạng:

```text
data: {"id":"evt_123", ...}
```

và đóng lại khi không có sự kiện khớp nào đến trong vòng `wait_for_data` giây. Hãy kết nối lại với `min_offset` tiếp theo để tiếp tục.

#### Các ví dụ về lọc sự kiện

Chỉ lấy tin nhắn:

```http
GET /sessions/{session_id}/events?kinds=message&wait_for_data=0
```

Chỉ lấy các cập nhật trạng thái cho một trace:

```http
GET /sessions/{session_id}/events?kinds=status&trace_id=trace_123&wait_for_data=30
```

Chỉ lấy đầu ra hiển thị của agent:

```http
GET /sessions/{session_id}/events?source=ai_agent&kinds=message&wait_for_data=0
```

Chỉ lấy các lệnh gọi công cụ của một lượt (để đọc đầu ra frontend của công cụ — tệp, dữ liệu UI — từ `result.metadata`, khớp với tin nhắn theo `trace_id`; xem [Nội dung phong phú (Rich Content)](rich-content.md)):

```http
GET /sessions/{session_id}/events?kinds=tool&trace_id=trace_123&wait_for_data=0
```

### Đọc một Sự kiện (Read One Event)

```http
GET /sessions/{session_id}/events/{event_id}
```

Các tham số truy vấn tùy chọn:

| Query parameter | Tác dụng |
|---|---|
| `wait_for_completion=true` | Chờ cho đến khi một sự kiện streaming hoàn thành trước khi trả về. |
| `wait_for_data` | Thời gian chờ tính bằng giây cho việc hoàn thành hoặc cập nhật streaming. |
| `sse=true` | Stream các cập nhật cho sự kiện này cho đến khi nó hoàn thành. |

Các sự kiện streaming sử dụng `data.chunks`. Việc hoàn thành được biểu diễn bằng một chunk `null` cuối cùng:

```json
{
  "data": {
    "message": "Hello there",
    "chunks": ["Hello", " there", null]
  }
}
```

Chờ sự kiện hoàn chỉnh:

```http
GET /sessions/{session_id}/events/{event_id}?wait_for_completion=true&wait_for_data=60
```

Stream các cập nhật cho một sự kiện đơn lẻ:

```javascript
const source = new EventSource(
  `${PARLANT_URL}/sessions/${sessionId}/events/${eventId}?sse=true&wait_for_data=60`,
);

source.onmessage = (message) => {
  const event = JSON.parse(message.data);
  renderStreamingEvent(event);
};
```

Đối với các sự kiện không streaming, `sse=true` gửi sự kiện một lần rồi đóng kết nối.

### Cập nhật Metadata của Sự kiện

Chỉ có metadata của sự kiện là có thể vá (patch):

```http
PATCH /sessions/{session_id}/events/{event_id}
Content-Type: application/json

{
  "metadata": {
    "set": {"reviewed": true, "sentiment": "positive"},
    "unset": ["temporary_flag"]
  }
}
```

Điều này hữu ích cho các cờ UI, trạng thái xét duyệt, chú thích kiểm duyệt, hoặc ghi chép tích hợp. Nó không làm thay đổi nội dung của sự kiện.

### Xóa các Sự kiện và Sinh lại từ một Thời điểm trước đó

```http
DELETE /sessions/{session_id}/events?min_offset=12
```

Thao tác này xóa tất cả các sự kiện có `offset >= min_offset` và cắt ngắn trạng thái agent đã lưu trữ thuộc về phạm vi trace đã bị xóa.

Ràng buộc quan trọng:

Sự kiện tại `min_offset` phải là sự kiện chưa bị xóa đầu tiên của `trace_id` của nó. Nếu không phải, API trả về `422` kèm thông báo:

```text
Cannot delete events with offset < min_offset unless they are the first event of their trace ID
```

Tại sao điều này quan trọng:

- Một lượt hội thoại tạo ra nhiều sự kiện có cùng `trace_id`, chẳng hạn như tin nhắn của khách hàng, các trạng thái, các lệnh gọi công cụ, và tin nhắn của agent.
- Việc xóa từ giữa trace đó sẽ để lại một lượt hội thoại không nhất quán.
- Để sinh lại một phản hồi, hãy xóa từ sự kiện đầu tiên của trace mà bạn muốn phát lại.

Quy trình sinh lại thông thường:

1. Tìm tin nhắn khách hàng mà bạn muốn phát lại.
2. Sử dụng `offset` của nó làm `min_offset`.
3. Xóa các sự kiện từ offset đó.
4. Gửi tin nhắn khách hàng thay thế.
5. Lắng nghe các sự kiện của trace mới.

### Các mẫu Client khuyến nghị (Recommended Client Patterns)

#### UI Chat đơn giản

1. `POST /sessions`.
2. `POST /sessions/{id}/events` với `kind=message`, `source=customer`.
3. Bắt đầu `GET /sessions/{id}/events?min_offset=<next>&sse=true`.
4. Hiển thị các sự kiện status cho trạng thái "đang suy nghĩ" và các sự kiện message cho nội dung trò chuyện hiển thị.

#### Ghi nhớ những gì UI đã hiển thị (Bookmark)

Một giao diện chat thường cần một dấu trang (bookmark): khách hàng đã xem những sự kiện nào? Hãy lưu trữ nó trong session metadata dưới một khóa chuyên dụng.

Sau khi hiển thị các sự kiện, hãy lưu offset cao nhất bạn đã hiển thị:

```http
PATCH /sessions/{session_id}
Content-Type: application/json

{
  "metadata": {
    "set": {"consumed_offset": 42}
  }
}
```

Khi UI tải lại, hãy đọc session và tiếp tục từ bookmark đó:

1. `GET /sessions/{session_id}` và đọc `metadata.consumed_offset`.
2. Hiển thị các sự kiện trước đó như đã đọc.
3. Đọc các sự kiện mới với `min_offset=<consumed_offset + 1>`.

Parlant lưu trữ giá trị và trao lại cho bạn; nó không gắn bất kỳ hành vi nào vào đó. Bạn tự chọn tên khóa, và bạn có thể lưu trữ một bookmark cho mỗi thiết bị hoặc người dùng bằng cách sử dụng các khóa khác nhau.

#### UI Chat sử dụng Long-Polling

Sử dụng phương pháp này khi không có sẵn SSE:

1. Duy trì một biến `nextOffset` cục bộ.
2. Gọi `GET /sessions/{id}/events?min_offset=<nextOffset>&wait_for_data=30`.
3. Khi gặp `504`, thử lại.
4. Khi nhận được các sự kiện, hiển thị chúng và tăng `nextOffset`.

#### Chuyển giao cho con người (Human Handoff)

1. `PATCH /sessions/{id}` với `mode: "manual"` và các nhãn như `["needs-human"]`.
2. Nhân viên con người gửi tin nhắn với `source: "human_agent"`.
3. Nếu AI hiện đang xử lý, hãy gửi sự kiện trạng thái `cancelled` trước.
4. Khi quay trở lại tự động hóa, `PATCH /sessions/{id}` với `mode: "auto"`.

#### Nút Dừng (Stop Button)

Khi một phản hồi đang trong quá trình sinh:

1. POST một sự kiện trạng thái hủy (`status: "cancelled"`).
2. Chờ sự kiện `cancelled` được trả về.
3. Tiếp tục lắng nghe trạng thái `ready` kết thúc trên cùng trace đó.
4. Xóa trạng thái "đang suy nghĩ" phía client khi `ready` xuất hiện.

#### Tác vụ đồng bộ hóa (Sync Job)

Để phản chiếu (mirror) các phiên vào một hệ thống khác:

1. Gọi `GET /sessions?limit=100&sort=asc&min_modified_utc=<last_sync_time>`.
2. Đi theo `next_cursor` cho đến khi `has_more` là false.
3. Đối với các phiên đã thay đổi, gọi `GET /sessions/{id}/events?wait_for_data=0`.
4. Lưu trữ dấu thời gian đồng bộ hóa mới nhất.

### Tham chiếu Mã lỗi (Error Reference)

| Mã lỗi | Nguyên nhân phổ biến |
|---|---|
| `401` | Thiếu hoặc thông tin xác thực không hợp lệ. |
| `403` | Người gọi đã được xác thực nhưng không thể truy cập phiên hoặc thao tác này. |
| `404` | Phiên hoặc sự kiện không tồn tại. |
| `409` | Yêu cầu hủy khi không có tác vụ xử lý nào đang hoạt động. |
| `422` | Body không hợp lệ, kết hợp source/kind không được hỗ trợ, thiếu trường bắt buộc, hoặc offset xóa sự kiện không hợp lệ. |
| `504` | Long-poll timed out, hoặc việc hủy không tạo ra sự kiện hủy trước khi hết thời gian chờ. |

### Tóm tắt các Endpoint

| Phương thức | Đường dẫn | Mục đích |
|---|---|---|
| `POST` | `/sessions` | Tạo một phiên. |
| `GET` | `/sessions` | Liệt kê các phiên, tùy chọn lọc và phân trang. |
| `GET` | `/sessions/{session_id}` | Đọc một phiên. |
| `PATCH` | `/sessions/{session_id}` | Cập nhật tiêu đề, mode, các trường sở hữu, metadata, và labels. |
| `DELETE` | `/sessions/{session_id}` | Xóa một phiên. |
| `DELETE` | `/sessions` | Xóa hàng loạt các phiên theo bộ lọc. |
| `POST` | `/sessions/{session_id}/events` | Tạo một sự kiện message, custom, hoặc status. Cũng được dùng để yêu cầu hủy. |
| `GET` | `/sessions/{session_id}/events` | Liệt kê, long-poll, hoặc stream SSE các sự kiện. |
| `PATCH` | `/sessions/{session_id}/events/{event_id}` | Cập nhật metadata của sự kiện. |
| `GET` | `/sessions/{session_id}/events/{event_id}` | Đọc hoặc stream một sự kiện. |
| `DELETE` | `/sessions/{session_id}/events` | Xóa các sự kiện từ một offset trở đi. |
