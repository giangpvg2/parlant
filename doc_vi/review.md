# Đánh Giá Tool & Tin Nhắn Tích Hợp (Integrated Tool & Message Reviews)

Tính năng Review (đánh giá kiểm duyệt) là một trong những tính năng mạnh mẽ nhất của Parlant.

Một lượt review là một đợt kiểm tra độc lập mà Parlant thực thi đối với những gì một lượt tương tác chuẩn bị thực hiện: các lời gọi tool mà nó đề xuất chạy, hoặc tin nhắn mà nó chuẩn bị gửi đi. Nếu đầu ra đó có nguy cơ vi phạm các chỉ dẫn quản lý agent, Parlant sẽ chặn đứng nó lại. Phán quyết này có tính thực thi tuyệt đối vì nó diễn ra trước khi bất kỳ điều gì xảy ra: một lời gọi tool bị từ chối sẽ không bao giờ được chạy, một tin nhắn bị từ chối sẽ không bao giờ hiển thị cho người dùng, và bước đó sẽ được sinh lại với chỉ dẫn về cách khắc phục vi phạm.

Bạn có thể yêu cầu review theo kiểu khai báo (declaratively) — dưới dạng mặc định trên toàn agent, chỉ khi các observation hoặc policy cụ thể được áp dụng, hoặc (đối với các tool cụ thể) bằng cách đánh dấu tool là `consequential`.

## Động lực thiết kế

Sinh ra một câu trả lời và phán đoán tính tuân thủ (compliance) của nó là hai nhiệm vụ hoàn toàn khác nhau, và chúng thường xung đột lẫn nhau.

Mô hình sinh phản hồi luôn nỗ lực tỏ ra hữu ích trong mạch của cuộc trò chuyện. Dưới áp lực đó, đôi khi nó có thể đi chệch hướng: gọi một tool mà tình huống không cho phép, tự nhận một hành động đã thành công trong khi chưa có tool nào thực sự chạy, hoặc diễn đạt một thông điệp theo cách mà policy ngăn cấm. Bắt chính lượt sinh đó tự bắt lỗi của bản thân là điều không đủ tin cậy trong thực tế — bởi suy luận (và mô hình) tạo ra sai sót cũng chính là thứ được yêu cầu đi tìm lỗi.

Tính năng Review tách rời hai nhiệm vụ này. Một lượt gọi mô hình độc lập — với route mô hình riêng, prompt riêng và hoàn toàn không bị thiên vị bởi bản nháp — sẽ đối chiếu đầu ra của bước xử lý với các chỉ dẫn của agent trước khi đầu ra đó có hiệu lực. Vì nó chạy *trước* khi thực thi và *trước* khi phân phối tin nhắn, phán quyết của nó có thể thực thi triệt để: một tool call bị từ chối không bao giờ được chạy, và một tin nhắn bị từ chối không bao giờ hiển thị.

Điều này có ý nghĩa sống còn ở những nơi mà sai sót gây tổn thất lớn: các tool có hậu quả thực tế (thanh toán, hủy dịch vụ, cập nhật hồ sơ) và các cuộc trò chuyện bị quản lý bởi các chính sách nghiêm ngặt (tuân thủ pháp lý, quy định thương hiệu). Review cho phép bạn chỉ chi trả chi phí bảo vệ này ở đúng nơi bạn cần, thay vì phải nâng mức effort của toàn bộ agent lên cao.

## Hướng dẫn thực hành

Để trải nghiệm tính năng, hãy bắt đầu với một agent kiểm duyệt mọi thứ nó làm:

```python
import parlant.sdk as p


async with p.Server(models={"*": "openai"}) as server:
    agent = await server.create_agent(
        id="my-agent",
        name="Banking Agent",
        instructions="Help customers manage their accounts.",
        message_review=True,   # review mọi tin nhắn nháp trước khi gửi
        tool_review=True,      # review mọi đề xuất gọi tool trước khi chạy
    )
```

