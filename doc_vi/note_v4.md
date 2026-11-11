# Ghi chú Parlant 4.0: so sánh với 3.x và chuyển đổi ứng dụng tuyển dụng

Tài liệu tổng hợp nội dung trao đổi về Parlant 4.0: thuật ngữ mới, thay đổi
engine, SDK/API, vận hành và cách chuyển ví dụ tuyển dụng từ 3.x. Các ví dụ
được dùng để giải thích cơ chế; không phải kết quả benchmark hay bản demo
hoàn chỉnh đã chạy kiểm thử.

## 1. Phạm vi đối chiếu

- Bản cũ: tag `v3.3.2`.
- Bản lớn mới: commit phát hành `87247c1e`, phiên bản `4.0.0`.
- Các bản cập nhật được xét thêm: `4.0.1` đến tag `v4.0.4`.
- Thời điểm tổng hợp: 11/11/2026.
- Checkout còn có mục `Unreleased`; không coi những mục đó là đã phát hành
  trong `4.0.4`.

Nội dung được đối chiếu bằng mã nguồn, tài liệu và lịch sử Git trong repo.
Changelog 4.0.0 chỉ ghi mốc phát hành, nên cần xem cả thay đổi mã nguồn so
với 3.3.2 để hiểu đầy đủ bản lớn.

Đọc changelog cũ:

```bash
git show v3.3.2:CHANGELOG.md
```

Xem thay đổi của bản lớn:

```bash
git diff v3.3.2 87247c1e -- src/parlant/sdk.py
git diff v3.3.2 87247c1e -- src/parlant/api/app.py
git diff v3.3.2 87247c1e -- pyproject.toml
```

**Kết luận quan trọng:** 4.0 thay đổi cả cách khai báo lẫn cơ chế điều phối.
Có thể giữ phần lớn nghiệp vụ trong tool, nhưng không thể chỉ đổi tên API
rồi mặc định hành vi giống hệt 3.x.

## 2. Bức tranh tổng thể

| Khía cạnh | 3.3.2 | 4.0 |
|---|---|---|
| Engine | Alpha | Compass |
| Quy tắc hướng dẫn hành vi | Guideline | Policy |
| Nhận diện tình huống | Observation dưới dạng guideline không có action | `Observation` riêng, cùng kế thừa `Rule` với `Policy` |
| Quy trình nhiều bước | Journey, state, transition | Policy dạng SOP |
| Thực hiện tác vụ | Vòng chuẩn bị, sau đó tạo phản hồi | Vòng reasoning, tool và phản hồi thống nhất |
| Review tool | Cơ chế engine/hook cũ | Tool review tích hợp trước thực thi |
| Review phản hồi | Composition, response analysis và hook | Message review tích hợp trước gửi |
| Canned response | Có composition mode, gồm `STRICT` | Mẫu hướng dẫn cho câu trả lời được sinh mới |
| Model | `NLPService` | Định tuyến theo từng loại tác vụ |
| Mức xử lý | Các cấu hình của engine cũ | `Effort` và nâng effort theo tình huống |
| Session/customer mặc định | RAM | SQLite |
| API quản lý hành vi | CRUD guideline, journey, canned response... | Thu hẹp; hành vi được định nghĩa bằng SDK/code |
| CLI | Chủ yếu là client quản trị tài nguyên | Scaffold, docs, widget, Dashboard/deploy |
| Auth | Authorization policy tổng quát | Identity, token, permission và ownership |
| Vận hành | Logs, inspection, health, OpenTelemetry | Mở rộng diagnostics, health, usage, pricing và budgets |

Kiến trúc repo vẫn theo hướng core/ports, adapters và API. Việc giữ cấu trúc
kiến trúc không có nghĩa implementation engine hoặc API công khai giữ nguyên.

## 3. Thuật ngữ: Rule, Policy, Observation và SOP

### 3.1. Rule là gì?

Ở SDK 4.0, `Rule` là mô hình chung cho `Policy` và `Observation`:

```text
Rule
├── Policy       → hướng dẫn agent làm gì
└── Observation  → nhận diện tình huống để điều khiển runtime
```

Bạn thường tạo bằng:

```python
await agent.create_policy(...)
await agent.create_observation(...)
```

Không cần tạo thêm một Rule rồi gắn Policy vào nó. Policy và Observation
tự chúng đã là các loại Rule.

Khi tài liệu nói “matching rules”, đó là đánh giá các rule thuộc hai loại
này, không chỉ riêng policy.

Những khả năng dùng chung gồm:

- Tool associations.
- Dependency, entailment và priority.
- Callback khi discovery/match.
- Labels.
- Yêu cầu review.
- Nâng effort.
- Canned response và field provider.

Khái niệm “quy tắc hành vi” đã có từ Guideline trước đây. Điểm mới là mô hình
`Rule` chung trong API 4.0, không phải trước 4.0 agent không có quy tắc.

### 3.2. Policy là gì?

Policy mô tả điều kiện áp dụng, hành động, yêu cầu và ngoại lệ bằng nội dung
ngôn ngữ tự nhiên trong `content`.

Một policy có thể là:

- Một quy tắc ngắn, tương đương vai trò của guideline.
- Một tài liệu chính sách nghiệp vụ.
- Một quy trình nhiều bước, thay vai trò của journey.

Ví dụ guideline cũ:

```python
await agent.create_guideline(
    condition="Ứng viên muốn đăng ký",
    action="Hỏi vị trí muốn ứng tuyển",
)
```

Sang 4.0:

```python
await agent.create_policy(
    title="Bắt đầu đăng ký",
    content="Khi ứng viên muốn đăng ký, hỏi vị trí muốn ứng tuyển.",
)
```

Ý nghĩa nghiệp vụ của ví dụ đơn giản này tương đương. Cơ chế đánh giá bên
trong không giống hoàn toàn, nên vẫn phải kiểm tra lại hành vi.

### 3.3. Observation là gì?

Observation nhận diện một tình huống, thay vì trực tiếp yêu cầu agent nói
hoặc làm một việc.

```python
await agent.create_observation(
    condition="Ứng viên phản ánh thông tin tuyển dụng sai lệch.",
    trigger_effort=p.Effort.HIGH,
    trigger_message_review=True,
    labels=["recruitment-complaint"],
)
```

Observation có thể làm điều kiện cho policy khác, cung cấp tool, kích hoạt
review, tăng effort, chạy callback hoặc gắn label.

Observation **đã có ở 3.3.2**, dưới dạng guideline không có action. 4.0 làm
rõ nó thành loại Rule riêng, có `condition` và `note` tùy chọn.

### 3.4. SOP là gì?

SOP viết tắt của **Standard Operating Procedure**, nghĩa là **quy trình
thao tác chuẩn**.

Một SOP mô tả:

- Làm những bước nào.
- Thứ tự và dữ liệu cần cho mỗi bước.
- Điều kiện rẽ nhánh.
- Khi nào được bỏ qua hoặc quay lại bước.
- Khi nào cần khách xác nhận.
- Khi nào phải dừng.

Trong Parlant, SOP là **cách viết nội dung policy**, không phải class hay
API riêng.

Ví dụ:

```python
await agent.create_policy(
    title="Đăng ký ứng tuyển",
    content="""
Khi ứng viên muốn đăng ký, thực hiện theo thứ tự:
1. Xác định vị trí muốn ứng tuyển.
2. Tra cứu và kiểm tra vị trí còn tuyển.
3. Đọc hồ sơ hiện có.
4. Kiểm tra và lưu từng thông tin hợp lệ đã được cung cấp.
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

Nguồn: [Policy Design](../docs/policy-design.md).

## 4. Policy có bao gồm cả guideline và journey cũ không?

**Có, xét về vai trò.**

| Vai trò ở 3.x | Cách biểu đạt ở 4.0 |
|---|---|
| Guideline: “khi X, làm Y” | Policy ngắn |
| Journey: quy trình gồm nhiều bước và nhánh | Policy dạng SOP |
| Guideline chỉ nhận diện tình huống | Observation |

Nhưng policy **không chứa lại đồ thị Journey SDK**:

- Không còn `create_journey()`.
- Không còn các đối tượng Journey state/transition cũ.
- Không còn `transition_to()` hoặc `END_JOURNEY` tương ứng trong API mới.
- Thứ tự, nhánh và điều kiện dừng được viết vào nội dung policy.

Nên giữ một quy trình hoàn chỉnh trong một policy thay vì tách mỗi bước
thành một policy nhỏ rồi bắt engine tái dựng luồng mỗi lượt.

Một điểm cần hiểu đúng: Journey cũ cũng dùng model để diễn giải trạng thái
và điều kiện; không phải máy trạng thái hoàn toàn tất định. Tài liệu 3.x cho
phép bỏ qua, quay lại hoặc nhảy bước theo ngữ cảnh.

## 5. Logic nghiệp vụ và logic core thay đổi khác nhau

| Phần | Có thể giữ gì? | Cần chuyển gì? |
|---|---|---|
| Validation nghiệp vụ | Quy tắc tên, điện thoại, vị trí hợp lệ | Chỗ đọc context/API cũ |
| Lưu dữ liệu | Repository/store nghiệp vụ, cách ghi hồ sơ | Contract gọi và kết quả nếu API thay đổi |
| Hội thoại | Mục tiêu, điều kiện nghiệp vụ | Guideline/journey sang policy/observation |
| Engine | Không giữ implementation Alpha | Compass có vòng xử lý và matching mới |
| Kiểm soát phản hồi | Yêu cầu không nói sai, không lưu sai | Composition, review và hooks mới |
| Handoff | Ý định bàn giao, trạng thái nghiệp vụ | Lifecycle hook và tích hợp session mới |

Do đó câu “chỉ đổi cách khai báo, logic vẫn nguyên” chỉ đúng với **một phần
logic nghiệp vụ do ứng dụng tự viết**, không đúng với toàn bộ framework.

Các điều kiện bắt buộc như quyền truy cập, dữ liệu hợp lệ và điều kiện ghi
phải tiếp tục được kiểm tra bằng code trong backend.

## 6. Alpha 3.x và Compass 4.0 khác nhau ở đâu?

### 6.1. Alpha: chuẩn bị trước, tạo phản hồi sau

```text
Đọc hội thoại
→ tìm guideline/journey phù hợp
→ suy luận tool cần gọi
→ thực thi tool
→ dùng kết quả để chuẩn bị tiếp nếu cần
→ khi chuẩn bị xong hoặc đạt giới hạn, tạo câu trả lời
```

Một vòng chuẩn bị có thể gồm:

1. Đánh giá guideline và journey.
2. Giải quyết dependency và priority.
3. Suy luận tool call.
4. Chạy không, một hoặc nhiều tool.
5. Cập nhật kết quả và trạng thái.

Giai đoạn tạo câu trả lời cuối nằm **sau** vòng chuẩn bị.

Alpha đã có feedback loop: kết quả tool có thể làm guideline/journey khác
trở nên phù hợp. Không nên mô tả 3.x là không có khả năng này.

### 6.2. Compass: reasoning, tool và phản hồi trong một vòng

```text
Đọc hội thoại và ngữ cảnh
→ tìm policy/observation liên quan
→ đánh giá rule áp dụng
→ đưa policy và tool phù hợp vào ngữ cảnh model
→ model suy luận và đề xuất tool call
→ review tool nếu được yêu cầu
→ engine thực thi tool
→ đưa kết quả vào vòng xử lý
→ đánh giá lại rule phụ thuộc tool khi cơ chế xử lý cho phép
→ model tiếp tục gọi tool hoặc viết phản hồi
→ review phản hồi nếu được yêu cầu
→ gửi phản hồi
```

Model sinh tool call theo cơ chế tool calling; Parlant mới là bên thực thi
Python/tool. Model không tự chạy code hoặc truy cập database tùy ý.

“Reasoning” ở đây là phần xử lý/suy luận của model trong bước thực thi,
không có nghĩa ứng dụng phải tự viết một chuỗi suy nghĩ cho mọi tình huống.

Nguồn: [Tools](../docs/tools.md),
[Compass engine](../src/parlant/core/engines/compass/engine.py),
[vòng xử lý](../src/parlant/core/engines/compass/loop/base_loop.py).

## 7. Policy thể hiện ở đâu trong luồng Compass?

Policy nằm trong “rule” ở bước matching, rồi tiếp tục chi phối các bước sau.
Nó không phải một bước được chạy một lần rồi biến mất.

| Thời điểm | Policy chi phối gì trong quy trình đăng ký? |
|---|---|
| Chọn hành vi | Ứng viên có thật sự muốn đăng ký không? |
| Trước tra cứu | Cần xác minh vị trí nào? |
| Trước lưu | Đã đủ điều kiện lưu và có dữ liệu hợp lệ chưa? |
| Sau tool | Kết quả thật là thành công, thất bại hay còn thiếu? |
| Viết phản hồi | Được xác nhận gì, cần hỏi gì tiếp? |
| Review | Đề xuất có vi phạm hướng dẫn đang áp dụng không? |

Ví dụ “Tôi muốn đăng ký CN001”:

- Engine xác định policy đăng ký liên quan và áp dụng.
- Model nhận quy trình cùng các tool phù hợp.
- Model dùng hướng dẫn để quyết định tra cứu vị trí trước.
- Sau kết quả, model tiếp tục lưu hoặc báo vị trí đã đóng.
- Reviewer, nếu được bật, kiểm tra đề xuất theo hướng dẫn đang chi phối.

Không nên rút gọn thành “nhét tất cả policy vào một prompt rồi để model tự
làm”. Engine còn có discovery, matching, dependency, priority, tool catalog
và các điểm kiểm soát thực thi.

## 8. Ví dụ cụ thể: đăng ký ứng tuyển ở hai engine

### 8.1. Tình huống

Ứng viên gửi:

> Tôi muốn đăng ký CN001. Tôi tên Nguyễn An, số điện thoại 0901234567.

Giả sử quy trình yêu cầu:

1. Kiểm tra vị trí còn tuyển.
2. Đọc hồ sơ hiện có.
3. Lưu thông tin hợp lệ.
4. Phản hồi đúng kết quả.

Để so sánh cơ chế, giản lược demo thành ba tool:

| Tool | Kết quả giả định |
|---|---|
| `search_jd_info("CN001")` | Vị trí còn tuyển |
| `get_candidate_profile(...)` | Chưa có hồ sơ |
| `save_profile(...)` | `saved=true`, hồ sơ đã đủ |

Đây là **một trình tự minh họa**, không phải trace bắt buộc. Hai engine có
thể gộp các call độc lập. Ví dụ này cũng không thay thế nguyên trạng journey
cũ vốn có thể gọi `update_candidate_field` cho từng trường.

### 8.2. Một trình tự ở Alpha

| Giai đoạn | Xử lý | Trạng thái |
|---|---|---|
| Chuẩn bị 1 | Match guideline/journey, gọi `search_jd_info` | Biết CN001 còn tuyển |
| Chuẩn bị 2 | Xét kết quả trước, gọi `get_candidate_profile` | Biết chưa có hồ sơ |
| Chuẩn bị 3 | Gọi `save_profile` | Biết lưu thành công |
| Tạo phản hồi | Dùng dữ liệu đã chuẩn bị | Gửi xác nhận |

Phản hồi cuối không phải một vòng chuẩn bị thứ tư.

### 8.3. Một trình tự ở Compass

| Bước | Quyết định theo policy | Engine xử lý |
|---|---|---|
| 1 | Cần kiểm tra vị trí | Review nếu bật, chạy `search_jd_info` |
| 2 | Cần đọc hồ sơ hiện có | Chạy `get_candidate_profile` |
| 3 | Có thể lưu thông tin | Review nếu bật, chạy `save_profile` |
| 4 | Kết quả đã xác nhận | Viết, review nếu bật và gửi phản hồi |

Ở Compass, bước phản hồi bình thường cũng nằm trong vòng xử lý.

### 8.4. Khi công việc cần khách bổ sung thông tin

Nếu ứng viên chưa cung cấp điện thoại, engine không tiếp tục vô hạn để chờ:

```text
Đọc hồ sơ / lưu phần đã biết
→ nhận missing_fields=["phone"]
→ hỏi số điện thoại
→ kết thúc lượt hiện tại
```

Ứng viên trả lời số điện thoại sẽ tạo lượt xử lý mới. Một SOP gồm nhiều bước
nghiệp vụ có thể trải qua nhiều lượt hội thoại.

## 9. Vì sao max_engine_iterations không bằng max_steps?

| | Alpha | Compass |
|---|---|---|
| Tham số | `max_engine_iterations` | `max_steps` |
| Đơn vị | Vòng chuẩn bị | Bước trong vòng phản hồi |
| Mặc định SDK | 3 | 15 |
| Phản hồi cuối bình thường | Sau vòng chuẩn bị | Là một bước của vòng xử lý |
| Khi đạt giới hạn | Chuyển sang phản hồi với thông tin đã có | Đi vào đường xử lý đạt giới hạn nếu chưa chuẩn bị xong phản hồi |

Trong trình tự minh họa ở mục 8:

```text
Alpha, max_engine_iterations=3:
  chuẩn bị 1: tra cứu vị trí
  chuẩn bị 2: đọc hồ sơ
  chuẩn bị 3: lưu hồ sơ
  sau đó: tạo câu trả lời

Compass, max_steps=3:
  bước 1: tra cứu vị trí
  bước 2: đọc hồ sơ
  bước 3: lưu hồ sơ
  chưa có lượt cho bước phản hồi bình thường
  → xử lý đạt giới hạn / on_giving_up
