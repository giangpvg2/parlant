# Công Cụ (Tools)

Tool (công cụ) là một Python function mà agent có thể gọi trong khi soạn thảo câu trả lời. Nó có thể tra cứu thông tin, thực hiện một hành động trên hệ thống bên ngoài, hoặc lấy dữ liệu cần thiết cho một chỉ dẫn. Bạn gắn các tool vào các rule — một policy hoặc một observation. Khi rule áp dụng cho lượt tương tác hiện tại, các tool của nó sẽ được cung cấp cho mô hình, và mô hình sẽ tự động gọi chúng như một phần của vòng lặp phản hồi.

Tài liệu này trình bày tư duy thiết kế (mental model), cách viết và gắn tool, các tùy chọn tham số và các cấu hình nâng cao.

## Tổng quan

```python
import parlant.sdk as p

@p.tool
async def check_balance(account_name: str) -> p.ToolResult:
    return p.ToolResult(
        data=await bank.get_balance(
            p.Customer.current.id,
            account_name,
        )
    )

await agent.create_observation(
    condition="You need to get the customer's current account balance",
    tools=[check_balance],
)
```

Rule quy định khi nào các tool của nó có ý nghĩa. Ở ví dụ trên, một observation mô tả tình huống ("bạn cần lấy số dư tài khoản"), và khi nó khớp với một lượt tương tác, các tool của nó sẽ gia nhập vào danh mục tool của mô hình cho lượt đó. Parlant thực thi các lời gọi mà mô hình đưa ra, đưa kết quả trở lại vòng lặp, và bước tiếp theo sẽ suy luận dựa trên các kết quả đó. Một policy cũng hoạt động theo cách tương tự: các tool của nó được cung cấp trong các lượt mà policy đó được khớp.

Một rule đơn lẻ có thể mang nhiều tool, và một tool có thể phục vụ cho nhiều rule. Việc chọn lọc tool diễn ra ở mọi lượt tương tác: chỉ những tool có rule áp dụng mới được cung cấp. Điều này giúp danh mục tool luôn nhỏ gọn và mô hình giữ được sự tập trung cao độ.

### Vòng lặp thực thi (Execution Loop)

Vòng lặp phản hồi di chuyển qua lại giữa các giai đoạn: suy luận, gọi tool và viết câu trả lời:

1. Parlant khớp các rule và tập hợp danh mục tool cho lượt tương tác.
2. Mô hình suy luận và có thể gọi một hoặc nhiều tool. Nó cũng có thể gọi cùng một tool nhiều lần với các đối số khác nhau.
3. Các kết quả được đưa vào trạng thái làm việc của vòng lặp. Các rule phụ thuộc vào kết quả của tool sẽ được đánh giá lại, và bất kỳ thuật ngữ hay rule nào mà kết quả mang lại sẽ cùng tham gia vào lượt này.
4. Mô hình tiếp tục gọi thêm các tool khác hoặc tiến hành viết câu trả lời hoàn chỉnh.