Đó là toàn bộ cấu hình cần thiết. Kể từ thời điểm này, bất cứ khi nào một lượt tương tác soạn thảo tin nhắn, Parlant sẽ giữ lại, đối chiếu với chỉ dẫn của agent, và chỉ gửi đi nếu vượt qua kiểm tra. Bất cứ khi nào một lượt đề xuất gọi tool, chúng sẽ được review trước khi bất kỳ lệnh gọi nào được thực thi. Quan sát một phiên hội thoại, bạn sẽ thấy các trạng thái ngắn gọn: "Reviewing message" và "Reviewing tool use".

Tuy nhiên, việc review trên toàn agent thường tốn kém hơn mức cần thiết, vì nó cộng thêm độ trễ và chi phí vào mọi lượt tương tác. Hai cơ chế kích hoạt chi tiết hơn thường được ưa chuộng hơn:

**Review theo từng Rule (Per-rule review)** — một rule có thể yêu cầu review chỉ cho những lượt mà nó có ý nghĩa:

```python
await agent.create_policy(
    title="Refund limits",
    content=(
        "Refunds above $500 require a manager approval reference. "
        "Never promise such a refund without one."
    ),
    trigger_message_review=True,
)
```

Giờ đây, việc review tin nhắn chỉ chạy trong những lượt mà policy này thực sự được khớp. Các cuộc trò chuyện chào hỏi thông thường vẫn đi theo con đường nhanh không bị chậm trễ.

**Công cụ có tác động lớn (Consequential tools)** — người viết tool có thể đánh dấu tool có tác động thực tế, điều này kích hoạt tool review bất cứ khi nào tool đó xuất hiện trong tập đề xuất gọi hàm, bất kể cấu hình trên agent hay rule:

```python
@p.tool(consequential=True)
async def cancel_order(order_id: str) -> p.ToolResult:
    ...
```

Ba cơ chế kích hoạt này kết hợp với nhau: review sẽ chạy nếu *bất kỳ* cơ chế nào yêu cầu nó. Một rule có thể thêm review vào một lượt, nhưng không gì có thể hủy bỏ một lượt review mà thành phần khác đã yêu cầu.

## Hai lộ trình Review độc lập

Tool review và Message review hoạt động hoàn toàn độc lập — một lượt có thể chạy một trong hai, cả hai, hoặc không chạy cái nào:

| | Tool review | Message review |
|---|---|---|
| **Đối tượng đánh giá** | Suy luận của bước xử lý cùng với các lời gọi tool được đề xuất | Bản nháp tin nhắn hoàn chỉnh |
| **Thời điểm chạy** | Sau khi một bước đề xuất tool call, trước khi bất kỳ tool nào thực thi | Sau khi một bước sinh tin nhắn hoàn tất, trước khi tin nhắn được phát ra |
| **Kích hoạt bởi** | `tool_review=True` trên agent, rule được khớp có `trigger_tool_review=True`, hoặc có consequential tool trong tập lệnh gọi | `message_review=True` trên agent, hoặc rule được khớp có `trigger_message_review=True` |
| **Khi vượt qua** | Các lệnh gọi được commit và thực thi (có thể mang theo ghi chú TODO cho bước sau) | Tin nhắn được chuyển phát tới người dùng |
| **Khi vi phạm** | Các lệnh gọi bị hủy bỏ và bước xử lý chạy lại với suy luận đã được hiệu chỉnh | Tin nhắn bị hủy bỏ và bước xử lý sinh lại; người dùng không bao giờ nhìn thấy |

Các điểm cốt lõi cần nắm rõ:

- **Mức effort tối thiểu:** Ở mức `Effort.MIN`, không có review nào chạy cả, bất kể có yêu cầu hay không — MIN là mức chi phí tối thiểu của Parlant (xem [Nỗ Lực Thích Ứng](adaptive-effort.md)). Mọi mức effort khác đều tuân thủ yêu cầu review, và effort cao hơn cho phép nhiều lần thử sinh lại hơn sau khi bị từ chối.
- **Truyền phát trực tiếp (Streaming):** Khi message review hoạt động trong một lượt, tin nhắn sẽ được đệm lại và đánh giá toàn bộ thay vì truyền phát từng token một — vì một tin nhắn đã review thì không thể hiển thị dở dang một nửa.
- **Tác động đến việc khớp Rule:** Việc thiết lập `trigger_message_review` hoặc `trigger_tool_review` trên một rule cũng sẽ tự động nâng cấp độ kỹ lưỡng khi *khớp* rule đó. Review chỉ kích hoạt ở các lượt mà rule thực sự áp dụng, vì vậy Parlant kiểm tra riêng lẻ cho rule này ở mỗi lượt, thay vì chỉ dựa vào tìm kiếm tương đồng.
- **Tuyên bố hành động không có căn cứ:** Message review luôn thực thi một quy tắc tích hợp sẵn: một tin nhắn tuyên bố hoặc ám chỉ rằng một hành động đã được thực hiện (đã hủy đơn hàng, đã gửi email, đã trừ tiền) bắt buộc phải có kết quả tool thực tế chứng minh đằng sau. Việc hứa hẹn một hành động sắp diễn ra mà không có tool nào chạy sẽ bị coi là vi phạm kể cả khi các phần khác đều tuân thủ.

## Ví dụ sử dụng

Các cờ review được chấp nhận ở mọi nơi tạo rule — cả `create_policy` lẫn `create_observation`.

Một observation khiến mọi lượt nó khớp đều được review kỹ lưỡng:

```python
await agent.create_observation(
    condition="the customer is discussing account closure",
    trigger_message_review=True,
    trigger_tool_review=True,
)
```

Một policy mang tool mà các lệnh gọi của nó luôn được review:

```python
await agent.create_policy(
    title="Wire transfers",
    content="Execute wire transfers only after verbal confirmation of the amount and recipient.",
    tools=[execute_wire_transfer],
    trigger_tool_review=True,
)
```

Kết hợp với `trigger_effort` (xem [Nỗ Lực Thích Ứng](adaptive-effort.md)) — vừa nâng effort vừa review khi tình huống nghiêm trọng:

```python
await agent.create_observation(
    condition="the customer disputes a charge or threatens legal action",
    trigger_effort=p.Effort.HIGH,
    trigger_message_review=True,
)
```

Cấu hình mặc định theo agent kết hợp bổ sung theo rule:

```python
agent = await server.create_agent(
    id="my-agent-2",
    name="Claims Agent",
    instructions="Process insurance claims.",
    tool_review=True,          # mọi lệnh gọi tool đều được review...
)

await agent.create_policy(
    title="Claim denial wording",
    content="When denying a claim, cite the specific policy clause.",
    trigger_message_review=True,       # ...và tin nhắn được review ở các lượt từ chối khiếu nại
)
```

## Sử dụng nâng cao

### Chọn mô hình Review

Bộ reviewer yêu cầu các route mô hình riêng — `review.tools` và `review.message` — giúp bạn chỉ định một mô hình rẻ hơn hoặc nghiêm ngặt hơn độc lập với mô hình sinh phản hồi:

```python
async with p.Server(
    models={
        "*": "openai",
        "review.*": p.ModelConfig("gemini:gemini-3.5-flash-lite"),
        "review.message[effort>=high]": p.ModelConfig(
            "openai:gpt-5.4-mini",
            reasoning="medium",
        ),
    },
) as server:
    ...
```

Khi `ModelConfig.reasoning` không được cấu hình, reviewer tự chọn độ sâu suy luận từ mức effort của lượt, và tăng lên khi có rule trọng số HIGH được khớp.

### Quan sát Review bằng Engine Hooks

Bốn hook trong engine bao bọc các lộ trình review — hữu ích cho việc ghi log kiểm toán (audit trails), đo lường metrics, hoặc debug lý do bước xử lý bị sinh lại:

```python
async def initialize_container(container: p.Container) -> None:
    hooks = container[p.CompassHooks]

    async def on_tool_calls_reviewed(
        context: p.EngineContext,
        payload: p.CompassHookPayload.ToolCallsReviewed,
        exc: Exception | None,
    ) -> p.CompassHookResult:
        if not payload.passed:
            audit_log.warning(f"Tool calls rejected: {payload.adjusted_reasoning}")
        return p.CompassHookResult.CALL_NEXT

    async def on_message_reviewed(
        context: p.EngineContext,
        payload: p.CompassHookPayload.MessageReviewed,
        exc: Exception | None,
    ) -> p.CompassHookResult:
        if not payload.passed:
            audit_log.warning(f"Message rejected: {payload.adjusted_reasoning}")
        return p.CompassHookResult.CALL_NEXT

    hooks.on_tool_calls_reviewed.append(on_tool_calls_reviewed)
    hooks.on_message_reviewed.append(on_message_reviewed)


async with p.Server(initialize_container=initialize_container) as server:
    ...
```

