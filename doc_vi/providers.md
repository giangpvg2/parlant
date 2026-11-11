# Cấu hình Mô hình và Nhà cung cấp (Configuring Models and Providers)

Một agent của Parlant không chỉ sử dụng một loại yêu cầu mô hình duy nhất. Đằng sau mỗi lượt hội thoại có nhiều loại công việc mô hình khác nhau: sinh câu trả lời, khớp quy tắc, xét duyệt bản nháp, tạo embedding, nén lịch sử. Bảng ánh xạ `models` kiểm soát mô hình nào sẽ chạy từng loại công việc, ở bất kỳ mức độ chi tiết nào bạn cần:

- **Một nhà cung cấp duy nhất cho tất cả** — `models={"*": "openrouter"}` là xong; mỗi loại công việc sẽ sử dụng mô hình mặc định hợp lý của nhà cung cấp đó.
- **Ghi đè một nhóm công việc** — ví dụ: chuyển các lượt xét duyệt sang một mô hình rẻ hơn.
- **Ghim chính xác từng mô hình cho từng thao tác cụ thể** — chi tiết đến từng route riêng lẻ và từng mức nỗ lực (effort).

Mỗi loại công việc yêu cầu các mô hình thông qua một **route** được đặt tên (`react`, `matching.rank`, `review.tools`, v.v.). Các khóa trong bảng ánh xạ của bạn lựa chọn các routes — một cách chính xác, theo ký tự đại diện (wildcard), hoặc được định phẩm chất (qualified) bởi ngữ cảnh như mức nỗ lực của lượt hội thoại. Phần còn lại của tài liệu này xây dựng cấu hình từng bước: khởi đầu nhanh và cài đặt provider, hệ thống route, giới hạn tần suất (rate limits), các provider tích hợp sẵn, thông tin xác thực (credentials), cấu hình theo từng agent và cấu hình trực tiếp (live configuration), các custom provider, và xử lý sự cố (troubleshooting).

## Khởi đầu nhanh (Quick Start)

Thiết lập thông tin xác thực mà provider của bạn mong đợi:

```bash
export OPENROUTER_API_KEY="..."
```

Sau đó cấu hình một provider và tạo một agent:

```python
import parlant.sdk as p


async with p.Server(
    models={"*": "openrouter"},  # OpenRouter thực tế đã là mặc định sẵn
) as server:
    agent = await server.create_agent(
        id="my-agent",
        name="Support Agent",
        instructions="Help customers resolve support requests.",
    )
```

`*` là một route đặc biệt: Nó sử dụng mô hình mặc định đã đăng ký của provider này cho từng loại công việc. Trong một lượt thông thường, điều này có thể bao gồm việc sinh phản hồi ReAct (agentic), khớp quy tắc, tạo embedding, xét duyệt, nén lịch sử, kiểm duyệt, và ước lượng token.

`p.Server()` mặc định là `{"*": "openrouter"}` khi `models` bị bỏ qua. Việc khai báo provider một cách tường minh được khuyến nghị vì nó giúp cấu hình triển khai dễ kiểm tra hơn.

### Cài đặt hỗ trợ cho Provider

Gói Parlant cơ sở bao gồm sẵn hỗ trợ cho cả OpenAI và OpenRouter. Gemini, Anthropic, và LiteLLM sử dụng các nhóm phụ thuộc tùy chọn (optional dependency groups) để các SDK của chúng chỉ được cài đặt khi cần:

| Provider | Lệnh cài đặt |
|---|---|
| OpenAI | `pip install parlant` |
| OpenRouter | `pip install parlant` |
| Gemini | `pip install 'parlant[gemini]'` |
| Anthropic | `pip install 'parlant[anthropic]'` |
| LiteLLM | `pip install 'parlant[litellm]'` |

Ví dụ: cài đặt Gemini mới sẽ như sau:

```python
async with p.Server(models={"*": "gemini"}) as server:
    ...
```

```bash
pip install 'parlant[gemini]'
export GEMINI_API_KEY="..."
python my_agent.py
```

OpenRouter không cần thêm gói phụ trợ nào sau khi cài đặt Parlant. Hãy thiết lập API key của nó trước khi chọn một route của OpenRouter:

```bash
pip install parlant
export OPENROUTER_API_KEY="..."
```

### Ghi đè một nhóm công việc (Overriding a family of work)

Bạn có thể sử dụng các giá trị mặc định của một provider trong khi ghi đè các task route cụ thể:

Trong ví dụ sau, việc sinh phản hồi chạy trên một mô hình Gemini, việc xét duyệt lệnh gọi công cụ và tin nhắn chạy trên một mô hình rẻ hơn, và mọi loại công việc khác đều dự phòng về OpenRouter. Ví dụ này đã thể hiện toàn bộ mô hình cấu hình. Phần còn lại của tài liệu này sẽ bổ sung các chi tiết.

```python
async with p.Server(
    models={
        "react": p.ModelConfig("gemini:gemini-3.1-flash-lite"),     # sinh phản hồi
        "review.*": p.ModelConfig("gemini:gemini-3.5-flash-lite"),  # cả hai lượt kiểm tra xét duyệt
        "*": "openrouter",                                          # tất cả những việc khác
    },
) as server:
    ...
```

## Các khái niệm cốt lõi (Core Concepts)

### Tuyến đường (Routes)

Một route là một chuỗi mở được yêu cầu bởi một thành phần tiêu thụ mô hình. Parlant hiện đang sử dụng các routes sau:

| Route | Năng lực (Capability) | Mục đích |
|---|---|---|
| `react` | ReAct | Các bước phản hồi của agent. |
| `indexing` | Schematic | Tạo tín hiệu quy tắc (rule signals) và các chỉ mục khác khi khởi động SDK. |
| `matching.rank` | Schematic | Xếp hạng hoặc cắt tỉa các quy tắc cho tương tác hiện tại. |
| `review.tools` | Schematic | Xét duyệt các lệnh gọi công cụ được đề xuất. |
| `review.message` | Schematic | Xét duyệt một tin nhắn được đề xuất. |
| `compaction` | Schematic | Tóm tắt lịch sử phiên cũ hơn. |
| `embedding.rules` | Embedding | Tạo embedding cho tín hiệu quy tắc và ngữ cảnh tương tác. |
| `embedding.tools` | Embedding | Tạo embedding cho các công cụ để lựa chọn mức độ liên quan. |
| `moderation.customer` / `moderation.agent` | Moderation | Hai điểm kiểm tra kiểm duyệt tùy chọn (xem [Kiểm duyệt (Moderation)](moderation.md)). |
| `tokenizer` | Tokenizer | Ước tính số lượng token. |

