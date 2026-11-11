Mình đối chiếu **Parlant 3.3.2 → 4.0.0 → 4.0.4** bằng code và tài liệu trong repo.

**4.0 là bản thay đổi lớn cả cách khai báo hành vi, engine thực thi và cách triển khai.** Với ứng dụng của bạn, có thể giữ phần lớn nghiệp vụ trong tool, nhưng không thể chỉ đổi `create_guideline()` thành `create_policy()` rồi mặc định hành vi sẽ giống hoàn toàn.

Một điểm cần làm rõ so với các câu trả lời trước: **Observation, streaming, retriever, MCP, human handoff và `/healthz` đã có ở 3.x**. Phần mới là cách chúng được tổ chức, vận hành và tích hợp trong 4.0.

**1. Bức tranh tổng thể**

| Khía cạnh | 3.3.2 | 4.0 |
|---|---|---|
| Engine | Alpha | Compass |
| Quy tắc hành vi | Guideline | Policy |
| Nhận diện tình huống | Observation dưới dạng guideline không có action | `Observation` riêng, cùng kế thừa `Rule` với `Policy` |
| Quy trình nhiều bước | Journey, state, transition | Policy mô tả quy trình dạng SOP |
| Gọi tool | Các vòng chuẩn bị và suy luận tool | Vòng lặp reasoning → tool → kết quả → reasoning |
| Kiểm tra trước hành động | Cơ chế của engine cũ và hook tùy chỉnh | Tool review tích hợp |
| Kiểm tra trước gửi phản hồi | Composition, response analysis và hook | Message review tích hợp |
| Canned response | Có các chế độ composition, gồm `STRICT` | Mẫu hướng dẫn cho câu trả lời được sinh mới |
| Model | Cấu hình qua `NLPService` | Định tuyến model theo từng tác vụ |
| Mức xử lý | Các cấu hình rời rạc | `Effort` và khả năng nâng effort theo tình huống |
| Session/customer mặc định | RAM, mất khi restart | SQLite trên đĩa |
| HTTP API quản lý hành vi | CRUD guideline, journey, canned response… | Thu hẹp; cấu hình hành vi bằng code |
| CLI | Chủ yếu quản lý tài nguyên qua API | Tạo project, tra docs, widget, Dashboard/deploy |
| Auth | Chính sách cấp quyền tương đối tổng quát | Identity, token, quyền thao tác và quyền sở hữu tài nguyên |
| Vận hành | Logs, inspection, health, OpenTelemetry | Mở rộng diagnostics, health, usage, pricing, budgets |

---

**2. Policy thay vai trò của cả Guideline và Journey, nhưng không giữ nguyên cấu trúc bên trong.**

Ở 3.x, một guideline thường được viết như:

```python
await agent.create_guideline(
    condition="Ứng viên muốn đăng ký",
    action="Hỏi vị trí muốn ứng tuyển",
)
```

Ở 4.0:

```python
await agent.create_policy(
    title="Bắt đầu đăng ký",
    content="Khi ứng viên muốn đăng ký, hỏi vị trí muốn ứng tuyển.",
)
```

Policy có thể ngắn như một guideline, hoặc dài thành một quy trình hoàn chỉnh:

```python
await agent.create_policy(
    title="Đăng ký ứng tuyển",
    content="""
Khi ứng viên yêu cầu đăng ký:

1. Xác định vị trí muốn ứng tuyển.
2. Tra cứu vị trí và kiểm tra còn tuyển.
3. Đọc hồ sơ hiện có.
4. Lưu từng thông tin hợp lệ ứng viên đã cung cấp.
5. Hỏi một trường còn thiếu mỗi lượt.
6. Chỉ xác nhận hoàn tất khi tool báo hồ sơ đã đủ.

Nếu ứng viên hủy, dừng thu thập.
Nếu vị trí đã đóng, đề nghị chọn vị trí khác.
""",
    tools=[
        search_jd_info,
        get_candidate_profile,
        update_candidate_field,
    ],
)
```

Các điểm khác nhau:

| Guideline/Journey cũ | Policy mới |
|---|---|
| Điều kiện và hành động thường nằm ở trường riêng | Điều kiện, hành động và ngoại lệ nằm chung trong `content` |
| Journey chia quy trình thành các node | Policy có thể chứa toàn bộ quy trình |
| Quan hệ giữa bước được khai báo bằng transition | Thứ tự, nhánh và điều kiện dừng được mô tả bằng nội dung |
| State có đối tượng SDK riêng | Không còn API state/transition tương ứng |

Tài liệu 4.0 khuyến khích **giữ một quy trình hoàn chỉnh trong một policy**, thay vì chia mỗi bước thành một policy riêng và bắt engine tự ghép lại.

Cũng cần hiểu đúng bản cũ: **Journey 3.x không phải máy trạng thái cứng hoàn toàn**. Model vẫn diễn giải điều kiện, có thể bỏ qua, quay lại hoặc nhảy bước theo ngữ cảnh. Điểm thay đổi là cấu trúc luồng từ đồ thị SDK được chuyển vào nội dung policy. [Nguồn: policy và SOP](/home/fw2025/MBW/parlant/docs/policy-design.md:56).

---

**3. Observation vẫn dùng để nhận diện tình huống, nhưng được phân biệt rõ hơn với Policy.**

