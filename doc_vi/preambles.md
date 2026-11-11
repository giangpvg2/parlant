# Tin Nhắn Mở Đầu Khi Gọi Công Cụ (Tool Preambles)

## Tổng quan

Preamble (tin nhắn mở đầu) là một thông điệp ngắn mà Parlant có thể tạo ra ngay trước khi nó gọi một công cụ (tool), chẳng hạn như: “Để tôi kiểm tra thông tin đó giúp bạn.” Nó giúp người dùng biết rằng hệ thống đang xử lý tác vụ trước khi bước vào một hoạt động có thể mất nhiều thời gian.

Bạn có thể cấu hình preamble cho từng agent thông qua `preamble_config`:

```python
import parlant.sdk as p


agent = await server.create_agent(
    id="my-agent",
    name="Support Agent",
    instructions="Help customers with their orders.",
    preamble_config=p.PreambleConfiguration.encourage(),
)
```

## Động lực và Ý nghĩa

Các lệnh gọi tool có thể mất đủ thời gian để sự im lặng khiến người dùng có cảm giác cuộc trò chuyện bị nghẽn (stalled), đặc biệt là trong các kênh thoại (voice) và kênh truyền phát trực tiếp (streaming). Một preamble ngắn gọn cung cấp phản hồi sớm cho người dùng trong lúc tool đang chạy.

Tuy nhiên, phản hồi này không phải lúc nào cũng cần thiết trong mọi hệ thống triển khai. Các tool chạy nhanh có thể không cần đến nó, và một số trải nghiệm thoại sẽ nghe có vẻ lặp đi lặp lại nếu mọi lệnh gọi tool đều bắt đầu bằng một thông báo cập nhật tiến độ. Do đó, Parlant cho phép bạn: để preamble ở trạng thái tự nhiên không quản lý, khuyến khích chúng xuất hiện theo khoảng thời gian được kiểm soát, hoặc triệt tiêu hoàn toàn.

## Hướng dẫn và các tùy chọn

### Để preamble tự nhiên (Unmanaged)

```python
preamble_config=p.PreambleConfiguration.default()
# Hoặc đơn giản là không truyền tham số này...
```

`default()` không thêm chỉ dẫn prompt đặc thù nào cho preamble và không áp dụng bất kỳ bộ lọc hay cắt gọt đặc biệt nào. Mô hình vẫn có thể tự sinh văn bản trước một lượt gọi tool; nếu có, Parlant sẽ chuyển tiếp văn bản đó ra ngoài một cách bình thường.

Đây cũng là cấu hình mặc định cho các agent dạng block và stream khi `preamble_config` bị bỏ qua.

### Khuyến khích preamble (Encourage)

```python
preamble_config=p.PreambleConfiguration.encourage()
```

`encourage()` yêu cầu mô hình đưa ra một câu ngắn gọn, tự nhiên trước lượt gọi tool đầu tiên. Nó cũng giới hạn các cập nhật tiến độ bị lặp lại và cắt gọt preamble phát ra thành một câu duy nhất.

Khuyến khích chỉ là một chỉ dẫn định hướng cho mô hình (guidance), chứ không phải là cam kết chắc chắn 100% rằng preamble sẽ luôn được tạo ra. Tham số khoảng thời gian (interval) kiểm soát xem các bản cập nhật trước tool tiếp theo có được hiển thị hay không; nó không lên lịch gửi tin nhắn theo bộ hẹn giờ (timer).

Khoảng thời gian mặc định là 15 giây. Để thay đổi:

```python
preamble_config=p.PreambleConfiguration.encourage(interval_seconds=8)
```

Các voice worker sẽ sử dụng `encourage()` khi agent không có cấu hình preamble tường minh. Hãy truyền `default()` một cách rõ ràng nếu bạn muốn một voice agent giữ nguyên trạng thái không quản lý.

### Hạn chế / Triệt tiêu preamble (Discourage)

```python
preamble_config=p.PreambleConfiguration.discourage()
```

`discourage()` chỉ thị cho mô hình sử dụng các tool trong im lặng. Parlant cũng thực thi lựa chọn này tại thời gian chạy (runtime): văn bản được sinh ra ngay trước một lệnh gọi tool sẽ không được gửi tới người dùng.

Đối với streaming và voice, Parlant buộc phải đệm tạm thời đoạn văn bản có khả năng là preamble cho đến khi nó biết chắc chắn có lệnh gọi tool đi sau hay không. Nếu không có lệnh gọi tool nào đi kèm, đoạn văn bản đó là một câu trả lời bình thường và được phát đi như thường lệ.

### Bảng so sánh các tùy chọn

| Tùy chọn | Chỉ dẫn prompt | Hành vi Runtime | Trường hợp sử dụng điển hình |
|---|---|---|---|
| `default()` | Không có | Chuyển tiếp nguyên trạng văn bản trước tool | Để mô hình ứng xử tự nhiên |
| `encourage()` | Yêu cầu cập nhật tiến độ ngắn gọn, kịp thời | Áp dụng rào cản thời gian (interval gating) và cắt gọt 1 câu | Các tool chạy chậm, streaming và voice |
| `discourage()` | Yêu cầu gọi tool trong im lặng | Triệt tiêu văn bản ngay trước lệnh gọi tool | Các tool chạy nhanh hoặc UX voice được kiểm soát chặt chẽ |

