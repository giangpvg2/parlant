# Các Điểm Móc Động Cơ (Engine Hooks)

Engine hooks là các hàm callback bạn đăng ký tại các thời điểm cố định trong vòng đời lượt tương tác của agent — khi một tin nhắn được sinh ra, khi các lời gọi tool được review, khi phiên hội thoại được nén, v.v. Engine sẽ gọi các hook này trong quá trình chạy, trao cho mỗi hàm context của lượt tương tác đang diễn ra cùng payload dữ liệu của sự kiện. Bạn sử dụng chúng để *quan sát* lượt tương tác (ghi log kiểm toán, đo lường metrics, tracing) và khi cần thiết, để *điều hướng* nó — bỏ qua một giai đoạn, từ chối một bước để nó sinh lại, hoặc dừng hẳn lượt tương tác và tự trả lời theo cách riêng của bạn.

Hooks là nửa mảnh ghép song hành với dependency-injection container. Container là nơi bạn hoán đổi *triển khai nào* mà một component sử dụng; hooks là nơi bạn theo dõi hoặc điều hướng *hành vi* của engine mà không cần thay thế bất kỳ component nào. Bạn chỉ cần viết các async function, nối chúng vào các điểm hook mà bạn quan tâm, và engine sẽ tự động thực thi chúng.

## Động lực thiết kế

Phần lớn những gì bạn muốn thực hiện xung quanh một agent không phải là thay đổi bản chất cách nó vận hành — mà là nắm bắt những gì nó đã làm và thỉnh thoảng can thiệp bổ sung logic tùy biến:

- **Khả năng quan sát (Observability):** Phát một chỉ số metric mỗi khi một tin nhắn được sinh ra, đo thời gian thực thi của từng bước suy luận, hoặc ghi log kiểm toán mỗi khi reviewer từ chối một tin nhắn. Những việc này cần chạy *bên trong* lượt tương tác, ngay thời điểm sự kiện xảy ra, với quyền truy cập vào trạng thái của lượt.
- **Sự can thiệp (Intervention):** Đi đường tắt qua một giai đoạn tốn kém khi có thể (chẳng hạn phát hiện câu chào hỏi đơn giản thì không cần khớp rule), từ chối một tin nhắn nháp hoặc lời gọi tool để bước đó sinh lại dưới sự điều chỉnh của bạn, hoặc dừng hẳn lượt tương tác để tự trả lời. Mỗi tình huống đều cần một cách thức để chỉ thị cho engine phải làm gì tại một thời điểm cụ thể.

Hooks cung cấp một giải pháp gọn gàng: các callback có kiểu dữ liệu rõ ràng, ổn định tại từng thời điểm vòng đời mà không cần fork mã nguồn Parlant hay kế thừa phức tạp các component của nó.

## Đăng ký Hooks

### `initialize_container`

Hooks được đăng ký thông qua container (xem [Dependency Injection](dependency-injection.md)): phân giải đối tượng `CompassHooks` đã bind trong hàm `initialize_container` và nối các callback của bạn vào các điểm mong muốn:

```python
import parlant.sdk as p


async def initialize_container(container: p.Container) -> None:
    hooks = container[p.CompassHooks]

    async def on_message_generated(
        context: p.EngineContext,
        message: str,
        exc: Exception | None,
    ) -> p.CompassHookResult:
        my_metrics.increment("messages.generated")
        return p.CompassHookResult.CALL_NEXT

    hooks.on_message_generated.append(on_message_generated)


async with p.Server(initialize_container=initialize_container) as server:
    ...
```

Mỗi điểm hook là một `list` thông thường, vì vậy bạn có thể nối nhiều callback vào cùng một điểm; chúng chạy theo thứ tự đăng ký như một chuỗi liên hoàn. Hooks được chia sẻ trên toàn server, không theo từng agent — một callback sẽ kích hoạt cho mọi lượt của mọi agent.

### Chữ ký hàm của Hook (Hook Signature)

Mọi hook đều có cùng cấu trúc chữ ký hàm:

```python
async def hook(
    context: p.EngineContext,
    payload: <tùy thuộc vào hook>,
    exc: Exception | None,
) -> p.CompassHookResult: ...
```

- **`context`**: Là đối tượng `p.EngineContext` trực tiếp của lượt tương tác — bao gồm session, agent, customer, lịch sử tương tác, trạng thái làm việc và các event emitter. Hook có thể đọc toàn bộ thông tin này, thậm chí có thể tự phát các sự kiện của riêng nó.
- **`payload`**: Chứa nội dung dữ liệu mà hook quan tâm. Kiểu dữ liệu phụ thuộc vào từng hook — số nguyên `int` biểu thị số bước, chuỗi `str` tin nhắn, một `Sequence` các tool call, hoặc một trong các dataclass payload dưới `p.CompassHookPayload` (`GaveUp`, `ToolCallOutcome`, `ToolCallsReviewed`, `MessageReviewed`, `Compacted`, v.v.). Nhiều hook không mang dữ liệu và truyền `None`.
- **`exc`**: Luôn là `None` cho mọi hook ngoại trừ `on_error` (nhận exception mà engine bắt được).