Hai đối tượng có vai trò khác nhau:

| Đối tượng | Vai trò |
|---|---|
| `Policy` | Hướng dẫn agent nên làm gì |
| `Observation` | Nhận diện một tình huống để engine quyết định cách xử lý |

Ví dụ:

```python
candidate_requests_human = await agent.create_observation(
    condition="Ứng viên yêu cầu nói chuyện với chuyên viên tuyển dụng.",
)
```

Observation có thể:

- Làm điều kiện phụ thuộc cho policy khác.
- Nâng effort.
- Yêu cầu review.
- Chạy callback.
- Gắn label.
- Cung cấp tool hoặc canned response.

Ví dụ:

```python
await agent.create_observation(
    condition="Ứng viên phản ánh thông tin tuyển dụng sai lệch.",
    trigger_effort=p.Effort.HIGH,
    trigger_message_review=True,
    labels=["recruitment-complaint"],
)
```

Observation đã tồn tại ở 3.3.2. Khi đó nó là một dạng guideline không có action; ở 4.0, `Observation` và `Policy` là hai loại `Rule` riêng. [Nguồn: Observation](/home/fw2025/MBW/parlant/docs/policy-design.md:387).

---

**4. Engine thực thi đổi từ Alpha sang Compass.**

Ở 3.x, cách xử lý có thể hiểu là:

```text
Đọc hội thoại
→ tìm guideline/journey phù hợp
→ suy luận và gọi tool
→ lặp lại vòng chuẩn bị nếu cần
→ tạo câu trả lời
```

Ở 4.0:

```text
Đọc hội thoại và ngữ cảnh
→ xác định rule và tool phù hợp
→ model suy luận
→ đề xuất gọi tool
→ review nếu được yêu cầu
→ thực thi tool
→ đưa kết quả vào vòng xử lý
→ tiếp tục suy luận hoặc viết câu trả lời
→ review phản hồi nếu được yêu cầu
→ gửi phản hồi
```

Đây là thay đổi logic core thực sự:

- Model gọi tool trực tiếp trong vòng phản hồi.
- Một lượt có thể gồm nhiều bước reasoning và tool.
- Kết quả tool có thể làm xuất hiện rule hoặc tool mới.
- Một bước bị reviewer từ chối có thể được tạo lại.
- Engine có giới hạn bước và số lần thử lại.

Vì vậy:

```python
max_engine_iterations=3
```

không tương đương với:

```python
max_steps=3
```

Biến cũ đếm vòng chuẩn bị; biến mới giới hạn số bước xử lý của Compass. Mặc định cũng đổi từ **3 vòng** sang **15 bước**, nhưng không nên so sánh hai con số như cùng một đơn vị. [Nguồn: vòng lặp tool](/home/fw2025/MBW/parlant/docs/tools.md:42), [create_agent](/home/fw2025/MBW/parlant/src/parlant/sdk.py:4303).

---

**5. Cách tìm và đánh giá rule đã thay đổi đáng kể.**

4.0 phân biệt hai việc:

| Khái niệm | Câu hỏi engine đang trả lời |
|---|---|
| **Discovery** | Rule này có liên quan đến cuộc hội thoại để đưa vào tập ngữ cảnh không? |
| **Turn evaluation/matching** | Rule này có thực sự áp dụng ở lượt hiện tại không? |

**Một policy được tìm thấy không đồng nghĩa với việc policy đó đang áp dụng.**

Ví dụ:

- Ứng viên từng hỏi đăng ký.
- Policy đăng ký được đưa vào tập ngữ cảnh của session.
- Lượt sau ứng viên hỏi nghĩa của “phụ cấp chuyên cần”.
- Policy đăng ký vẫn có thể nằm trong ngữ cảnh, nhưng không có nghĩa agent phải tiếp tục đòi số điện thoại ngay.

Cơ chế discovery mới gồm:

- Bộ phân loại riêng cho từng rule, theo từng agent.
- Embedding.
- `signals`: ví dụ thể hiện khi nào rule liên quan.
- `anti_signals`: ví dụ gần giống nhưng không được áp dụng.
- Tập rule liên quan được giữ qua các lượt và được cắt tỉa khi cần.

Ví dụ cho demo:

```python
await agent.create_policy(
    title="Đăng ký ứng tuyển",
    content="...",
    signals=[
        "Tôi muốn ứng tuyển vị trí này",
        "Đăng ký giúp tôi",
    ],
    anti_signals=[
        "Vị trí này lương bao nhiêu?",
        "Công ty có cấp MacBook không?",
    ],
)
```

Hai nhóm ví dụ giúp phân biệt **ý định ứng tuyển** với **hỏi thông tin trước khi quyết định**.

Một chi tiết vận hành: classifier được train khi khởi động. Theo tài liệu hiện tại, sửa nội dung/signals của một rule đã tồn tại lúc server đang chạy có thể vẫn dùng classifier cũ cho discovery đến lần restart tiếp theo. [Nguồn: discovery](/home/fw2025/MBW/parlant/docs/rule-discovery.md:3), [thay đổi rule sau startup](/home/fw2025/MBW/parlant/docs/rule-discovery.md:195).

---

**6. Quan hệ giữa các rule vẫn còn, nhưng cần kiểm tra lại semantics.**

