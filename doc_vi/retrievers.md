# Bộ Truy Xuất Dữ Liệu (Retrievers)

Một **retriever** (bộ truy xuất) là một async function thực hiện lấy thông tin và nạp nó vào ngữ cảnh của agent cho một lượt hội thoại. Bạn gắn nó vào một agent, hoặc vào một policy hay observation đơn lẻ, và Parlant sẽ thực thi nó như một phần của quá trình chuẩn bị phản hồi.

Agent không bao giờ phải tự quyết định việc gọi một retriever. Đó chính là điểm khác biệt cốt lõi giữa retriever và tool, và là toàn bộ mục đích của tính năng này.

## Động lực và Ý nghĩa

Một lượt gọi tool (tool call) tiêu tốn một vòng khứ hồi (round trip). Mô hình phải đọc cuộc hội thoại, quyết định xem tool có áp dụng hay không, sinh các đối số (arguments), chờ đợi kết quả trả về, và chỉ sau đó mới viết câu trả lời. Quy trình đó là phù hợp khi việc ra quyết định thực sự quan trọng — khi agent phải cân nhắc *có nên* tra cứu điều gì đó hay không, hoặc cần tra cứu *cái gì*.

Tuy nhiên, trong nhiều trường hợp, việc này không cần mô hình phải quyết định. Nếu mọi cuộc trò chuyện về đơn hàng đều cần có lịch sử đơn hàng của khách hàng, thì không có gì phải cân nhắc cả. Bắt mô hình phải tự quyết định sẽ cộng thêm một bước vào vòng lặp và tăng nguy cơ xảy ra sai sót.

Một retriever tự động chạy độc lập. Parlant khởi chạy các retriever ở cấp agent ngay khi tin nhắn của khách hàng được ghi nhận, song song với phần còn lại của quá trình chuẩn bị, và chờ đợi (await) chúng hoàn tất trước khi agent viết câu trả lời. Dữ liệu đã có sẵn ở đó, và không tốn một bước lặp nào để lấy nó.

Các retriever cũng mang tính **nhận biết ngữ cảnh (contextual)**. Khi gắn một retriever vào một policy hoặc observation, nó chỉ chạy trong những lượt mà rule đó được khớp, đảm bảo công việc chỉ diễn ra chính xác khi tình huống tương ứng xảy ra.

## So sánh Tools, Retrievers và Variables

Ba tính năng này đưa dữ liệu bên ngoài đến trước mặt agent. Chúng khác nhau ở chỗ ai quyết định và khi nào việc truy xuất diễn ra:

| | Ai quyết định lấy dữ liệu | Khi nào chạy | Phù hợp nhất cho |
|---|---|---|---|
| **Tool** | Agent | Giữa lượt hội thoại, trong vòng lặp | Các hành động, và các truy vấn cần tham số từ cuộc trò chuyện |
| **Retriever** | Bạn | Trong quá trình chuẩn bị, chạy song song | Ngữ cảnh mà lượt tương tác luôn cần, hoặc một rule được khớp luôn cần |
| **Variable** | Parlant | Trước lượt hội thoại, theo lịch trình | Các dữ kiện ít thay đổi về khách hàng |

Xem thêm [Tools](tools.md) và [Biến Ngữ Cảnh](variables.md).

## Retriever ở cấp toàn Agent (Agent-wide retriever)

```python
async def recall_recent_orders(ctx: p.RetrieverContext) -> p.RetrieverResult | None:
    orders = await orders_service.recent(ctx.customer.id)

    if not orders:
        return None

    return p.RetrieverResult(
        data=[f"Order {o.id}: {o.status}, expected {o.eta}" for o in orders],
    )


await agent.attach_retriever(recall_recent_orders)
```

`data` là bất kỳ giá trị nào có thể tuần tự hóa thành JSON và đến được với agent dưới dạng ngữ cảnh truy xuất cho lượt đó. Trả về `None` đồng nghĩa với việc không thêm gì cả — đó là cách thông thường để nói "không có thông tin liên quan ở đây", và nó hoàn toàn không tốn chi phí cho lượt tương tác.

Bạn có thể gắn bao nhiêu retriever tùy thích. Chúng chạy đồng thời (concurrently), và mỗi hàm tự quyết định độc lập xem nó có đóng góp gì hay không.

## Retriever gắn với một Rule (Rule-bound retriever)

Gắn một retriever vào một policy hoặc một observation và nó chỉ chạy khi rule đó được khớp:

```python
refund_questions = await agent.create_observation(
    condition="the customer asks about a refund they are expecting",
)

async def load_refund_status(ctx: p.RetrieverContext) -> p.RetrieverResult | None:
    refund = await billing.pending_refund(ctx.customer.id)

    if refund is None:
        return None

    return p.RetrieverResult(
        data=f"Pending refund of ${refund.amount:.2f}, issued {refund.issued_on}.",
    )


await refund_questions.attach_retriever(load_refund_status)
```

Giờ đây, lệnh gọi sang hệ thống thanh toán (billing) chỉ xảy ra trong các lượt hỏi về hoàn tiền và không xuất hiện ở bất kỳ đâu khác. Rule quyết định tình huống; retriever cung cấp các dữ kiện cho tình huống đó.

Việc gắn retriever sẽ làm thay đổi cách rule được đánh giá. Một rule có gắn retriever phải nhận được phán quyết thực sự theo từng lượt, do đó Parlant đánh dấu nó cần được xếp hạng (ranked) thay vì chỉ đơn thuần là gợi nhớ (recalled). Xem thêm [Khám Phá Rule (Rule Discovery)](rule-discovery.md).

## Mô tả các Attachment trong Dashboard

Cả hai phương thức gắn kết đều chấp nhận các tham số dạng keyword-only tùy chọn là `title` và `description`:

```python
await refund_questions.attach_retriever(
    load_refund_status,
    id="refund-status",
    title="Pending refund status",
    description="Supplies the customer's pending refund when this observation matches.",
)
```

Các trường này dùng để mô tả liên kết attachment. Chúng không thực thi hàm, không làm thay đổi việc khớp rule, và không trở thành ngữ cảnh truy xuất. Không đưa thông tin đăng nhập hoặc dữ liệu nhạy cảm của khách hàng vào các phần mô tả này. Dashboard sẽ hiển thị tiêu đề `title` (hoặc tên đăng ký cục bộ hiện có nếu không có title) và liên kết attachment với đối tượng sở hữu của nó. Các attachment ở cấp toàn agent sẽ xuất hiện trong tab riêng **Retrievers**.

Mỗi liên kết gắn với rule là một hook riêng biệt, ngay cả khi cùng một hàm hoặc id cục bộ được gắn hai lần. Việc tái sử dụng id cấp agent sẽ thay thế callback hiện có của agent đó. Danh mục lưu trữ giữ nguyên các ngữ nghĩa này. Các attachment id ẩn danh của nó xác định server/container hiện tại; chúng không phải là id thực thi bền vững theo lịch sử.

Danh mục chỉ chứa metadata và tham chiếu đối tượng sở hữu. Nó không để lộ callback, mã nguồn, giá trị đã truy xuất, hoặc bằng chứng rằng retriever đã chạy. Việc liệt kê danh mục không kích hoạt các callback trực tiếp hay trì hoãn. Các runtime cũ hơn sẽ hiển thị thông báo nâng cấp thay vì danh mục trống; lỗi đọc danh mục được hiển thị riêng.

## Dữ liệu một Retriever có thể trả về

`RetrieverResult` có thể mang nhiều dữ liệu hơn là chỉ một trường `data`:

```python
return p.RetrieverResult(
    data="Order 1234 shipped on Tuesday.",
    metadata={"source": "orders-api"},
    canned_responses=["Your order shipped on {{ ship_date }}."],
    canned_response_fields={"ship_date": "Tuesday"},
    rules=[{"content": "Offer expedited shipping on the next order"}],
)
```

- **`data`** — chính là ngữ cảnh được truy xuất.
- **`metadata`** — mang đi kèm kết quả, phục vụ client và việc theo dõi (observability).
- **`canned_responses`** — các tin nhắn mẫu nguyên văn cho lượt này. Một phản hồi được cung cấp theo cách này sẽ bỏ qua khâu xếp hạng độ liên quan, vì nó đã được chọn chính xác cho thời điểm này. Xem [Phản Hồi Soạn Sẵn](canned-responses.md).
- **`canned_response_fields`** — các giá trị điền vào các placeholder `{{ placeholders }}` trong các câu trả lời soạn sẵn của lượt này.
- **`rules`** — các rule tạm thời chỉ áp dụng cho phản hồi này, được diễn đạt như nội dung của một policy, với các thuộc tính tùy chọn `condition`, `priority`, và `weight`.