Hooks chạy **trực tiếp (inline)** và được await ngay bên trong lượt tương tác, vì vậy một hook chạy chậm sẽ làm tăng độ trễ phản hồi. Hãy giữ cho chúng chạy nhanh, hoặc ủy thác các tác vụ nặng cho một background task.

### Giá trị trả về (Return Value)

Một hook trả về một `p.CompassHookResult` quyết định điều gì sẽ diễn ra tiếp theo:

- **`CALL_NEXT`** — chạy hook tiếp theo được đăng ký trên điểm này (nếu có). Đây là giá trị trả về thông thường cho mọi tác vụ chỉ thuần túy quan sát.
- **`RESOLVE`** — bỏ qua công việc thông thường của engine tại điểm này và nhảy cóc về phía trước, không chạy các hook còn lại trên điểm này. Những gì bị bỏ qua phụ thuộc vào từng hook: `RESOLVE` trên `on_preparing` sẽ bỏ qua khâu discovery/matching và chuyển thẳng tới phản hồi trực tiếp (dành cho câu chào hỏi); trên `on_reviewing_tool_calls` / `on_reviewing_message` nó bỏ qua bước review và coi như đã được phê duyệt; trên `on_giving_up` nó bỏ qua tin nhắn xin lỗi mặc định vì handler của bạn đã tự phát câu trả lời thay thế.
- **`BAIL`** — kích hoạt nhánh phủ định / dừng lại của bất cứ thứ gì hook này bao bọc. Tại các cổng đầu lượt (`on_acknowledging` / `on_acknowledged` / `on_preparing` / `on_generating_messages`), nó **dừng toàn bộ lượt tương tác**; tại các review hook (`on_reviewing_tool_calls` / `on_reviewing_message`), nó **từ chối** cuộc gọi/tin nhắn — bước xử lý sẽ sinh lại với ghi chú `note` trong payload, hoặc từ bỏ ngay lập tức nếu hook đặt `payload.give_up = True`.

Nếu không có hook nào trả về `RESOLVE` hoặc `BAIL`, lượt tương tác sẽ tiếp tục diễn ra bình thường.

## Danh sách các điểm Hook

### Vòng đời lượt tương tác (Turn lifecycle)

| Hook | Thời điểm kích hoạt | Payload |
| --- | --- | --- |
| `on_error` | Engine bắt được một lỗi runtime | — (lỗi nằm trong `exc`) |
| `on_acknowledging` | Ngay trước sự kiện trạng thái ghi nhận (acknowledgement) | — |
| `on_acknowledged` | Ngay sau sự kiện trạng thái ghi nhận | — |
| `on_preparing` | Ngay trước khi giai đoạn chuẩn bị (khớp rule, chọn tool) bắt đầu | — |
| `on_generating_messages` | Ngay trước khi quá trình sinh tin nhắn bắt đầu | — |
| `on_message_generated` | Một tin nhắn đã được sinh ra (chế độ blocking: chưa phát ra ngoài) | `str` (nội dung tin nhắn) |
| `on_messages_emitted` | Tất cả tin nhắn đã được phát vào session | `Sequence[str]` (danh sách tin nhắn đã phát của lượt) |

**`on_messages_emitted`** kích hoạt một lần cho mỗi lượt tương tác, sau khi câu trả lời đã thực sự đến được với khách hàng, và payload là mọi tin nhắn mà lượt đó đã phân phối theo đúng thứ tự hiển thị. Đây là vị trí lý tưởng cho các tác vụ phản ứng sau khi cuộc trao đổi kết thúc — ghi vào bộ nhớ bên ngoài (external memory), kiểm toán audit, phân tích analytics.

`RESOLVE` trên **`on_preparing`** bỏ qua discovery/matching và phản hồi trực tiếp — hữu ích khi bạn nhận diện nhanh một đầu vào đơn giản (câu chào) và muốn phản hồi nhanh không cần rule.

### Vòng lặp suy luận của Compass Engine

| Hook | Thời điểm kích hoạt | Payload |
| --- | --- | --- |
| `on_step_started` | Ngay trước khi một bước ReAct thực thi | `int` (số thứ tự bước) |
| `on_step_completed` | Một bước đã kết thúc (không tính các lần restart do reviewer ép buộc) | `int` (số thứ tự bước) |
| `on_message_updated` | Một tin nhắn streaming có thêm nội dung mới (chỉ áp dụng chế độ stream) | `str` (toàn bộ văn bản cho đến hiện tại) |
| `on_giving_up` | Vòng lặp hết lượt thử và chuẩn bị ép buộc gửi tin nhắn từ bỏ cuối cùng | `CompassHookPayload.GaveUp` (`reason`, `steps`, `kind`) |