Các khả năng sau không biến mất:

```python
await policy.depend_on(other)
await policy.depend_on_any(first, second)
await policy.prioritize_over(other)
await policy.entail(other)
await policy.reevaluate_after(tool)
```

Chúng cũng không phải tất cả đều mới ở 4.0; nhiều phương thức đã có trong 3.x.

Những điểm cần chú ý ở engine mới:

- **Dependency cần một lần match thực sự**, discovery đơn thuần chưa đủ.
- Một prerequisite đã áp dụng có thể mở khóa policy phụ thuộc ở các lượt sau trong session.
- `prioritize_over()` nhắm vào các rule cụ thể.
- `priority=` bằng số tác động rộng hơn, có thể làm các rule không liên quan cũng bị đặt sang một bên.
- Rule thua trong quan hệ ưu tiên không nhất thiết bị xóa khỏi ngữ cảnh; engine có thể giữ nội dung và ghi rõ nó bị thu hồi cho phản hồi hiện tại.

Với đoạn cũ của bạn:

```python
await missing_information.prioritize_over(scope)
```

ý định vẫn biểu đạt được. Nhưng cần kiểm tra lại các trường hợp:

- Đúng phạm vi nhưng thiếu thông tin.
- Ngoài phạm vi agent.
- Không có công việc phù hợp.
- Nguồn trả lỗi.
- HR đã xác nhận thông tin ở lượt trước.

Những trường hợp này có thể chịu ảnh hưởng khác nhau từ dependency, lịch sử match và priority. [Nguồn: priority và dependency](/home/fw2025/MBW/parlant/docs/policy-design.md:264).

---

**7. `Weight`, `Effort` và `Review` là ba điều khiển khác nhau.**

Đây là điểm dễ nhầm khi chuyển từ `criticality` cũ.

| Điều khiển | Ý nghĩa |
|---|---|
| `weight` | Policy là gợi ý mềm hay giới hạn cần giữ chặt |
| `effort` | Engine đầu tư bao nhiêu công sức xử lý |
| `message_review` / `tool_review` | Có kiểm tra đề xuất trước khi gửi/thực thi không |

`Weight` có ba mức chính:

| Weight | Cách dùng |
|---|---|
| `LOW` | Hướng dẫn có thể linh hoạt |
| `MEDIUM` | Quy tắc nghiệp vụ cần tuân theo; mặc định |
| `HIGH` | Giới hạn quan trọng cần giữ ngay cả khi khách gây áp lực |

`Effort` có năm mức:

```python
MIN, LOW, MEDIUM, HIGH, MAX
```

Effort tác động đến:

- Model được chọn nếu có route theo effort.
- Mức reasoning.
- Cách đánh giá rule.
- Số lần thử lại sau khi review từ chối.
- Cách chọn canned response.
- Nén lịch sử.
- Tái đánh giá rule sau tool.

Policy/observation có thể nâng effort trong lượt hiện tại:

```python
trigger_effort=p.Effort.HIGH
```

**Điểm đặc biệt: ở `Effort.MIN`, review không chạy, kể cả khi bạn đã yêu cầu.** Do đó không thể hiểu `MIN` chỉ là cùng một cơ chế nhưng chạy bằng model rẻ hơn. [Nguồn: weight](/home/fw2025/MBW/parlant/docs/policy-design.md:166), [adaptive effort](/home/fw2025/MBW/parlant/docs/adaptive-effort.md:1).

---

**8. Tool review và message review trở thành cơ chế tích hợp rõ ràng.**

| | Tool review | Message review |
|---|---|---|
| Kiểm tra | Reasoning và các tool call được đề xuất | Câu trả lời hoàn chỉnh |
| Thời điểm | Trước khi tool chạy | Trước khi phản hồi được gửi |
| Nếu bị từ chối | Không chạy các call đó; tạo lại bước xử lý | Không gửi bản nháp đó; tạo lại câu trả lời |
| Phạm vi cấu hình | Toàn agent hoặc theo rule | Toàn agent hoặc theo rule |

Toàn agent:

```python
agent = await server.create_agent(
    id="recruitment",
    name="Recruitment",
    instructions="...",
    tool_review=True,
    message_review=True,
)
```

Theo policy:

```python
await agent.create_policy(
    content="...",
    trigger_tool_review=True,
    trigger_message_review=True,
)
```

Các chi tiết ảnh hưởng trực tiếp đến ứng dụng:

- Mặc định hai cờ review trên agent là `False`.
- Khi message review hoạt động, phản hồi được giữ lại để review toàn bộ, kể cả agent cấu hình stream.
- Reviewer có quy tắc kiểm tra việc agent tuyên bố đã làm một hành động phải có kết quả tool hỗ trợ.
- Review có giới hạn thử lại; không lặp vô hạn.
- Hết số lần thử, engine chuyển sang phản hồi không hoàn thành được tác vụ.
- Review bằng model không thay thế validation trong backend.

Với demo của bạn, kiểm tra “không được nói đã lưu nếu `saved=false`” có thêm lớp review hỗ trợ, nhưng kiểm tra lưu dữ liệu vẫn phải nằm trong tool. [Nguồn: review](/home/fw2025/MBW/parlant/docs/review.md:97).