Các kết quả được lưu vào phiên hội thoại dưới dạng các sự kiện tool (tool events). Tham số điều khiển `lifespan` của kết quả sẽ quyết định liệu chúng có được lưu giữ lâu dài ở đó hay không — xem phần [Vòng đời của kết quả](#vòng-đời-của-kết-quả).

## Kết quả Tool (Tool Results)

`ToolResult` mang nhiều dữ liệu hơn là chỉ một trường dữ liệu `data`:

- `data`: Dữ liệu mô hình nhìn thấy và dùng để suy luận.
- `metadata`: Gắn vào tool event dành riêng cho frontend. Mô hình không bao giờ nhìn thấy trường này.
- `control`: Các tùy chọn xử lý (ví dụ: `lifespan`, session `mode`).
- `canned_responses`: Các văn bản phản hồi soạn sẵn nguyên văn mà tool cung cấp cho lượt này (xem [Phản Hồi Soạn Sẵn](canned-responses.md), mục "Tool-provided responses").
- `canned_response_fields`: Các giá trị thay thế cho các trường trong câu trả lời soạn sẵn.
- `rules`: Các rule tạm thời ("làm điều X cho phản hồi này", có thể kèm độ ưu tiên). Chúng cạnh tranh như bất kỳ chỉ dẫn được khớp nào, chỉ duy nhất cho lượt hiện tại.

## Vòng đời của kết quả (Lifespan)

Một kết quả tool là tài liệu nằm trong prompt. Một kết quả được lưu vào phiên hội thoại sẽ được phát lại (replay) trong mọi lượt tương tác sau này của cuộc trò chuyện đó, vì vậy một kết quả dung lượng lớn không phải là chi phí một lần — mà là chi phí bạn phải trả lại ở mọi lượt cho đến khi phiên kết thúc.

Tham số `lifespan` quyết định điều này, nhận một trong ba giá trị:

```python
@p.tool
async def summarize_policy_document(topic: str) -> p.ToolResult:
    return p.ToolResult(
        data=await docs.render(topic),
        control={"lifespan": "response"},
    )
```

- **`"response"`** — kết quả chỉ phục vụ cho phản hồi hiện tại và không được lưu lại lâu dài. Nó vẫn hoàn toàn khả dụng cho phần còn lại của lượt tương tác hiện tại, bao gồm cả các bước sau, giúp agent có thể suy luận dựa trên nó và gọi thêm các tool khác. Nó chỉ đơn giản là không xuất hiện lại ở lượt tương tác tiếp theo.
- **`"session"`** — kết quả được lưu lại và phát lại ở các lượt tiếp theo, nhờ đó agent vẫn nhớ được thông tin đó mà không cần gọi lại tool.
- **`"auto"`** — giá trị mặc định. Parlant ước tính kích thước của kết quả và tự quyết định: nếu vượt quá khoảng 1.000 token, nó được đối xử như `"response"` và ghi log cảnh báo; các kết quả nhỏ hơn sẽ được lưu theo `"session"`.

Hãy chọn `"response"` khi kết quả có dung lượng lớn, hoặc khi dữ liệu chỉ đúng ở thời điểm tức thời — một tài liệu hoàn chỉnh, tập kết quả tìm kiếm, hàng đợi công việc hôm nay. Đây chính là giải pháp cho câu hỏi "tool của tôi trả về quá nhiều dữ liệu": agent vẫn nhận được toàn bộ dữ liệu để suy luận trong lượt này, và cuộc trò chuyện không phải gánh nặng chi phí token ở các lượt sau. Hãy chọn `"session"` khi đó là một dữ kiện nhỏ gọn mà agent cần ghi nhớ xuyên suốt cuộc trò chuyện, chẳng hạn như số tài khoản mà nó vừa tra cứu.

Parlant đưa ra cảnh báo khi một kết quả có vẻ quá nặng so với vòng đời của nó: trên 2.000 tokens cho `"response"` và `"auto"`, và trên 1.000 tokens cho `"session"` (nơi chi phí bị lặp lại). Một cảnh báo `"session"` sẽ gợi ý chuyển sang `"response"` rõ ràng:

> Tool local:fetch_report returned a session-lifespan result with 3,400 tokens.
> Consider compacting it, or setting ToolResult(control={"lifespan":
> "response"}) to avoid excessive token accumulation throughout the session.

Hãy nghiêm túc lưu tâm đến những cảnh báo này. Chúng là ranh giới giữa một cuộc trò chuyện duy trì chi phí rẻ và một cuộc trò chuyện mà prompt phình to sau mỗi lượt.

### Giới hạn Payload

Một kết quả tool truyền về Parlant qua HTTP, và một đoạn phản hồi đơn lẻ mặc định bị giới hạn ở mức **16KB**. Một tool trả về nhiều hơn mức này sẽ thất bại với lỗi `ToolResultError`:

```
url='http://localhost:8818/...', arguments='...', Response exceeds 16KB limit
```

Bạn có thể nâng giới hạn này bằng biến môi trường, được đọc một lần khi server khởi động:

```sh
export PARLANT_TOOL_RESULT_MAX_PAYLOAD_KB=64
```

Nâng giới hạn là bước đi đúng đắn khi dữ liệu thực sự cần thiết phải đến tay agent trọn vẹn — chẳng hạn một tài liệu dài mà agent bắt buộc phải trích dẫn trực tiếp. Nhưng đó là quyết định sai lầm nếu tool đang trả về một payload thô khổng lồ mà không ai thực sự đọc hết: mô hình sẽ phải trả tiền cho từng token trong đó. Hãy ưu tiên chỉ trả về những gì agent thực sự cần, và kết hợp kết quả lớn với lifespan `"response"` để không lặp lại ở các lượt sau.

## Các tham số (Parameters)

Các tham số của tool được tự động suy luận từ chữ ký hàm (type hints). Các kiểu dữ liệu được hỗ trợ bao gồm kiểu vô hướng (scalars), enums, danh sách (lists), dates/datetimes, `Optional`, và các model Pydantic. Mỗi tham số có thể mang cấu hình `ToolParameterOptions`:

```python
@p.tool
async def transfer(
    amount: int,
    to_account: Annotated[str, p.ToolParameterOptions(
        description="The recipient's account name",
        source="customer",
    )],
) -> p.ToolResult: ...
```

- `description`: Hướng dẫn cách trích xuất đối số. Hiển thị cho mô hình thấy.
- `source`: Nguồn gốc giá trị có thể đến từ đâu: `"customer"` (bắt buộc phải do khách hàng nêu ra, tuyệt đối không được tự đoán), `"context"` (lấy từ dữ liệu phiên, không hỏi lại khách hàng), hoặc `"any"`.
- `significance`: Giải thích tại sao tham số này lại cần thiết. Nó giúp mô hình giải thích cho khách hàng khi cần hỏi giá trị đó.
- `examples`: Các giá trị ví dụ, được gộp vào phần mô tả tham số.
- `hidden`: Chỉ dùng nội bộ: mô hình không bao giờ tiết lộ, nhắc đến hoặc hỏi khách hàng về tham số này.
- `display_name`: Tên thân thiện với khách hàng của tham số. Mô hình sẽ luôn dùng tên này thay vì tên biến kỹ thuật nội bộ mỗi khi trò chuyện với khách hàng.

Khi thiếu một đối số bắt buộc, agent sẽ chủ động hỏi khách hàng một cách tự nhiên trong cuộc trò chuyện, sử dụng display name, tôn trọng thiết lập `source` và không bao giờ để lộ các tham số `hidden`.

## Truy cập ngữ cảnh lượt tương tác từ Tool

Một tool nhận các đối số của nó, và không bắt buộc thêm điều gì khác. Nhưng đôi khi một tool cần biết điều gì đang diễn ra trong cuộc trò chuyện ngay lúc này. Bên trong một lượt tương tác đang chạy, các bộ truy cập `.current` cung cấp bức tranh toàn cảnh:

- `p.Session.current`: Phiên hội thoại đang hoạt động: `.interaction` (cuộc trò chuyện cho đến nay), `.effort` (mức effort đã phân giải của lượt — xem [Nỗ Lực Thích Ứng](adaptive-effort.md)), metadata, và nhiều thông tin khác.
- `p.Customer.current` / `p.Agent.current`: Ai đang nói chuyện, và agent nào đang phục vụ họ.
- `p.Server.current`: Server đang chạy, dùng cho các thao tác SDK từ bên trong tool. Nó cũng cung cấp `.logger`.

**Khi nào nên dùng:** Khi hành vi của tool phụ thuộc vào diễn biến thực tế của lượt tương tác, chứ không chỉ dựa vào các đối số của nó. Dưới đây là hai ví dụ:

Một tool phản ứng với những gì khách hàng vừa nói (lấy attachment từ tin nhắn cuối):

```python
@p.tool
async def file_complaint(summary: str) -> p.ToolResult:
    last = p.Session.current.interaction.last_customer_message
    attachments = last.attachments if last else []
    return p.ToolResult(data=await crm.open_complaint(summary, attachments))
```

Một tool điều chỉnh khối lượng công việc theo mức effort của lượt (tìm kiếm rộng hơn khi yêu cầu phức tạp):

```python
@p.tool
async def search_knowledge_base(query: str) -> p.ToolResult:
    limit = 20 if p.Session.current.effort >= p.Effort.HIGH else 5
    return p.ToolResult(data=await kb.search(query, limit=limit))
```

**Một lưu ý quan trọng:** Các bộ truy cập `.current` chỉ hoạt động đối với các tool chạy cùng tiến trình với Parlant server. Một tool được lưu trữ trên một dịch vụ từ xa (remote service) riêng biệt sẽ không thể sử dụng chúng. Những tool như vậy nên dựa hoàn toàn vào các đối số truyền vào.

Đối với trường hợp dịch vụ từ xa, tool có thể khai báo một tham số đầu tiên tùy chọn: `context: p.ToolContext`. Nó mang các thông tin cơ bản: session id, agent id, customer id, cùng với các callback để phát sự kiện. Parlant truyền nó qua mạng đến các remote plugin service. Các tool chạy in-process không cần đến nó — đối với chúng, hãy ưu tiên các accessor `.current`.

```python
@p.tool
async def remote_lookup(context: p.ToolContext, query: str) -> p.ToolResult:
    return p.ToolResult(data=await search(query, customer_id=context.customer_id))
```

## Công cụ có tác động lớn (Consequential Tools)

Hãy đánh dấu một tool là `consequential=True` khi việc thực thi nó gây ra các hiệu ứng thực tế trong đời thực mà khách hàng cần phải phê duyệt trước: một giao dịch thanh toán, một lượt đặt chỗ, một hành động không thể hoàn tác.

```python
@p.tool(consequential=True)
async def book_flight(destination: str, date: str) -> p.ToolResult: ...
```

Agent bắt buộc phải xác nhận lại với khách hàng trước khi chạy một consequential tool. Các thao tác tra cứu thông thường không nên đánh dấu là consequential; agent sẽ thực hiện chúng trực tiếp như một phần của việc xử lý yêu cầu mà không cần hỏi xin phép.

## Thông báo cho khách hàng biết Agent đang làm gì (Narration)

Trong khi tool đang chạy, khách hàng sẽ nhìn thấy một trạng thái. Mặc định trạng thái đó là thông báo chung chung *Running tools*, không nói rõ điều gì thực sự đang diễn ra. Hãy cung cấp cho tool tham số `narration`, và Parlant sẽ phát tin nhắn của bạn ngay khi tool bắt đầu chạy:

```python
@p.tool(narration="Looking up your order…")
async def check_order_status(order_id: str) -> p.ToolResult: ...
```

Bạn có thể truyền một danh sách các câu, Parlant sẽ chọn ngẫu nhiên một câu cho mỗi lần gọi, giúp khách hàng không phải đọc đi đọc lại cùng một câu nếu phải đợi qua 2 lần tra cứu:

```python
@p.tool(narration=["Checking with the warehouse…", "Looking up your order…"])
async def check_order_status(order_id: str) -> p.ToolResult: ...
```

Đối với thông điệp phụ thuộc vào người đang hỏi, hãy truyền một hàm. Hàm này được phân giải trên server một lần cho mỗi lần gọi, và chỉ chuỗi kết quả cuối cùng mới được gửi tới client. Các tham số của nó được liên kết theo tên: khai báo `context: ToolContext` để nhận agent, session và customer id, và đặt tên bất kỳ key `plugin_data` nào bạn cần. Hàm có thể là đồng bộ hoặc bất đồng bộ:

```python
async def narrate_lookup(context: p.ToolContext) -> str:
    customer = await customers.find(context.customer_id)
    return f"Looking up {customer.first_name}'s order…"


@p.tool(narration=narrate_lookup)
async def check_order_status(order_id: str) -> p.ToolResult: ...
```

Narration hoạt động theo cơ chế best-effort: nếu việc phân giải narration thất bại, Parlant sẽ ghi log cảnh báo, giữ nguyên trạng thái mặc định và vẫn thực thi tool bình thường: một tin nhắn trạng thái tuyệt đối không bao giờ được làm hỏng câu trả lời của khách hàng.

Tin nhắn của bạn đến dưới dạng sự kiện `status` với `status="processing"`, phát ra một lần cho mỗi lượt gọi tool ngay sau thông báo chung:

```
processing | Running tools
processing | Checking with the warehouse…
```

Cả hai sự kiện đều nằm trong luồng stream; client nào hiển thị trạng thái mới nhất sẽ hiển thị thông điệp của bạn. Trên giao thức AG-UI, chúng đến dưới dạng các sự kiện `CUSTOM` có tên `parlant.status`; xem [AG-UI](ag-ui.md).

## Nâng cao: Các công cụ chồng chéo nhau (Overlapping Tools)

Đôi khi có hai tool cùng giải quyết một vấn đề tương tự: một công cụ tìm kiếm chuyên biệt đặt cạnh một công cụ tìm kiếm chung, hoặc cùng một thao tác được cung cấp bởi hai dịch vụ khác nhau. Việc gọi cả hai cho cùng một mục đích sẽ gây trùng lặp công việc — hoặc tệ hơn là gây trùng lặp tác dụng phụ (side effect).

Hãy khai báo sự chồng chéo và Parlant sẽ chỉ dẫn mô hình rằng các tool này là sự lựa chọn thay thế lẫn nhau:

- Thiết lập trên từng tool thông qua tùy chọn `overlap`:
  - `ToolOverlap.AUTO` (mặc định) — coi là chồng chéo khi có mối quan hệ khai báo nó.
  - `ToolOverlap.ALWAYS` — luôn được coi là sự thay thế cho mọi tool khác được cung cấp cùng lúc với nó.
  - `ToolOverlap.NONE` — không bao giờ bị coi là chồng chéo, ngay cả khi có mối quan hệ chỉ định tên nó.

Khi bất kỳ tool nào được cung cấp trong lượt tương tác bị chồng chéo (và chỉ khi đó), Parlant sẽ thêm một ghi chú vào chỉ dẫn phản hồi. Ghi chú này liệt kê các cặp công cụ chồng chéo và yêu cầu mô hình chỉ chọn duy nhất một tool phù hợp nhất cho mỗi mục tiêu. Các mục tiêu khác nhau trong cùng một yêu cầu vẫn có thể dùng các tool khác nhau: yêu cầu "chuyển 200 shekels cho Alisse và 300 USD cho Bob" sẽ sử dụng chính xác `transfer_shekels` cho khoản thứ nhất và `transfer_money` cho khoản thứ hai. Nếu không cấu hình overlap, không có prompt bổ sung nào được sinh ra và không tốn thêm token nào.
