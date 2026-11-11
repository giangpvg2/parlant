# Nỗ Lực Thích Ứng (Adaptive Effort)

Effort (mức độ nỗ lực) kiểm soát lượng tài nguyên tính toán mà một agent đầu tư vào một lượt tương tác (turn). Nó ảnh hưởng đến việc mô hình nào sẽ chạy, mô hình suy luận sâu đến đâu, các rule được khớp cẩn thận như thế nào, và một quá trình duyệt (review) có bao nhiêu cơ hội thử lại.

Có 5 cấp độ effort: `MIN`, `LOW`, `MEDIUM`, `HIGH`, và `MAX`. Bạn có thể thiết lập effort ở hai vị trí:

- **Trên agent** — mức cơ sở (baseline) mà mọi lượt tương tác bắt đầu.
- **Trên một rule** — một policy hoặc observation khi được khớp có thể nâng mức effort của lượt tương tác hiện tại lên cao hơn.

Tại sao lại cần cả hai? Phần lớn các lượt tương tác trong hội thoại là thông thường và nên chạy nhanh chóng với chi phí rẻ. Tuy nhiên, bạn không thể biết trước lượt nào sẽ quan trọng. Với nỗ lực thích ứng (adaptive effort), chính diễn biến cuộc hội thoại sẽ phát tín hiệu khi tình huống trở nên nghiêm trọng — và agent chỉ chi tiêu nhiều tài nguyên tính toán hơn trong những trường hợp đó.

## Mức cơ sở của agent (Baseline)

```python
agent = await server.create_agent(
    id="my-agent",
    name="Support Agent",
    instructions="...",
    effort=p.Effort.MEDIUM,   # MEDIUM là giá trị mặc định sẵn có
)
```

Mức baseline là điểm xuất phát của mọi lượt tương tác. Các rule có thể nâng mức này lên cho một lượt cụ thể, nhưng không bao giờ hạ thấp nó xuống.

## Nâng mức effort từ một rule

Bất kỳ policy hay observation nào cũng có thể mang tham số `trigger_effort`:

```python
await agent.create_observation(
    condition="the customer disputes a charge or threatens legal action",
    trigger_effort=p.Effort.HIGH,
)
```

Miễn là observation này được khớp, **mức effort động (dynamic effort level)** của lượt đó sẽ trở thành giá trị cao nhất giữa baseline của agent và tất cả các trigger của các rule được khớp. Ví dụ: một trigger `HIGH` trên agent có baseline `MEDIUM` sẽ tạo ra một lượt chạy ở mức `HIGH`. Hai trigger không cộng dồn vượt quá mức cao nhất. Một rule đã khớp ở lượt trước nhưng không khớp ở lượt hiện tại sẽ không có tác dụng lên effort.

Việc nâng mức effort có hiệu lực ngay lập tức trong cùng một lượt tương tác. Trong ví dụ trên, ngay khi observation được khớp, phần còn lại của lượt — chọn tool, sinh phản hồi, duyệt review — đều chạy ở mức effort `HIGH`.

## Effort thay đổi những gì

**Mô hình nào sẽ chạy.** Mức effort được chuyển đến bộ định tuyến mô hình (model routing) dưới dạng định danh `effort`, giúp các route có điều kiện effort lựa chọn mô hình khác nhau theo từng cấp độ. Cấu hình mặc định của các provider tích hợp sẵn đã hoạt động theo cách này: ví dụ cấu hình react mặc định của OpenAI sử dụng model nhỏ hơn ở mức `min`/`low` và model lớn nhất ở mức `max`. Xem thêm [Cấu hình Model và Provider](providers.md).

```python
models={
    "react": p.ModelConfig("openai:gpt-5.6-luna"),
    "react[effort>=high]": p.ModelConfig("openai:gpt-5.6-terra", reasoning="high"),
}
```

**Độ sâu suy luận của responder.** Nếu một route không thiết lập `reasoning` rõ ràng, độ sâu suy luận của bộ phản hồi (responder) sẽ tuân theo cấp độ effort: tối thiểu và ẩn ở mức `MIN`, sâu hơn ở các mức cao hơn.

**Độ kỹ lưỡng khi khớp rule.** Ở mức effort cao hơn, nhiều rule hơn sẽ được mô hình kiểm tra riêng lẻ câu hỏi "rule này có thực sự áp dụng lúc này không?", thay vì chỉ dựa vào tìm kiếm tương đồng (similarity search).

Các rule nào được kiểm tra riêng lẻ phụ thuộc vào trọng số (weight) của chúng:

| Effort | Kiểm tra riêng lẻ từng rule | Chỉ tìm kiếm theo độ tương đồng |
|---|---|---|
| `MIN` / `LOW` | — | Tất cả các trọng số |
| `MEDIUM` | Rule có trọng số HIGH | LOW, MEDIUM |
| `HIGH` / `MAX` | Rule có trọng số MEDIUM và HIGH | LOW |