---

**9. Canned response là thay đổi lớn đối với code đang dùng `STRICT`.**

Ở 3.x có:

```python
composition_mode=p.CompositionMode.STRICT
```

Ở 4.0, `CompositionMode` không còn trong API mới.

Canned response vẫn có:

```python
await agent.create_canned_response(
    template="...",
    field_dependencies=[...],
)
```

Nhưng vai trò hiện tại là:

- Mẫu được đưa cho thành phần viết câu trả lời.
- Chuẩn tham chiếu cho reviewer.
- Có thể nội suy các field từ tool hoặc field provider.
- Câu trả lời cuối cùng vẫn được model viết mới.

**Không được mặc định rằng nội dung gửi ra chính là template được thay biến nguyên văn.**

Điều này ảnh hưởng rõ đến template hồ sơ của bạn:

```text
Họ tên: {{candidate_full_name}}
Số điện thoại: {{candidate_phone}}
Vị trí: {{candidate_job}}
```

Nếu yêu cầu là:

- Họ tên phải giữ nguyên dấu.
- Số điện thoại không được sửa.
- Trạng thái lưu phải đúng tuyệt đối.
- Một thông báo phải có câu chữ cố định.

thì cần thiết kế cách render/gửi dữ liệu có kiểm soát bằng code hoặc UI phù hợp. **Bật message review không khôi phục nguyên trạng contract của `STRICT` cũ.**

`canned_response_fields` và `field_dependencies` vốn đã có ở 3.x; thay đổi chính nằm ở cách sử dụng mẫu trong engine mới. [Nguồn: semantics của canned response](/home/fw2025/MBW/parlant/docs/canned-responses.md:3).

---

**10. SDK có nhiều thay đổi không tương thích, gồm cả các mặc định.**

| Code/cấu hình cũ | 4.0 | Ý nghĩa khi chuyển |
|---|---|---|
| `description=` | `instructions=` | Cập nhật khai báo agent |
| Agent `id` có thể bỏ qua | `id` bắt buộc, keyword-only | Cần ID ổn định |
| Output mặc định `BLOCK` | Mặc định `STREAM` | Frontend/hook có thể thấy hành vi khác |
| `max_engine_iterations` | `max_steps` | Khác đơn vị xử lý |
| `composition_mode` | Bị bỏ | Thiết kế lại phần kiểm soát phản hồi |
| `planner=` | Bị bỏ khỏi `create_agent()` | Custom planner cũ cần thiết kế lại |
| `perceived_performance_policy=` | Bị bỏ | Chuyển sang cơ chế preamble/progress mới |
| `tags`, `Tag`, `TagId` | `groups`, `Group`, `GroupId` | Sửa scope và membership |
| `matcher=` | `evaluation_func=` | Chữ ký và context thay đổi |
| `on_match` và callback cũ | `on_discovered`, `on_matched` và hook mới | Không ánh xạ một-một |
| `criticality=` | `weight=` | Cần xem lại ý nghĩa, không chỉ tên |
| `ToolContextAccessor` | Bị bỏ | Dùng các đối tượng `.current` |
| `EngineHooks` | `CompassHooks` | Lifecycle thay đổi |

Ví dụ đọc hội thoại trong tool:

```python
interaction = p.Session.current.interaction
```

Thay cho:

```python
interaction = p.ToolContextAccessor(context).current_interaction
```

**`ToolContext` vẫn còn**, gồm `agent_id`, `session_id`, `customer_id` và các phương thức emit. Các đối tượng `Server.current`, `Agent.current`, `Customer.current`, `Session.current` cũng không phải tất cả mới xuất hiện ở 4.0. [Nguồn: SDK](/home/fw2025/MBW/parlant/src/parlant/sdk.py:4303), [ToolContext](/home/fw2025/MBW/parlant/src/parlant/core/tools.py:84).

---

**11. Tool vẫn là nơi giữ nghiệp vụ, nhưng một số contract đã đổi.**

Phần có thể giữ lại nhiều nhất trong demo của bạn là:

- Validation tên và điện thoại.
- Đối chiếu dữ liệu với lời ứng viên.
- Kiểm tra job thuộc phạm vi agent.
- Lưu hồ sơ từng phần.
- Đánh giá mô phỏng.
- Đồng bộ CRM.
- Phân biệt ghi dữ liệu thành công với tích hợp CRM thất bại.

Các thay đổi API đáng chú ý:

| Cũ | Mới |
|---|---|
| `ToolResult(guidelines=...)` | `ToolResult(rules=...)` |
| `TransientGuideline` | `TransientRule` |
| Nội dung transient dùng `action` | Dùng `content` |
| `Agent.utter(guidelines=...)` | `Agent.utter(rules=...)` |
| `ToolParameterOptions.precedence` | Bị bỏ |
| Chưa có narration theo thiết kế mới | Có narration cho trạng thái tool |
| Kết quả tool | Có thêm khả năng ghi nhận chi phí |

`consequential=True` cũng đáng chú ý: cờ này đã tồn tại trước, nhưng ở 4.0 có vai trò thực tế trong hướng dẫn xác nhận và kích hoạt tool review, trừ giới hạn của `Effort.MIN`.

