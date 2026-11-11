# Nội Dung Đa Phương Tiện — Files, Hình Ảnh và Dữ Liệu Công Cụ (Rich Content)

## Tổng quan

Các cuộc hội thoại không chỉ đơn thuần là văn bản. Một khách hàng có thể gửi một bức ảnh chụp sản phẩm bị hỏng. Một công cụ có thể mở một yêu cầu khiếu nại và trả về một đường dẫn tới hóa đơn thanh toán. Parlant hỗ trợ điều này dựa trên một nguyên lý đơn giản: **nó chỉ mang các tham chiếu và các mẩu dữ liệu nhỏ, tuyệt đối không lưu trữ các file của bạn.** Một file sẽ luôn nằm trong kho lưu trữ của *chính bạn*. Giao diện frontend của bạn tải file lên bất kỳ nơi nào bạn đang lưu trữ file và nhận lại một URL. Parlant chỉ truyền một tham chiếu nhỏ gọn, có định kiểu (typed reference) tới URL đó xuyên suốt phiên hội thoại.

Thiết kế này là có chủ đích. Việc tự vận hành hệ thống lưu trữ file đòi hỏi các endpoint upload, giới hạn dung lượng, kiểm soát quyền truy cập và dọn dẹp file rác — những thứ mà hệ thống của bạn gần như chắc chắn đã xây dựng sẵn, dưới những quy tắc nghiệp vụ riêng mà Parlant không thể biết trước. Do đó, Parlant chỉ lưu trữ các tham chiếu, và các file vẫn nằm nguyên vẹn tại nơi lưu trữ gốc của bạn. Khi một tool cần đến file, nó sử dụng URL đó, và thông thường nó chỉ cần chuyển tiếp URL (chẳng hạn như gửi sang một mô hình vision) mà không cần phải tải bất kỳ file nào về.

Nội dung đa phương tiện (rich content) di chuyển theo hai chiều, và hai chiều sử dụng hai cơ chế hoàn toàn khác nhau. Hãy phân biệt rõ các thuật ngữ:

- **Chiều gửi vào (Inbound - Khách hàng → Agent)** sử dụng **attachments (tệp đính kèm)**: là các tham chiếu file gắn trên tin nhắn của khách hàng. Ví dụ: khách hàng gửi ảnh sản phẩm bị hư hỏng để mở yêu cầu bảo hành, hoặc tải lên hóa đơn để tool tra cứu đơn hàng.
- **Chiều gửi ra (Outbound - Agent → Khách hàng)** **không phải** là attachment. Một tool trả về dữ liệu JSON thông thường trong trường `metadata` của kết quả của nó, và frontend của bạn sẽ hiển thị dữ liệu đó: một liên kết tải về, hình ảnh sản phẩm, bản tóm tắt đơn hàng. Không có cơ chế nào để "đính kèm file" trực tiếp vào tin nhắn của agent, và cũng không cần thiết — metadata của tool được truyền đi trong cùng một lượt tương tác với câu trả lời của agent.

## Chiều gửi vào: Attachments

### Cấu trúc tham chiếu Attachment

Một kiểu dữ liệu nhỏ gọn đại diện cho một tham chiếu file:

```python
class AttachmentRef(TypedDict):
    url: str                        # nơi file được lưu trữ, trong hệ thống lưu trữ của BẠN
    media_type: NotRequired[str]    # IANA MIME type: image/jpeg, application/pdf, ...
    caption: NotRequired[str]       # mô tả ngắn, người dùng và model đều đọc được
    filename: NotRequired[str]      # tên file gốc, dùng để hiển thị và tải xuống
    metadata: NotRequired[Mapping[str, JSONSerializable]]  # bất kỳ dữ liệu bổ sung nào bạn muốn mang theo
```

`url` là trường bắt buộc duy nhất và là bộ định vị duy nhất. Nó có thể là một URL công khai hoặc một signed URL có thời hạn. Parlant không tự mình mở hay truy cập URL đó.

**Những gì mô hình nhìn thấy.** Đối với mỗi attachment, Parlant sẽ nối thêm một ghi chú ngắn vào nội dung văn bản tin nhắn của khách hàng. Ghi chú này ưu tiên sử dụng trường `caption` nếu có, sau đó đến `filename`, và đánh dấu loại file dựa trên `media_type`:

- `[image: photo of a leaking sink pipe]` — có caption, kiểu là `image/*`
- `[file: receipt.pdf]` — không có caption, sử dụng filename; không phải là hình ảnh
- `[image attached]` / `[file attached]` — không có cả caption lẫn filename