Một số rule luôn được kiểm tra sâu hơn ở bất kỳ cấp độ effort nào, vì phán quyết của chúng ảnh hưởng đến các thành phần khác, do đó việc khớp sai sẽ gây tổn thất lớn hơn. Ví dụ: các rule có nhãn (label), các rule mà rule khác phụ thuộc vào, các rule trong mối quan hệ ưu tiên (priority), các rule liên kết với tool, và các rule kích hoạt review.

**Quy trình review có chạy không và chạy thế nào.** Ở mức `MIN`, không có review nào chạy cả. Ở tất cả các mức khác, các yêu cầu review đều được tôn trọng, và mức effort cao hơn cho phép thử lại nhiều lần hơn sau khi review từ chối bản nháp (2 lần ở `LOW`, lên đến 10 lần ở `MAX`). Xem thêm [Đánh giá Tool & Tin nhắn Tích hợp](review.md).

**Cách thu gọn lịch sử hội thoại (compaction).** Effort cao hơn sẽ giữ lại nhiều lịch sử gốc hơn trước khi nén, và viết tóm tắt chi tiết hơn khi thực hiện nén. Xem thêm [Nén Phiên Hội Thoại](compaction.md).

**Có đánh giá lại rule sau khi chạy tool hay không.** Trên mức `LOW`, một bước diễn ra sau một lượt gọi tool sẽ đánh giá lại các rule bị ràng buộc vào nó, nhờ đó các rule mà kết quả tool làm cho có hiệu lực vẫn có thể tham gia vào lượt này. Ở mức `MIN` và `LOW`, lượt hội thoại giữ nguyên tập rule đã khớp ban đầu.

**Cách chọn câu trả lời soạn sẵn (canned responses).** Trên mức `LOW`, các ứng viên phản hồi soạn sẵn được xếp hạng theo độ liên quan với ngữ cảnh thời điểm đó và chỉ vài câu tốt nhất được hiển thị. Ở mức `MIN` và `LOW`, không có xếp hạng — việc xếp hạng đòi hỏi phải embed tin nhắn của khách hàng và tìm kiếm trong vector store — nên mọi phản hồi đủ điều kiện đều được hiển thị, cho đến khi đạt giới hạn lớn hơn. Xem thêm [Phản Hồi Soạn Sẵn](canned-responses.md).

## MIN: Mức chi phí tối thiểu

`Effort.MIN` không chỉ đơn giản là "ít hơn LOW một chút". Đây là cấp độ mà Parlant bỏ qua hoàn toàn các tác vụ tùy chọn: không chạy review (kể cả khi được yêu cầu), chỉ tìm kiếm tương đồng cho toàn bộ việc khớp rule, và suy luận ẩn ở mức tối thiểu. Sử dụng mức này khi độ trễ (latency) và chi phí là ưu tiên số một và chỉ riêng chỉ dẫn (instructions) của agent là đã đủ.

## Đọc giá trị cấp độ effort

Bên trong một lượt tương tác đang chạy, cấp độ đã phân giải có thể truy cập qua `p.Session.current.effort`. Đây là giá trị mà mọi quyết định dựa trên effort ở trên sử dụng, và mã nguồn của riêng bạn cũng có thể tận dụng nó.

Ví dụ: một tool có thể điều chỉnh khối lượng công việc của nó theo mức effort của lượt, bằng cách đọc từ `p.Session.current` (xem [Tools](tools.md)):

```python
@p.tool
async def search_knowledge_base(query: str) -> p.ToolResult:
    limit = 20 if p.Session.current.effort >= p.Effort.HIGH else 5
    return p.ToolResult(data=await kb.search(query, limit=limit))
```

Trong một lượt tương tác bình thường, tool chỉ lấy vài kết quả. Nhưng trong một lượt đòi hỏi cao, nó sẽ tìm kiếm rộng hơn — mà không cần bất kỳ thay đổi nào đối với policy gọi nó.

Một [model provider tùy chỉnh](providers.md#custom-model-providers) có thể kết hợp cấp độ này với các điều kiện khác mà bộ chọn route không biểu đạt được — ví dụ: chỉ dùng mô hình đắt tiền cho khách hàng VIP trong các lượt phức tạp:

```python
async def provide_react(context: p.EngineContext | None) -> ReactGenerator:
    if context is None:
        return standard_react

    premium = await p.Customer.current.metadata.get("tier") == "premium"
    demanding = p.Session.current.effort >= p.Effort.HIGH
    return premium_react if premium and demanding else standard_react
```

(Đối với việc chọn mô hình theo effort thông thường, bạn nên ưu tiên các route key có điều kiện effort như `"react[effort>=high]"` — chỉ nên can thiệp bằng code khi logic nghiệp vụ phức tạp hơn những gì ngữ pháp selector cung cấp.)