Một chi tiết từ implementation: **nhiều tool call trong cùng một bước có thể chạy đồng thời**. Không nên dựa vào thứ tự model liệt kê tool để bảo đảm hai thao tác ghi chạy tuần tự. Nếu thao tác sau bắt buộc chờ thao tác trước, cần bảo đảm trong backend hoặc cấu trúc bước xử lý. [Nguồn: tools](/home/fw2025/MBW/parlant/docs/tools.md:1), [thực thi tool call](/home/fw2025/MBW/parlant/src/parlant/core/engines/compass/loop/base_loop.py:1155).

---

**12. Hook phải chuyển theo ý nghĩa lifecycle, không chỉ đổi tên class.**

Cũ:

```python
configure_hooks=configure_profile_hooks
```

Mới đăng ký qua container:

```python
async def initialize_container(container: p.Container) -> None:
    hooks = container[p.CompassHooks]
    hooks.on_message_generated.append(my_hook)
```

Các nhóm hook mới gồm:

- Bắt đầu/kết thúc một bước.
- Trước/sau tool call.
- Trước/sau review.
- Cập nhật nội dung streaming.
- Trước/sau compaction.
- Khi engine không hoàn thành được tác vụ.
- Khi rule được discovery hoặc match.

Các hook cũ như `on_preparation_iteration_end` không có đối tác đổi tên trực tiếp.

Trong file bạn gửi, cần xem lại riêng:

```python
AUTO_HANDOFF.ensure_company_source
AUTO_HANDOFF.before_generation
HR.guard_ai_response
populate_profile_template_fields
```

Ví dụ, kiểm tra kết quả tool có thể cần chuyển sang `on_tool_calls_completed`; chặn câu trả lời trước gửi cần chọn đúng điểm phát sinh hoặc review phản hồi.

`CALL_NEXT`, `RESOLVE`, `BAIL` vẫn có các tên quen thuộc, nhưng **tác dụng phụ thuộc hook đang chạy**. Chẳng hạn `RESOLVE` ở bước review có nghĩa chấp thuận, không mang ý nghĩa giống mọi hook khác. [Nguồn: hooks](/home/fw2025/MBW/parlant/docs/hooks.md:36).

---

**13. Cấu hình model chuyển từ một `NLPService` sang định tuyến theo tác vụ.**

Cũ:

```python
p.Server(
    nlp_service=p.NLPServices.litellm,
)
```

Mới:

```python
p.Server(
    models={
        "*": "openrouter",
        "react": "anthropic",
        "review.*": "gemini",
        "embedding.*": "openai",
    },
)
```

Đây là ví dụ phân chia công việc, cần cấu hình credentials tương ứng.

Các route tiêu biểu:

| Route | Công việc |
|---|---|
| `react` | Suy luận, gọi tool, viết phản hồi |
| `indexing` | Chuẩn bị/chỉ mục rule |
| `matching.*` | Đánh giá rule |
| `review.tools` | Review tool call |
| `review.message` | Review phản hồi |
| `compaction` | Nén lịch sử |
| `embedding.*` | Tạo embedding |
| `moderation.customer` | Kiểm tra đầu vào |
| `moderation.agent` | Kiểm tra đầu ra |
| `tokenizer` | Ước lượng token |

Có thể:

- Cấu hình ở server và override theo agent.
- Chọn model theo effort.
- Cập nhật route khi server đang chạy.
- Dùng custom provider trả về implementation cho từng loại tác vụ.

Các provider tích hợp trực tiếp hiện tập trung vào:

**OpenAI, Gemini, Anthropic, OpenRouter và LiteLLM.**

Nhiều adapter trực tiếp cũ bị gỡ, gồm các adapter cho AWS, Azure, Ollama, Qwen, Vertex và một số nhà cung cấp khác. Điều này không đồng nghĩa mọi model của các nhà cung cấp đó không dùng được; nhưng **import và cấu hình adapter cũ không còn dùng nguyên trạng**.

Với Qwen/vLLM trong ví dụ của bạn, phải kiểm tra lại:

- Kết nối endpoint tự host.
- Model phục vụ reasoning/tool calling.
- Các tác vụ trả JSON có cấu trúc.
- Embedding.
- Tokenizer và moderation nếu sử dụng.

Chỉ khai báo model chat chưa đủ để cấu hình toàn bộ hệ thống. `ModelConfig.args` cũng là cấu hình constructor được kiểm tra, không phải chỗ truyền tùy ý mọi tham số request của provider. [Nguồn: model routing](/home/fw2025/MBW/parlant/docs/providers.md:110), [custom providers](/home/fw2025/MBW/parlant/docs/providers.md:1116).

Cơ chế mới còn có `SecretRef`, `SecretValue` và rate limit theo model. Rate limiter mặc định hoạt động trong một process, không phải quota chung tự động cho cả cluster.

---

**14. Lưu trữ mặc định đổi; nâng cấp dữ liệu cần được xử lý riêng.**

| Dữ liệu | 3.3.2 SDK | 4.0 |
|---|---|---|
| Session mặc định | `transient` | `local` |
| Customer mặc định | `transient` | `local` |
| `local` dùng gì | File JSON | SQLite |
| Context variable mặc định | `transient` | Vẫn `transient` |
| MongoDB | Có | Vẫn có, nhưng cách bố trí dữ liệu thay đổi |
| S3 | Không có trong bản cũ | Được ghi nhận bổ sung ở 4.0.2 |

