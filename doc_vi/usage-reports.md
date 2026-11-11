# Báo Cáo Sử Dụng và Minh Bạch Chi Phí (Usage Reporting and Cost Visibility)

Parlant trả lời 4 câu hỏi về chi phí, mỗi câu hỏi tương ứng với một lớp riêng biệt — việc hạch toán thô luôn luôn được bật, và mỗi lớp tiếp theo là tùy chọn kích hoạt bổ sung:

| Câu hỏi | Lớp chức năng |
|---|---|
| Mỗi mô hình đã sử dụng bao nhiêu request và token? | Bản ghi sử dụng (Usage records - luôn bật) |
| Lượng sử dụng đó tốn bao nhiêu chi phí? | [Bảng giá (Pricing)](#bảng-giá-pricing) |
| Một phiên hội thoại đã vượt quá hạn mức chưa? | [Ngân sách phiên (Session budgets)](#ngân-sách-phiên-session-budgets) |
| Có nên tiếp tục các công việc engine bị tính phí không? | [Kiểm soát chi phí (Cost control)](#kiểm-soát-chi-phí-cost-control) |

## Những gì được ghi nhận (What gets recorded)

Mọi yêu cầu sinh phản hồi (generation) và embedding đều báo cáo mức độ sử dụng: số lượng request, input tokens, cached input tokens, output tokens và các bộ đếm tùy chọn đặc thù của provider (ví dụ: reasoning tokens, đồng hồ đo cache-write). Parlant tổng hợp các dữ liệu này theo từng trace thực thi, theo từng provider và model, rồi lưu trữ bản ghi bền vững cùng phiên hội thoại sau khi quá trình thực thi kết thúc.

Một lượt tương tác thông thường có một lần thực thi. Một thao tác chạy ngầm `Session.emit_tool_result()` đã hoàn tất và mỗi phản hồi tiếp nối sinh ra qua `Agent.utter()` hoặc `Agent.queue_response()` đều có trace riêng và các bản ghi sử dụng bất biến của riêng chúng.

```python
await p.Session.current.emit_tool_result(my_tool, result)
await p.Agent.current.queue_response()
```

Mức sử dụng được lưu theo khóa `provider:model` — cùng định dạng với cú pháp model route, ví dụ như `anthropic:claude-sonnet-5-5` hoặc `openrouter:openai/gpt-5.6-terra`. Phần provider là định danh mà adapter báo cáo: tiền tố của provider tích hợp sẵn (`openai`, `gemini`, `anthropic`, `openrouter`, `litellm`) hoặc bất kỳ tên nào bạn đặt cho adapter tùy chỉnh (xem [Đặt tên provider](#đặt-tên-provider)). Giữ lại provider trong key là rất quan trọng vì cùng một mô hình có thể được truy cập qua nhiều provider khác nhau với các mức giá khác nhau: `openai:gpt-5.5` và `openrouter:openai/gpt-5.5` được đếm, định giá và báo cáo hoàn toàn tách biệt.

Một điểm tinh tế: Để đảm bảo tốc độ phản hồi, Parlant đôi khi kích hoạt cơ chế *hedging* cho một yêu cầu mô hình bị chậm trễ — nó sẽ gửi một yêu cầu bản sao giống hệt và sử dụng kết quả của yêu cầu nào hoàn thành trước. Cả hai lần thử đều bị tính phí từ nhà cung cấp, do đó cả hai đều được kiểm đếm: lần thử thua cuộc vẫn được phép hoàn tất và số token của nó được cộng vào trước khi bản ghi của lượt được lưu trữ.

## Bảng giá (Pricing)

Bản ghi sử dụng chỉ đếm token; để chuyển token thành chi phí tiền tệ, Parlant cần có giá. Hãy cung cấp cho server một bảng giá (tính trên 1 triệu đơn vị sử dụng), và mọi bản ghi lượt tương tác sau đó sẽ được tính giá tự động:

```python
from decimal import Decimal
import parlant.sdk as p

pricing = await server.set_pricing(
    {
        "gemini-3.1-flash-lite": p.ModelPricing(
            input_tokens=Decimal("0.10"),
            cached_input_tokens=Decimal("0.025"),
            output_tokens=Decimal("0.40"),
        ),
    },
    currency="USD",  # Mặc định
)
```

Việc đặt bảng giá kích hoạt báo cáo chi phí ngay lập tức mà không cần cấu hình budget. Việc thay thế bảng giá chỉ ảnh hưởng đến các lượt tương lai — một lượt đang chạy dở vẫn giữ nguyên snapshot lúc nó bắt đầu. Trường `ModelPricing.extra` định giá cho các chỉ số đo lường đặc thù của provider (Anthropic cache writes, Gemini cache storage, reasoning tokens tính phí riêng).

### Khóa trong bảng giá (Price table keys)

Một mục trong bảng giá có thể được gán khóa theo 1 trong 2 cách:

- **Chỉ tên mô hình (Bare model id):** (`"gemini-3.1-flash-lite"`) định giá cho mô hình đó dưới *bất kỳ* provider nào. Đây là trường hợp phổ biến: một mức giá duy nhất cho model bất kể qua đường nào.
- **Khóa dạng `provider:model`:** (`"azure-eu:gpt-5.5"`) định giá cho mô hình đó khi được phục vụ bởi đúng provider chỉ định. Khi cả hai dạng cùng tồn tại, khóa chính xác `provider:model` sẽ thắng đối với provider đó, và khóa thông thường sẽ áp dụng cho các provider còn lại.

Ví dụ:

```python
pricing = await server.set_pricing(
    {
        # Giá thông thường của mô hình ở mọi nơi phục vụ...
        "gpt-5.5": p.ModelPricing(
            input_tokens=Decimal("1.25"),
            cached_input_tokens=Decimal("0.125"),
            output_tokens=Decimal("10"),
        ),
        # ...ngoại trừ khi đi qua provider này với chi phí cao hơn.
        "azure-eu:gpt-5.5": p.ModelPricing(
            input_tokens=Decimal("1.50"),
            cached_input_tokens=Decimal("0.15"),
            output_tokens=Decimal("12"),
        ),
    },
)
```

### Chi phí do Provider tự báo cáo (Provider-reported charges)

Một số provider tự định giá mức sử dụng: OpenRouter và LiteLLM báo cáo chi phí USD có thẩm quyền của họ cùng với mỗi yêu cầu, vì vậy một lượt tương tác được tạo thành hoàn toàn từ các hoạt động của họ sẽ có báo cáo chi phí ngay cả khi không có bảng giá — và [ngân sách phiên](#ngân-sách-phiên-session-budgets) cũng hoạt động bình thường mà không cần bảng giá.

### Đặt tên Provider (Naming a provider)

Khi bạn tự xây dựng một adapter — cho một model provider tùy chỉnh hoặc để kết nối với một nhà cung cấp qua hai tài khoản khác nhau — hãy cung cấp định danh provider riêng với tham số `provider_name`:

```python
from parlant.adapters.nlp.openai_service import OpenAIReactGenerator

primary = OpenAIReactGenerator(model="gpt-5.5", logger=logger)
eu_region = OpenAIReactGenerator(
    model="gpt-5.5",
    logger=logger,
    api_key=eu_api_key,
    provider_name="openai-eu",
)
```

Mức sử dụng từ `primary` sẽ mang khóa `openai:gpt-5.5`; mức sử dụng từ `eu_region` mang khóa `openai-eu:gpt-5.5`, cho phép bạn định giá riêng trong bảng giá (`"openai-eu:gpt-5.5"`).

## Đọc mức sử dụng từ Session API

`GET /sessions/{id}` trả về một bảng ánh xạ `usage` theo trace ID:

```json
{
  "usage": {
    "<trace_id>": {
      "timestamp_utc": "2026-07-16T12:34:56Z",
      "requests": {
        "gemini:gemini-3.1-flash-lite": {
          "request_count": 3,
          "input_tokens": 48210,
          "output_tokens": 512,
          "cached_input_tokens": 45800,
          "extra": {"reasoning_tokens": 128}
        },
        "openrouter:anthropic/claude-sonnet-5": {
          "request_count": 1,
          "input_tokens": 9120,
          "output_tokens": 240,
          "cached_input_tokens": 0,
          "extra": {"reported_cost": "0.030960"}
        }
      },
      "costs": {
        "currency": "USD",
        "total": "0.032385",
        "per_model": {
          "gemini:gemini-3.1-flash-lite": "0.001425",
          "openrouter:anthropic/claude-sonnet-5": "0.030960"
        },
        "per_provider": {
          "gemini": "0.001425",
          "openrouter": "0.030960"
        }
      }
    }
  },
  "costs": {
    "currency": "USD",
    "total": "0.032385",
    "per_model": { "...": "tổng cộng trên mọi lượt" },
    "per_provider": { "...": "tổng cộng trên mọi lượt" }
  }
}
```

Trường `costs` ở cấp cao nhất thể hiện chi phí của toàn bộ phiên: chi phí của mọi lượt được cộng dồn theo model và theo provider.

## Ngân sách Phiên (Session Budgets)

Budget (ngân sách) biến chi phí thành một hạn mức kiểm soát: nó đo lường mức chi tiêu của phiên và cho phép bạn hành động khi vượt quá ngưỡng:

```python
budget = await server.create_session_budget(
    name="conversation-cap",
    value=Decimal("1.50"),          # tính theo đơn vị tiền tệ của bảng giá; mặc định là USD
    # window=timedelta(hours=24),   # cửa sổ trượt tùy chọn
)
```

Một budget không tự ý hành động — nó là công cụ bạn tham khảo từ code chạy *bên trong* ngữ cảnh cuộc trò chuyện, chẳng hạn trong callback `on_matched` của một observation hoặc trong một custom evaluator:

- `await budget.measure()` — đo mức chi tiêu của session hiện tại từ trước đến nay.
- `await budget.reset()` — đặt lại mức đo của session về 0 (ví dụ sau khi nhân viên hỗ trợ xử lý xong và bàn giao lại cho bot).

### Hướng dẫn: Bàn giao cho nhân viên hỗ trợ khi vượt ngân sách

Cách chuẩn để thực thi ngân sách là tạo một **observation** có callback `on_matched`. Tính áp dụng của observation được quyết định trực tiếp bằng code: `budget.exceeded` là một bộ đánh giá bằng code mang tính tất định (không cần gọi mô hình). Callback sẽ chuyển session sang chế độ thủ công (`manual`), nơi agent dừng phản hồi và con người tiếp quản:

```python
import parlant.sdk as p
from decimal import Decimal

budget = await server.create_session_budget(
    name="handoff-cap",
    value=Decimal("2.00"),
)

async def handoff(context: p.EngineContext, match: p.RuleEvaluation) -> None:
    # Chuyển session sang chế độ manual để agent AI dừng trả lời
    await p.Session.current.update(mode="manual")

    # Phát một tin nhắn thông báo nguyên văn trực tiếp vào session — không dùng LLM:
    await p.Session.current.emit_message(
        "Cuộc trò chuyện này đang được chuyển tiếp tới nhân viên hỗ trợ. Vui lòng chờ trong giây lát."
    )

    # Báo động tới hệ thống hỗ trợ (helpdesk, Slack, CRM) để nhân viên tiếp nhận:
    await support_desk.create_ticket(
        session_id=p.Session.current.id,
        customer_id=p.Customer.current.id,
        reason="Đã vượt quá ngân sách phiên — vui lòng tiếp nhận hỗ trợ",
    )

# Chạy hàm handoff bất cứ khi nào ngân sách của phiên bị vượt quá
await agent.create_observation(
    evaluation_func=budget.exceeded,
    on_matched=handoff,
)
```

Các observation về ngân sách được đánh giá ngay từ đầu lượt tương tác, trước khi bất kỳ tác vụ mô hình nào diễn ra. Trong lượt đầu tiên mà chi tiêu vượt ngân sách, observation được khớp, hàm `handoff` chạy, và lượt tương tác dừng lại sạch sẽ — **agent hoàn toàn không sinh câu trả lời mới**. Khách hàng chỉ thấy đúng thông điệp bạn đã phát ra.

### Hướng ngược lại: Khi ngân sách vẫn còn (While budget still holds)

`budget.not_exceeded` là hình ảnh phản chiếu của `budget.exceeded` — nó khớp miễn là phiên hội thoại vẫn còn ngân sách. Dùng nó để kích hoạt các hành vi chỉ có thể chi trả khi còn ngân sách:

```python
within_budget = await agent.create_observation(
    evaluation_func=budget.not_exceeded,
)

deep_research = await agent.create_policy(
    content=(
        "When the customer asks a question the knowledge base does not answer, "
        "research it with `search_literature` before replying"
    ),
    tools=[search_literature],
)

await deep_research.depend_on(within_budget)
```

Policy tốn kém giờ đây chỉ được xem xét trong các lượt mà session vẫn đủ khả năng chi trả. Khi vượt quá budget, observation ngừng khớp, policy sẽ im lặng rút lui và agent tiếp tục các tác vụ thông thường khác.

## Lắng nghe mức sử dụng theo thời gian thực (Programmatic observation)

Bạn có thể gắn một listener để liên tục nhận cập nhật mức sử dụng:

```python
container[UsageReporter].add_listener(
    lambda trace_id, key, usage: metrics.increment(key, usage.input_tokens)
)
```

## Kiểm soát Chi phí (Cost control)

`CostControlPolicy` là port kiểm soát cấp thấp được sử dụng tại các ranh giới TURN, STEP và BACKGROUND. Nó không thực hiện định giá token mà quyết định xem công việc có được phép tiếp tục tại từng ranh giới hay không, và bạn có thể triển khai chính sách của riêng mình qua DI container.