## Sử dụng nâng cao

### Các quyết định Preamble (Preamble decisions)

Trước mỗi bước có khả năng gọi tool, Parlant sẽ tính toán một **quyết định preamble (preamble decision)** — sự phán đoán xem đây có phải là thời điểm thích hợp để cập nhật tiến độ hay không, dựa trên những gì khách hàng đã thấy trong lượt này:

- `ALLOW_INITIAL` — chưa có nội dung nào hiển thị cho người dùng trong lượt này; một câu tin nhắn mở đầu "để tôi kiểm tra việc này" đầu tiên sẽ rất hữu ích tại đây.
- `ALLOW_INTERVAL_UPDATE` — đã có nội dung hiển thị trước đó, nhưng đã vượt quá khoảng thời gian cấu hình kể từ tin nhắn hiển thị gần nhất; khách hàng có thể đang băn khoăn chuyện gì đang diễn ra.
- `SUPPRESS` — khách hàng vừa nhận được thông tin từ agent gần đây (trong khoảng thời gian interval); việc cập nhật thêm sẽ gây phiền nhiễu.

Quyết định này là trạng thái căn thời gian (timing state), chứ không phải là cấu hình — bạn không bao giờ phải gán giá trị cho nó. Parlant tự động suy luận nó ở mỗi bước từ lịch sử phát tin của lượt tương tác và tham số `interval_seconds` của bạn. Quyết định này sau đó được sử dụng ở 2 nơi:
**Hàm tạo ghi chú (note factory)** nhận nó, nhờ đó chỉ dẫn prompt có thể thích ứng với thời điểm: yêu cầu preamble đầu tiên hoặc yêu cầu im lặng. Dưới policy phát tin `INTERVAL`, nó cũng kiểm soát tại runtime xem đoạn văn bản trước tool có thực sự được phân phối hay không. Hành vi tích hợp sẵn `encourage()` chính là cơ chế này: một ghi chú tùy chỉnh theo từng quyết định, kết hợp với bộ lọc interval gating.

### Định nghĩa một Policy tùy chỉnh

Khởi tạo trực tiếp `PreambleConfiguration` khi các tùy chọn tiêu chuẩn không đáp ứng yêu cầu. Hàm tạo ghi chú nhận context hiện tại của engine, quyết định thời gian (timing decision) và khoảng thời gian đã cấu hình. Nó trả về chỉ dẫn prompt cho bước đó, hoặc `None`:

```python
import parlant.sdk as p


def preamble_note(
    context: p.EngineContext,
    decision: p.PreambleDecision,
    interval_seconds: float,
) -> str | None:
    if decision is p.PreambleDecision.SUPPRESS:
        return "Run the next tool silently; the user was updated recently."

    return "Before using a tool, briefly state which account detail you are checking."


custom_preambles = p.PreambleConfiguration(
    interval_seconds=10,
    note_factory=preamble_note,
    emission_policy=p.PreambleEmissionPolicy.INTERVAL,
)
```

Policy phát tin (`emission_policy`) kiểm soát việc xử lý tại runtime độc lập với ghi chú prompt:

- `PASSTHROUGH`: Luôn cho phép văn bản trước tool đi qua.
- `INTERVAL`: Cho phép preamble ban đầu và các bản cập nhật sau đó sau khi đã hết khoảng thời gian cấu hình, kèm theo việc cắt gọn thành một câu.
- `SUPPRESS`: Không bao giờ phân phối văn bản trước tool.

### Thiết lập Policy trên toàn hệ thống triển khai

`PreambleConfigurationProvider` là nguồn cung cấp cài đặt theo từng agent tại runtime. Bạn có thể thay thế nó bằng `configure_container` để áp dụng mặc định trên toàn hệ thống triển khai trong khi vẫn cho phép các giá trị `preamble_config` tường minh được ưu tiên:

```python
import parlant.sdk as p


class DeploymentPreambles(p.PreambleConfigurationProvider):
    def get(self, agent_id: p.AgentId) -> p.PreambleConfiguration | None:
        return super().get(agent_id) or p.PreambleConfiguration.discourage()


async def configure_container(container: p.Container) -> p.Container:
    container[p.PreambleConfigurationProvider] = DeploymentPreambles()
    return container


async with p.Server(configure_container=configure_container) as server:
    ...
```

Provider tích hợp sẵn lưu trữ cấu hình trong bộ nhớ tiến trình (process memory). Hãy áp dụng lại cấu hình SDK hoặc container khi khởi động; cấu hình này không được lưu bền vững cùng với bản ghi của agent. Điều này cũng cho phép các cấu hình tùy chỉnh sử dụng các hàm callback của Python như `note_factory`, vốn là các đối tượng không thể tuần tự hóa (non-serializable).