Ví dụ:

```text
sessions.json → sessions.db
customers.json → customers.db
```

Điều này có hai hệ quả:

- Code trước đây không lưu session qua restart có thể bắt đầu lưu mặc định.
- Thư mục dữ liệu JSON cũ không được mặc định coi là đã chuyển sang SQLite.

**Mình chưa thấy cơ chế chuyển toàn bộ dữ liệu 3.x sang 4.0 tự động.** `migrate=True` cho phép migration schema mà store hỗ trợ; nó không chứng minh có đầy đủ chuyển đổi JSON → SQLite, tag → group và mô hình dữ liệu cũ → mới.

MongoDB cũng cần kiểm tra lại database/collection layout.

Với dữ liệu đang dùng thật, phần chuyển code và phần export/map/import dữ liệu là hai công việc riêng. [Nguồn: cấu hình store](/home/fw2025/MBW/parlant/src/parlant/sdk.py:3008).

---

**15. HTTP API quản lý hành vi bị thu hẹp rất nhiều.**

Đây là thay đổi dễ bị bỏ sót nếu chỉ đọc SDK.

Các router quản lý cũ bị gỡ khỏi app, gồm:

```text
/guidelines
/journeys
/terms
/canned_responses
/context-variables
/relationships
/evaluations
/capabilities
/services
/tags
```

**Không có `/policies` CRUD để thay `/guidelines` theo kiểu đổi tên endpoint.**

Agent được cấu hình bằng code. API agent hiện tập trung vào liệt kê/đọc thông tin định danh để chọn agent; các thao tác tạo/sửa/xóa agent qua REST cũ không còn như trước.

Các phần runtime như session, customer, events vẫn có, cùng groups, logs và diagnostics.

Do đó:

- Frontend chat vẫn có thể tích hợp qua HTTP/SSE.
- Công cụ quản trị đang tạo guideline/journey qua REST phải viết lại.
- Client được sinh cho API 3.x không nên mặc định dùng tương thích với 4.0.

Dependency `parlant-client==3.3.1` cũng đã được bỏ khỏi package. [Nguồn: API agent](/home/fw2025/MBW/parlant/src/parlant/api/agents.py:56), [router đăng ký trong app](/home/fw2025/MBW/parlant/src/parlant/api/app.py:403).

---

**16. Auth mới quản lý danh tính và quyền sở hữu session rõ hơn.**

3.x đã có authorization policy. 4.0 bổ sung mô hình tích hợp gồm:

```text
Xác thực danh tính
→ kiểm tra quyền thao tác
→ rate limit
→ kiểm tra quyền đối với tài nguyên
```

Các loại principal:

- Anonymous.
- Guest.
- Customer.
- Admin.

Những thay đổi thực tế:

- Customer có thể được xác thực bằng JWT do backend hoặc IdP của bạn phát hành.
- Guest dùng token riêng cho identity của trình duyệt.
- Guest/customer chỉ truy cập session thuộc quyền của mình theo policy mặc định.
- Backend không đơn giản tin `customer_id` do client gửi.
- Kết quả tool và reasoning nội bộ được lọc theo quyền.
- Có mã lỗi rõ hơn cho chưa xác thực, thiếu quyền và vượt rate limit.

Cần phân biệt:

- **Development mặc định vẫn cho phép rộng.**
- Có auth mới không có nghĩa chỉ nâng version là server tự được bảo vệ.
- Production cần cấu hình credentials thích hợp.
- Parlant xác minh token, không trở thành hệ thống đăng nhập/IdP thay cho ứng dụng của bạn.

Trong demo tuyển dụng, quyền xem hồ sơ ứng viên ở `/hr` và quyền ứng viên ở `/chat` vẫn cần được tích hợp đúng với lớp auth này. [Nguồn: authentication và authorization](/home/fw2025/MBW/parlant/docs/auth.md:1).

---

**17. Session, customer và memory được mở rộng, nhưng handoff vẫn cần hệ thống người nhận.**

Một số điểm đáng chú ý:

- Customer dùng `groups` thay cho `tags`.
- Có phân biệt customer thật và persona dùng cho kiểm thử.
- Có khả năng kết nối trực tiếp customer database của ứng dụng qua `CustomerStore`.
- Context variable bổ sung scope theo agent.

Thứ tự tìm giá trị context variable hiện là:

```text
Customer → nhóm customer → agent → global
```

Về memory:

- **Lịch sử trong session:** có sẵn.
- **Compaction:** tự tóm tắt phần lịch sử cũ khi session dài.
- **Bộ nhớ về customer qua nhiều session:** vẫn cần tích hợp kho nhớ/CRM riêng.

Không nên hiểu tài liệu `memory.md` là Parlant đã có một kho nhớ khách hàng dài hạn hoàn chỉnh.

Về handoff:

- Chế độ `auto`/`manual` đã có từ 3.x.
- Chuyển session sang `manual` giúp AI ngừng trả lời.
- Để HR thực sự nhận phiên, có hàng chờ, nhận thông báo và phản hồi, vẫn cần phần tích hợp người nhận.

