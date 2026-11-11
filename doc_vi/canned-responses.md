# Phản Hồi Soạn Sẵn (Canned Responses)

Một canned response (câu trả lời soạn sẵn) là một tin nhắn mẫu đã được doanh nghiệp phê duyệt — mang chính xác câu từ, giọng điệu và cấu trúc mà bạn muốn agent sử dụng trong những tình huống nhất định. Bạn viết nó một lần, chỉ định nơi nó áp dụng — cho các rule cụ thể, hoặc trên toàn bộ agent — và Parlant sẽ đưa nó ra trước mặt mô hình để tham khảo khi agent soạn câu trả lời.

Parlant sử dụng câu trả lời soạn sẵn như một **ví dụ dẫn dắt (guiding example)**. Khi một câu trả lời mẫu phù hợp với tình huống thực tế, agent sẽ đọc thông điệp đã được duyệt trong khi viết câu trả lời của riêng nó, tái tạo lại hình thức và chức năng của nó — giọng điệu, cách diễn đạt, những gì nên nói và những gì không nên nói — được điều chỉnh linh hoạt cho phù hợp với cuộc trò chuyện thực tế. Khách hàng luôn nhận được câu từ của chính agent, được định hướng bởi ví dụ của bạn chứ không phải một kịch bản cứng nhắc vô hồn.

## Động lực thiết kế

Hai áp lực kéo theo hai hướng ngược nhau khi bạn xây dựng một agent tiếp xúc với khách hàng:

- **Sự kiểm soát (Control):** Đội ngũ pháp lý, thương hiệu và tuân thủ cần agent nói những điều nhất định theo một cách nhất định — một lời khước từ trách nhiệm pháp lý phải chuẩn từng chữ, một lời từ chối phải giữ được sự lịch thiệp và đúng thông điệp thương hiệu.
- **Sự tự nhiên, trôi chảy (Fluency):** Các cuộc trò chuyện ngoài đời thực không bao giờ đi theo một kịch bản định sẵn. Một agent cứng nhắc đọc kịch bản nguyên văn sẽ gây cảm giác như robot, không thể thích ứng với những gì khách hàng thực sự hỏi và sẽ đổ vỡ ngay khi tình huống chệch khỏi khuôn mẫu một chút.

Các tin nhắn cứng nhắc, luôn nguyên văn mang lại sự kiểm soát nhưng đánh mất sự tự nhiên. Việc để mô hình tự do sinh câu trả lời mang lại sự tự nhiên nhưng đánh mất khả năng kiểm soát. Canned responses dung hòa cả hai: bạn cung cấp câu từ đã được duyệt làm ví dụ mẫu mực, và mô hình tái tạo lại *hình thức và chức năng* của nó trong khi vẫn viết ra câu trả lời phù hợp nhất với ngữ cảnh trực tiếp. Khi ví dụ khớp hoàn hảo, mô hình sẽ tự nhiên bám sát gần như từng từ; khi tình huống thay đổi, mô hình sẽ tự điều chỉnh thay vì gượng ép đọc một kịch bản không khớp.

Bởi vì cùng những ví dụ này được hiển thị trong khâu review, chúng cũng trở thành **thước đo tuân thủ**: giai đoạn review có thể gắn cờ một tin nhắn nháp đi chệch khỏi biểu mẫu đã được phê duyệt và yêu cầu sinh lại.

## Tổng quan

### Tư duy thiết kế (Mental Model)

Hãy coi một canned response như một **ví dụ thực tế được trao cho hai người**: người viết (component soạn tin nhắn phản hồi của agent) và người biên tập (component review tin nhắn). Cả hai đều được dặn dò: "đây là cách mà doanh nghiệp muốn kiểu tin nhắn này diễn đạt — hãy khớp hình thức và chức năng, tuân thủ các ghi chú, nhưng bạn không bắt buộc phải sao chép nguyên văn từng chữ." Không ai bị bắt buộc phải "gửi nguyên văn đoạn văn bản này": tin nhắn khách hàng nhận được luôn được viết mới, không bao giờ là một đoạn văn bản mẫu bị dán trực tiếp vào.

Hai nhân vật này hành động tại hai thời điểm trong một lượt: khi agent **viết** câu trả lời, và khi câu trả lời đó được **review** trước khi gửi đi. Cả hai đều dựa trên cùng một tập hợp ứng viên, được chọn lọc qua ba bước:

1. **Phạm vi (Scope):** Xác định *nhóm ứng viên tiềm năng (pool)*. Một canned response là ứng viên trong một lượt khi nó khả dụng **trên toàn agent (agent-wide)** hoặc được gắn vào một **rule được khớp** trong lượt đó.
2. **Độ ưu tiên (Precedence):** Sắp xếp nhóm thành hai tầng. Các phản hồi gắn với rule được khớp xếp trước; các phản hồi cấp toàn agent là tầng dự phòng.
3. **Độ liên quan (Relevance):** Quyết định *danh sách rút gọn (shortlist)*. Parlant giữ lại vài câu trả lời có độ tương đồng ngữ nghĩa cao nhất với thời điểm hiện tại — tin nhắn mới nhất của khách hàng khi soạn thảo, hoặc bản nháp câu trả lời khi review — lấp đầy hạn ngạch từ tầng gắn rule trước và chỉ để phản hồi toàn agent lấy các vị trí còn lại. Hạn ngạch mặc định là 10 cho responder và 5 cho reviewer.

### Các thuật ngữ chính

**Canned response (Phản hồi soạn sẵn)**
: Một tin nhắn mẫu được doanh nghiệp phê duyệt với một `template` (nội dung văn bản), một `note` tùy chọn, các `signals` truy xuất tùy chọn và các trường dữ liệu nội suy tùy chọn.

**Template (Bản mẫu)**
: Văn bản của canned response — một chuỗi có thể chứa các placeholder `{{ field }}` cho các giá trị được phân giải tại thời điểm render (tên khách hàng, mã đơn hàng, v.v.).

**Style reference (Tham chiếu phong cách)**
: Cách mà **message generator** nhìn nhận canned responses — một section prompt gồm các ví dụ mẫu để lấy cảm hứng khi viết câu trả lời.

**Canned guidance (Chỉ dẫn chuẩn mực)**
: Cách mà **reviewer** nhìn nhận chúng — một section prompt dùng để đánh giá xem tin nhắn nháp có tuân thủ khuôn mẫu được duyệt hay không.

**Field provider**
: Một callback (hoặc kết quả tool) cung cấp giá trị cho các placeholder của template tại thời điểm lượt chạy.

## Hướng dẫn thực hành

### 1. Tạo một Canned Response và gắn vào một Rule

```python
import parlant.sdk as p


async def main() -> None:
    async with p.Server() as server:
        agent = await server.create_agent(
            id="my-agent",
            name="Support",
            instructions="Handle billing questions.",
        )

        refund_reply = await agent.create_canned_response(
            template=(
                "Tôi rất tiếc về sự cố này. Tôi đã tiến hành thủ tục hoàn tiền số tiền "
                "{{ amount }} cho bạn — tiền sẽ về tài khoản trong vòng 5–10 ngày làm việc."
            ),
            note=(
                "Sử dụng giọng điệu ấm áp, ân cần xin lỗi. Luôn nêu rõ khoảng thời gian 5–10 ngày làm việc. "
                "Tuyệt đối không bao giờ hứa hẹn một ngày chính xác."
            ),
        )

        await agent.create_policy(
            content=(
                "When the customer is owed a refund and it has been approved, "
                "tell them their refund is on the way"
            ),
            canned_responses=[refund_reply],
        )
```

Ở bất kỳ lượt nào rule này được khớp, bộ sinh câu trả lời nhận được ví dụ hoàn tiền này làm tài liệu tham chiếu phong cách và viết câu trả lời phản ánh đúng giọng điệu cũng như tuân thủ ràng buộc "5–10 ngày làm việc, không hứa ngày cụ thể".

Trường `note` là tùy chọn nhưng rất quan trọng: nó được hiển thị cạnh ví dụ, và cả bộ sinh lẫn reviewer đều được chỉ thị phải tuân thủ nghiêm ngặt ghi chú này.

### 2. Cung cấp Canned Response trên toàn Agent

Một số tin nhắn mẫu không gắn liền với một tình huống cụ thể — câu chào hỏi chuẩn của công ty, lời tạm biệt, cách diễn đạt "tôi không thể hỗ trợ việc này". Tạo chúng trên agent và không gắn vào rule nào; chúng sẽ trở thành ứng viên ở mọi lượt:

```python
sign_off = await agent.create_canned_response(
    "Tôi có thể hỗ trợ thêm thông tin gì khác cho bạn hôm nay không?",
)
```

### 3. Điền giá trị động vào Template thông qua Fields

Templates có thể chứa các biến placeholder `{{ field }}`. Có hai cách cung cấp giá trị:

**Từ kết quả của Tool (Tool result):**

```python
@p.tool
async def look_up_refund(order_id: str) -> p.ToolResult:
    refund = await billing.get_refund(order_id)
    return p.ToolResult(
        data={"status": refund.status},
        canned_response_fields={"amount": f"${refund.amount:.2f}"},
    )
```

**Từ Field Provider gắn với Rule:**

```python
async def provide_refund_fields() -> dict[str, object]:
    amount = await billing.pending_refund_amount(p.Customer.current.id)
    return {"amount": f"${amount:.2f}"}


await agent.create_policy(
    content=(
        "When the customer is owed a refund and it has been approved, "
        "tell them their refund is on the way"
    ),
    canned_responses=[refund_reply],
    canned_response_field_provider=provide_refund_fields,
)
```

## Sử dụng nâng cao

### Thêm Signals để cải thiện việc truy xuất (Signals)

Trong khâu rút gọn danh sách, Parlant so khớp thời điểm hiện tại với *văn bản template* của từng ứng viên. Điều này hoạt động tốt nếu template đọc giống như tình huống của nó. Nhưng nhiều template không như vậy: một khách hàng hỏi "tiền của tôi đâu rồi??" có rất ít từ ngữ và ngữ nghĩa trùng khớp với câu trả lời "Khoản hoàn tiền của bạn sẽ đến trong vòng 5–10 ngày làm việc."

`signals` giải quyết điều này bằng cách cung cấp cho canned response các cách diễn đạt truy xuất thay thế — những câu mà khách hàng thực sự nói:

```python
refund_status = await agent.create_canned_response(
    template="Khoản hoàn tiền của bạn sẽ đến trong vòng 5–10 ngày làm việc.",
    signals=[
        "Khoản hoàn tiền của tôi đang ở đâu?",
        "Khi nào tôi nhận lại được tiền?",
        "Tiền hoàn của tôi vẫn chưa thấy về",
        "Đã một tuần rồi mà tôi chưa thấy tiền đâu cả",
    ],
)
```

Giờ đây, tin nhắn của khách hàng sẽ khớp với signal và câu trả lời mẫu sẽ được hiển thị vào danh sách rút gọn.

### Các điều khiển nâng cao khác

- **`field_dependencies` loại trừ các câu trả lời mà tiền đề dữ liệu không tồn tại:** Một canned response có thể khai báo các trường dữ liệu mà nó bắt buộc phải có:

  ```python
  await agent.create_canned_response(
      template="Đơn hàng của bạn đã sẵn sàng để lấy.",
      field_dependencies=["order"],
  )
  ```

  Nếu không có công cụ hay provider nào cung cấp trường `order` trong lượt này, câu trả lời mẫu này sẽ bị loại trừ hoàn toàn, tránh việc mô hình khẳng định những dữ kiện không có căn cứ.

- **Tool và Retriever có thể cung cấp câu trả lời nguyên văn cho lượt hiện tại:** Một `ToolResult` hoặc `RetrieverResult` có thể mang tham số `canned_responses` — một danh sách các **văn bản phản hồi nguyên văn**. Chúng sẽ có độ ưu tiên cao nhất, bỏ qua bước xếp hạng ngữ nghĩa và được xếp trước tiên trong hạn ngạch.

- **Điều chỉnh hạn ngạch hiển thị mỗi lượt:**

  ```python
  from parlant.core.engines.compass.responder.responder import Responder
  from parlant.core.engines.compass.reviewer import Reviewer


  async def initialize_container(container: p.Container) -> None:
      container[Responder].max_canned_responses = 8
      container[Reviewer].max_canned_responses = 3
  ```

- **Ở mức MIN và LOW effort, không có xếp hạng ngữ nghĩa:** Việc xếp hạng đòi hỏi phải embed và tìm kiếm vector store. Ở `MIN` và `LOW`, Parlant bỏ qua xếp hạng ngữ nghĩa và gửi tất cả các phản hồi hợp lệ cho agent theo thứ tự ưu tiên (tối đa 20 câu mặc định).

- **Tin nhắn khách hàng nhận được luôn do agent tự sinh ra:** Canned responses định hướng phong cách và tính tuân thủ, nhưng mô hình luôn tự mình viết đoạn văn bản cuối cùng. Điều này giúp agent vừa tuân thủ đúng thông điệp doanh nghiệp vừa duy trì được tính tự nhiên của cuộc trò chuyện.
