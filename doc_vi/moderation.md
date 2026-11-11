# Kiểm Duyệt (Moderation)

Kiểm duyệt là một lớp bảo vệ an toàn tùy chọn với 2 trạm kiểm soát (checkpoints) độc lập: các tin nhắn gửi đến của khách hàng (incoming) và các tin nhắn gửi đi của agent (outgoing).

Có hai thiết lập riêng biệt kiểm soát tính năng này:

1. **Có kiểm duyệt hay không** là một thuộc tính của agent — thiết lập `moderation` trên từng agent (`auto`/`on`/`off`).
2. **Mô hình nào thực hiện việc kiểm duyệt** là cấu hình triển khai hệ thống — cùng là bảng ánh xạ `models={...}` chọn mô hình chat nhưng có thêm 2 mục kiểm duyệt cho mỗi checkpoint: `moderation.customer` cho tin nhắn gửi đến và `moderation.agent` cho tin nhắn gửi đi (chi tiết xem phần [Định tuyến các mô hình kiểm duyệt](#định-tuyến-các-mô-hình-kiểm-duyệt) bên dưới).

Hai thiết lập này được tách rời có chủ đích: một agent có thể *khai báo* rằng nó cần phải được kiểm duyệt mà không cần biết mô hình cụ thể nào, hoặc provider nào, sẽ đảm nhận việc kiểm tra trong một môi trường triển khai nhất định.

## Thuộc tính kiểm duyệt của Agent

Mỗi agent đều mang một thiết lập `moderation`:

```python
import parlant.sdk as p

agent = await server.create_agent(
    id="my-agent",
    name="Support Agent",
    instructions="...",
    moderation=p.Moderation.AUTO,
)
```

- **`auto`** (mặc định) — việc kiểm duyệt tuân theo cấu hình của bạn: từng checkpoint sẽ chạy nếu bạn cấu hình một mô hình kiểm duyệt cho nó, và sẽ tự động bỏ qua nếu bạn không cấu hình. Không có provider nào tự động kích hoạt kiểm duyệt ngầm, do đó ở chế độ `auto`, việc kiểm duyệt chỉ diễn ra đúng như những gì cấu hình của bạn khai báo. Thiết lập bao phủ một phần vẫn hợp lệ: ví dụ chỉ cấu hình kiểm duyệt tin nhắn của khách hàng sẽ chỉ kiểm tra phía đầu vào và bỏ qua phía đầu ra.
- **`on`** — bắt buộc: cả hai checkpoint đều phải có model được cấu hình. Điều này được kiểm tra xác thực khi server khởi động và bất cứ khi nào một agent được tạo hoặc cập nhật với chế độ `on` — một model bị thiếu sẽ báo lỗi cấu hình ngay lập tức (fail fast) thay vì âm thầm bỏ qua một lớp an toàn mà bạn đã tuyên bố là bắt buộc. Nếu muốn bắt buộc một checkpoint trong khi chủ ý miễn trừ checkpoint còn lại, hãy cấu hình checkpoint được miễn trừ với provider `null` (xem bên dưới).
- **`off`** — tắt kiểm duyệt hoàn toàn cho agent này, bất kể cấu hình server có những gì.

Kiểm duyệt không thể cấu hình theo từng tin nhắn đơn lẻ: các bên gọi API không thể tùy chọn bật hay tắt kiểm duyệt cho một tin nhắn cụ thể nào.

## Kiểm duyệt tin nhắn khách hàng (Customer-message moderation)

Khi một tin nhắn của khách hàng được gửi đến phiên hội thoại của một agent có bật kiểm duyệt, nó sẽ đi qua mô hình được định tuyến tại **`moderation.customer`** trước khi bước vào session. Một tin nhắn bị gắn cờ (flagged) sẽ được lưu trữ với thuộc tính `flagged: true` và các tag kiểm duyệt của nó (`harassment`, `hate`, `jailbreak`, …) trong mảng `groups`. Kể từ đó, Parlant xử lý tin nhắn như thể đã bị che (censored) ở mọi nơi quan trọng:

- Văn bản bị gắn cờ không bao giờ lọt vào bất kỳ prompt nào. Mọi thành phần tiêu thụ — khớp rule, sinh phản hồi, chọn canned-response — chỉ nhìn thấy một thông báo kiểm duyệt kèm lý do ("tin nhắn này đã bị ẩn: quấy rối") thay vì nội dung gốc.
- Các policy có thể đặt điều kiện dựa trên nó ("khi tin nhắn gần nhất của khách hàng bị kiểm duyệt, …"), và agent có thể giải thích lý do tại sao tin nhắn không được xử lý.

## Kiểm duyệt tin nhắn của Agent (Agent-message moderation)

Mô hình được định tuyến tại **`moderation.agent`** kiểm tra các phản hồi hoàn chỉnh do chính agent sinh ra. Ở chế độ xuất tin nhắn dạng khối (block message-output mode), phản hồi phải vượt qua kiểm tra trước khi bất kỳ nội dung nào được hiển thị. Một phản hồi bị gắn cờ sẽ được **sinh lại (regenerated)** chứ không hiển thị: lý do kiểm duyệt (không bao giờ gửi kèm đoạn văn bản bị gắn cờ) được phản hồi ngược lại làm chỉ dẫn và agent sẽ thử lại, dùng chung ngân sách số lần thử lại (retry budget) với tính năng message review. Nếu vẫn bị gắn cờ sau những lần thử đó, lượt tương tác sẽ từ bỏ và tạo ra một tin nhắn cuối cùng giải thích rằng nó không thể phản hồi. Chỉ khi tin nhắn giải thích này *cũng* bị gắn cờ thì Parlant mới phát ra một chuỗi fallback cố định. Bất cứ khi nào một tin nhắn bị chặn, phán quyết (bao gồm cả các tag) sẽ được ghi lại trên metadata nội bộ của sự kiện phát ra phục vụ frontend và kiểm toán (audit).

Chuỗi fallback cứu cánh cuối cùng này có thể cấu hình trên responder thông qua container DI:

```python
from parlant.core.engines.compass.responder.responder import Responder


async def initialize_container(container: p.Container) -> None:
    container[Responder].moderation_fallback = (
        "Xin lỗi, tôi không thể phản hồi yêu cầu này lúc này. Tôi có thể giúp gì khác cho bạn không?"
    )
```

Lưu ý:

- Chỉ áp dụng cho chế độ Block: đầu ra dạng stream (streaming output) đã được truyền đi qua mạng ngay trong quá trình sinh tin nhắn, vì vậy vòng lặp streaming không thể chặn trước. Parlant ghi log cảnh báo khi khởi động và khi tạo/cập nhật agent nếu agent đó có cấu hình kiểm duyệt tin nhắn agent nhưng lại dùng chế độ xuất không phải block — hãy miễn trừ checkpoint đó bằng provider `null` nếu đó là chủ ý của bạn.
- Cơ chế kiểm tra an toàn theo hướng mở (fails open): nếu mô hình kiểm duyệt gặp lỗi, tin nhắn gốc vẫn được phát ra và một cảnh báo sẽ được ghi log. Kiểm duyệt là một lớp an toàn bổ sung trên quá trình sinh nội dung, chứ không phải là cổng chặn phát tin nhắn.

## Định tuyến các mô hình kiểm duyệt (Routing moderation models)

Hai checkpoint là các model route thông thường và được phân giải độc lập — thông thường chúng sẽ trỏ đến các mô hình khác nhau:

```python
models={
    "moderation.customer": p.ModelConfig("openai:omni-moderation-latest"),
    "moderation.agent": p.ModelConfig("openai:omni-moderation-latest"),
}
```

Kiểm duyệt hoàn toàn mang tính tự nguyện (opt-in): không provider nào đăng ký mô hình kiểm duyệt mặc định, vì vậy một cấu hình bao quát toàn provider như `models={"*": "openai"}` không bao giờ tự động bật kiểm duyệt — chỉ các route tường minh ở trên mới kích hoạt. Trong số các provider tích hợp sẵn, chỉ OpenAI cung cấp mô hình kiểm duyệt (`omni-moderation-latest`); các hệ thống triển khai trên provider khác có thể định tuyến các checkpoint kiểm duyệt tới một provider có hỗ trợ (hoặc một mô hình tùy chỉnh), hoặc để trống không cấu hình.

### Provider `null`

Định tuyến một checkpoint tới provider tích hợp sẵn `null` sẽ cấu hình nó với một service không bao giờ gắn cờ:

```python
models={
    "moderation.customer": p.ModelConfig("openai:omni-moderation-latest"),
    "moderation.agent": p.ModelConfig("null"),
}
```

Điều này sinh ra dành cho các agent cài đặt `moderation=on`: route thực sự đã được cấu hình, vì vậy yêu cầu bắt buộc được thỏa mãn, và cấu hình thể hiện rõ ràng rằng checkpoint này được chủ ý miễn trừ.

## Viết một mô hình kiểm duyệt tùy chỉnh

Một mô hình kiểm duyệt tùy chỉnh cần triển khai `ModerationService`:

```python
from parlant.core.nlp.moderation import (
    AgentModerationContext,
    CustomerModerationContext,
    ModerationCheck,
    ModerationService,
)

class MyGuard(ModerationService):
    async def moderate_customer(self, context: CustomerModerationContext) -> ModerationCheck:
        verdict = await my_classifier(context.message)
        return ModerationCheck(flagged=verdict.bad, tags=verdict.tags)
```

Cả hai context object đều chứa session và — đối với các kiểm tra phía agent — toàn bộ generic engine context của lượt tương tác (`context.engine_context`). Nhờ đó, một mô hình nhận biết ngữ cảnh có thể cân nhắc toàn bộ cuộc trò chuyện, các policy được khớp và kết quả tool, chứ không chỉ riêng văn bản tin nhắn. Kiểm duyệt phía khách hàng chạy ở ranh giới API trước khi lượt tương tác bắt đầu, vì vậy `engine_context` ở đó là `None`; tuy nhiên session (và lịch sử của nó) vẫn luôn có sẵn.

Hàm `moderate_agent` theo mặc định sẽ chạy cùng một logic kiểm tra như `moderate_customer`; hãy ghi đè hàm này khi việc kiểm duyệt phía agent cần hành xử khác biệt.