Vì vậy `DemoHR` và cơ chế bàn giao của bạn vẫn có vai trò. [Nguồn: variables](/home/fw2025/MBW/parlant/docs/variables.md:35), [memory](/home/fw2025/MBW/parlant/docs/memory.md:1), [session](/home/fw2025/MBW/parlant/docs/sessions.md:10).

---

**18. Compaction, usage và ngân sách trở thành các lớp vận hành rõ ràng hơn.**

**Compaction** xử lý hội thoại dài:

- Tóm tắt phần lịch sử cũ.
- Lưu summary vào session.
- Các bước sau dùng summary cùng phần hội thoại mới.
- Chạy sau phản hồi trong giai đoạn hoàn tất lượt.
- Mức effort ảnh hưởng ngưỡng và độ chi tiết của summary.

Đây không phải xóa dữ liệu nghiệp vụ hoặc thay thế hồ sơ ứng viên. Hồ sơ vẫn nên được đọc từ store của bạn. [Nguồn: compaction](/home/fw2025/MBW/parlant/docs/compaction.md:1).

**Usage và pricing** được mở rộng thành:

- Số request.
- Token đầu vào/đầu ra.
- Cached tokens.
- Theo model/provider.
- Chi phí theo lượt và toàn session.
- Chi phí do tool phát sinh.
- Bảng giá tùy chỉnh hoặc giá do provider báo.

3.x đã có một phần token usage; điểm mới là lớp tổng hợp và điều khiển chi phí rõ hơn.

**Budget không tự chặn chi tiêu chỉ vì được tạo.**

Bạn cần gắn hành động khi vượt ngân sách, chẳng hạn:

- Chuyển sang HR.
- Dừng xử lý.
- Hạn chế tác vụ.
- Thay đổi hành vi theo policy/evaluator.

Nếu thiếu thông tin định giá cần thiết, phép đo budget báo lỗi cấu hình thay vì âm thầm coi phần thiếu là miễn phí. [Nguồn: usage và budgets](/home/fw2025/MBW/parlant/docs/usage-reports.md:284).

---

**19. Review và moderation là hai lớp riêng, không nên đánh đồng.**

| | Review | Moderation |
|---|---|---|
| Mục đích | Kiểm tra tuân thủ hướng dẫn, hành động và phản hồi | Kiểm tra nội dung bị gắn cờ theo mô hình moderation |
| Cấu hình | Agent/rule và effort | Agent cùng route moderation |
| Tool call | Có review trước thực thi | Không thay validation nghiệp vụ |
| Nội dung hội thoại | Kiểm tra phản hồi theo quy tắc | Có checkpoint đầu vào và đầu ra |

Một số giới hạn hiện tại cần biết:

- `Moderation.AUTO` chỉ chạy checkpoint đã được cấu hình; không tự bật chỉ vì chọn provider.
- Moderation đầu ra có cơ chế chặn trước gửi trong **block mode**.
- Streaming không có cùng cơ chế chặn moderation đầu ra.
- Tài liệu hiện tại ghi rằng lỗi gọi model moderation có thể cho phản hồi đi qua và ghi warning.
- Message review hoạt động theo cơ chế giữ bản nháp riêng đã mô tả ở trên.

Các khác biệt này quan trọng nếu ứng dụng đang dựa vào một lớp kiểm tra duy nhất để kiểm soát đầu ra. [Nguồn: moderation](/home/fw2025/MBW/parlant/docs/moderation.md:21).

---

**20. CLI, Dashboard và widget thay đổi cách xây dựng và triển khai ứng dụng.**

CLI mới tập trung vào:

| Nhóm | Công việc |
|---|---|
| `parlant init` | Tạo project/scaffold |
| `parlant docs query` | Hỏi tài liệu |
| `parlant widget init` | Copy mã nguồn widget vào ứng dụng |
| `parlant dashboard ...` | Project, deploy, secrets, session, logs… |

Các scaffold có sẵn:

- `basic`.
- `retail-store`.
- `lead-gen`.

Các executable cũ `parlant-server` và `parlant-prepare-migration` không còn được đăng ký như trước.

Dashboard được tích hợp cho:

- Local/self-hosted project.
- Managed hosting.
- Deploy từ GitHub.
- Build/runtime logs.
- Secrets.
- Xem session, trace và analytics.

Về frontend:

- 3.x đã có giao diện `/chat`.
- 4.0 bổ sung widget chính thức để tích hợp vào ứng dụng.
- Widget được copy dưới dạng source để bạn sở hữu và tùy chỉnh.
- Có transport SSE, suggestions, trạng thái kết nối, auth, tool widgets và rich content.

Với file/ảnh, Parlant chủ yếu mang **tham chiếu tới file trong storage của ứng dụng**, không tự trở thành dịch vụ lưu file. Tài liệu AG-UI là hướng dẫn viết adapter, không có nghĩa đã có endpoint AG-UI hoàn chỉnh chạy sẵn.

Server còn có `hot_reload=True` mặc định: khi file Python thay đổi, server shutdown và chạy lại script; không phải vá code trực tiếp trong process. [Nguồn: CLI](/home/fw2025/MBW/parlant/docs/parlant-cli.md:1), [widget](/home/fw2025/MBW/parlant/widget/README.md:40), [rich content](/home/fw2025/MBW/parlant/docs/rich-content.md:1), [hot reload](/home/fw2025/MBW/parlant/docs/hot-reload.md:1).

