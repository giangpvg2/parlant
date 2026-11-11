# Khám Phá Rule (Rule Discovery)

Parlant đưa ra hai quyết định rất khác nhau đối với từng rule (quy tắc), và việc phân biệt rạch ròi giữa chúng là cực kỳ quan trọng:

- **Đánh giá lượt tương tác (Turn evaluation)** trả lời câu hỏi: *Rule này có áp dụng cho lượt hiện tại hay không?* Phán quyết này có tính ngắn hạn. Parlant đánh giá lại nó ở mọi lượt.
- **Khám phá (Discovery)** trả lời câu hỏi: *Cuộc trò chuyện đã làm cho rule này trở nên liên quan đến phiên hội thoại hay chưa?* Phán quyết này có tính lưu giữ lâu dài (sticky). Một rule được khám phá sẽ gia nhập vào tập làm việc (working set) của phiên và nằm ở đó cho đến khi bị cắt tỉa (pruned).

Tài liệu này giải thích về cơ chế discovery: cách nó hoạt động, cách các bộ phân loại (classifiers) đằng sau nó được huấn luyện và huấn luyện lại, cũng như cách định hướng nó bằng các tín hiệu tùy chỉnh (custom signals).

Luồng dữ liệu tổng thể:

```text
Danh mục Rule (nội dung + signals + anti-signals)
  -> Huấn luyện (theo từng agent, offline)
  -> Bộ phân loại theo từng rule
  -> Gợi nhớ (recall) tại thời điểm lượt chạy (embed cuộc trò chuyện, chấm điểm từng rule)
  -> Tập làm việc của session (working set)
  -> Chỉ dẫn của Responder
```

## Các thuật ngữ chính

| Thuật ngữ | Ý nghĩa |
|---|---|
| **Discovery** | Quyết định rằng một rule có tính liên quan liên tục đối với session. Một rule được khám phá sẽ được nạp vào tập làm việc của session. |
| **Recall** | Cơ chế dựa trên embedding thực hiện quá trình discovery. Hoàn toàn không gọi LLM. Recall là phép tính tích vô hướng (dot product) đối chiếu với các bộ phân loại đã được huấn luyện. |
| **Session working set** | Tập hợp các rule đã được nạp vào session cho đến nay. Parlant đưa chúng vào chỉ dẫn của agent ở mọi lượt, kèm theo chú thích: "có thể liên quan hoặc không liên quan ngay lúc này — hãy dùng phán đoán của bạn." |
| **Signal** | Một đoạn văn bản ngắn trên một rule thể hiện cách mà cuộc trò chuyện có thể kích hoạt nó, thường là một câu nói của khách hàng. Signal là các mẫu dương tính (positive examples) của bộ phân loại. |
| **Anti-signal** | Một trường hợp suýt soát (near-miss): một câu văn bản *trông giống* một kích hoạt nhưng tuyệt đối không được làm kích hoạt rule. Anti-signal là các mẫu âm tính (negative examples) của bộ phân loại. |
| **Pin** | Một signal có tiền tố `[__pin__]`. Nó huấn luyện bộ phân loại như mọi signal khác, đồng thời đóng vai trò như một cơ chế ghi đè bắt buộc kích hoạt: một tin nhắn khách hàng rất gần với câu pin sẽ tự động gợi nhớ rule bất kể bộ phân loại kết luận ra sao. |
| **Frame** | Toàn bộ tập hợp các bộ phân loại theo rule đã được huấn luyện của một agent. Frame chỉ áp dụng riêng cho từng agent và không bao giờ chia sẻ. Bộ phân loại của một rule chỉ có ý nghĩa tương đối trong danh mục của chính agent đó. |
| **Training** | Bước chạy ngoại tuyến (offline) sinh ra từng bộ phân loại từ danh mục hiện tại. An toàn để chạy lại bất cứ lúc nào; huấn luyện lại một danh mục không đổi sẽ không làm thay đổi kết quả. |
| **Pruning** | Bước xử lý sau phản hồi nhằm giới hạn quy mô tập làm việc của session. Nó loại bỏ các thành viên không còn liên quan đến hướng đi tiếp theo của cuộc trò chuyện. |

## Những Rule nào đi qua Discovery

Dưới góc nhìn của hệ thống, mọi rule rơi vào một trong ba nhóm:

- **Luôn luôn được render, không bao giờ cần discovery.** Hai loại rule đơn giản là luôn có mặt trong chỉ dẫn của agent:
  - **Rule có trọng số LOW** — với một ngoại lệ: một rule LOW làm tăng mức effort, làm điều kiện tiên quyết cho một rule phụ thuộc, hoặc nằm trong mối quan hệ ưu tiên (priority) thì cần có phán quyết thực tế theo từng lượt, do đó Parlant khớp nó như bất kỳ rule nào khác.
  - **Rule mà điều kiện của nó tham chiếu đến các policy khác của agent** (ví dụ: "bất cứ điều gì không được xử lý bởi policy khác") và không mang tool hay handler nào. Recall bằng embedding không thể phán đoán điều kiện như vậy, nên Parlant đưa rule này vào tĩnh.
- **Rule được đánh giá bằng code.** Một rule có `evaluation_func=` tùy chỉnh (một hàm Python) được phán đoán bằng code của bạn và không bao giờ đi qua discovery. Nó cũng không nhận các đề xuất signal: signal sinh ra cho embedding recall, và các rule này không sử dụng embedding recall.
- **Tất cả các rule còn lại đều qua discovery.** Bất cứ khi nào một rule như vậy chưa nằm trong session working set, recall sẽ chấm điểm nó dựa trên cuộc hội thoại.

Discovery không phải là toàn bộ câu chuyện đối với các rule có mức độ rủi ro cao. Bất kỳ rule nào mà kết quả khớp gây ra các hệ quả cơ chế — cung cấp tool, kích hoạt review, chạy handler `on_matched`, gắn nhãn label, có dependent, có quan hệ priority hoặc nâng mức effort — đều nhận thêm một phán quyết LLM thực sự cho lượt hiện tại. Đó là khâu đánh giá lượt tương tác (turn evaluation). Nó chạy song song cùng discovery, chứ không thay thế discovery.

Hai lối tắt hữu ích khi debug:

- **Danh mục nhỏ sẽ bỏ qua recall:** Nếu agent có từ 5 rule khả dụng trở xuống, toàn bộ danh mục vốn đã nằm gọn trong chỉ dẫn của agent. Các rule thông thường sẽ được nạp trực tiếp mà không cần embed. Các rule cần phán quyết LLM vẫn giữ nguyên quy trình đầy đủ.
- **Các rule đã được nạp sẽ bỏ qua recall:** Discovery chỉ đánh giá các rule chưa nằm trong working set, vì vậy chi phí recall sẽ giảm dần khi phiên hội thoại diễn ra lâu hơn.

### Khám phá (Discovered) không đồng nghĩa với Khớp (Matched)

Discovery đưa một rule ra trước mặt agent cùng lời nhắc "hãy dùng phán đoán của bạn". Nó không tuyên bố rằng rule đó đang áp dụng ngay lúc này. Những hệ quả phụ thuộc vào việc *khớp (match)* — chạy handler `on_matched`, gắn label của rule — đòi hỏi một phán quyết khớp lượt thực sự, điều mà riêng discovery không bao giờ sinh ra. `on_discovered` (bên dưới) là sự kiện kích hoạt từ chính discovery.

Một rào cản nạp dữ liệu nữa: **Sự phụ thuộc (Dependencies)**. Một rule được tạo với `depend_on(...)` chỉ gia nhập working set sau khi rule phụ thuộc của nó đã thực sự khớp trong một lượt của session này. Cho đến lúc đó, rule có thể đạt điểm Relevant trong mọi đợt discovery nhưng vẫn bị giữ lại bên ngoài. Một phán quyết discovery mới sẽ được đánh giá ở mỗi lượt, đảm bảo rule bước vào ngay thời điểm dependency của nó được khớp.

Một rule có nhiều dependency sẽ phải đợi tất cả được thỏa mãn, trừ khi chúng được khai báo với `depend_on_any`, khi đó chỉ cần một dependency là đủ.

## Cơ chế hoạt động của Recall

Hiểu rõ cơ chế ở cấp độ này là đủ để bạn dự đoán điều gì sẽ hoặc không được gợi nhớ, và lý do tại sao.

### Quá trình huấn luyện (Training)