Một kết quả không chứa bất kỳ trường nào trong số này sẽ được coi là không truy xuất được gì, và Parlant sẽ không thêm gì vào lượt tương tác.

## Quyết định muộn: Deferred Retrievers

Một retriever ở cấp agent bắt đầu từ rất sớm, trước khi Parlant biết rule nào được khớp. Đôi khi công việc nên được bắt đầu sớm nhưng *quyết định sử dụng* lại cần bức tranh toàn cảnh đến muộn hơn. Hãy trả về một callable thay vì một kết quả, và Parlant sẽ gọi nó sau khi hoàn tất việc khớp rule, kèm theo toàn bộ context của engine.

Dạng này chỉ thuộc về retriever cấp toàn agent. Một retriever gắn với rule vốn dĩ đã chạy sau khi khớp rule — đó là ý nghĩa của việc "gắn vào một rule" — do đó nó không có gì để trì hoãn cả:

```python
import asyncio

billing_questions = await agent.create_observation(
    condition="the customer asks about billing, an invoice, or a charge",
)


async def load_account_health(ctx: p.RetrieverContext) -> p.DeferredRetriever:
    # Bắt đầu ngay lập tức, song song với phần còn lại của khâu chuẩn bị.
    report = asyncio.create_task(analytics.account_health(ctx.customer.id))

    async def decide(engine_ctx: p.EngineContext) -> p.RetrieverResult | None:
        # Chạy khi các rule của lượt tương tác đã được xác định.
        rules_in_play = {rule.id for rule in engine_ctx.state.discovered_rules}

        if billing_questions.id not in rules_in_play:
            report.cancel()
            return None

        return p.RetrieverResult(data=await report)

    return decide


await agent.attach_retriever(load_account_health)
```

Đọc tập hợp đang hoạt động từ `discovered_rules`. Một observation không có gì gắn vào nó sẽ được đưa vào đây và thể hiện dưới dạng một chỉ dẫn thường trực; nó không bao giờ có phán quyết khớp theo từng lượt, vì vậy việc tìm kiếm nó trong các kết quả khớp của lượt sẽ không thấy gì.

Lời gọi hàm tốn kém tài nguyên vẫn diễn ra gối đầu với khâu chuẩn bị trong cả hai trường hợp. Điều mà callable dạng trì hoãn (deferred) bổ sung là khả năng hủy bỏ kết quả khi lượt tương tác hóa ra không cần đến nó — vì vậy hãy hủy công việc bạn đã khởi chạy trước khi trả về `None`.

## Chi phí đối với lượt tương tác

Kết quả của một retriever đi vào lượt tương tác dưới dạng kết quả tool mang id của retriever, với vòng đời theo phản hồi (response lifespan): nó chỉ thuộc về phản hồi này, và không kéo dài sang các lượt sau.

Điều này dẫn đến hai hệ quả đáng chú ý: Mọi thứ mà retriever trả về đều là văn bản nằm trong prompt, do đó một retriever trả về tài liệu dung lượng lớn sẽ tiêu tốn token thực tế ở mỗi lượt nó chạy. Và vì agent không chủ động yêu cầu nó, nó không thể từ chối — dữ liệu sẽ hiển thị trước mặt mô hình bất kể lượt tương tác cụ thể này có thực sự cần hay không. Tốt nhất là hãy trả về `None` thay vì trả về những dữ liệu cận biên ít hữu ích.

## Khi nào chọn Tool và khi nào chọn Retriever

Hãy chọn **retriever** khi:

- Dữ liệu cần thiết ở mọi lượt, hoặc ở mọi lượt mà một rule được khớp
- Không có gì phải suy luận để quyết định và không có tham số cần trích xuất
- Bạn muốn quá trình truy xuất diễn ra gối đầu song song với khâu chuẩn bị

Hãy chọn **tool** khi:

- Agent phải tự đánh giá xem tình huống có cần đến nó hay không
- Lời gọi cần các tham số từ cuộc trò chuyện, chẳng hạn như mã đơn hàng
- Nó thực hiện hành động làm thay đổi thế giới bên ngoài thay vì chỉ đọc dữ liệu, và có thể cần xác nhận từ người dùng (xem [Tools](tools.md))

Hai thành phần này có thể kết hợp với nhau: Một retriever có thể nạp các đơn hàng đang mở của khách hàng để agent bước vào cuộc hội thoại với đầy đủ thông tin, trong khi một tool sẽ thực hiện khiếu nại khi khách hàng yêu cầu.