Nhờ đó, mô hình có thể đọc được phần chú thích (caption), tên file và biết được file đó có phải là hình ảnh hay không. Nó không bao giờ nhìn thấy `url` hay `metadata`; những trường đó chỉ dành riêng cho các tool và frontend của bạn. Hãy viết caption dựa trên lưu ý này: một caption tốt là thứ giúp một rule như: *"khi khách hàng gửi ảnh chụp vấn đề, hãy mở một phiếu sửa chữa"* được khớp chính xác.

### Đính kèm file vào tin nhắn

Frontend của bạn trước tiên tải file lên kho lưu trữ của bạn. Sau đó nó thêm tham chiếu khi gửi tin nhắn của khách hàng. Trường `attachments` thuộc về endpoint events (xem [Phiên Hội Thoại (Sessions)](sessions.md) để biết chi tiết API):

```http
POST /sessions/{session_id}/events
Content-Type: application/json

{
  "kind": "message",
  "source": "customer",
  "message": "Here's the leak under my sink.",
  "attachments": [
    {
      "url": "https://cdn.example.com/u/9f3a.jpg",
      "media_type": "image/jpeg",
      "caption": "photo of a leaking sink pipe"
    }
  ]
}
```

Một tin nhắn cũng có thể chỉ mang attachments mà không cần bất kỳ văn bản nào. Một khách hàng chỉ gửi một bức ảnh duy nhất vẫn là một tin nhắn hoàn toàn hợp lệ.

**Phân quyền (Permissions).** Việc gửi attachments đòi hỏi quyền thao tác `create_customer_event_with_attachments`; nếu không có quyền này, yêu cầu sẽ bị từ chối với mã lỗi `403`. Policy phân quyền môi trường phát triển mặc định cấp quyền này cho khách hàng (customer) và khách vãng lai (guest). Một policy phân quyền tùy chỉnh phải cấp quyền này tường minh (xem [Xác Thực (Authentication)](auth.md)).

**Kiểm duyệt (Moderation).** Tính năng kiểm duyệt của Parlant chỉ kiểm tra phần *văn bản* của tin nhắn. Caption và tên file không bị kiểm duyệt, tuy nhiên chúng vẫn được gửi đến mô hình — hãy coi chúng là đầu vào không đáng tin cậy nếu khách hàng có thể tự do nhập chúng. Khi một tin nhắn bị gắn cờ vi phạm, mô hình chỉ nhìn thấy thông báo ẩn nội dung và các ghi chú attachment sẽ bị loại bỏ cùng với văn bản. Các tool vẫn có thể đọc được các attachment này.

### Đọc Attachments bên trong một Tool

Một tool có thể đọc danh sách attachment từ tin nhắn khách hàng gần nhất thông qua `p.Session.current`:

```python
@p.tool
async def open_repair_ticket() -> p.ToolResult:
    last = p.Session.current.interaction.last_customer_message
    attachments = last.attachments if last else []
    images = [a for a in attachments if a.get("media_type", "").startswith("image/")]

    if not images:
        return p.ToolResult(
            data="No photo found on the customer's message. Ask them to attach a photo of the problem."
        )

    # Trường hợp phổ biến: chỉ cần chuyển tiếp URLs. Không có file nào cần tải về ở đây.
    ticket = await crm.create_ticket(  # client CRM của chính bạn
        customer_id=p.Customer.current.id,
        photos=[a["url"] for a in images],
    )
    return p.ToolResult(data=f"Opened repair ticket {ticket.id}.")
```

Lưu ý nhánh khi không có ảnh: hàm trả về một `ToolResult` chỉ dẫn mô hình cần làm gì tiếp theo, để agent có thể lịch sự đề nghị khách hàng gửi một bức ảnh. Việc ném ra một ngoại lệ (exception) thay vì trả về kết quả sẽ chỉ khiến mô hình phải tự ứng biến xử lý lỗi.

`.attachments` là danh sách các `AttachmentRef` trên tin nhắn đó. Một tool có thể tải file từ URL của nó nếu thực sự cần thiết. Nhưng thông thường thì không cần.

## Chiều gửi ra: Kết quả Tool dành cho Frontend

Một kết quả tool (`ToolResult`) có hai trường dữ liệu then chốt:

- `data`: Là dữ liệu mà agent đọc và dùng để suy luận.
- `metadata`: Chỉ dành riêng cho frontend. Agent không bao giờ nhìn thấy trường này.