Với mỗi rule, quá trình huấn luyện xây dựng một bộ phân loại tuyến tính nhỏ tách biệt các *kích hoạt (triggers)* của rule đó khỏi các *trường hợp suýt soát (near-misses)*:

- **Các mẫu dương tính (positive examples)** là các signal của rule, bao gồm cả các pin. Nếu một rule thiếu cả signal lẫn anti-signal, chính văn bản nội dung của nó (tiêu đề, "When *condition*, then *action*", content) sẽ cùng tham gia vào tập dương tính.
- **Các mẫu âm tính (negative examples)** là các anti-signal của rule. Nếu không có, Parlant sẽ lấy mẫu từ văn bản của *các rule khác*, giúp bộ phân loại ít nhất học được điểm khác biệt giữa rule này với phần còn lại của danh mục.

Lưu ý hệ quả quan trọng: Đối với một rule điển hình có đầy đủ cả signal và anti-signal, **bộ phân loại được huấn luyện dựa trên các signal của bạn đối chiếu với các anti-signal của bạn. Bản thân văn bản điều kiện (condition) của rule không phải là đầu vào huấn luyện.** Chất lượng recall của một rule chính là chất lượng của các signal của nó.

Tất cả văn bản được embed một lần và lưu cache, do đó việc huấn luyện lại một danh mục không đổi diễn ra rất nhanh và rẻ.

### Chấm điểm tại thời điểm lượt chạy (Scoring at turn time)

Tại thời điểm khớp, Parlant embed một tập hợp các *truy vấn (queries)* bắt nguồn từ cuộc trò chuyện:

- một truy vấn tích lũy — toàn bộ cuộc trò chuyện cho đến nay, có gắn tiền tố là bản tóm tắt phiên nếu phiên đã được nén — và
- một truy vấn cho mỗi tin nhắn riêng lẻ của khách hàng.

Bộ phân loại của từng rule ứng viên sẽ chấm điểm trên mọi truy vấn, và rule sẽ lấy điểm **cao nhất (maximum score)** trong số đó. Rule được khám phá (discovered) khi điểm cao nhất đó vượt qua ngưỡng biên của bộ phân loại.

Cơ chế lấy điểm cực đại (max-pooling) giúp recall quan sát toàn bộ cuộc trò chuyện thay vì chỉ nhìn vào tin nhắn mới nhất: một rule có kích hoạt xuất hiện từ trước đó vẫn tiếp tục ghi điểm dựa trên tin nhắn cũ đó, nhờ vậy nó vẫn có thể được khám phá sau đó vài lượt.