Các hook gồm: `on_reviewing_tool_calls` / `on_tool_calls_reviewed` và `on_reviewing_message` / `on_message_reviewed`.

### Tùy biến Prompt Review

Các prompt review được xây dựng thông qua cơ chế tùy biến prompt chuẩn dưới các route key `review.tools` và `review.message`, với các section mang tên `reviewer.tools.*` và `reviewer.message.*`. Xem [Tùy Biến Prompt](prompt-customization.md).

## Cơ chế chi tiết (Mechanism)

### Tool review

Khi một bước phản hồi kết thúc với các lệnh gọi tool đang chờ xử lý và tính năng review được kích hoạt, reviewer nhận suy luận của bước đó và các lệnh gọi đề xuất, cùng với các chỉ dẫn quản lý lượt. Nó trả lời bằng một phán quyết boolean gọn gàng (`ReviewSchema`): liệu suy luận hoặc các lệnh gọi có vi phạm hoặc đi chệch khỏi chỉ dẫn hay không?

- **Phán quyết hợp lệ (Clean verdict):** Các lệnh gọi được commit và thực thi theo thứ tự. Reviewer vẫn có thể trả về một `todo`: tóm tắt những gì agent phải tiếp tục làm trước khi đưa ra câu trả lời cuối cùng. TODO này được lưu vào trạng thái lượt và render vào chỉ dẫn của bước tiếp theo.
- **Phán quyết vi phạm (Breach verdict):** Reviewer trả về `adjusted_reasoning`: một bản suy luận thay thế hoàn chỉnh cho bước xử lý, được viết như thể agent đã suy luận đúng đắn ngay từ đầu. Các lệnh gọi đề xuất bị hủy bỏ mà không chạy, suy luận sai lầm được thay bằng bản đã hiệu chỉnh, và bước xử lý chạy lại.

### Message review

Khi một bước kết thúc với một tin nhắn và không có tool call nào đang chờ xử lý, tin nhắn nháp được giữ lại và review toàn bộ. Nếu agent có câu trả lời soạn sẵn (canned responses), các câu liên quan nhất sẽ được đưa vào prompt review làm chỉ dẫn phong cách và tính tuân thủ. Quy tắc kiểm tra tuyên bố hành động không căn cứ luôn có mặt trong prompt.

Tin nhắn hợp lệ sẽ được chuyển phát bình thường. Nếu vi phạm, `adjusted_reasoning` của reviewer sẽ thay thế suy luận của bước, bước xử lý sinh lại từ đầu và bản nháp vi phạm không bao giờ đến tay người dùng.

### Ngân sách thử lại (Retry Budget)

Mỗi lần reviewer từ chối sẽ khiến bước xử lý khởi động lại (đây gọi là *semantic failure*). Số lần thử lại tối đa mà một lượt chấp nhận phụ thuộc vào mức effort của nó:

| Effort | Số lần thử lại tối đa |
|---|---|
| MIN | 1 (review không chạy ở MIN) |
| LOW | 2 |
| MEDIUM | 3 |
| HIGH | 5 |
| MAX | 10 |

Nếu vượt quá ngân sách thử lại, Parlant ngừng cố gắng thực hiện tác vụ và đưa ra một tin nhắn cuối cùng giải thích cho người dùng rằng nó không thể hoàn thành yêu cầu. Hệ thống sẽ không bao giờ gửi đi một câu trả lời đã liên tục thất bại trong khâu review. Bạn có thể thay thế tin nhắn bỏ cuộc này bằng logic riêng thông qua hook `on_giving_up` (xem [Engine Hooks](hooks.md#take-over-the-give-up-message)).