Bạn có thể đặt bất cứ thứ gì mà frontend cần vào trường `metadata`: một đường dẫn link, một tham chiếu file, hoặc một object JSON nhỏ để UI của bạn render. Parlant không áp đặt một định dạng widget cứng nhắc nào; frontend của bạn toàn quyền quyết định cách hiển thị dữ liệu.

```python
@p.tool
async def generate_invoice(order_id: str) -> p.ToolResult:
    url = await billing.render_invoice_pdf(order_id)   # được lưu trong kho lưu trữ của BẠN

    return p.ToolResult(
        data=f"Invoice for order {order_id} is ready and shown to the customer for download.",
        metadata={"invoice": {"url": url, "media_type": "application/pdf"}},
    )
```

Mô hình đọc trường `data`, nhờ đó nó có thể thông báo cho khách hàng biết hóa đơn đã sẵn sàng. Nó không bao giờ nhìn thấy URL. URL nằm trong `metadata`, nơi mà chỉ có frontend của bạn đọc — ví dụ dùng để render một thẻ tải file (download card).

### Cách Frontend nhận dữ liệu này

Bạn không cần thêm endpoint mới hay gửi thêm request bổ sung nào. Các sự kiện tool đến ngay trong luồng sự kiện mà frontend vốn đã đang đọc: cơ chế long-poll `list_events` và luồng SSE đều phân phối các sự kiện `kind=tool` song song cùng các sự kiện `message` và `status` (xem [Phiên Hội Thoại](sessions.md)).

Mọi sự kiện được tạo ra trong cùng một lượt tương tác đều chia sẻ chung một `trace_id`. Để hiển thị đầu ra của tool ngay bên cạnh tin nhắn của agent, chỉ cần lấy `trace_id` từ sự kiện tin nhắn bạn đã render và so khớp nó với các sự kiện tool đến từ cùng một luồng stream.

Trường `data` của một sự kiện tool chứa các lệnh gọi tool của lượt đó:

```jsonc
{
  "kind": "tool", "source": "system", "trace_id": "trc_9f…",
  "data": {
    "tool_calls": [
      {
        "tool_id": "built-in:generate_invoice",
        "arguments": { "order_id": "5567" },
        "result": {
          "metadata": { "invoice": { "url": "…", "media_type": "application/pdf" } },
          "data": "Invoice for order 5567 is ready…"
        }
      }
    ]
  }
}
```

Frontend đọc theo đường dẫn sau: **`toolEvent.data.tool_calls[i].result.metadata`**. Ba lưu ý quan trọng:

- **`tool_calls` là một danh sách chứa từng lệnh gọi riêng lẻ, không phải gom theo từng tool.** Nếu một tool chạy ba lần trong một lượt, nó sẽ xuất hiện ba lần. Hãy lặp qua danh sách và phân biệt các lần gọi thông qua `arguments`.
- **`tool_id` được định danh đầy đủ** theo dạng `service:tool`. Các SDK tool xuất hiện dưới dạng `built-in:generate_invoice`, không phải là `generate_invoice` — hãy so khớp tương ứng.
- **Bỏ qua key `__parlant__`** nếu nó xuất hiện trong `result.metadata`. Đó là namespace nội bộ của Parlant (chi tiết lỗi, v.v.), không phải là dữ liệu do tool của bạn sinh ra.

### Lấy các lượt gọi Tool của một lượt tương tác theo Trace ID

Nếu bạn đang theo dõi luồng sự kiện trực tiếp, bạn đã tự động nhận được các sự kiện tool này. Đôi khi bạn muốn tải riêng các lệnh gọi tool của một lượt tương tác — chẳng hạn khi tải lại lịch sử cũ. Không cần endpoint chuyên biệt nào cả. Hãy gọi endpoint events yêu cầu các sự kiện `kind=tool` có `trace_id` đó, và truyền `wait_for_data=0` để nó trả về kết quả ngay lập tức (trả về danh sách rỗng nếu lượt đó không gọi tool nào):

**Python** (sử dụng `httpx`):

```python
import httpx

PARLANT_URL = "http://localhost:8800"


def tool_calls_for_trace(session_id: str, trace_id: str) -> list[dict]:
    events = httpx.get(
        f"{PARLANT_URL}/sessions/{session_id}/events",
        params={
            "trace_id": trace_id,   # lấy từ sự kiện tin nhắn bạn đã render
            "kinds": "tool",
            "wait_for_data": 0,     # trả về những gì đang có; không dùng long-poll
        },
    ).raise_for_status().json()

    return [call for e in events for call in e["data"]["tool_calls"]]


for call in tool_calls_for_trace(session_id, trace_id):
    metadata = call["result"]["metadata"]
    ...  # render những gì tool của bạn đưa vào đây
```