Việc duy trì trong cuộc chơi là câu chuyện khác. Một khi rule đã được khám phá, Parlant ghi nhận nó vào working set của session và ngừng chấm điểm nó — đó là điều làm cho discovery mang tính *lưu giữ lâu dài (sticky)* qua các lượt. Xem phần [Tính lưu giữ, cắt tỉa và nạp lại](#tính-lưu-giữ-cắt-tỉa-và-nạp-lại).

Điểm số bạn thấy trong log được nén về khoảng `[0, 1]`, với mốc `0.5` là ranh giới: trên 0.5 là rule được khám phá, dưới 0.5 là không.

### Các ghim (Pins)

Một signal bắt đầu bằng `[__pin__]` mang hai nhiệm vụ: Nó huấn luyện bộ phân loại như bất kỳ signal nào khác. Bên cạnh đó, Parlant giữ văn bản pin như một tham chiếu thô: nếu bất kỳ tin nhắn nào của khách hàng *rất gần* với nó (độ tương đồng cosine trên 0.9), rule sẽ được gợi nhớ bất kể bộ phân loại phán quyết ra sao.

Hãy dùng pin cho những câu nói tuyệt đối không được phép bỏ sót. Lưu ý rằng cơ chế ghi đè này rất nghiêm ngặt: cosine 0.9 đòi hỏi khách hàng gần như phải nói chính xác từng chữ của văn bản pin, chứ không chỉ là nói về cùng một chủ đề. Đối với độ bao phủ rộng hơn, pin vẫn đóng vai trò là một signal thông thường — và việc có thêm nhiều signal riêng biệt sẽ hữu ích hơn.

Pin luôn do bạn tự viết tay; tính năng tự động đề xuất signal không bao giờ sinh ra pin.

### Tính lưu giữ, cắt tỉa và nạp lại (Stickiness, pruning, and readmission)

Các rule được khám phá sẽ tích lũy dần. Để giữ cho chỉ dẫn luôn gọn gàng, Parlant giới hạn dung lượng working set: khi vượt quá 30 thành viên, một bước cắt tỉa (pruning) sau phản hồi sẽ đánh giá thành viên nào còn liên quan đến hướng đi của cuộc trò chuyện, và loại bỏ các thành viên ít liên quan nhất xuống còn 20. Các thành viên có trọng số HIGH và các rule được khớp trong lượt hiện tại không bao giờ bị loại bỏ, và pruning chỉ chạy tối đa một lần sau mỗi 10 tin nhắn khách hàng.

Một rule bị loại bỏ không phải là biến mất vĩnh viễn, nhưng Parlant sẽ ghi nhớ lần loại bỏ đó. Chỉ những nội dung trò chuyện xuất hiện **sau** thời điểm bị loại bỏ mới có thể nạp lại rule đó. Tin nhắn khách hàng ban đầu từng kích hoạt nó không còn quyền đưa nó trở lại nữa. Nếu không có cơ chế này, tính năng sticky max-pool sẽ lập tức nạp lại mọi rule vừa bị loại bỏ dựa trên kích hoạt cũ của chúng, và việc cắt tỉa sẽ hoàn toàn vô nghĩa. Một kích hoạt mới mẻ sẽ nạp lại rule ngay lập tức.

## Huấn luyện và Huấn luyện lại (Training and Retraining)

Bộ phân loại của một rule chỉ có ý nghĩa tương đối với toàn bộ danh mục: các rule khác cung cấp mẫu âm tính, và không gian embedding được căn giữa dựa trên giá trị trung bình của danh mục. Do đó, bất kỳ thay đổi nào đối với danh mục — thêm, sửa, xóa rule hoặc signal — đều cần phải huấn luyện lại. Việc huấn luyện diễn ra offline, theo từng agent, an toàn để chạy lại và không chạm vào LLM.

### Khi nào quá trình huấn luyện diễn ra

Parlant tự động huấn luyện mọi agent trong lúc khởi động server (thanh tiến trình "Training classifiers"). Các rule được định nghĩa trong code, vì vậy thay đổi chúng đồng nghĩa với việc khởi động lại server — và việc khởi động lại sẽ huấn luyện lại tất cả. Khi bật hot reload (xem [Hot Reload](hot-reload.md)), việc lưu file sẽ tự động khởi động lại và huấn luyện lại giúp bạn.

Các bộ phân loại đã huấn luyện nằm trong bộ nhớ RAM, không lưu trên đĩa. Sau khi khởi động lại server, bước huấn luyện lúc startup sẽ tái tạo lại chúng.

### Các Rule được tạo sau khi khởi động

Nếu code của bạn tạo hoặc sửa rule trong khi server đang chạy sẵn, recall vẫn tiếp tục hoạt động chứ không báo lỗi, nhưng có hai trường hợp hành xử khác nhau:

- **Một rule mới** (một id mà frame đã huấn luyện chưa bao hàm) sẽ khiến Parlant huấn luyện một frame dự phòng cho batch tại thời điểm khớp. Đúng đắn nhưng sẽ chậm hơn ở lần dùng đầu tiên, và cache dự phòng khá nhỏ.
- **Một rule được chỉnh sửa** (một id có sẵn bị thay đổi signal hoặc nội dung) là trường hợp nguy hiểm: frame đã huấn luyện vẫn *bao hàm* id đó, vì vậy recall sẽ tiếp tục sử dụng bộ phân loại **cũ**. Các chỉnh sửa của bạn sẽ âm thầm không có hiệu lực đối với discovery cho đến lần khởi động lại tiếp theo.

Cả hai trường hợp đều được giải quyết triệt để khi khởi động lại server.

## Quản lý các Custom Signals

### Nguồn gốc của Signals

> **Tránh nhầm lẫn với** `signals` của câu trả lời soạn sẵn ([Canned Responses](canned-responses.md)). Đó là các cách diễn đạt truy xuất thay thế để hiển thị một tin nhắn mẫu — không liên quan đến huấn luyện hay anti-signals. Rule signals ở đây là dữ liệu huấn luyện cho bộ phân loại discovery, đi kèm với `anti_signals`, và có hiệu lực khi huấn luyện lại.

Cả `signals` và `anti_signals` đều là danh sách các chuỗi ký tự trên một rule:

```python
await agent.create_policy(
    content=(
        "When the customer reports a product defect within the warranty "
        "period, open a warranty claim and give them the claim number"
    ),
    signals=[
        "My blender stopped working after a month",
        "This arrived broken — can I get it repaired?",
        "[__pin__] I want to file a warranty claim",
    ],
    anti_signals=[
        "What does the warranty cover?",       # hỏi về điều khoản, không phải khiếu nại bảo hành
        "How long is the warranty period?",
    ],
)
```

Đối với mọi rule sử dụng evaluator mặc định, Parlant cũng tự động **đề xuất** các signal khi khởi động: một LLM sẽ sinh ra 10 signal và 10 anti-signal từ nội dung của rule, và chúng được gộp vào rule — các mục do bạn viết đứng trước, các mục sinh tự động nối tiếp sau, loại bỏ trùng lặp không phân biệt hoa thường. Các signal bạn tự viết không bao giờ bị xóa hay viết lại. Kết quả đề xuất được cache lại, nên chỉ tốn chi phí gọi LLM khi nội dung rule thay đổi.

Điều này đồng nghĩa một rule thông thường đã có sẵn một tập huấn luyện vững chắc mà bạn không cần tốn công sức. Hãy thêm custom signals khi bạn có những tri thức thực tế mà bộ sinh tự động thiếu — chính là những câu từ mà khách hàng thực tế của bạn sử dụng.

### Những lưu ý đối với Custom Signals

- **Viết signal như những câu nói thực tế của khách hàng:** Truy vấn được tạo từ tin nhắn hội thoại. Một signal được diễn đạt theo cách khách hàng thực sự nói ("máy xay của tôi bị hỏng sau một tháng") sẽ nằm gần hơn trong không gian embedding so với một mô tả trừu tượng ("kịch bản lỗi sản phẩm").
- **Anti-signal dành cho các trường hợp suýt soát, không phải các câu đối lập hoàn toàn:** Bộ phân loại học *ranh giới* giữa signal và anti-signal. Câu "Chính sách bảo hành bao gồm những gì?" là một anti-signal rất hữu ích cho rule khiếu nại bảo hành vì nó ở rất gần (cùng mang sắc thái bảo hành) nhưng không được phép kích hoạt rule. Một câu nói vu vơ lạc đề không dạy thêm điều gì cho bộ phân loại.
- **Một rule bị gợi nhớ quá mức (over-recalled) cần thêm anti-signals, chứ không phải bớt signals:** Hãy lấy chính các tin nhắn kích hoạt nhầm và thêm chúng (hoặc các câu tương tự) làm anti-signals, sau đó huấn luyện lại.
- **Một rule bị gợi nhớ quá ít (under-recalled) cần các signal đa dạng hơn:** Hãy bao quát các cách diễn đạt khác nhau có thể kích hoạt nó; 10 câu nói tương tự nhau có giá trị ít hơn nhiều so với 5 câu kích hoạt hoàn toàn khác biệt về ngữ cảnh.
- **Signal chỉ cạnh tranh trong phạm vi một agent:** Cùng một rule gắn vào hai agent khác nhau sẽ được huấn luyện với hai danh mục khác nhau và có thể hành xử khác nhau. Đó là chủ ý thiết kế.
- **Observation cũng nhận signals:** Observation cũng là rule và được khám phá theo cách hoàn toàn tương tự; `create_observation` chấp nhận các tham số `signals` và `anti_signals` tương tự.

### Phản ứng với sự kiện Discovery

Vì discovery là sự kiện "rule này vừa trở nên liên quan đến phiên hội thoại", SDK cho phép bạn gắn hook trực tiếp vào nó. Một trường hợp thực tế: gắn tag cho session ngay khoảnh khắc một chủ đề xuất hiện, giúp dashboard và hàng đợi của bạn nhận biết ngay mà không cần chờ phán quyết khớp chính thức:

```python
async def on_warranty_discovered(
    ctx: p.EngineContext,
    evaluation: p.RuleEvaluation,
) -> None:
    await p.Session.current.labels.add("warranty-claim")

await agent.create_observation(
    condition="the customer is reporting a product defect",
    on_discovered=on_warranty_discovered,
)
```

`on_discovered` kích hoạt khi rule **mới bước vào** session working set: một lần cho mỗi lần nạp, không phải một lần cho mỗi lượt. Nếu rule sau đó bị loại bỏ do pruning và được nạp lại bởi một kích hoạt mới, handler sẽ kích hoạt lại.

Hãy chọn hook dựa trên chi phí: `on_discovered` đi kèm với recall, vốn rất rẻ. Trong khi đó, `on_matched` đòi hỏi phán quyết xác nhận theo từng lượt, khiến Parlant phải đánh giá rule bằng LLM ở mọi lượt. Hãy dùng `on_matched` khi hành động chỉ được phép diễn ra nếu rule thực sự áp dụng lúc này; hãy dùng `on_discovered` khi chỉ cần "chủ đề này đã xuất hiện trong cuộc hội thoại" là đủ.

## Gỡ lỗi Recall (Debugging Recall)

Parlant ghi log mọi batch discovery ở cấp độ debug — hãy tìm cụm từ `Rule discovery results` trong log để xem điểm số và phán quyết của từng ứng viên:

```text
... Rule discovery results:
### 1 Open a warranty claim [Score: 0.82 (Relevant)]
    Condition: the customer reports a product defect
    ...
### 2 Explain warranty terms [Score: 0.31 (Not Relevant)]
    ...
```

Các hiện tượng thường gặp và nguyên nhân:

| Hiện tượng | Nguyên nhân có thể |
|---|---|
| Rule luôn được đưa vào, không bao giờ được chấm điểm | Agent có ≤ 5 rule khả dụng (danh mục nhỏ bỏ qua recall), rule có trọng số LOW, hoặc điều kiện tham chiếu policy khác (cả hai đều được render tĩnh). |
| Rule không bao giờ xuất hiện trong kết quả discovery | Rule có `evaluation_func=` tùy chỉnh (rule đánh giá bằng code bỏ qua discovery), hoặc đã nằm sẵn trong session working set. |
| Rule đạt điểm Relevant nhưng không bao giờ vào working set | Rule có mục tiêu `depend_on(...)` chưa từng khớp một lượt nào trong session này. |
| Rule hiển thị `Score: 0.00 (Relevant)` | Batch discovery chỉ có duy nhất rule đó và nó không có anti-signal, nên Parlant nạp thẳng không cần chấm điểm. Điều này hoàn toàn bình thường. |
| Sửa signal nhưng không thấy tác dụng | Server chưa được khởi động lại sau khi sửa — recall vẫn dùng bộ phân loại cũ lúc startup. Hãy khởi động lại (hoặc lưu file nếu bật hot reload). |
| Rule kích hoạt nhầm trên các tin nhắn không mong muốn | Signal quá chung chung. Hãy thêm các tin nhắn bị kích hoạt nhầm làm anti-signals và huấn luyện lại. |
| Rule bỏ sót các câu nói lẽ ra phải bắt được | Tập signal quá hẹp. Thêm các cách diễn đạt kích hoạt thực sự khác biệt; ghim (pin) câu bắt buộc không được bỏ sót. |
| Pin không kích hoạt | Ngưỡng cosine 0.9 rất khắt khe — tin nhắn của khách hàng gần như phải lặp lại nguyên văn câu pin. |
| Rule bị loại bỏ không quay trở lại với chủ đề cũ | Đúng thiết kế: chỉ những cuộc trò chuyện mới hơn thời điểm loại bỏ mới có thể nạp lại rule. |
| Rule vẫn còn nán lại sau khi chủ đề đã qua | Tính lưu giữ (stickiness) là chủ ý thiết kế; working set chỉ bị cắt tỉa khi vượt quá 30 thành viên, và tối đa 1 lần mỗi 10 tin nhắn. |
| Tool hoặc `on_matched` không kích hoạt dù rule đã được phát hiện | Khám phá (Discovery) không phải là Khớp (Match). Các hệ quả đó đòi hỏi phán quyết khớp lượt (xem phần "Khám phá không đồng nghĩa với Khớp"). |
