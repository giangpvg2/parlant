# Biến Ngữ Cảnh (Context Variables)

Một **biến ngữ cảnh (context variable)** là một giá trị có tên mà Parlant nạp vào ngữ cảnh của agent trước khi một lượt hội thoại (turn) bắt đầu. Đây là cách agent biết nó đang trò chuyện với ai mà không cần phải hỏi người dùng, cũng như không cần tiêu tốn một lượt gọi công cụ (tool call) để tìm hiểu.

```python
await agent.create_variable(
    name="subscription_plan",
    description="The plan this customer is on, which decides what they can be offered.",
)
```

Agent sẽ nhìn thấy tên biến, mô tả của biến và giá trị hiện tại của nó trong mọi lượt hội thoại. Nhờ đó, một policy có thể quy định "cung cấp ưu đãi giảm giá hàng năm cho khách hàng theo gói tháng", và agent đã biết sẵn khách hàng này đang thuộc gói nào.

## Thiết lập giá trị

Một biến có thể giữ giá trị khác nhau cho từng khách hàng, từng nhóm, từng agent, hoặc một giá trị chung cho tất cả mọi người:

```python
plan = await agent.create_variable(name="subscription_plan")

await plan.set_value_for_customer(customer, "premium")
await plan.set_value_for_tag(vip_group.id, "premium")
await plan.set_value_for_agent(agent, "trial")
await plan.set_global_value("free")
```

Các giá trị đều có thể tuần tự hóa thành JSON (JSON-serializable), do đó biến có thể chứa một chuỗi ký tự, một con số hoặc cả một object hoàn chỉnh.

### Thứ tự ưu tiên giá trị mà agent nhìn thấy

Parlant tìm kiếm giá trị theo thứ tự sau và dừng lại ở giá trị đầu tiên tìm thấy:

1. Giá trị riêng của chính khách hàng (`customer`)
2. Giá trị được thiết lập cho nhóm/tag mà khách hàng thuộc về
3. Giá trị được thiết lập cho agent
4. Giá trị toàn cục (`global`)

Như vậy, giá trị toàn cục đóng vai trò là giá trị mặc định, giá trị theo nhóm sẽ ghi đè lên giá trị toàn cục đối với các khách hàng trong nhóm đó, và giá trị riêng của khách hàng sẽ được ưu tiên cao nhất so với cả hai mức trên. Một biến không có giá trị ở bất kỳ cấp độ nào sẽ đơn giản là không xuất hiện trong lượt hội thoại.

## Biến tự động duy trì tính cập nhật

Giá trị bạn gán thủ công sẽ giữ nguyên trạng thái bạn đã gán. Để Parlant tự động truy vấn dữ liệu thay thế, hãy gắn kèm một tool và chỉ định mức độ cập nhật (freshness) mong muốn của giá trị:

```python
@p.tool
async def fetch_open_orders(context: p.ToolContext) -> p.ToolResult:
    return p.ToolResult(data=await orders.open_for(context.customer_id))


await agent.create_variable(
    name="open_orders",
    description="The customer's orders that have not been delivered yet.",
    tool=fetch_open_orders,
    freshness_rules="*/15 * * * *",
)
```

`freshness_rules` là một biểu thức cron mô tả thời điểm giá trị đã lưu bị coi là hết hạn (stale). Parlant tính toán thời gian kể từ thời điểm giá trị được ghi lần cuối: nếu chưa đến thời điểm đã lên lịch tiếp theo, giá trị đã lưu sẽ được tái sử dụng nguyên trạng; nếu đã đến hạn, Parlant sẽ gọi tool và lưu lại kết quả trả về.

Từ cơ chế này, có hai điều cần lưu ý: Tool được gọi mà **không có đối số (arguments)** nào — chỉ có `ToolContext` mang theo agent id, session id và customer id — vì không có lượt chat trực tiếp để lấy đối số. Và nếu không cấu hình `freshness_rules`, biến gắn tool sẽ bị làm mới ở **mọi** lượt hội thoại, điều mà hiếm khi bạn mong muốn.

## Giữ kích thước giá trị nhỏ gọn

Giá trị của biến ngữ cảnh nằm trong prompt ở mọi lượt tương tác, vì vậy dung lượng của nó là một chi phí lặp lại liên tục, chứ không phải chi phí một lần. Parlant sẽ đưa ra cảnh báo khi một biến gắn tool sinh ra nhiều hơn khoảng 1.000 token:

> Tool-enabled context variable 'open_orders' produced 4,300 tokens for key
> 'guest'. Consider compacting it or using a tool with a response-lifetime
> result instead.

Hãy làm theo lời khuyên đó: Chỉ trả về bản tóm tắt thay vì toàn bộ payload dữ liệu thô — ví dụ trả về 3 dòng tóm tắt đơn hàng thay vì toàn bộ object đơn hàng chi tiết — hoặc chuyển dữ liệu sang một tool hay retriever, nơi mà nó chỉ tiêu tốn chi phí cho các lượt thực sự cần dùng đến.

## So sánh Biến (Variables), Công cụ (Tools) và Bộ truy xuất (Retrievers)

Cả ba đều đưa dữ liệu bên ngoài đến trước mặt agent, và chúng khác nhau ở thời điểm việc truy xuất diễn ra:

| | Khi nào chạy | Vòng đời tồn tại | Phù hợp nhất cho |
|---|---|---|---|
| **Variable** | Trước lượt hội thoại, theo lịch của bạn | Đến lần làm mới (refresh) tiếp theo | Các dữ kiện ít thay đổi: gói dịch vụ, hạng mức, quyền lợi |
| **Retriever** | Trong giai đoạn chuẩn bị, chạy song song | Trong phản hồi này | Ngữ cảnh mà lượt này cần, do bạn quyết định |
| **Tool** | Giữa lượt hội thoại, khi agent chủ động gọi | Trong phản hồi này | Các hành động, và các truy vấn cần tham số từ cuộc trò chuyện |

Một mẹo phân biệt hữu ích: Nếu câu trả lời cho khách hàng này vẫn giữ nguyên trong một giờ tới, đó là một **variable**. Nếu nó chỉ đúng đối với cuộc trò chuyện hiện tại, đó là một **retriever**. Nếu agent phải tự cân nhắc xem có cần hỏi/truy vấn hay không, đó là một **tool**.

Xem thêm [Tools](tools.md) và [Retrievers](retrievers.md).

## Viết mô tả (description) tốt

Phần mô tả không phải là một ghi chú comment thông thường. Nó được gửi đến mô hình cùng với giá trị của biến, và là thứ hướng dẫn model cách hiểu giá trị đó.

```python
# Không nên: model thấy "tier: 2" và phải tự đoán 2 nghĩa là gì.
await agent.create_variable(name="tier")

# Nên: giá trị giờ đây đã mang đầy đủ ý nghĩa rõ ràng.
await agent.create_variable(
    name="tier",
    description=(
        "Loyalty tier from 1 to 3. Tier 3 customers get free returns; "
        "tier 1 customers pay return shipping."
    ),
)
```

Khi ý nghĩa của biến dẫn dắt hành vi của agent, hãy đưa hành vi đó vào một policy và để phần description chỉ giải thích giá trị đó *là gì*. Xem thêm [Policy Design](policy-design.md).