---

**21. Diagnostics và health được mở rộng; không phải mới xuất hiện hoàn toàn.**

3.x đã có `/healthz` và OpenTelemetry. 4.0 mở rộng:

- Health của engine.
- Tỷ lệ thành công và độ trễ NLP theo route.
- Event-loop health.
- Diagnostic report theo trace.
- Logs và traceback liên quan.
- Session/events để điều tra lỗi.
- Thông tin pricing coverage.

Diagnostic reports được bật mặc định và có thể xuất thành ZIP.

Một điểm vận hành: `/healthz` có thể trả **HTTP 200 ngay cả khi trạng thái nội dung là degraded/unhealthy**. Hệ thống theo dõi cần kiểm tra body nếu muốn dùng các trạng thái này.

Thông tin chi tiết được giới hạn theo quyền, còn caller không đủ quyền chỉ nhận trạng thái tổng quát. [Nguồn: diagnostics](/home/fw2025/MBW/parlant/docs/diagnostics.md:48).

---

**22. Các bản 4.0.1–4.0.4 bổ sung gì sau bản lớn?**

| Phiên bản | Thay đổi nổi bật theo changelog |
|---|---|
| **4.0.1** | Preamble trong scaffold lead-gen; narration cho tool; sửa tương thích Anthropic |
| **4.0.2** | S3; WebMCP; avatar video; cải thiện widget mobile; hoàn tất setup Dashboard với session có sẵn; sửa pagination, cancellation và một số lỗi dữ liệu |
| **4.0.3** | Dashboard nhận diện hoạt động CLI bằng thông tin command/invocation |
| **4.0.4** | `Agent.queue_response()`; cải thiện câu hỏi mơ hồ và thông tin thiếu; reasoning của stream trên Dashboard; sửa Anthropic SDK và hiển thị RTL |

Riêng `queue_response()`:

- Phối hợp phản hồi từ tác vụ nền.
- Có thể gộp kết quả sẵn sàng với lượt khách hoặc kết quả khác.
- Điều phối hiện nằm trong một process.
- Cần session routing affinity.
- Công việc đang chờ không được phục hồi sau restart.

Checkout hiện tại còn có **Unreleased** gồm sửa structured MCP results, cạnh tranh cache Gemini và startup MongoDB. Những mục này không nên coi là đã phát hành trong 4.0.4. [Nguồn: changelog](/home/fw2025/MBW/parlant/CHANGELOG.md:14).

---

**23. Với demo tuyển dụng của bạn, mức ảnh hưởng cụ thể như sau.**

| Thành phần hiện tại | Hướng chuyển | Mức ảnh hưởng |
|---|---|---|
| `ProfilePatch`, validation điện thoại | Giữ phần lớn | Thấp |
| `RecruitmentData`, `JsonStore` nghiệp vụ | Giữ, kiểm tra contract/context | Thấp–vừa |
| Tool tra cứu và lưu hồ sơ | Giữ nghiệp vụ, cập nhật API cần thiết | Vừa |
| `create_guideline()` | Chuyển thành policy/observation | Vừa |
| `create_application_journey()` | Viết lại thành SOP đầy đủ | Cao |
| Template dùng `STRICT` | Thiết kế lại cách bảo toàn dữ liệu/câu chữ | Cao |
| `AUTO_HANDOFF.evidence_ready` | Chuyển evaluator và context mới | Cao |
| Hook kiểm tra nguồn và chặn AI | Chuyển theo lifecycle Compass | Cao |
| `ToolContextAccessor` | Dùng `.current` | Thấp |
| LiteLLM + Qwen/vLLM | Cấu hình lại các model route/endpoint | Vừa–cao |
| Session/customer đã lưu | Lập phương án chuyển dữ liệu riêng | Cao |
| `/chat`, `/hr` tùy chỉnh | Kiểm tra auth, event và streaming | Vừa–cao |

Các hành vi quan trọng cần đối chiếu lại sau chuyển đổi:

- Hỏi thông tin công việc không bị hiểu thành đồng ý đăng ký.
- Chỉ bắt đầu thu thập khi có ý định đăng ký rõ.
- Lưu từng phần, không đợi đủ mọi trường.
- Không sửa tên hoặc suy đoán số điện thoại.
- Không xác nhận lưu khi tool từ chối.
- Phân biệt thông tin chung với chi tiết cụ thể, như “máy tính” và “MacBook”.
- Chỉ bàn giao vì thiếu thông tin sau khi đã tra đúng nguồn.
- Không chuyển HR chỉ vì danh sách việc rỗng hoặc vị trí đã đóng.
- Sau khi bàn giao, AI không tiếp tục hỏi hồ sơ.
- Khi HR trả lại phiên, agent dùng đúng thông tin HR đã xác nhận.
- Khi ứng viên hủy hoặc gửi tin nhắn mới lúc engine đang xử lý, không thực hiện tiếp thao tác đã mất hiệu lực.

**Phần nên giữ chắc trong Python là quyền truy cập, validation, điều kiện ghi dữ liệu và trạng thái bàn giao. Policy mô tả quy trình hội thoại; tool quyết định một thao tác nghiệp vụ có được phép thực hiện hay không.**