**`on_giving_up`** là vị trí duy nhất bạn có thể thay thế lời nói từ bỏ của Parlant. Mặc định hệ thống tốn thêm một lệnh gọi mô hình để nói câu xin lỗi không giúp được gì. Trả về `RESOLVE` và câu đó sẽ không bao giờ được sinh ra: handler của bạn toàn quyền phát thông điệp của riêng mình (hoặc im lặng chuyển giao cho con người).

### Các lệnh gọi Tool (Compass engine)

| Hook | Thời điểm kích hoạt | Payload |
| --- | --- | --- |
| `on_reviewing_tool_calls` | Ngay trước khi reviewer kiểm tra các lệnh gọi tool đề xuất | `CompassHookPayload.ReviewingToolCalls` |
| `on_tool_calls_reviewed` | Ngay sau khi review xong, trước khi sinh lại (nếu có) | `CompassHookPayload.ToolCallsReviewed` |
| `on_calling_tools` | Ngay trước khi các lệnh gọi tool đã duyệt được chạy | `Sequence[ToolCallPart]` |
| `on_tool_calls_completed` | Các lệnh gọi tool của bước xử lý hoàn tất | `Mapping[str, list[CompassHookPayload.ToolCallOutcome]]` |

### Review tin nhắn (Compass engine)

| Hook | Thời điểm kích hoạt | Payload |
| --- | --- | --- |
| `on_reviewing_message` | Ngay trước khi reviewer kiểm tra tin nhắn nháp | `CompassHookPayload.ReviewingMessage` |
| `on_message_reviewed` | Ngay sau khi review xong, trước khi sinh lại (nếu có) | `CompassHookPayload.MessageReviewed` |

### Nén phiên (Compass engine)

| Hook | Thời điểm kích hoạt | Payload |
| --- | --- | --- |
| `on_compacting` | Ngay trước khi nén lịch sử phiên | `int` (số token trước khi nén) |
| `on_compacted` | Ngay sau khi nén xong | `CompassHookPayload.Compacted` |

## Handler theo từng Rule (Per-rule handlers)

Một số trường trong `CompassHooks` không phải là điểm hook thông thường mà là các bảng ánh xạ handler theo từng rule cụ thể, với chữ ký hàm `(context, RuleEvaluation) -> None`:

- `on_rule_matched_handlers`: Gọi khi một rule cụ thể được khớp.
- `on_rule_discovered_handlers`: Gọi khi một rule bước vào session working set.

Thông thường bạn không cần thao tác trực tiếp với các map này mà dùng tham số `on_matched` hoặc `on_discovered` khi tạo rule qua SDK:

```python
async def on_matched(context: p.EngineContext, evaluation: p.RuleEvaluation) -> None:
    audit_log.info(f"Rule matched: {evaluation.rule.id}")


await agent.create_policy(
    content="When the customer asks for a refund, explain the refund policy",
    on_matched=on_matched,
)
```

## Sổ tay công thức thực tế (Cookbook)

### Thay thế tin nhắn từ bỏ khi gặp sự cố (Give-up message)

```python
async def initialize_container(container: p.Container) -> None:
    hooks = container[p.CompassHooks]

    async def hand_off_instead_of_apologizing(
        ctx: p.EngineContext,
        payload: p.CompassHookPayload.GaveUp,
        exc: Exception | None,
    ) -> p.CompassHookResult:
        ticket = await support_desk.open_ticket(
            customer_id=ctx.customer.id,
            session_id=ctx.session.id,
            summary=payload.reason,
            steps_taken=payload.steps,
        )

        # Chuyển session sang chế độ thủ công để agent không tự động trả lời nữa
        await p.Session.current.update(mode="manual")

        await ctx.session_event_emitter.emit_message_event(
            trace_id=ctx.tracer.trace_id,
            data=(
                f"Tôi không thể tự giải quyết vấn đề này. Tôi đã mở phiếu hỗ trợ #{ticket.id} "
                "và nhân viên hỗ trợ sẽ tiếp nhận ngay tại đây."
            ),
        )

        return p.CompassHookResult.RESOLVE

    hooks.on_giving_up.append(hand_off_instead_of_apologizing)
```

### Từ chối tin nhắn không hợp lệ mà không cần qua Reviewer

Khi bạn có thể phát hiện vi phạm trực tiếp bằng code:

```python
async def on_reviewing_message(
    context: p.EngineContext,
    payload: p.CompassHookPayload.ReviewingMessage,
    exc: Exception | None,
) -> p.CompassHookResult:
    if leaks_another_customers_data(payload.message):
        payload.note = "Không bao giờ để lộ dữ liệu của khách hàng khác; hãy xin lỗi và đề nghị giúp đỡ tài khoản của chính họ."
        return p.CompassHookResult.BAIL
    return p.CompassHookResult.CALL_NEXT
```

## So sánh Hooks và Container

- Sử dụng **hooks** (`container[p.CompassHooks]` trong `initialize_container`) để *quan sát hoặc điều hướng một lượt tương tác* — phản ứng với sự kiện, ghi chép hoặc can thiệp dừng lượt.
- Sử dụng **container** (`configure_container`) để *thay thế một triển khai* — thay đổi logger, store hoặc optimization policy.