```

Những điều cần nhớ:

- Một iteration không bằng một tool call.
- Một step không bằng một tool call.
- Một iteration/step không bằng tổng một request LLM của hệ thống.
- Một bước có thể đề xuất nhiều tool call.
- Matching, review và retry có thể tạo thêm request LLM.
- Tool tự gọi các hàm Python bên trong không tự biến mỗi hàm thành step mới.
- Đạt giới hạn không tự rollback các thao tác đã commit.

Trong ví dụ Compass ba bước trên, hồ sơ có thể đã lưu ở bước 3 nhưng agent
không còn bước phản hồi bình thường. Engine có đường xử lý không hoàn thành
và thông báo cuối; không có nghĩa chắc chắn không gửi bất kỳ thông báo nào.

Không chuyển số `3` của tham số cũ sang tham số mới một cách máy móc. Tăng
giới hạn cũng không sửa được policy hoặc tool sai.

## 10. Ví dụ review: chặn lưu sai và chặn xác nhận sai

### 10.1. Tool review trước thao tác

Giả sử model đề xuất `save_profile` trước khi xác minh vị trí còn tuyển,
trong khi policy yêu cầu phải tra cứu trước.

| Thời điểm | Kết quả |
|---|---|
| Model đề xuất lưu | Tool chưa chạy |
| Reviewer kiểm tra | Phát hiện thiếu điều kiện tra cứu |
| Reviewer từ chối | Call chưa được thực thi bị loại |
| Tạo lại bước | Model nhận hướng dẫn sửa reasoning |
| Đề xuất mới | Gọi tra cứu vị trí trước |

Review không hoàn tác các thao tác đã chạy ở bước trước. Validation backend
vẫn phải bảo vệ dữ liệu khi reviewer không nhận ra sai sót.

### 10.2. Message review trước gửi

Tool trả:

```json
{
  "saved": false,
  "error": "Số điện thoại không hợp lệ"
}
```

Nhưng model viết:

> Mình đã lưu hồ sơ của bạn.

Message reviewer có thể từ chối bản nháp trước khi gửi và yêu cầu tạo lại
phản hồi phù hợp với kết quả tool.

### 10.3. Retry không đồng nghĩa với step mới thông thường

Trong code Compass hiện tại, các lần bị reviewer buộc tạo lại nằm trong
vòng retry của bước đang xử lý. Không lấy tổng số request model làm số
`max_steps`.

Review có giới hạn thử lại. Nếu liên tục thất bại, engine đi vào đường
không hoàn thành tác vụ; có thể tùy chỉnh qua `on_giving_up`.

Review không phải bảo đảm tất định rằng reviewer luôn phát hiện mọi lỗi.

## 11. Ví dụ kết quả tool làm đổi hướng: “có cấp MacBook không?”

Ứng viên hỏi:

> Vị trí CN001 có cấp MacBook không?

Tool thông tin công ty trả:

```json
{
  "equipment": "Công ty cấp máy tính làm việc"
}
```

Thông tin chung “máy tính” không xác nhận chi tiết “MacBook”.

| Alpha 3.x | Compass 4.0 |
|---|---|
| Vòng đầu gọi tool tra cứu | Bước đầu gọi tool tra cứu |
| Vòng sau xét guideline phụ thuộc kết quả | Kết quả vào reasoning; đánh giá lại rule phụ thuộc tool khi cơ chế xử lý cho phép |
| Guideline thiếu thông tin có thể dẫn tới handoff | Policy thiếu thông tin dẫn tới đề xuất handoff |
| Hook và session mode kiểm soát AI sau bàn giao | Hook, session mode và review nếu bật kiểm soát phần tiếp theo |

Quan hệ như sau vẫn có ý nghĩa:

```python
await missing_information.reevaluate_after(search_company_info)
```

Effort ảnh hưởng việc tái đánh giá sau tool. Theo tài liệu, trên LOW có
rematching rule phụ thuộc tool; MIN/LOW giữ match đầu lượt. Không coi mọi
cấu hình effort là tương đương.

Trong demo, backend cần tiếp tục kiểm tra bằng chứng tra cứu của **lượt
hiện tại**, không chỉ tin model khai báo rằng đã tra cứu.

## 12. Discovery khác matching theo lượt

| Khái niệm | Câu hỏi |
|---|---|
| Discovery | Rule có liên quan đến session để đưa vào working set không? |
| Turn evaluation/matching | Rule có thực sự áp dụng ở lượt hiện tại không? |

**Discovered không có nghĩa matched ngay lúc này.**

Ví dụ:

1. Ứng viên từng nói muốn đăng ký.
2. Policy đăng ký được đưa vào working set.
3. Lượt sau ứng viên hỏi nghĩa “phụ cấp chuyên cần”.
4. Agent không vì policy vẫn trong ngữ cảnh mà phải đòi số điện thoại ngay.

Discovery ở 4.0 dùng bộ phân loại embedding riêng cho từng rule, theo agent:

- `signals`: ví dụ dương.
- `anti_signals`: các tình huống gần giống nhưng không được kích hoạt.
- Recall tại runtime dùng classifier; không phải mỗi recall đều gọi LLM.
- Rule có hệ quả runtime cần đánh giá phù hợp theo chiến lược matching.
- Working set được giữ qua các lượt và được cắt tỉa khi cần.

Ví dụ:

```python
await agent.create_policy(
    title="Đăng ký ứng tuyển",
    content="Khi ứng viên yêu cầu đăng ký rõ ràng, thực hiện quy trình đăng ký.",
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

Chất lượng signals/anti-signals ảnh hưởng khả năng recall. Chúng không thay
thế một policy diễn đạt rõ ràng hoặc validation bắt buộc.

Classifier được train khi khởi động. Theo tài liệu hiện tại:

- Rule mới sau startup có thể dùng fallback training.
- Sửa nội dung/signals của ID đã được train có thể vẫn dùng classifier cũ
  cho discovery đến lần restart tiếp theo.

Custom `evaluation_func` dùng code để quyết định, không đi qua discovery
và signal proposition theo cùng cách. Custom matcher đã có từ 3.x; đây là
giao diện và tổ chức mới, không phải lần đầu có khả năng đánh giá bằng code.

Nguồn: [Rule Discovery](../docs/rule-discovery.md),
[Matching](../docs/internal/matching.md).

## 13. Dependency, priority và entailment

Các phương thức vẫn có:

```python
await policy.depend_on(other)
await policy.depend_on_any(first, second)
await policy.prioritize_over(other)
await policy.entail(other)
await policy.reevaluate_after(tool)
```

Nhiều phương thức này đã tồn tại ở 3.x, nhưng semantics trên Compass cần được
kiểm tra lại:

- Dependency cần một lần match thật; discovery đơn thuần chưa đủ.
- Prerequisite đã match có thể mở khóa policy phụ thuộc ở lượt sau.
- `prioritize_over` nhắm vào các target cụ thể.
- `priority` bằng số có tác động rộng hơn, có thể đặt cả rule không liên
  quan sang một bên.
- Rule thua priority không nhất thiết bị xóa khỏi session working set.
- Nội dung rule bị đặt sang một bên có thể vẫn hiện cùng ghi chú thu hồi
  cho phản hồi hiện tại.
- Rule bị thu hồi theo priority có thể vẫn có ý nghĩa với dependency.

Trong ví dụ tuyển dụng:

```python
await missing_information.prioritize_over(scope)
```

Cần phân biệt rõ:

- Đúng phạm vi nhưng thiếu chi tiết.
- Job ngoài phạm vi agent.
- Job đã đóng.
- Không có job hợp tiêu chí.
- Nguồn tra cứu bị lỗi.
- HR đã xác nhận chi tiết trong cùng session.

Không dùng numeric priority cao chỉ để “chắc chắn thắng” nếu nó làm mất các
quy tắc vẫn cần áp dụng ở phần khác của lượt.

Nguồn: [Priority và dependency](../docs/policy-design.md).

## 14. Weight, Effort và Review là ba điều khiển riêng

| Điều khiển | Ý nghĩa |
|---|---|
| `weight` | Policy là gợi ý mềm hay giới hạn cần giữ chặt |
| `effort` | Mức công sức engine đầu tư vào lượt |
| `tool_review` / `message_review` | Kiểm tra đề xuất trước thực thi hoặc gửi |

### 14.1. Weight

| Mức | Vai trò |
|---|---|
| `LOW` | Hướng dẫn mềm, có thể linh hoạt |
| `MEDIUM` | Quy tắc nghiệp vụ cần tuân theo; mặc định |
| `HIGH` | Giới hạn quan trọng cần giữ trước áp lực từ khách |

`weight` thay cho tham số `criticality` cũ trong API mới, nhưng không nên
chỉ đổi tên rồi giả định matching và hành vi giống hoàn toàn.

LOW-weight rule thường được đưa vào hướng dẫn như gợi ý mềm; những rule
có hệ quả runtime có cách đánh giá riêng. Weight không chỉ là một con số
thứ tự ưu tiên.

### 14.2. Effort

Có năm mức:

```python
p.Effort.MIN
p.Effort.LOW
p.Effort.MEDIUM
p.Effort.HIGH
p.Effort.MAX
```

Baseline được cấu hình trên agent; rule áp dụng có thể nâng mức cho lượt:

```python
await agent.create_observation(
    condition="Ứng viên khiếu nại hoặc yêu cầu xử lý tình huống phức tạp.",
    trigger_effort=p.Effort.HIGH,
)
```

Effort ảnh hưởng:

- Model routing nếu có route theo effort.
- Mức reasoning.
- Chiến lược matching.
- Retry sau review.
- Tái đánh giá sau tool.
- Chọn canned response.
- Ngưỡng và độ chi tiết compaction.

Rule nâng effort cho lượt hiện tại, không tự hạ thấp baseline.

**MIN bỏ qua review kể cả khi đã yêu cầu.** Không xem MIN đơn giản là cùng
cơ chế nhưng dùng model rẻ hơn.

Nguồn: [Adaptive Effort](../docs/adaptive-effort.md).

## 15. Review và moderation

### 15.1. Tool review và message review

| | Tool review | Message review |
|---|---|---|
| Đối tượng | Reasoning và tool call đề xuất | Phản hồi hoàn chỉnh |
| Thời điểm | Trước thực thi | Trước gửi |
| Nếu từ chối | Bỏ call chưa thực thi, tạo lại bước | Bỏ bản nháp, tạo lại phản hồi |
| Cấu hình | Agent, matched rule hoặc consequential tool | Agent hoặc matched rule |

Bật toàn agent:

```python
agent = await server.create_agent(
    id="recruitment",
    name="Recruitment",
    instructions="Tư vấn tuyển dụng bằng dữ liệu được cấp.",
    effort=p.Effort.MEDIUM,
    tool_review=True,
    message_review=True,
)
```

Hoặc chỉ yêu cầu theo policy:

```python
await agent.create_policy(
    content="Chỉ nói đã lưu hồ sơ khi kết quả tool xác nhận thành công.",
    trigger_message_review=True,
)
```

Các điểm quan trọng:

- Hai cờ review trên agent mặc định `False`.
- Matched rule có thể yêu cầu thêm review.
- Khi message review hoạt động, câu trả lời được giữ lại để kiểm tra cả
  bản nháp, kể cả agent cấu hình stream.
- Reviewer kiểm tra tuyên bố đã thực hiện hành động phải được kết quả tool
  hỗ trợ.
- Hết retry budget, engine đi vào đường không hoàn thành; thông báo give-up
  cuối không được review theo cùng vòng lặp.
- Có thể thay hành vi give-up bằng hook.
- MIN bỏ qua review.

### 15.2. Moderation khác review

| | Review | Moderation |
|---|---|---|
| Mục đích | Tuân thủ hướng dẫn, hành động và phản hồi | Phát hiện nội dung bị gắn cờ |
| Cấu hình | Agent/rule, effort | Agent và model route |
| Tác vụ nghiệp vụ | Có thể kiểm tra đề xuất tool | Không thay validation nghiệp vụ |
| Checkpoint | Tool và phản hồi | Tin khách và tin agent |

Moderation có ba chế độ trên agent: `AUTO`, `ON`, `OFF`.

- `AUTO` chỉ chạy checkpoint được cấu hình.
- Chọn provider qua `*` không tự bật moderation.
- `ON` yêu cầu cấu hình checkpoint thích hợp, được kiểm tra khi khởi động/
  tạo hoặc cập nhật agent.
- Kiểm soát moderation đầu ra trước khi gửi hiện áp dụng ở block mode.
- Stream không có cùng gate moderation đầu ra.
- Tài liệu hiện tại ghi rằng nếu model moderation lỗi, phản hồi có thể
  được cho qua và ghi warning.

Không suy diễn rằng mọi cấu hình review/moderation đều là một lớp chặn
tuyệt đối hoặc có semantics giống nhau.

Nguồn: [Review](../docs/review.md), [Moderation](../docs/moderation.md).

## 16. Canned response và việc mất CompositionMode.STRICT

Ở 3.x, code có thể dùng:

```python
composition_mode=p.CompositionMode.STRICT
```

API 4.0 không còn `CompositionMode` tương ứng.

Canned response vẫn tồn tại:

```python
await agent.create_canned_response(
    template="Họ tên: {{candidate_full_name}}",
    field_dependencies=["candidate_full_name"],
)
```

Nhưng vai trò hiện tại là:

- Mẫu hướng dẫn cho thành phần viết phản hồi.
- Chuẩn tham chiếu cho reviewer.
- Có thể nội suy field trước khi đưa vào ngữ cảnh.
- Nội dung cuối vẫn do model viết mới.

**Không mặc định đầu ra là template được thay biến nguyên văn.**

Đối với demo tuyển dụng:

```text
Họ tên: {{candidate_full_name}}
Số điện thoại: {{candidate_phone}}
Vị trí: {{candidate_job}}
```

Nếu phải bảo toàn tuyệt đối tên có dấu, số điện thoại hoặc thông báo cố
định, cần thiết kế render/gửi từ code hoặc UI có kiểm soát. Message review
không khôi phục nguyên trạng contract của STRICT cũ.

### 16.1. Truyền field từ tool

Ví dụ trích đoạn, `result` và `profile` phải là dữ liệu thật từ backend:

```python
return p.ToolResult(
    data=result,
    canned_response_fields={
        "candidate_full_name": profile.get("full_name", "Chưa cung cấp"),
        "candidate_phone": profile.get("phone", "Chưa cung cấp"),
        "candidate_job": profile.get("job_id", "Chưa cung cấp"),
    },
)
```

`canned_response_fields` và `field_dependencies` đã có từ 3.x. Cách engine
dùng mẫu mới là thay đổi chính.

Tool ghi thất bại cũng cần phản ánh đúng trạng thái mới nhất. Không để
field/thông báo thành công của lần ghi trước làm che khuất lỗi hiện tại.

### 16.2. Field provider

4.0 hỗ trợ callback `canned_response_field_provider` trên rule. Callback
có thể đọc ngữ cảnh hiện tại và trả mapping field.

Tuy nhiên không mặc định thời điểm callback chạy tương đương hook cũ
“sau tất cả tool”. Với yêu cầu xác nhận kết quả ghi mới nhất, thường cần
trả field ngay từ tool hoặc chọn lifecycle hook thật sự phù hợp.

Nguồn: [Canned Responses](../docs/canned-responses.md).

## 17. Bảng chuyển SDK và mặc định

| 3.3.2 | 4.0 | Ý nghĩa |
|---|---|---|
| `Server(nlp_service=...)` | `Server(models=...)` | Model routing theo capability |
| Provider mặc định Emcie | OpenRouter | Credentials/default model thay đổi |
| Agent `description` | `instructions` | Đổi tham số và thuộc tính |
| Agent `id` có thể bỏ qua | `id` bắt buộc, keyword-only | Cần identity ổn định |
| Output mặc định BLOCK | STREAM | Kiểm tra client/hook |
| `max_engine_iterations` | `max_steps` | Khác đơn vị |
| `composition_mode` | Bị bỏ | Thiết kế lại kiểm soát phản hồi |
| `planner` | Bị bỏ khỏi `create_agent` | Custom planner cần chuyển thiết kế |
| `perceived_performance_policy` | Bị bỏ | Xem preamble/progress mới |
| `tags`, `Tag`, `TagId` | `groups`, `Group`, `GroupId` | Scope/membership mới |
| `create_guideline` | `create_policy` | Chuyển condition/action thành nội dung |
| `Journey` và transition | Bị bỏ | SOP trong policy |
| `matcher` | `evaluation_func` | Đổi chữ ký và context |
| `GuidelineMatchingContext` | `RuleEvaluationContext` | Sửa evaluator |
| `GuidelineMatch` | `RuleEvaluation` | Sửa kết quả đánh giá |
| `on_match`, callback cũ | `on_discovered`, `on_matched`, hooks mới | Không đổi tên máy móc |
| `criticality` | `weight` | Effort và review là điều khiển riêng |
| `ToolContextAccessor` | Bị bỏ | Dùng các đối tượng `.current` |
| `EngineHooks` | `CompassHooks` | Lifecycle thay đổi |
| `EngineHookResult` | `CompassHookResult` | Xem semantics theo hook |
| `configure_hooks` | Container initialization | Đăng ký callback qua container |

Rule ID có thể được suy ra từ nội dung nếu không truyền. Nếu cần identity
ổn định qua sửa nội dung để giữ quan hệ/analytics, dùng ID tường minh.

Nguồn: [SDK](../src/parlant/sdk.py).

## 18. Tool và context

### 18.1. Đọc hội thoại

Cũ:

```python
interaction = p.ToolContextAccessor(context).current_interaction
```

Mới, trong ngữ cảnh thực thi phù hợp:

```python
interaction = p.Session.current.interaction

texts = [
    message.content
    for message in interaction.messages
    if message.source == p.EventSource.CUSTOMER
]
```

`ToolContext` vẫn còn, bao gồm agent/session/customer ID, plugin data và
các phương thức emit. Tool remote không được mặc định có toàn bộ các đối
tượng `.current` của process server.

`Server.current`, `Agent.current`, `Customer.current` và `Session.current`
không phải tất cả đều mới ở 4.0.

### 18.2. Contract thay đổi

| Cũ | Mới |
|---|---|
| `ToolResult(guidelines=...)` | `ToolResult(rules=...)` |
| `TransientGuideline` | `TransientRule` |
| Nội dung transient dùng `action` | Dùng `content` |
| `Agent.utter(guidelines=...)` | `Agent.utter(rules=...)` |
| `ToolParameterOptions.precedence` | Bị bỏ |

Tool có narration để UI mô tả công việc đang thực hiện, và có thể ghi nhận
chi phí.

`consequential=True` đã tồn tại trước nhưng chưa có vai trò thực thi như
hiện tại. 4.0 dùng nó trong hướng dẫn xác nhận và kích hoạt tool review,
với ngoại lệ effort MIN.

### 18.3. Kết quả và vòng đời

`ToolResult` có thể mang:

- `data`: dữ liệu cho model.
- `metadata`: dữ liệu cho client/observability, không phải ngữ cảnh model.
- `control`: mode/lifespan.
- `canned_responses` và `canned_response_fields`.
- `rules`: quy tắc tạm thời.
- `costs`: chi phí.

Các khả năng như field, lifespan, mode và transient instruction phần lớn
đã có trước; không nên gọi tất cả là mới.

### 18.4. Không mặc định các tool call là tuần tự hoặc transactional

Implementation hiện tại có thể thực thi nhiều call trong một bước bằng
`safe_gather`. Thứ tự model liệt kê không phải bảo đảm transaction.

Nếu bước sau bắt buộc chờ bước trước:

- Gộp phần phụ thuộc vào một tool/use case backend phù hợp; hoặc
- Thiết kế bước xử lý riêng và kiểm tra lại điều kiện ở backend.

Các thao tác ghi cần cơ chế chống ghi đè/lặp phù hợp với store của ứng dụng.

Nguồn: [Tools](../docs/tools.md),
[Tool contracts](../src/parlant/core/tools.py),
[Compass loop](../src/parlant/core/engines/compass/loop/base_loop.py).

## 19. Hooks phải chuyển theo lifecycle

Cấu hình cũ:

```python
configure_hooks=configure_profile_hooks
```

Mẫu đăng ký mới:

```python
import parlant.sdk as p


async def observe_message(
    context: p.EngineContext,
    message: str,
    exc: Exception | None,
) -> p.CompassHookResult:
    # Chèn quan sát hoặc kiểm tra riêng tại lifecycle này.
    return p.CompassHookResult.CALL_NEXT


async def initialize_container(container: p.Container) -> None:
    hooks = container[p.CompassHooks]
    hooks.on_message_generated.append(observe_message)
```

Các nhóm hook mới gồm:

- `on_step_started` / `on_step_completed`.
- `on_calling_tools` / `on_tool_calls_completed`.
- Trước/sau tool review và message review.
- `on_message_updated` khi stream.
- Trước/sau compaction.
- `on_giving_up`.
- Rule discovery/match handlers.

Các hook cũ như `on_preparation_iteration_end`, hook draft và hook journey
không có phép đổi tên một-một.

`CALL_NEXT`, `RESOLVE`, `BAIL` có ý nghĩa phụ thuộc điểm hook. Ví dụ
`RESOLVE` ở review có nghĩa chấp thuận, không có cùng tác dụng ở mọi stage.

Với demo cần xem riêng:

- `AUTO_HANDOFF.ensure_company_source`.
- `AUTO_HANDOFF.before_generation`.
- `HR.prepare_ai_response`.
- `HR.guard_ai_response`.
- `populate_profile_template_fields`.

Ví dụ kiểm tra kết quả tool có thể cần `on_tool_calls_completed`; chặn
phản hồi cần chọn đúng hook trước phát/gate review. Không chỉ đổi class
return type rồi giữ nguyên giả định thời điểm chạy.

Nguồn: [Hooks](../docs/hooks.md),
[CompassHooks](../src/parlant/core/engines/compass/hooks.py).

## 20. Model routing, provider và credentials

### 20.1. Từ NLPService sang routes

Cũ:

```python
p.Server(nlp_service=p.NLPServices.litellm)
```

Mới, ví dụ phân chia công việc:

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

Ví dụ cần credentials cho các provider tương ứng. Đây không phải cấu hình
Qwen/vLLM thay thế trực tiếp cho file cũ.

| Route | Công việc |
|---|---|
| `react` | Reasoning, tool calling, viết phản hồi |
| `indexing` | Chuẩn bị/chỉ mục rule |
| `matching.*` | Đánh giá rule |
| `review.tools` | Review tool |
| `review.message` | Review phản hồi |
| `compaction` | Nén lịch sử |
| `embedding.*` | Embedding rule, tool, glossary, canned response... |
| `moderation.customer` | Moderation đầu vào |
| `moderation.agent` | Moderation đầu ra |
| `tokenizer` | Ước lượng token |

`*` dùng tên provider fallback. Khi chọn một model cụ thể, dùng
`p.ModelConfig("provider:model")` trên route thích hợp.

Có thể:

- Cấu hình toàn server rồi override theo agent.
- Định tuyến theo effort.
- Cập nhật model route trong khi server chạy.
- Dùng callback custom provider cho từng capability.

Request đang chạy tiếp tục dùng model cũ; operation sau thấy cấu hình mới.

### 20.2. Provider tích hợp trực tiếp

Tập provider hiện tập trung vào:

- OpenAI.
- Gemini.
- Anthropic.
- OpenRouter.
- LiteLLM.

Nhiều adapter trực tiếp cũ bị gỡ: Emcie, AWS, Azure, Cerebras, DeepSeek,
GLM, Mistral, ModelScope, Novita, Ollama, Qwen, Snowflake, Together, Vertex,
Zhipu và các adapter liên quan khác.

Không suy ra rằng mọi model của các hãng này không dùng được. Có thể dùng
gateway/provider được hỗ trợ hoặc tự triển khai capability phù hợp; nhưng
import/cấu hình adapter cũ không còn tương thích nguyên trạng.

OpenAI/OpenRouter nằm trong base install; Gemini, Anthropic và LiteLLM có
extras tương ứng. Nhiều dependency torch/transformers cũ không còn trong
nhóm provider như trước.

Anthropic embedding mặc định được cung cấp qua Voyage AI; cần key phù hợp
hoặc route embedding sang provider khác.

### 20.3. Qwen/vLLM trong demo

Phải xác minh riêng:

1. Endpoint tự host.
2. Model cho reasoning/tool calling.
3. Các tác vụ trả JSON có cấu trúc.
4. Embedding.
5. Tokenizer.
6. Moderation nếu bật.

Tên model có thể được biểu đạt bằng dạng:

```python
p.ModelConfig("litellm:openai/Qwen/Qwen3-8B")
```

Nhưng tên route không tự cấu hình endpoint. Không sao chép nguyên các biến
`LITELLM_PROVIDER_*` cũ rồi mặc định adapter mới sử dụng chúng.

`ModelConfig.args` là cấu hình constructor được kiểm tra, không phải chỗ
truyền tùy ý mọi tham số request. Adapter LiteLLM hiện không công bố nhận
`api_base` qua args này.

### 20.4. Custom provider, secrets và rate limits

Custom provider mới nhận `EngineContext | None` và trả implementation cho
capability cụ thể, ví dụ ReactGenerator/Embedder/SchematicGenerator, thay
vì cấu hình cả NLPService cũ.

Callback được resolve trước từng operation; cần xử lý trường hợp
`context=None` cho công việc offline. Ứng dụng chịu trách nhiệm lifecycle
và concurrency của đối tượng tự cung cấp.

- `SecretRef` lưu tham chiếu secret.
- `SecretValue` giữ credential process-local.
- Chuỗi plaintext trong cấu hình bền vững có thể bị lưu; không coi string
  thường là secret tự động.
- Model rate limits có concurrency/RPM và shared bucket.
- Limiter mặc định là process-local, không tự thành quota toàn cluster.
- Rate limit model khác rate limit HTTP API.

Nguồn: [Providers và model routing](../docs/providers.md).

## 21. Storage và chuyển dữ liệu

| Thành phần | 3.3.2 SDK | 4.0 |
|---|---|---|
| Session mặc định | `transient` | `local` |
| Customer mặc định | `transient` | `local` |
| Explicit local store | JSON | SQLite |
| Context variable mặc định | `transient` | Vẫn `transient` |
| MongoDB/custom stores | Có | Vẫn có, cần xem layout/contract |
| S3 URL | Không có ở 3.3.2 | Được ghi nhận bổ sung trong changelog 4.0.2 |

Ví dụ tên file:

```text
sessions.json → sessions.db
customers.json → customers.db
```

`PARLANT_HOME` là thư mục dữ liệu nền; mặc định hiện là `./parlant-data`
nếu không cấu hình khác. Diagnostics/logs còn có biến đường dẫn riêng.

Hệ quả:

- Code trước đây không lưu session qua restart có thể bắt đầu lưu mặc định.
- JSON cũ không tự trở thành dữ liệu SQLite mới.
- MongoDB cần đối chiếu database/collection layout; không chỉ đổi version
  rồi mặc định trỏ URI cũ là xong.
- Không có bằng chứng về một importer tổng quát tự chuyển toàn bộ dữ liệu
  3.x sang 4.0.
- `migrate=True` là quyền cho phép migration schema store hỗ trợ, không
  đồng nghĩa với chuyển JSON→SQLite hoặc chuyển toàn bộ mô hình cũ.

Phải tách hai việc: chuyển code và export/map/import dữ liệu.

Đối với S3, storage cần conditional writes. Query tổng quát có thể scan
objects; không xem S3 như một database có indexed queries tương đương Mongo.

Nguồn: [Server và store factory](../src/parlant/sdk.py),
[changelog](../CHANGELOG.md).

## 22. HTTP API và CLI quản trị cũ

Các router quản lý cũ không còn được đăng ký như trước:

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

**Không có /policies CRUD để đổi tên endpoint một-một từ /guidelines.**

Agent được định nghĩa bằng code. Public Agent REST API hiện tập trung
list/get identity để chọn agent; CRUD tạo/sửa/xóa agent qua REST cũ đã thay đổi.

Runtime vẫn có các API như sessions, events, customers, groups, logs, health
và diagnostics, nhưng payload/auth phải được đối chiếu.

`parlant-client==3.3.1` không còn là dependency package như trước. Không
mặc định client API 3.x tương thích 4.0.

Nguồn: [API app](../src/parlant/api/app.py),
[Agent API](../src/parlant/api/agents.py).

## 23. Authentication, ownership và dữ liệu frontend

3.x đã có AuthorizationPolicy. 4.0 tích hợp rõ hơn chuỗi:

```text
Xác thực identity
→ kiểm tra quyền thao tác
→ rate limit
→ kiểm tra quyền đối với tài nguyên
```

Các principal:

- Anonymous.
- Guest.
- Customer.
- Admin.

Những thay đổi cần biết:

- Customer JWT do backend hoặc IdP của ứng dụng phát hành.
- Guest có token theo identity; không chỉ dùng một ID guest chung để phân
  biệt quyền truy cập.
- Customer/guest bị giới hạn theo ownership session mặc định.
- Không đơn giản tin `customer_id` do client gửi.
- Kết quả tool và reasoning nội bộ được lọc theo quyền.
- Frontend cần dùng metadata/public payload đúng thiết kế, không dựa vào
  việc đọc mọi raw tool result như admin.
- Sai/thiếu identity, thiếu quyền và rate limit có mã lỗi riêng.

**Development vẫn cho phép rộng.** Chỉ nâng version không tự biến server
thành deployment đã bật bảo vệ đầy đủ.

Production cần credentials phù hợp; thiếu admin key bắt buộc có thể fail
fast. Secret guest token không bền vững có thể làm token cũ không còn dùng
được sau restart.

Parlant xác minh token và quyền, không thay ứng dụng làm IdP.

Với demo, quyền HR xem hồ sơ ở `/hr` và quyền ứng viên ở `/chat` phải được
tích hợp với lớp auth của ứng dụng.

Nguồn: [Auth](../docs/auth.md), [Sessions](../docs/sessions.md).

## 24. Session, customer, variables và memory

### 24.1. Những khả năng đã có từ 3.x

- Session `auto`/`manual` và nền tảng human handoff.
- Session/event metadata.
- Labels và lan truyền labels từ các entity phù hợp.
- SSE và streaming.
- Customer metadata.
- Retriever và context variables.

Không gọi các khả năng này là hoàn toàn mới ở 4.0.

### 24.2. Những thay đổi đáng chú ý

- Customer `tags` chuyển sang `groups`.
- Có phân biệt customer thật và persona kiểm thử.
- Persona không phải identity customer được xác thực như customer thật.
- Có khả năng dùng CustomerStore kết nối customer database của ứng dụng,
  hoặc auto-provision theo cấu hình.
- Có scope giá trị context variable theo agent.

Thứ tự ưu tiên context variable:

```text
Customer → nhóm customer → agent → global
```

### 24.3. Session memory khác customer memory

| Loại | Có sẵn? | Nội dung |
|---|---|---|
| Session memory | Có | Lịch sử hội thoại và summary trong session |
| Customer memory qua nhiều session | Cần tích hợp store riêng | Sở thích, thông tin bền vững và lịch sử qua các cuộc trò chuyện |

Tài liệu memory hướng dẫn nối thêm hệ thống như CRM/kho nhớ của ứng dụng.
Không có nghĩa Parlant tự cung cấp đầy đủ một kho customer memory dài hạn.

### 24.4. Compaction

Compaction tự tóm tắt phần hội thoại cũ khi session dài:

- Summary được lưu vào event stream.
- Các prompt sau dùng summary và phần lịch sử mới.
- Chạy ở finalize sau phản hồi.
- Effort ảnh hưởng ngưỡng và chi tiết summary.
- Không thay thế hồ sơ nghiệp vụ trong database.

Không dùng summary hội thoại làm nguồn sự thật duy nhất để quyết định
hồ sơ đã lưu thành công hoặc quyền truy cập dữ liệu.

### 24.5. Handoff không tự tạo đội ngũ người nhận

Chuyển mode sang `manual` giúp bot ngừng trả lời. Việc HR thực sự nhận
thông báo, có hàng chờ, nhận phiên và trả lời vẫn cần tích hợp.

`DemoHR` và backend bàn giao của ứng dụng vì thế vẫn có vai trò.

Nguồn: [Customers](../docs/customers.md),
[Variables](../docs/variables.md), [Memory](../docs/memory.md),
[Compaction](../docs/compaction.md).

## 25. Usage, pricing, budgets và cost control

3.x đã ghi nhận một phần token usage trong inspection. 4.0 mở rộng thành
lớp accounting và điều khiển rõ hơn:

- Request count.
- Input/output/cached tokens.
- Theo model/provider.
- Chi phí theo trace/lượt và toàn session.
- Bảng giá tùy chỉnh.
- Chi phí provider báo.
- Chi phí do tool phát sinh.
- Budget theo session và cửa sổ thời gian.

`GET /sessions/{id}` có usage chi tiết; session listing không mang toàn bộ
usage history.

Chi phí chỉ có khi dữ liệu định giá đủ. Không lấy phần chưa định giá là
miễn phí hoặc mặc định tổng chi phí luôn đầy đủ.

Ví dụ:

```python
from decimal import Decimal

budget = await server.create_session_budget(
    name="conversation-cap",
    value=Decimal("1.50"),
)
```

**Tạo budget không tự chặn chi tiêu.** Phải gắn evaluator/callback/policy
để hành động khi vượt ngưỡng: dừng, chuyển HR hoặc hành vi khác.

Nếu không đủ pricing để đo, budget có thể báo `PricingConfigurationError`
thay vì âm thầm đếm thiếu.

Không mặc định budget là hard cap tuyệt đối trước từng request. Việc đo
và hành động theo budget, cùng lớp cost-control admission, cần được cấu
hình đúng thời điểm.

Nguồn: [Usage Reporting](../docs/usage-reports.md).

## 26. Diagnostics, health và logs

`/healthz` và OpenTelemetry đã có ở 3.x. 4.0 mở rộng:

- Engine health.
- NLP success/latency theo route.
- Event-loop health.
- Dashboard tunnel health.
- Diagnostic report theo trace.
- Trace/log/session/events liên quan.
- Pricing coverage.

Diagnostic reports bật mặc định. Có thể xuất ZIP phục vụ điều tra; thông
tin chi tiết bị giới hạn theo quyền.

`/healthz` có thể trả HTTP 200 dù body là degraded/unhealthy. Monitor cần
kiểm tra nội dung thay vì chỉ nhìn status code.

Log rotation, retention và đường dẫn report có cấu hình riêng. Diagnostics
cục bộ không yêu cầu phải có external OpenTelemetry collector.

Nguồn: [Diagnostics](../docs/diagnostics.md).

## 27. CLI, Dashboard, widget và phát triển ứng dụng

### 27.1. CLI mới

| Nhóm | Mục đích |
|---|---|
| `parlant init` | Tạo project/scaffold |
| `parlant docs query` | Hỏi tài liệu |
| `parlant widget init` | Copy source widget vào ứng dụng |
| `parlant dashboard ...` | Project, deploy, secrets, session, logs... |

Scaffold gồm `basic`, `retail-store` và `lead-gen`.

Executable `parlant-server` và `parlant-prepare-migration` cũ không còn
được đăng ký như trước. CLI `parlant` cũng không giữ nguyên bộ CRUD cũ.

`docs query` là dịch vụ hỏi tài liệu, không mặc định là tra cứu hoàn toàn
offline.

### 27.2. Dashboard và hosting

Tích hợp local/self-hosted và managed project:

- Kết nối bằng project token.
- Setup/check/confirm.
- Managed deployment từ GitHub.
- Build/deployment/runtime logs.
- Secrets.
- Session, trace và analytics.

Managed hosting là lựa chọn triển khai; framework vẫn có thể self-host.

### 27.3. Widget

3.x đã có integrated `/chat`. 4.0 có thêm widget chính thức:

- React và CSS đi kèm.
- Fetch/SSE transport.
- Floating/inline cùng các kiểu bố trí.
- Guest/customer auth.
- Suggestions và trạng thái kết nối.
- Tool widgets.
- Rich content.
- Source được copy vào ứng dụng để tùy chỉnh.

Không xem đây là việc cài npm runtime package rồi tự động nhận mọi nâng cấp.
Khi copy lại source cần đối chiếu các tùy chỉnh của ứng dụng.

### 27.4. File, ảnh và AG-UI

Parlant mang tham chiếu file/ảnh trong storage của ứng dụng, không tự trở
thành dịch vụ upload/lưu file.

Metadata tool có thể dùng cho frontend render dữ liệu có cấu trúc; không
đồng nghĩa model tự nhận nguyên file hoặc mọi metadata.

Tài liệu AG-UI hướng dẫn viết adapter chuyển event. Không có nghĩa có sẵn
một endpoint AG-UI hoàn chỉnh được bật tự động.

### 27.5. Preamble và progress

`PreambleConfiguration` có các lựa chọn như `default()`, `encourage()`,
`discourage()`.

- Default để model tự xử lý phần lời nói trước tool.
- Encourage hướng dẫn lời báo ngắn và điều tiết lặp lại.
- Discourage có kiểm soát runtime để không phát lời trước tool.
- Narration của tool mô tả công việc đang chạy cho UI.

Không coi preamble là một phản hồi cuối hoặc một sự xác nhận thao tác đã
thành công.

### 27.6. Hot reload

`Server(hot_reload=True)` mặc định theo dõi thay đổi Python và shutdown/
re-exec script. Không phải vá code trực tiếp trong process.

REPL/notebook có thể tự tắt watcher do không có file entrypoint phù hợp.
Đây cũng không phải cơ chế tự nhận mọi thay đổi `.env`/file dữ liệu.

Nguồn: [CLI](../docs/parlant-cli.md), [Widget](../widget/README.md),
[Rich Content](../docs/rich-content.md), [AG-UI](../docs/ag-ui.md),
[Preambles](../docs/preambles.md), [Hot Reload](../docs/hot-reload.md).

## 28. Phân biệt 4.0.0, các bản vá và Unreleased

| Mốc | Nội dung nổi bật |
|---|---|
| 4.0.0 | Compass, Rule/Policy/Observation, SOP thay Journey, SDK/model/API/auth/storage mới |
| 4.0.1 | Preamble ở scaffold lead-gen, narration cho scaffold tools, sửa tương thích Anthropic |
| 4.0.2 | S3 URL, WebMCP, avatar video, cải thiện mobile widget/setup Dashboard, sửa pagination/cancellation và các lỗi khác |
| 4.0.3 | Thông tin nhận diện lệnh CLI/invocation trên request Dashboard |
| 4.0.4 | `queue_response`, cải thiện xử lý mơ hồ/thông tin thiếu, reasoning stream trên Dashboard, sửa SDK Anthropic/RTL |

Các mục 4.0.2/4.0.4 phía trên được phân loại theo changelog phát hành; không
đồng nhất thời điểm công bố khả năng hoàn chỉnh với thời điểm mọi phần
adapter nội bộ đầu tiên được thêm vào lịch sử.

### 28.1. queue_response ở 4.0.4

`Agent.queue_response()` phối hợp phản hồi từ công việc nền, có thể gộp kết
quả sẵn sàng với lượt khách/kết quả khác. Có `after=coroutine` để đăng ký
công việc trước khi bắt đầu.

Giới hạn được ghi rõ:

- Điều phối trong một process.
- Cần routing affinity cho session.
- Công việc chờ không được phục hồi sau restart.

Không coi nó là durable job queue phân tán.

### 28.2. Unreleased trong checkout

Các mục hiện có:

- Structured MCP result được chuyển JSON thay vì báo nhầm tool call error.
- Cải thiện cạnh tranh/cache creation Gemini.
- Bỏ scan migration không cần thiết khi Mongo store đã đúng version.

Không báo những mục này là đã có trong tag 4.0.4.

Nguồn: [Changelog](../CHANGELOG.md).

## 29. Mẫu chuyển phần điều phối demo tuyển dụng

Các đoạn dưới minh họa chuyển phần SDK. Chúng dựa vào tool/data/module của
demo đã được chuyển context và contract sang 4.0.

Đây **không phải file standalone chạy ngay**, không bao gồm lại toàn bộ
`recruitment_demo_data`, `recruitment_demo_handoff`, `recruitment_demo_hr`
và `recruitment_demo_store`.

### 29.1. Ba policy chính

```python
import parlant.sdk as p


async def add_recruitment_policies(agent: p.Agent) -> None:
    await agent.create_policy(
        id=p.RuleId(f"{agent.id}-application"),
        title="Đăng ký ứng tuyển",
        content="""
Chỉ bắt đầu khi ứng viên yêu cầu đăng ký rõ ràng hoặc xác nhận muốn ứng
tuyển vị trí đang trao đổi. Hỏi JD, lương, ca hoặc phúc lợi không phải
đồng ý đăng ký.

Theo dõi và thực hiện các bước:
1. Xác định vị trí muốn ứng tuyển. Không hỏi lại mã đã chọn rõ, kể cả
   trong trao đổi với HR. Nếu mơ hồ, hỏi làm rõ trước khi thu thập hồ sơ.
2. Gọi search_jd_info. Nếu found=false, giải thích và đề nghị chọn vị trí
   đang mở trong phạm vi; không lưu cho vị trí không hợp lệ.
3. Gọi get_candidate_profile cho vị trí đang đăng ký. Không tự chuyển dữ
   liệu từ hồ sơ của vị trí khác.
4. Gọi update_candidate_field để lưu từng trường hợp lệ đã được cung cấp.
   Lưu job_id trước, rồi các trường khác. Giữ nguyên tên có dấu và một số
   điện thoại; không ghép số điện thoại với số giấy tờ.
   Lưu từng phần, không đợi đủ hồ sơ, không ghi lại dữ liệu không đổi.
5. Nếu saved=false, không nói đã lưu thay đổi. Nếu còn missing_fields,
   chỉ hỏi một trường còn thiếu mỗi lượt. Không hỏi lại trường đã lưu.
6. Chỉ nói hồ sơ đủ khi tool xác nhận. Đây là đăng ký quan tâm, chưa phải
   kết quả tuyển dụng. Không hứa trúng tuyển, xét duyệt hoặc HR liên hệ.

Chỉ bắt buộc full_name, phone, job_id. Các trường khác chỉ lưu khi ứng viên
tự cung cấp. Không yêu cầu CMND, CCCD, ảnh giấy tờ hoặc thông tin ngân hàng.
Nếu hỏi xen ngang, giải quyết câu hỏi rồi tiếp tục khi phù hợp.
Nếu hủy, dừng và giữ dữ liệu đã lưu. Nếu đã bàn giao HR, dừng thu thập.
""",
        tools=[
            search_jd_info,
            get_candidate_profile,
            update_candidate_field,
        ],
        trigger_message_review=True,
        trigger_tool_review=True,
    )

    await agent.create_policy(
        id=p.RuleId(f"{agent.id}-recruitment-information"),
        title="Tra cứu thông tin tuyển dụng",
        content="""
Khi tìm việc, gọi job_list hoặc recommend_jobs theo yêu cầu.
Chỉ giới thiệu vị trí từ tool, tối đa 5 vị trí khi gợi ý.
Khi hỏi lương, ca hoặc yêu cầu công việc, gọi search_jd_info.
Khi hỏi doanh nghiệp, phúc lợi hoặc thiết bị, gọi search_company_info.
Khi hỏi chính sách/thủ tục, tra nguồn liên quan và search_knowledge.
Nếu chưa rõ vị trí, hỏi lại trước.

Chỉ trả lời phần được nguồn xác nhận. 'Cấp máy tính' không xác nhận
'cấp MacBook'. Sau khi tra đúng nguồn mà vẫn thiếu chi tiết trong phạm
vi, gọi trigger_handoff với reason_code='missing_information'.
Không bắt ứng viên chủ động xin gặp HR. Có thể dùng câu trả lời HR đã
xác nhận trong chính session, không tự biến thành FAQ chung.

Danh sách rỗng, job đóng hoặc chưa có hồ sơ không tự là lý do bàn giao.
Job ngoài quyền cần hướng dẫn chọn trợ lý phù hợp.
Hỏi thông tin không có nghĩa đồng ý đăng ký; chưa tự yêu cầu hồ sơ.
""",
        tools=[
            job_list,
            recommend_jobs,
            search_jd_info,
            search_company_info,
            search_knowledge,
            trigger_handoff,
        ],
        trigger_message_review=True,
    )

    await agent.create_policy(
        id=p.RuleId(f"{agent.id}-human-handoff"),
        title="Bàn giao chuyên viên tuyển dụng",
        content="""
Khi ứng viên yêu cầu người thật/HR, gọi trigger_handoff với
reason_code='candidate_request'.

Nếu tool trả waiting_for_hr, backend đã thông báo và dừng AI:
không gửi thêm xác nhận, không hỏi đăng ký hoặc thu thập tiếp.
Nếu handoff_failed, nói chưa chuyển được; không nói đã bàn giao.

Nếu lookup_failed, không gọi lại tool tra cứu trong lượt đó.
Làm theo trạng thái bàn giao backend trả về.
Không tự gán lookup_error; lỗi này do backend xác định.
""",
        tools=[trigger_handoff],
        trigger_message_review=True,
    )
```

Đây là ba policy minh họa để thể hiện cách tổ chức. Chưa bao gồm mọi hành vi
trong file cũ, như xem/sửa hồ sơ, ghi chú HR và đồng bộ CRM. Khi chuyển thật,
phải đối chiếu toàn bộ yêu cầu cũ thay vì coi đoạn mẫu đã bảo toàn mọi hành vi.

### 29.2. Tạo agent

Ví dụ dùng lại `RecruitmentData` của demo:

```python
async def create_demo_agent(
    server: p.Server,
    data: RecruitmentData,
) -> p.Agent:
    config = data.agent

    if config["id"] != data.agent_id:
        raise ValueError(
            "Configured agent id must match the selected recruitment agent."
        )

    agent = await server.create_agent(
        id=config["id"],
        name=config["name"],
        instructions=(
            f"{config['description']}\n"
            "Tư vấn tuyển dụng bằng tiếng Việt, ngắn gọn và lịch sự. "
            "Chỉ dùng dữ liệu được cấp cho agent hiện tại. "
            "Không yêu cầu CMND, CCCD, ảnh giấy tờ hoặc thông tin ngân hàng. "
            "Không nhắc lại giá trị nhạy cảm ứng viên gửi. "
            "Chỉ xác nhận thao tác theo kết quả tool."
        ),
        output_mode=p.OutputMode.BLOCK,
        max_steps=15,
        effort=p.Effort.MEDIUM,
        message_review=True,
        tool_review=True,
    )

    await add_domain_glossary(agent, data.agent_id)
    await add_recruitment_policies(agent)
    return agent
```

BLOCK được chọn tường minh cho ví dụ có kiểm soát đầu ra; không phải bắt
buộc dùng BLOCK mới có message review, vì message review đang hoạt động
cũng buffer phản hồi của stream agent. Moderation đầu ra có giới hạn riêng
đã nêu ở mục 15.

### 29.3. Giữ kiểm tra nghiệp vụ trong tool

Giữ lại và chuyển API cần thiết cho:

- `check_agent` và phạm vi job/knowledge.
- Validation tên/điện thoại và field cho phép.
- Đối chiếu giá trị với lời ứng viên thật, không chỉ tin tham số model.
- Phân biệt ứng viên tham khảo với đồng ý tạo hồ sơ.
- Lưu từng phần và giữ trường chưa thay đổi.
- Không coi CRM sync lỗi là hồ sơ chưa được lưu nếu commit đã thành công.
- Xác minh bằng chứng lookup trong lượt hiện tại trước handoff.
- Chặn AI sau khi HR nhận phiên.

Không thay các kiểm tra này bằng một câu trong policy.

## 30. Mức ảnh hưởng tới các phần của demo

| Thành phần | Hướng chuyển | Mức ảnh hưởng |
|---|---|---|
| ProfilePatch, validation điện thoại | Giữ phần lớn | Thấp |
| RecruitmentData/JsonStore nghiệp vụ | Giữ, đối chiếu contract và concurrency | Thấp–vừa |
| Tool tra cứu/lưu | Giữ nghiệp vụ, sửa context và kết quả cần thiết | Vừa |
| create_guideline | Policy hoặc Observation | Vừa |
| create_application_journey | SOP hoàn chỉnh | Cao |
| Template STRICT | Thiết kế bảo toàn dữ liệu/câu chữ | Cao |
| evidence_ready | Evaluation function/context mới | Cao |
| Hook kiểm tra nguồn và chặn AI | Lifecycle Compass | Cao |
| ToolContextAccessor | .current phù hợp | Thấp |
| LiteLLM/Qwen/vLLM | Cấu hình route/endpoint/capability | Vừa–cao |
| Dữ liệu session/customer cũ | Export/map/import riêng | Cao |
| /chat và /hr tùy chỉnh | Auth, event, streaming và quyền dữ liệu | Vừa–cao |

## 31. Checklist kiểm tra hành vi khi chuyển thật

Đây là danh mục tình huống cần xác minh, không phải các test đã được viết
hoặc chạy trong quá trình tạo ghi chú.

### 31.1. Ý định và thu thập dữ liệu

- [ ] Hỏi JD/lương/thiết bị không bị coi là đăng ký.
- [ ] Ý định mơ hồ được hỏi làm rõ trước khi thu thập.
- [ ] Ý định đã rõ không bị hỏi xác nhận lại vô ích.
- [ ] Job đã chọn rõ, kể cả với HR, không bị hỏi lại mã.
- [ ] Chỉ bắt buộc full_name, phone, job_id.
- [ ] Không yêu cầu giấy tờ/thông tin ngân hàng.
- [ ] Lưu từng phần, không đợi đủ mọi trường.
- [ ] Mỗi lượt chỉ chủ động hỏi một trường còn thiếu.

### 31.2. Ghi dữ liệu và phản hồi

- [ ] Giữ nguyên tên có dấu.
- [ ] Không ghép điện thoại với số giấy tờ.
- [ ] Không suy đoán giá trị chưa được cung cấp.
- [ ] Tool từ chối thì không xác nhận đã lưu.
- [ ] Hồ sơ chưa đủ thì không nói đã đủ.
- [ ] Không tự chuyển dữ liệu từ job cũ.
- [ ] Ghi thành công nhưng CRM lỗi vẫn phản ánh đúng hai trạng thái.
- [ ] Nhiều tool call không làm ghi đè/lặp dữ liệu ngoài ý muốn.
- [ ] Đạt max_steps không bị hiểu nhầm là rollback dữ liệu.

### 31.3. Tra cứu và handoff

- [ ] Thiết bị chung không được suy ra thành model thiết bị cụ thể.
- [ ] Đã tra đúng nguồn mà thiếu chi tiết thì bàn giao theo yêu cầu.
- [ ] Có bằng chứng lookup ở lượt hiện tại trước missing_information.
- [ ] Job đóng/danh sách rỗng/ngoài phạm vi được phân biệt với thiếu nguồn.
- [ ] Backend xác định lookup_error, model không tự gán.
- [ ] Handoff thất bại không bị thông báo là thành công.
- [ ] Sau bàn giao, AI không tiếp tục thu thập hoặc gửi xác nhận trùng.
- [ ] HR trả phiên thì agent dùng thông tin HR trong chính session.
- [ ] Không tự biến câu HR thành FAQ chung.

### 31.4. Hội thoại và vận hành

- [ ] Hỏi xen ngang được xử lý và đăng ký tiếp tục phù hợp.
- [ ] Hủy đăng ký thì dừng thao tác tiếp theo.
- [ ] Tin nhắn mới khi engine đang xử lý không dẫn tới thao tác lỗi thời.
- [ ] Review bật đúng, effort không vô tình đặt MIN.
- [ ] Hook chọn đúng stage và return semantics.
- [ ] Client xử lý đúng output mode và SSE.
- [ ] Customer/guest không đọc được hồ sơ/session của người khác.
- [ ] Dữ liệu cũ được kiểm tra sau export/map/import.
- [ ] Rule thay đổi có hiệu lực discovery sau restart/training phù hợp.

Nếu triển khai test trong repo, tuân thủ quy trình xác nhận kế hoạch và TDD
trong AGENTS.md; engine/SDK test dùng SDKTest và phong cách classical testing.

## 32. Những cách hiểu cần tránh

| Cách hiểu | Chính xác hơn |
|---|---|
| Policy chỉ là guideline đổi tên | Policy bao quát cả quy tắc và quy trình; matching/engine đổi |
| Policy giữ nguyên đồ thị journey | SOP được diễn giải từ nội dung và ngữ cảnh |
| Journey cũ là FSM cứng | Journey cũng dùng model và cho phép linh hoạt theo hội thoại |
| Rule là một object phải tạo trước Policy | Policy và Observation tự là các loại Rule |
| SOP là class mới | SOP là cách viết quy trình |
| Policy chạy một lần ở đầu | Hướng dẫn chi phối cả lượt và các bước sau |
| Alpha không có feedback loop | Alpha đã xét lại dựa trên tool result |
| Chỉ Compass mới gọi nhiều tool | Alpha đã có; cách tổ chức vòng thay đổi |
| Một iteration/step bằng một tool | Không đúng |
| max_steps là tổng số request LLM | Không đúng |
| Tăng max_steps sẽ sửa quy trình sai | Chỉ tăng khoảng xử lý |
| Review bằng STRICT cũ | Không tương đương contract đầu ra |
| Có review thì bỏ validation | Validation backend vẫn bắt buộc |
| Có auth mới là deployment tự an toàn | Development vẫn cho phép rộng nếu chưa cấu hình |
| Có budget là tự hard-cap mọi request | Phải gắn hành động/điểm kiểm soát thích hợp |
| migrate=True chuyển toàn bộ 3.x | Chỉ migration mà store hỗ trợ; cần kế hoạch chuyển dữ liệu |
| Có memory docs là có customer memory store | Kho nhớ qua session vẫn cần tích hợp |
| Manual mode tự đưa người thật vào chat | Cần hệ thống người nhận/hàng chờ/thông báo |
| Tất cả feature liệt kê đều mới 4.0 | Nhiều khả năng cũ được giữ và thiết kế lại |

## 33. Tài liệu và mã nguồn tham chiếu

Các liên kết dưới trỏ tới nguồn tiếng Anh và mã nguồn cùng repo để ghi chú
có thể dùng độc lập với các bản dịch đang nằm trong workspace:

- [Changelog hiện tại](../CHANGELOG.md).
- [SDK công khai](../src/parlant/sdk.py).
- [Policy Design](../docs/policy-design.md).
- [Rule Discovery](../docs/rule-discovery.md).
- [Matching nội bộ](../docs/internal/matching.md).
- [Adaptive Effort](../docs/adaptive-effort.md).
- [Tool và Message Review](../docs/review.md).
- [Canned Responses](../docs/canned-responses.md).
- [Tools](../docs/tools.md).
- [Tool contracts](../src/parlant/core/tools.py).
- [Compass engine](../src/parlant/core/engines/compass/engine.py).
- [Compass loop](../src/parlant/core/engines/compass/loop/base_loop.py).
- [Hooks](../docs/hooks.md).
- [CompassHooks](../src/parlant/core/engines/compass/hooks.py).
- [Providers](../docs/providers.md).
- [Auth](../docs/auth.md).
- [API app](../src/parlant/api/app.py).
- [Agent API](../src/parlant/api/agents.py).
- [Sessions](../docs/sessions.md).
- [Customers](../docs/customers.md).
- [Variables](../docs/variables.md).
- [Retrievers](../docs/retrievers.md).
- [Memory](../docs/memory.md).
- [Compaction](../docs/compaction.md).
- [Usage Reporting](../docs/usage-reports.md).
- [Diagnostics](../docs/diagnostics.md).
- [Moderation](../docs/moderation.md).
- [CLI](../docs/parlant-cli.md).
- [Widget](../widget/README.md).
- [Rich Content](../docs/rich-content.md).
- [AG-UI](../docs/ag-ui.md).
- [Preambles](../docs/preambles.md).
- [Hot Reload](../docs/hot-reload.md).

Đối chiếu Alpha và SDK cũ bằng Git:

```bash
git show v3.3.2:src/parlant/core/engines/alpha/engine.py
git show v3.3.2:src/parlant/sdk.py
git show v3.3.2:src/parlant/core/tools.py
git show v3.3.2:src/parlant/api/app.py
git show v3.3.2:docs/concepts/customization/journeys.md
```

Những ghi chú về mặc định, giới hạn và implementation phản ánh các mốc đã
đối chiếu. Khi nâng qua một phiên bản khác, đọc lại changelog và code tương
ứng thay vì coi mọi chi tiết nội bộ ở đây là contract bất biến.