Các route xét duyệt (review) được yêu cầu với `ReviewSchema` trả về phán quyết boolean của reviewer. Tên route duy trì ổn định trong khi định phẩm chất `effort` của lượt hội thoại thay đổi, vì vậy các bộ chọn định phẩm theo mức nỗ lực (xem [Bộ định phẩm Tuyến đường](#bộ-định-phẩm-tuyến-đường-route-qualifiers)) là cách để thay đổi mô hình xét duyệt theo effort. Một route không được engine cài đặt của bạn sử dụng sẽ không gây ra yêu cầu gọi tới provider.

### Cấu hình Mô hình (Model Configurations)

Sử dụng `ModelConfig` để liên kết một route với một mô hình cụ thể:

```python
p.ModelConfig(
    "openai:gpt-4o",
    args={"api_key": p.SecretRef("models/openai/api-key")},
)
```

Định danh mô hình có hai phần được phân tách bằng dấu hai chấm đầu tiên:

```text
provider:model
```

Ví dụ:

```text
openai:gpt-5.6-luna
gemini:gemini-3.5-flash-lite
anthropic:claude-sonnet-5
openrouter:openai/gpt-5.6-terra
```

Tiền tố provider chọn adapter của Parlant. Phần văn bản còn lại được truyền nguyên vẹn cho provider đó.

Thay vì một chuỗi `provider:model`, `ModelConfig.model` cũng có thể là một **`ModelProvider`** do ứng dụng cung cấp — dành cho trường hợp việc chọn mô hình cần diễn ra một cách *động*, với logic có điều kiện mà bảng route tĩnh không thể biểu đạt (ví dụ: theo các thuộc tính của khách hàng). Đây là một hàm async callable nhận `p.EngineContext` hiện tại (hoặc `None` cho việc phân giải ngoại tuyến) và trả về đối tượng sẽ thực thi thao tác đó:

```python
async def provide_react(context: p.EngineContext | None) -> ReactGenerator:
    if context and await p.Customer.current.metadata.get("tier") == "premium":
        return premium_react
    return standard_react

models={"react": p.ModelConfig(provide_react)}
```

Xem [Nhà cung cấp Mô hình Tùy chỉnh (Custom Model Providers)](#nhà-cung-cấp-mô-hình-tùy-chỉnh-custom-model-providers) để biết hợp đồng đầy đủ (vòng đời, caching, ràng buộc schema).

Bảng ánh xạ `args` tùy chọn chỉ cấu hình cho các chuỗi mô hình có định danh provider. Nó không phải là payload của yêu cầu mô hình. Ví dụ: `api_key` chọn thông tin xác thực, `dimensions` cấu hình cho một embedder, và `service_tier` chọn một cấp độ xử lý của provider cho các route ReAct. Mỗi phần của provider trong mục [Các nhà cung cấp tích hợp sẵn](#các-nhà-cung-cấp-tích-hợp-sẵn-built-in-providers) liệt kê chính xác những tham số nào mà nó chấp nhận cho từng năng lực; bất kỳ điều gì khác đều bị từ chối kèm thông báo lỗi rõ ràng. Một callable đã tự làm chủ việc khởi tạo của nó, do đó việc kết hợp một callable với `args` không rỗng là không hợp lệ.

### Mức độ Lập luận (Reasoning Level)

`ModelConfig.reasoning` thiết lập mức độ lập luận cho các route ReAct và schematic. Vì nó đi kèm trên route mô hình, nó tuân theo sự phân giải chính xác như chính mô hình đó — **theo từng agent, và theo từng bộ định phẩm effort** — do đó bạn kiểm soát nó theo cùng cách bạn kiểm soát mô hình nào sẽ chạy.

Nó chấp nhận một giá trị `ReasoningConfig` đầy đủ hoặc một cách viết tắt độ sâu:

```python
p.ModelConfig("anthropic:claude-sonnet-5", reasoning="high")            # viết tắt
p.ModelConfig("anthropic:claude-sonnet-5", reasoning=p.ReasoningConfig( # kiểm soát đầy đủ
    effort="high",        # "minimal" | "low" | "medium" | "high"
    visibility="full",    # "none" | "summary" | "full" — những lập luận nào được trả về
))
```

Đối với ReAct, cả `effort` và `visibility` đều áp dụng. Việc sinh schematic không có kênh hiển thị lập luận (reasoning-visibility), vì vậy các route schematic chỉ sử dụng `effort`. Parlant hiện sử dụng cấu hình lập luận schematic trên `matching.rank` (xếp hạng và cắt tỉa), `review.tools`, và `review.message`. Các năng lực khác (embedding/tokenizer/moderation) bỏ qua `reasoning`.

Khi `reasoning` không được thiết lập (mặc định), ánh xạ effort→reasoning tích hợp sẵn của từng thành phần engine sẽ được sử dụng, do đó các route hiện có không bị thay đổi.

Để thay đổi lập luận theo mức nỗ lực của agent, hãy gắn nó vào các route được định phẩm theo effort (xem [Bộ định phẩm Tuyến đường](#bộ-định-phẩm-tuyến-đường-route-qualifiers) bên dưới):

```python
models={
    "react": p.ModelConfig("openai:gpt-5.6-terra", reasoning="low"),
    "react[effort>=high]": p.ModelConfig("openai:gpt-5.6", reasoning="high"),
    "matching.rank": p.ModelConfig("openai:gpt-5.4-nano", reasoning="minimal"),
    "matching.rank[effort>=high]": p.ModelConfig(
        "openai:gpt-5.4-mini",
        reasoning="medium",
    ),
    "review.*": p.ModelConfig("gemini:gemini-3.5-flash-lite", reasoning="low"),
}
```

Điều này cũng có thể thiết lập theo từng agent thông qua `create_agent(models=...)`, vì các route của agent sẽ ghi đè các route được cấu hình ở cấp độ server:

```python
await server.create_agent(
    id="my-agent-2",
    name="Deep Thinker",
    effort=p.Effort.HIGH,
    models={
        "react": p.ModelConfig("anthropic:claude-sonnet-5", reasoning="high"),
        "review.*": p.ModelConfig("openai:gpt-5.4-mini", reasoning="medium"),
    },
)
```

### Các Tuyến đường Chính xác và Ký tự Đại diện (Exact and Wildcard Routes)

Các thành phần tiêu thụ luôn yêu cầu các route cụ thể, chẳng hạn như `react` hoặc `matching.rank`. Cấu hình có thể sử dụng một route chính xác hoặc một ký tự đại diện namespace ở cuối:

```python
models={
    "matching.*": p.ModelConfig("gemini:gemini-3.1-flash-lite"),
}
```

Chỉ hỗ trợ ký tự đại diện `.*` ở cuối. Các mẫu như `matching*`, `*.rank`, và `review.*.tools` đều không hợp lệ.

### Bộ định phẩm Tuyến đường (Route Qualifiers)

Bộ định phẩm lựa chọn một mô hình bằng cách sử dụng các thuộc tính của thao tác hiện tại. Parlant hiện cung cấp một bộ định phẩm là `effort`:

```python
models={
    "react": p.ModelConfig("gemini:gemini-3.1-flash-lite"),
    "react[effort>=high]": p.ModelConfig("anthropic:claude-sonnet-5"),
    "matching.*[effort<medium]": p.ModelConfig(
        "openai:gpt-5.4-nano"
    ),
}
```

Các toán tử so sánh được hỗ trợ là `=`, `!=`, `<`, `<=`, `>`, và `>=`. Chúng sử dụng thứ tự sau:

```text
min < low < medium < high < max
```

Nhiều ràng buộc được kết hợp bằng toán tử AND, vì vậy bộ chọn này khớp với các mức nỗ lực low và medium:

```python
"react[effort>=low,effort<high]"
```

Giá trị effort được phân giải khi mỗi thao tác mô hình bắt đầu. Nó là giá trị lớn nhất giữa mức effort đã cấu hình của agent và bất kỳ mức effort nào được kích hoạt bởi các quy tắc đã khớp (xem [Mức nỗ lực thích ứng (Adaptive Effort)](adaptive-effort.md)) cho đến thời điểm đó. Một quy tắc được phát hiện trong quá trình matching không thể thay đổi hồi tố mô hình đã phát hiện ra nó, nhưng mức effort được kích hoạt sẽ áp dụng cho các thao tác tiếp theo.

### Tuyến đường Nhà cung cấp (The Provider Route)

Route `*` là lựa chọn dự phòng cho provider:

```python
models={"*": "gemini"}
```

Giá trị của nó phải là một tên provider trần trụi duy nhất. Parlant chọn mô hình mặc định đã đăng ký của provider đó cho năng lực mà route cụ thể yêu cầu. Nó có thể mang các bộ định phẩm effort để chọn một provider trên phạm vi toàn cầu:

```python
models={
    "*": "openrouter",
    "*[effort>=high]": "anthropic",
}
```

Trong ví dụ này, các thao tác ở mức nỗ lực high và maximum sử dụng các giá trị mặc định của Anthropic. Các thao tác khác sử dụng các giá trị mặc định của OpenRouter.

Hợp lệ:

```python
{"*": "openai"}
{"*": "gemini"}
{"*": "anthropic"}
{"*": "openrouter"}
{"*[effort>=high]": "anthropic"}
```

Không hợp lệ:

```python
{"*": "openai:gpt-5.6-luna"}
{"*": "openrouter:openai/gpt-4.1"}
{"*[effort>=high]": "anthropic:claude-sonnet-5"}
{"react": "openai"}
```

Sử dụng `ModelConfig` bất cứ khi nào bạn chỉ định một mô hình:

```python
{
    "*": "openai",
    "react": p.ModelConfig("openai:gpt-4o"),
}
```

### Độ ưu tiên Tuyến đường (Route Precedence)

Các route của agent có độ ưu tiên cao hơn các route của server. Trong mỗi phạm vi, các route chính xác được ưu tiên hơn các ký tự đại diện namespace, và các ký tự đại diện namespace được ưu tiên hơn route provider. Đối với cùng một mẫu route, một bộ chọn có định phẩm khớp sẽ đánh bại bộ chọn dự phòng không có định phẩm của nó. Một bộ chọn khớp với ít mức effort hơn sẽ có tính cụ thể cao hơn bộ chọn khớp với nhiều mức hơn.

Đối với `matching.distill` ở mức nỗ lực high, việc phân giải sẽ kiểm tra theo thứ tự:

```text
1. agent matching.distill[ràng buộc effort khớp, hẹp nhất trước]
2. agent matching.distill
3. agent matching.*[ràng buộc effort khớp, hẹp nhất trước]
4. agent matching.*
5. agent *[ràng buộc effort khớp, hẹp nhất trước]
6. agent *
7. server matching.distill[ràng buộc effort khớp, hẹp nhất trước]
8. server matching.distill
9. server matching.*[ràng buộc effort khớp, hẹp nhất trước]
10. server matching.*
11. server *[ràng buộc effort khớp, hẹp nhất trước]
12. server *
```

Thứ tự này có nghĩa là việc ghi đè `matching.*` của agent sẽ cố tình đánh bại một giá trị mặc định server `matching.distill` cụ thể hơn. Hãy xóa phần ghi đè của agent khi bạn muốn agent kế thừa lại cấu hình của server.

Hai bộ chọn cho cùng một mẫu route không thể trùng lặp với mức độ cụ thể tương đương của định phẩm. Ví dụ, những trường hợp sau đây bị mơ hồ ở mức nỗ lực medium và sẽ bị từ chối:

```python
{
    "react[effort>=medium]": p.ModelConfig(...),
    "react[effort<=medium]": p.ModelConfig(...),
}
```

## Giới hạn tần suất (Rate Limits)

Các provider thiết lập hạn ngạch ở cấp tài khoản: số lượng yêu cầu đồng thời tối đa, và tốc độ yêu cầu tối đa. Một server bận rộn có thể vượt quá các hạn ngạch này — khi nhiều phiên cùng xử lý một lúc, hoặc các đợt làm việc song song bùng nổ bên trong một thao tác. Thay vì để provider từ chối yêu cầu, bạn có thể gắn một `RateLimit` vào cùng `ModelConfig` chọn mô hình, để việc định tuyến và kiểm soát tiếp nhận đi liền với nhau. Các yêu cầu vượt quá giới hạn sẽ chờ theo thứ tự FIFO; bộ giới hạn không bao giờ trả về phản hồi mô hình giả mạo và không bao giờ để lộ lỗi rate-limit cho agent.

```python
async with p.Server(
    models={
        "*": "openai",
        "indexing": p.ModelConfig(
            "openai:gpt-4o-mini",
            rate_limit=p.RateLimit(
                max_concurrency=4,
                requests_per_minute=60,
            ),
        ),
    },
) as server:
    ...
```

Ví dụ trên giới hạn `indexing` vì đây là trường hợp bùng nổ kinh điển: việc đánh chỉ mục khi khởi động chạy nhiều lượt sinh schematic song song, và mỗi bộ đề xuất chỉ mục đều yêu cầu cùng một route — vì vậy chúng chia sẻ giới hạn này ngay cả khi chúng sử dụng các output schema khác nhau. Cơ chế tương tự áp dụng cho bất kỳ route schematic hoặc ReAct nào.

`RateLimit` có ba trường:

| Trường | Ý nghĩa |
|---|---|
| `max_concurrency` | Số lượng yêu cầu tối đa đã được chấp thuận có thể đồng thời xử lý. |
| `requests_per_minute` | Tốc độ bắt đầu yêu cầu tối đa. Các lượt bắt đầu được giãn đều đặn, thay vì giải phóng ồ ạt trong một đợt bùng nổ một phút. |
| `bucket` | Nhóm dung lượng tường minh tùy chọn được chia sẻ bởi mọi cấu hình sử dụng cùng tên đó. |

Cần có ít nhất một ràng buộc dạng số. Bạn có thể cấu hình riêng rẽ từng loại, hoặc kết hợp chúng:

```python
# Chỉ giới hạn đồng thời: hữu ích để bảo vệ pool kết nối hoặc giới hạn provider.
p.RateLimit(max_concurrency=3)

# Chỉ giới hạn thông lượng: cho phép một yêu cầu bắt đầu mỗi hai giây.
p.RateLimit(requests_per_minute=30)

# Cả hai ràng buộc đều phải được thỏa mãn trước khi yêu cầu bắt đầu.
p.RateLimit(max_concurrency=3, requests_per_minute=30)
```

Nếu không có `bucket`, dung lượng thuộc về liên kết route đã chọn. Đây thường là hành vi phù hợp: các lệnh gọi `indexing` chia sẻ một hàng đợi, trong khi `review.*` và `react` có các hàng đợi độc lập. Việc thay thế trực tiếp một route sẽ tạo ra một liên kết mới và do đó là một bucket tạm thời mới.

Sử dụng một bucket có tên khi các route riêng biệt cùng tiêu thụ một hạn ngạch của provider:

```python
shared_openai_quota = p.RateLimit(
    max_concurrency=8,
    requests_per_minute=240,
    bucket="openai-production",
)

models = {
    "matching.*": p.ModelConfig(
        "openai:gpt-4o-mini",
        rate_limit=shared_openai_quota,
    ),
    "review.*": p.ModelConfig(
        "openai:gpt-4o",
        rate_limit=shared_openai_quota,
    ),
    "react[effort>=high]": p.ModelConfig(
        "openai:gpt-4o",
        rate_limit=shared_openai_quota,
    ),
}
```

Mỗi lần sử dụng cùng một named bucket đều phải chỉ định các ràng buộc giống nhau. Các cấu hình xung đột sẽ làm phát sinh `RateLimitConflictError` khi bucket đó được yêu cầu cấp phát.

Rate limits hiện bao bọc các generator schematic và ReAct. Một giấy phép schematic bao gồm một thao tác `generate()`, bao gồm cả các lần thử lại nội bộ của provider. Giới hạn ReAct được áp dụng tại ranh giới nỗ lực stream của provider, vì vậy một lần phòng ngừa TTFT (TTFT hedge) sẽ tiêu thụ một giấy phép khác. Giấy phép luôn được giải phóng sau khi thành công, thất bại, hoặc bị hủy. Các route embedding, moderation, và tokenizer từ chối rate limit đính kèm khi được phân giải.

`TransientRateLimiter` mặc định hoạt động cục bộ trong tiến trình. Nó điều phối mọi route được phân giải bởi một tiến trình server, nhưng nó không điều phối nhiều worker cũng như không bảo toàn trạng thái hạn ngạch qua các lần khởi động lại. Hãy thay thế port DI `RateLimiter` bằng một bản triển khai bền vững hoặc phân tán khi bạn cần một trong hai đặc tính đó:

```python
from lagom import Container

from parlant.core.nlp.rate_limits import RateLimiter


async def configure_container(container: Container) -> Container:
    container[RateLimiter] = RedisRateLimiter(...)
    return container


async with p.Server(
    configure_container=configure_container,
    models={...},
) as server:
    ...
```

Đối với các hạn ngạch bền vững, hãy sử dụng các tên bucket tường minh có định danh ổn định qua các tiến trình và triển khai. Một custom limiter triển khai `acquire(bucket=..., limit=...)` và trả về một giấy phép có thể giải phóng an toàn nhiều lần.

Cấu hình hợp lệ:

```python
models = {
    "indexing": p.ModelConfig(
        "openai:gpt-5.6-terra",
        rate_limit=p.RateLimit(max_concurrency=4),
    ),
    "react": p.ModelConfig(
        custom_react_provider,
        rate_limit=p.RateLimit(requests_per_minute=60),
    ),
    "review.tools[effort>=high]": p.ModelConfig(
        "openrouter:anthropic/claude-sonnet-5",
        rate_limit=p.RateLimit(
            max_concurrency=2,
            requests_per_minute=20,
            bucket="openrouter-anthropic",
        ),
    ),
}
```

Các cấu hình không hợp lệ và hành vi tương ứng:

| Cấu hình | Kết quả |
|---|---|
| `p.RateLimit()` | Bị từ chối vì không định nghĩa ràng buộc nào. |
| Các trường số bằng không, âm, boolean, không hữu hạn, hoặc không phải số | Bị từ chối khi khởi tạo `RateLimit`. |
| Một `bucket` rỗng hoặc chỉ toàn khoảng trắng | Bị từ chối. |
| `p.ModelConfig(provider_callable, args={...})` | Bị từ chối vì các callable provider tự quản lý việc khởi tạo của chúng. |
| Một callable trần trụi làm giá trị route | Bị từ chối; hãy bọc nó trong `ModelConfig`. |
| Một rate limit gắn trên embedding, moderation, hoặc tokenizer | Bị từ chối khi route đó được phân giải. |
| Các giới hạn khác nhau sử dụng cùng một named bucket | Bị limiter từ chối do xung đột bucket. |
| `"*": p.ModelConfig(...)` | Bị từ chối; `*` duy trì là một provider fallback trần trụi. Thay vào đó hãy cấu hình các route cụ thể hoặc namespace có giới hạn. |

Các xung đột bucket khi chạy và các năng lực route không được hỗ trợ sẽ sử dụng các chẩn đoán định tuyến mô hình được mô tả trong mục Troubleshooting.

## Các nhà cung cấp tích hợp sẵn (Built-In Providers)

Các provider tích hợp sẵn là OpenAI, Gemini, Anthropic, OpenRouter, và LiteLLM.

| Provider | Tiền tố | Biến môi trường | Schematic | ReAct | Embedding | Moderation | Tokenizer |
|---|---|---|---|---|---|---|---|
| OpenAI | `openai` | `OPENAI_API_KEY` | Có | Có | Có | Có (chỉ route tường minh) | Có |
| Gemini | `gemini` | `GEMINI_API_KEY` | Có | Có | Có | Không | Có |
| Anthropic | `anthropic` | `ANTHROPIC_API_KEY` | Có | Có | Voyage AI (`VOYAGE_API_KEY`) | Không | Có |
| OpenRouter | `openrouter` | `OPENROUTER_API_KEY` | Có | Có | Có | Không | Có |
| LiteLLM | `litellm` | theo từng model (vd: `OPENAI_API_KEY`) | Có | Có | Có | Không | Có |

Các adapter provider được tải lười (lazily). Việc khởi động Parlant không import mọi gói provider tùy chọn. Cấu hình một route chỉ tải provider đã chọn; một bản cập nhật route trực tiếp sau đó có thể tải một provider khác mà không cần khởi động lại server.

Nếu thiếu một gói provider tùy chọn, cấu hình route sẽ thất bại kèm theo lệnh cài đặt có thể thực hiện được, chẳng hạn như `pip install 'parlant[gemini]'`. Một provider tùy chọn không được sử dụng thì không cần phải cài đặt. Xem [Cài đặt hỗ trợ cho Provider](#cài-đặt-hỗ-trợ-cho-provider) để biết tất cả các lệnh cài đặt; OpenAI và OpenRouter đã được bao gồm trong gói cơ sở.

Các giá trị mặc định của provider rất tiện lợi, nhưng các route `ModelConfig` tường minh sẽ tốt hơn khi việc lựa chọn mô hình cần duy trì sự ổn định qua các lần nâng cấp Parlant.

### OpenAI

Cấu hình tối thiểu:

```python
server = p.Server(models={"*": "openai"})
```

Cấu hình hỗn hợp tường minh:

```python
server = p.Server(
    models={
        "*": "openai",
        "react": p.ModelConfig("openai:gpt-4o"),
        "matching.rank": p.ModelConfig("openai:gpt-5.4-nano"),
        "embedding.*": p.ModelConfig(
            "openai:text-embedding-3-small",
            args={"dimensions": 1536, "max_tokens": 8192},
        ),
        "moderation": p.ModelConfig("openai:omni-moderation-latest"),
        "tokenizer": p.ModelConfig("openai:gpt-4o"),
    }
)
```

Các tham số hàm khởi tạo được chấp nhận:

| Năng lực | Các tham số |
|---|---|
| Schematic | `api_key`, `tokenizer_model_name` |
| ReAct | `api_key`, `service_tier` |
| Embedding | `api_key`, `dimensions`, `max_tokens` |
| Moderation | `api_key` |
| Tokenizer | Không có |

Số chiều embedding của OpenAI mặc định theo các kích thước đã biết cho các mô hình embedding tiêu chuẩn và mặc định là 1536 cho các trường hợp khác. Hãy thiết lập `dimensions` một cách tường minh cho các mô hình khác.

`service_tier` chọn cấp độ xử lý cho mỗi yêu cầu ReAct trên route: `"standard"` (mặc định), `"flex"` (rẻ hơn, chậm hơn), hoặc `"priority"` (nhanh hơn, có phụ phí — tên riêng của OpenAI cho cấp này là `fast`, và Parlant sẽ ánh xạ cho bạn):

```python
"react": p.ModelConfig("openai:gpt-5.6-terra", args={"service_tier": "priority"}),
```

### Gemini

```python
server = p.Server(
    models={
        "*": "gemini",
        "react[effort>=high]": p.ModelConfig("gemini:gemini-3.5-flash"),
        "embedding.*": p.ModelConfig(
            "gemini:gemini-embedding-2",
            args={"dimensions": 3072, "max_tokens": 8192},
        ),
    }
)
```

Mô hình embedding mặc định là `gemini-embedding-2`. Các embedding đã lưu được lưu giữ theo từng embedder, vì vậy việc chuyển đổi mô hình sẽ tạo lại embedding cho các tài liệu của bạn trong lần khởi động tiếp theo.

Các tham số hàm khởi tạo được chấp nhận:

| Năng lực | Các tham số |
|---|---|
| Schematic | `api_key` |
| ReAct | `api_key`, `service_tier` |
| Embedding | `api_key`, `dimensions`, `max_tokens` |
| Moderation | Không cung cấp; hãy định tuyến kiểm duyệt sang provider có hỗ trợ. |
| Tokenizer | `api_key` |

`service_tier` (`"standard"` / `"flex"` / `"priority"`) ánh xạ trực tiếp vào các cấp cùng tên của Gemini, ví dụ `args={"service_tier": "flex"}`.

### Anthropic

Anthropic không cung cấp API embedding, vì vậy provider Anthropic của Parlant đáp ứng các route embedding thông qua [Voyage AI](https://platform.claude.com/docs/en/build-with-claude/embeddings), đối tác embedding được khuyến nghị của Anthropic (mô hình mặc định `voyage-3.5`). Khi cả `ANTHROPIC_API_KEY` và `VOYAGE_API_KEY` đều được thiết lập, đây là một cấu hình hoàn chỉnh:

```python
server = p.Server(models={"*": "anthropic"})
```

Thay vào đó, bạn có thể định tuyến embeddings sang một provider khác — khi đó không cần key Voyage:

```python
server = p.Server(
    models={
        "*": "anthropic",
        "embedding.*": p.ModelConfig("openai:text-embedding-3-large"),
    }
)
```

Các tham số hàm khởi tạo được chấp nhận:

| Năng lực | Các tham số |
|---|---|
| Schematic | `api_key` |
| ReAct | `api_key`, `max_tokens`, `service_tier` |
| Embedding | `api_key` (một key Voyage AI; mặc định là `VOYAGE_API_KEY`) |
| Moderation | Không cung cấp; hãy định tuyến kiểm duyệt sang provider có hỗ trợ. |
| Tokenizer | `api_key` |

`service_tier` chấp nhận các giá trị trung lập giống như các provider khác (`"standard"` / `"flex"` / `"priority"`) và ánh xạ chúng vào những gì Anthropic cung cấp: `"priority"` trở thành `auto` của Anthropic (dung lượng ưu tiên khi khả dụng), và `"flex"` không có giá trị tương đương trong Anthropic, vì vậy nó chạy như standard.

Bạn có thể sử dụng Gemini hoặc OpenRouter cho `embedding.*` thay vì OpenAI.

### OpenRouter

Các định danh mô hình OpenRouter chứa đường dẫn provider/model riêng của chúng. Parlant chỉ phân tách tại dấu hai chấm đầu tiên:

```python
p.ModelConfig("openrouter:openai/gpt-4o")
p.ModelConfig("openrouter:google/gemini-3.5-flash")
p.ModelConfig("openrouter:anthropic/claude-sonnet-5")
```

Đối với `openrouter:google/gemini-3.5-flash`, Parlant chọn adapter OpenRouter và gửi `google/gemini-3.5-flash` tới OpenRouter. Nó không cố gắng chọn adapter Gemini cục bộ lần thứ hai.

Ví dụ:

```python
server = p.Server(
    models={
        "*": "openrouter",
        "react": p.ModelConfig(
            "openrouter:anthropic/claude-sonnet-5",
            args={
                "site_url": "https://support.example.com",
                "app_name": "Example Support",
                "provider": {
                    "sort": "latency",
                    "preferred_max_latency": {"p90": 2.0},
                    "allow_fallbacks": True,
                },
            },
        ),
        "matching.*": p.ModelConfig(
            "openrouter:google/gemini-3.5-flash"
        ),
        "embedding.*": p.ModelConfig(
            "openrouter:openai/text-embedding-3-large"
        ),
    }
)
```

Các tham số hàm khởi tạo được chấp nhận:

| Năng lực | Các tham số |
|---|---|
| Schematic | `api_key`, `site_url`, `app_name`, `provider` |
| ReAct | `api_key`, `site_url`, `app_name`, `provider` |
| Embedding | `api_key`, `site_url`, `app_name`, `provider` |
| Moderation | Không cung cấp; hãy định tuyến kiểm duyệt sang provider có hỗ trợ. |
| Tokenizer | Không có |

**Bảng ánh xạ `provider` — Tùy chọn định tuyến của OpenRouter.** Một ID mô hình trên OpenRouter thường được phục vụ bởi nhiều backend provider, và bảng ánh xạ `provider` kiểm soát bên nào trong số đó được phép phục vụ yêu cầu của bạn, và theo thứ tự nào. Parlant chuyển nguyên văn bảng ánh xạ này tới OpenRouter trên mỗi yêu cầu suy luận, vì vậy mọi trường từ [schema định tuyến provider của OpenRouter](https://openrouter.ai/docs/features/provider-routing) đều hoạt động mà không cần bản dịch đặc thù nào của Parlant. Các trường bạn sẽ thường sử dụng nhất:

| Trường | Chức năng |
|---|---|
| `sort` | Xếp hạng các backend ứng viên theo `"price"`, `"throughput"`, hoặc `"latency"`. |
| `order` | Một danh sách tường minh các slug của provider để thử, theo thứ tự. |
| `only` / `ignore` | Danh sách cho phép (allow-list) hoặc danh sách từ chối (deny-list) các slug provider. |
| `allow_fallbacks` | Liệu OpenRouter có được phép dự phòng vượt ra ngoài danh sách `order` của bạn hay không (mặc định `True`). |
| `require_parameters` | Chỉ định tuyến tới các backend hỗ trợ mọi tham số của yêu cầu (quan trọng cho structured output). |
| `max_price` | Giá trần, ví dụ `{"prompt": 1.0, "completion": 4.0}` (USD trên một triệu tokens). |
| `quantizations` | Mức lượng tử hóa chấp nhận được cho các mô hình mã nguồn mở (open-weight), ví dụ `["fp16", "bf16"]`. |
| `data_collection` | `"deny"` để chỉ định tuyến tới các backend không lưu giữ hoặc không huấn luyện trên prompt của bạn. |
| `zdr` | `True` để yêu cầu các backend zero-data-retention (không lưu giữ dữ liệu). |

Hai cấu hình mẫu đã được thử nghiệm. Đầu tiên, một route tập trung vào tính tuân thủ: chỉ các backend được đặt tên, không dự phòng âm thầm tới ai khác, và không lưu giữ dữ liệu:

```python
"react": p.ModelConfig(
    "openrouter:anthropic/claude-sonnet-5",
    args={
        "provider": {
            "order": ["anthropic", "google-vertex"],
            "allow_fallbacks": False,
            "data_collection": "deny",
        },
    },
),
```

Thứ hai, một route bảo vệ chi phí cho công việc nền với khối lượng lớn: backend rẻ nhất đi trước, với giá trần nghiêm ngặt và chỉ sử dụng weights có độ chính xác đầy đủ:

```python
"matching.*": p.ModelConfig(
    "openrouter:meta-llama/llama-3.3-70b-instruct",
    args={
        "provider": {
            "sort": "price",
            "max_price": {"prompt": 0.5, "completion": 1.0},
            "quantizations": ["fp16", "bf16"],
            "require_parameters": True,
        },
    },
),
```

Bởi vì `provider` là một phần trong `args` của route, các route khác nhau có thể mang các tùy chọn khác nhau — một cấu hình ghim chặt chẽ cho `react` trong khi `matching.*` tìm kiếm theo giá, như ở trên.

**Báo cáo chi phí.** Khoản phí USD chính xác của OpenRouter được ghi lại cho các yêu cầu schematic, ReAct, và embedding dưới dạng chuỗi số thập phân có độ chính xác cố định trong `usage.extra["reported_cost"]`. Mức sử dụng được đánh khóa theo `openrouter:<model path>` (ví dụ `openrouter:anthropic/claude-sonnet-5`), vì vậy chi phí `per_provider` của một phiên thể hiện toàn bộ những gì OpenRouter đã tính phí. Một trace được tạo hoàn toàn từ các thao tác có giá từ provider sẽ có báo cáo chi phí mà không cần gọi `server.set_pricing()`. Hãy cấu hình một bảng giá USD tường minh khi một trace cũng sử dụng các provider hoặc thao tác không tự báo cáo chi phí của chúng. Việc tạo ngân sách cho phiên vẫn yêu cầu `server.set_pricing()`; một bảng USD rỗng là đủ khi mọi thao tác có ngân sách đều cung cấp chi phí có thẩm quyền.

Việc sinh schematic của OpenRouter gửi mô hình Pydantic được yêu cầu dưới dạng định dạng structured-output JSON Schema nghiêm ngặt. Nếu một backend từ chối structured output, adapter sẽ thử lại với chế độ JSON object và sau đó là một prompt thuần JSON tường minh. Chế độ hoạt động được lưu cache trong suốt vòng đời của tiến trình cho mỗi mô hình, cấu hình định tuyến provider, và schema đầu ra, vì vậy các yêu cầu sau đó không phải chịu lại độ trễ dự phòng. Hãy đặt `provider.require_parameters` thành `True` khi OpenRouter chỉ nên định tuyến tới các backend hỗ trợ mọi tham số được yêu cầu, bao gồm cả structured output.

Việc sinh ReAct của OpenRouter sử dụng biểu diễn tương thích giữa các provider cho các chỉ dẫn hệ thống ở giữa cuộc hội thoại. Mã ứng dụng không cần phát hiện xem mô hình phía sau OpenRouter có hỗ trợ các tin nhắn hệ thống ở giữa cuộc hội thoại theo cách gốc hay không.

### LiteLLM

LiteLLM là một cổng hợp nhất trên hơn 100 provider. Không giống như OpenRouter (một cổng HTTP), provider LiteLLM của Parlant điều khiển trực tiếp **LiteLLM Python SDK** (`litellm.acompletion` / `litellm.aembedding`), do đó một provider duy nhất có thể tiếp cận bất kỳ mô hình nào mà LiteLLM hỗ trợ. Cài đặt nó bằng `pip install 'parlant[litellm]'`.

Định danh mô hình sau dấu hai chấm được chuyển nguyên văn tới LiteLLM, vì vậy nó sử dụng quy ước đặt tên riêng của LiteLLM (`provider/model`):

```python
p.ModelConfig("litellm:openai/gpt-4o")
p.ModelConfig("litellm:anthropic/claude-sonnet-5")
p.ModelConfig("litellm:gemini/gemini-3.1-flash-lite")
p.ModelConfig("litellm:bedrock/anthropic.claude-3-5-sonnet-20240620-v1:0")
```

Bởi vì LiteLLM định tuyến tới bất kỳ provider cơ sở nào mà mỗi mô hình gọi tên, không có một `LITELLM_API_KEY` duy nhất: hãy thiết lập key cho các provider mà mô hình của bạn sử dụng (ví dụ: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`). LiteLLM xác minh thông tin xác thực tại thời điểm gọi.

Ví dụ:

```python
server = p.Server(
    models={
        "*": "litellm",
        "react": p.ModelConfig("litellm:anthropic/claude-sonnet-5"),
        "matching.*": p.ModelConfig("litellm:gemini/gemini-3.1-flash-lite"),
        "embedding.*": p.ModelConfig("litellm:openai/text-embedding-3-large"),
    }
)
```

Các tham số hàm khởi tạo được chấp nhận:

| Năng lực | Các tham số |
|---|---|
| Schematic | `api_key` |
| ReAct | `api_key` |
| Embedding | `api_key`, `dimensions` |
| Moderation | Không cung cấp; hãy định tuyến kiểm duyệt sang provider có hỗ trợ. |
| Tokenizer | Không có |

**Báo cáo chi phí.** LiteLLM định giá từng phản hồi mà nó có thể, và adapter hiển thị con số đó làm chi phí có thẩm quyền cho các báo cáo chi phí/sử dụng, ngân sách, và kiểm soát chi phí — không cần bảng giá phía Parlant cho các mô hình đã có giá. Nếu LiteLLM không thể định giá một mô hình (mô hình không có trong bản đồ chi phí của LiteLLM), Parlant sẽ quay lại phương án định giá dựa trên token của chính nó cho route đó, hoàn toàn giống như các provider khác; mục trong bảng khi đó là `litellm:<model>` (ví dụ `"litellm:anthropic/claude-sonnet-5"`) hoặc đường dẫn mô hình trần trụi.

## Thông tin xác thực và Bí mật (Credentials and Secrets)

### Biến môi trường (Environment Variables)

Khi `api_key` bị bỏ qua, các adapter tích hợp sẵn sẽ sử dụng biến môi trường tiêu chuẩn của chúng:

```bash
export OPENAI_API_KEY="..."
export GEMINI_API_KEY="..."
export ANTHROPIC_API_KEY="..."
export OPENROUTER_API_KEY="..."
```

Đây là thiết lập đơn giản nhất trên toàn server. Nó không đủ khi các agent khác nhau cần các thông tin xác thực khác nhau cho cùng một provider.

### Tham chiếu Bí mật Bền vững (Durable Secret References)

`SecretRef` lưu trữ một bộ định vị (locator), không phải là một thông tin xác thực. Ứng dụng của bạn cung cấp một `SecretLoader` phân giải bộ định vị từ hệ thống bí mật hiện có của nó, được liên kết trong container (xem [Tiêm phụ thuộc (Dependency Injection)](dependency-injection.md)):

```python
import parlant.sdk as p


class VaultSecretLoader(p.SecretLoader):
    async def load(self, ref: p.SecretRef) -> str:
        return await MY_VAULT.read(ref.key)


async def configure_container(container: p.Container) -> p.Container:
    container[p.SecretLoader] = VaultSecretLoader()
    return container


server = p.Server(
    configure_container=configure_container,
    models={"*": "openai"},
)

agent = await server.create_agent(
    id="my-agent-3",
    name="Claims Agent",
    instructions="Help customers manage claims.",
    models={
        "react": p.ModelConfig(
            "openai:gpt-4o",
            args={"api_key": p.SecretRef("agents/claims/openai")},
        )
    },
)
```

Parlant lưu trữ bền vững khóa `agents/claims/openai`, chứ không phải khóa đã tải. Trình tải được gọi một cách lười (lazily) khi bản triển khai đã chọn được khởi tạo.

Đối với môi trường phát triển và kiểm thử cục bộ:

```python
async def configure_container(container: p.Container) -> p.Container:
    container[p.SecretLoader] = p.MappingSecretLoader(
        {"agents/claims/openai": "local-development-key"}
    )
    return container


server = p.Server(
    configure_container=configure_container,
    models={"*": "openai"},
)
```

`MappingSecretLoader` giữ các giá trị trong bộ nhớ tiến trình. Nó không phải là một kho lưu trữ bí mật cho production.

### Giá trị Bí mật Tạm thời (Transient Secret Values)

Sử dụng `SecretValue` khi mã ứng dụng đã có sẵn một thông tin xác thực dạng văn bản thuần (plaintext) và không muốn Parlant lưu trữ nó bền vững:

```python
import os


agent = await server.create_agent(
    id="my-agent-4",
    name="Private Agent",
    instructions="...",
    models={
        "react": p.ModelConfig(
            "gemini:gemini-3.1-flash-lite",
            args={"api_key": p.SecretValue(os.environ["PRIVATE_GEMINI_KEY"])},
        )
    },
)
```

Bất kỳ route nào của agent chứa một `SecretValue`, bao gồm cả trường hợp lồng nhau, đều được giữ trong nguồn route cục bộ của tiến trình. Nó sẽ biến mất khi khởi động lại và phải được mã ứng dụng đăng ký lại.

Các liên kết route của server dù sao cũng là cục bộ của tiến trình, vì chúng là cấu hình khởi động chứ không phải dữ liệu của agent.

### Không sử dụng chuỗi thông thường cho Thông tin xác thực của Agent

Các giá trị tham số thông thường trong một route của agent là cấu hình bền vững. Điều này đúng cho các giá trị như `site_url`, `app_name`, `dimensions`, và `max_tokens`, nhưng không đúng cho thông tin xác thực dạng văn bản thuần.

Tránh:

```python
args={"api_key": "plaintext-key"}
```

Thay vào đó, hãy sử dụng `SecretRef` hoặc `SecretValue`: Parlant không thể suy đoán xem một chuỗi tùy ý có phải là dữ liệu nhạy cảm hay không.

Biểu diễn đối tượng và các chẩn đoán định tuyến mô hình sẽ tự động che giấu (redact) các giá trị tham số khởi tạo.

## Cấu hình theo từng Agent (Per-Agent Configuration)

Các route của server là giá trị mặc định. Các route của agent cho phép các agent sử dụng các mô hình hoặc thông tin xác thực khác nhau mà không cần tách riêng các tiến trình Parlant.

```python
server = p.Server(
    models={
        "*": "anthropic",
        "embedding.*": p.ModelConfig("openai:text-embedding-3-large"),
    }
)

fast_agent = await server.create_agent(
    id="my-agent-5",
    name="Fast Agent",
    instructions="Resolve simple requests quickly.",
    models={
        "react": p.ModelConfig("gemini:gemini-3.1-flash-lite"),
        "review.*": p.ModelConfig("gemini:gemini-3.5-flash-lite"),
    },
)

quality_agent = await server.create_agent(
    id="my-agent-6",
    name="Quality Agent",
    instructions="Handle complex requests carefully.",
    models={
        "react": p.ModelConfig("anthropic:claude-sonnet-5"),
        "review.*": p.ModelConfig("anthropic:claude-opus-5"),
    },
)
```

Cả hai agent đều kế thừa route embedding OpenAI của server. Các route ReAct và review của chúng là khác nhau.

Các agent cũng có thể sử dụng cùng một mô hình với các thông tin xác thực riêng biệt:

```python
agent_a = await server.create_agent(
    id="my-agent-7",
    name="Tenant A",
    instructions="...",
    models={
        "react": p.ModelConfig(
            "openai:gpt-4o",
            args={"api_key": p.SecretRef("tenants/a/openai")},
        )
    },
)

agent_b = await server.create_agent(
    id="my-agent-8",
    name="Tenant B",
    instructions="...",
    models={
        "react": p.ModelConfig(
            "openai:gpt-4o",
            args={"api_key": p.SecretRef("tenants/b/openai")},
        )
    },
)
```

Các thực thể mô hình được lưu cache theo provider, model, định danh tham số đã làm sạch, capability, và schematic schema. Do đó, các tham chiếu thông tin xác thực khác nhau không dùng chung một thực thể generator.

## Thay đổi Mô hình Trực tiếp (Live Model Changes)

Việc tra cứu route diễn ra ngay trước mỗi thao tác mô hình. Việc cập nhật một agent không đòi hỏi khởi động lại server, agent hay session.

```python
await agent.update(
    models={
        "react[effort>=high]": p.ModelConfig("openai:gpt-4o"),
    }
)
```

Khung nhìn `agent.models` đã cập nhật sẽ sẵn sàng ngay sau lệnh gọi.

Xóa một phần ghi đè bằng cách gán `None`:

```python
await agent.update(
    models={
        "react[effort>=high]": None,
        "review.*": None,
    }
)
```

Lần phân giải tiếp theo sẽ quay lui qua các route còn lại của agent và sau đó là các route của server.

Một yêu cầu provider đã bắt đầu sẽ hoàn tất trên mô hình ban đầu của nó. Thao tác mô hình tiếp theo sẽ thấy route mới, bao gồm cả một thao tác sau đó trong cùng một lượt.

## Nhà cung cấp Mô hình Tùy chỉnh (Custom Model Providers)

Một `ModelProvider` là một async callable nhận `EngineContext` hiện tại, hoặc `None` cho việc phân giải ngoại tuyến, và trả về đối tượng sẽ thực thi thao tác đã được định tuyến.

```python
import parlant.sdk as p
from parlant.core.nlp.react import ReactGenerator


shared_react = MyReactGenerator(...)


async def provide_react(
    context: p.EngineContext | None,
) -> ReactGenerator:
    return shared_react


agent = await server.create_agent(
    id="my-agent-9",
    name="Custom Agent",
    instructions="...",
    models={"react": p.ModelConfig(provide_react)},
)
```

**Khi nào nó chạy:** callable là bước phân giải của route. Parlant phân giải các route một cách lười, ngay trước mỗi thao tác mô hình. Vì vậy callable chạy mỗi khi route phục vụ một thao tác — có thể vài lần mỗi lượt — và không bao giờ chỉ chạy một lần tại thời điểm cấu hình. Không giống như các chuỗi `provider:model` (vốn có các thực thể được khởi tạo và lưu cache), kết quả của callable được sử dụng đúng như được trả về, ở mỗi lần gọi. Đó là điều giúp cho việc lựa chọn theo từng yêu cầu trở nên khả thi. Nó cũng chạy với `context=None` cho các phân giải ngoại tuyến, chẳng hạn như xác thực các route kiểm duyệt khi khởi động.

Hai hệ quả thực tế: hãy giữ cho callable nhẹ nhàng và không có tác dụng phụ (nó nằm trên đường dẫn nóng - hot path), và để nó *chọn* một đối tượng đã được dựng sẵn thay vì khởi tạo một đối tượng mới. Parlant không cache hoặc đóng đối tượng mà callable trả về, do đó ứng dụng chịu trách nhiệm về an toàn đồng thời (concurrency safety), hành vi hủy (cancellation behavior), và vòng đời tài nguyên.

Provider có thể chọn một đối tượng từ ngữ cảnh hiện tại:

```python
async def provide_react(context: p.EngineContext | None) -> ReactGenerator:
    if context is None:
        return default_react

    tenant = tenant_for_customer(p.Customer.current.id)
    return react_by_tenant[tenant]
```

Điều này cho phép định tuyến đặc thù cho ứng dụng theo agent, session, customer, tenant, feature flag, hoặc bất kỳ trạng thái nào khác mà ứng dụng của bạn sở hữu.

Callable không nhận các bộ định phẩm route làm tham số, nhưng nó không cần: chúng được suy ra từ cùng một lượt — mức effort của nó, ví dụ, là `p.Session.current.effort`. (Đối với việc chọn mô hình thuần túy theo effort, hãy ưu tiên các khóa route có định phẩm effort; chỉ sử dụng provider callable khi logic vượt quá những gì bộ chọn có thể biểu đạt.)

### Định danh Provider trong Báo cáo mức sử dụng

Các bản ghi mức sử dụng và chi phí được đánh khóa theo `provider:model`, và phần provider đến từ đối tượng mà callable trả về: `provider_name` của nó. Một adapter tích hợp sẵn báo cáo dưới tiền tố riêng của nó (`openai`, `anthropic`, ...), do đó ví dụ theo từng tenant ở trên sẽ ghi nhận chi tiêu của mọi tenant dưới cùng một provider. Khi các đối tượng khác nhau theo cách bạn muốn phân biệt rõ — hai tài khoản cho cùng một nhà cung cấp, hai vùng, hai tenant — hãy đặt tên cho chúng khi bạn tạo chúng:

```python
from parlant.adapters.nlp.anthropic_service import AnthropicReactGenerator

react_by_tenant = {
    "acme": AnthropicReactGenerator(
        model="claude-sonnet-5-5",
        logger=logger,
        api_key=acme_key,
        provider_name="anthropic-acme",
    ),
    "globex": AnthropicReactGenerator(
        model="claude-sonnet-5-5",
        logger=logger,
        api_key=globex_key,
        provider_name="anthropic-globex",
    ),
}
```

Mỗi generator schematic, embedder, ReAct generator, và decision maker tích hợp sẵn đều chấp nhận `provider_name`. Một custom adapter tự triển khai một port sẽ cần một thuộc tính `provider_name` khi nó là một ReAct generator (port bắt buộc phải có); các schematic generator và embedder kế thừa nó từ `BaseSchematicGenerator` và `BaseEmbedder`, vốn nhận `provider_name` trong hàm khởi tạo của chúng. Định danh là tự do và không được chứa dấu hai chấm. Hãy định giá mỗi tên bằng một mục `provider:model` trong bảng giá, hoặc để một mục mô hình trần trụi bao quát tất cả; tài liệu [Báo cáo mức sử dụng (Usage Reports)](usage-reports.md#price-table-keys) có các quy tắc cụ thể.

### Schematic Providers bị Ràng buộc bởi Schema

Các thành phần tiêu thụ schematic yêu cầu một schema đầu ra cụ thể. Một custom provider phải trả về một generator được ràng buộc với đúng schema đó:

```python
async def provide_ranker(
    context: p.EngineContext | None,
) -> p.SchematicGenerator:
    # Thực thể này phải có schema là RuleRankSchema được yêu cầu bởi matching.rank.
    return rule_rank_generator


models={"matching.rank": p.ModelConfig(provide_ranker)}
```

Một callback đơn lẻ đằng sau `review.*` chỉ hợp lệ nếu generator được trả về tương thích với mọi schema được yêu cầu qua mẫu đó. Các route schematic chính xác thường rõ ràng và an toàn hơn cho các custom provider.

Parlant xác thực cả năng lực được trả về và schematic schema. Một route React trả về một schematic generator, hoặc một route review trả về một generator cho sai schema, sẽ thất bại trước khi được gọi.

### Tokenizer tùy chỉnh (Custom Tokenizers)

Việc ước tính token cũng được định tuyến:

```python
async def provide_tokenizer(
    context: p.EngineContext | None,
) -> p.EstimatingTokenizer:
    return MyEstimatingTokenizer(...)


agent = await server.create_agent(
    id="my-agent-10",
    name="Custom Tokenizer Agent",
    instructions="...",
    models={"tokenizer": p.ModelConfig(provide_tokenizer)},
)
```

Parlant phân giải route này khi cần ước lượng thay vì tiếp nhận một tokenizer toàn cục cho tiến trình.

### Caching do Provider quản lý

Một model provider có thể chọn bất kỳ vòng đời nào phù hợp với ứng dụng:

```python
# Một thực thể dùng chung duy nhất.
async def shared_provider(context):
    return shared_generator


# Một thực thể cho mỗi tenant.
async def tenant_provider(context):
    tenant_id = tenant_for(context)
    return generators_by_tenant[tenant_id]


# Một thực thể mới cho mỗi thao tác được định tuyến.
async def fresh_provider(context):
    return MyReactGenerator(...)
```

Các callback là các liên kết SDK cục bộ của tiến trình. Hãy đăng ký lại chúng sau khi khởi động lại.

## Xử lý sự cố (Troubleshooting)

### Không có Tuyến đường Mô hình nào có thể Thỏa mãn Thao tác

Ví dụ:

```text
No model route for agent 'claims-agent' can satisfy 'review.tools'
(schematic). Checked: review.tools, review.*, *
```

Hãy cấu hình một route chính xác, một ký tự đại diện phù hợp, hoặc `*` ở phạm vi agent hoặc server.

### Nhà cung cấp không xác định (Unknown Provider)

```text
Unknown model provider 'gemni'. Did you mean 'gemini'?
```

Sử dụng một trong các tiền tố `openai`, `gemini`, `anthropic`, hoặc `openrouter` trước dấu hai chấm đầu tiên.

### Năng lực không được hỗ trợ (Unsupported Capability)

```text
Provider route '*' selected provider 'custom-provider' for route 'embedding.rules',
but provider 'custom-provider' has no default embedding model
```

Thêm một route embedding tường minh sử dụng OpenAI, Gemini, Anthropic (Voyage AI), hoặc OpenRouter.

### Gói Provider chưa được Cài đặt

```text
Gemini model support is not installed. Install it with: pip install 'parlant[gemini]'
```

Hãy cài đặt gói bổ trợ được thông báo hoặc thay đổi route sang một provider sẵn có trong môi trường triển khai. Parlant tải các adapter provider theo yêu cầu, vì vậy lỗi này được nêu ra khi provider lần đầu được cấu hình hoặc phân giải chứ không phải khi các provider không liên quan khác khởi động.

### Tuyến đường Provider không hợp lệ

```text
Provider route '*' must contain one bare provider name
```

Hãy di chuyển mô hình cụ thể sang một task route:

```python
models={
    "*": "openrouter",
    "react": p.ModelConfig("openrouter:openai/gpt-4o"),
}
```

### Ký tự đại diện không hợp lệ

```text
Invalid model route 'react*'; only terminal namespace wildcards and the global
provider route are supported
```

Sử dụng `react` hoặc một bộ chọn có định phẩm như `react[effort=low]`.

### Bộ định phẩm không hợp lệ

```text
Unknown effort level 'medum'. Did you mean 'medium'?
```

Tên bộ định phẩm, các toán tử và giá trị được xác thực khi các route được cấu hình. Hiện tại `effort` là bộ định phẩm duy nhất được hỗ trợ.

### Các Tuyến đường có định phẩm bị Mơ hồ

```text
Model route selectors 'react[effort>=medium]' and
'react[effort<=medium]' are ambiguous because they overlap with equal
specificity
```

Hãy làm cho một bộ chọn hẹp hơn, loại bỏ sự trùng lặp, hoặc thêm một bộ chọn chính xác cho mức nỗ lực bị trùng lặp. Việc chọn route không bao giờ phụ thuộc vào thứ tự sắp xếp trong bảng ánh xạ.

### Tham số bị Sai chính tả hoặc bị Dành riêng

```text
Unsupported openai model argument(s): api_keey. Did you mean 'api_key'?
```

Các tham số do framework sở hữu như `logger`, `tracer`, `meter`, `usage_reporter`, và `provider_name` không thể được cung cấp thông qua `ModelConfig.args`; một mô hình được định tuyến luôn báo cáo dưới tiền tố provider của nó.

### Không thể Tải Tham chiếu Bí mật

Kiểm tra xem:

1. Một `SecretLoader` đã được liên kết trong container (thông qua `configure_container`).
2. Tham chiếu thực sự tồn tại trong hệ thống bí mật của ứng dụng.
3. Trình tải sẵn sàng trong mọi tiến trình có thể khởi tạo mô hình.
4. Route đã chọn thực sự sử dụng tham chiếu dự kiến.

Đừng thay thế một `SecretRef` bị lỗi bằng một tham số văn bản thuần cho agent.

### Kết quả Provider tùy chỉnh Sai loại

Nếu một callback trả về sai kiểu đối tượng hoặc sai schematic schema, hãy cấu hình nó trên đúng route hoặc trả về một bản triển khai khớp với năng lực của route đó. Các route chính xác là lựa chọn ưu tiên trong khi chẩn đoán các custom schematic provider.

### Giới hạn Tần suất không hợp lệ

Hàm khởi tạo từ chối các ràng buộc bị thiếu, không dương, boolean, và không hữu hạn. Nếu một yêu cầu bị đình trệ trong bước tiếp nhận, hãy kiểm tra xem route đã chọn có chia sẻ một named bucket với một route khác có lưu lượng cao hay không.

`RateLimitConflictError` có nghĩa là hai cấu hình được chọn sử dụng cùng một tên bucket tường minh với các ràng buộc khác nhau. Hãy định nghĩa `RateLimit` một lần và tái sử dụng nó, hoặc đặt các tên bucket khác nhau cho các hạn ngạch độc lập.

`UnsupportedRateLimitCapabilityError` có nghĩa là một cấu hình có giới hạn tần suất đã được chọn cho embedding, moderation, hoặc tokenization. Hãy chuyển giới hạn sang một route schematic hoặc ReAct, hoặc thực thi hạn ngạch provider đó trong một custom adapter.