**TypeScript** (dùng `fetch` thông thường):

```typescript
const PARLANT_URL = "http://localhost:8800";

async function toolCallsForTrace(sessionId: string, traceId: string) {
  const params = new URLSearchParams({
    trace_id: traceId,          // lấy từ sự kiện tin nhắn bạn đã render
    kinds: "tool",
    wait_for_data: "0",         // trả về những gì đang có; không dùng long-poll
  });
  const res = await fetch(`${PARLANT_URL}/sessions/${sessionId}/events?${params}`);
  const events = await res.json();
  return events.flatMap((e: any) => e.data.tool_calls ?? []);
}

for (const call of await toolCallsForTrace(sessionId, traceId)) {
  const metadata = call.result.metadata ?? {};
  // render những gì tool của bạn đưa vào đây
}
```

Mỗi lệnh gọi đều chứa `result.metadata`. Nó cũng chứa cả `result.data` khi bên gọi có quyền `READ_TOOL_RESULT_DATA`; nếu không, trường đó sẽ được thay thế bằng dấu hiệu `{"redacted": true}`. Cấu trúc trường được giữ nguyên, vì vậy hãy kiểm tra sự hiện diện của dấu hiệu này thay vì kiểm tra trường bị thiếu.

## Lưu ý và Giới hạn

- **URL do bạn tự bảo vệ:** Parlant coi `url` là chuỗi văn bản thông thường và không bao giờ mở nó. Nếu một file cần được bảo mật riêng tư, hãy cung cấp cho Parlant một signed URL có thời hạn hết hạn ngắn.
- **Parlant không xác thực tính hợp lệ của Attachments:** Không giới hạn số lượng, không kiểm tra dung lượng, không kiểm tra lược đồ URL scheme — nó lưu trữ những gì frontend của bạn gửi lên. Hãy kiểm tra ở tầng biên (edge) của bạn: giới hạn số lượng attachment, kiểm tra định dạng mime-type và chỉ chấp nhận URL từ kho lưu trữ của chính bạn.
- **Khi một tool tải file từ URL, đó là lệnh gọi mạng của chính bạn:** Hãy xử lý nó như bất kỳ yêu cầu gửi ra ngoài nào khác: chỉ cho phép các host tin cậy đã biết và cài đặt timeout. Một URL do kẻ tấn công cung cấp có thể bị lợi dụng để tấn công giả mạo yêu cầu từ phía server (SSRF).
- **Bạn tự cung cấp `media_type`; Parlant không kiểm tra:** Parlant không bao giờ tiếp cận file thực tế, nên không thể xác nhận kiểu file. Hãy tự kiểm tra nếu điều đó quan trọng với nghiệp vụ.
- **Trường `metadata` của Tool bị ẩn khỏi Agent và không bị kiểm duyệt:** Nó không ảnh hưởng đến suy luận của agent, và các cơ chế xác thực hay kiểm duyệt không kiểm tra nó. Không đặt các dữ kiện quan trọng với agent vào đây; hãy đưa chúng vào `data`.
- **Việc hiển thị (rendering) là trách nhiệm của Frontend:** Trang web chat tích hợp sẵn của server chỉ hiển thị văn bản và trạng thái. Widget chat có thể nhúng (`widget/` trong repository) hỗ trợ render trường `result.metadata` của tool và hỗ trợ đính kèm file từ khung soạn thảo tin nhắn — hãy sử dụng nó nếu bạn không muốn tự xây dựng giao diện từ đầu. Nó có sẵn một widget tích hợp là `choices`: tool trả về `{"widget": {"type": "choices", "options": [{"id": …, "label": …}]}}` và cú click chuột của khách truy cập sẽ được gửi đi như một tin nhắn của chính họ.
- **Đối với dữ liệu thuần túy dành cho Frontend nằm ngoài lượt gọi Tool**, hãy gửi một sự kiện `kind=custom` vào session — cùng luồng feed, không cần đến tool (xem [Phiên Hội Thoại](sessions.md)).
- **Bộ nhớ phiên và Attachments là độc lập:** Các attachment chỉ thuộc về từng tin nhắn đơn lẻ trong một session cụ thể. Chúng không phải là bộ nhớ khách hàng dài hạn (xem [Bộ Nhớ (Memory)](memory.md)).
