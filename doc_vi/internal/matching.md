# Khớp quy tắc (Matching - Compass) — Hướng dẫn Kỹ thuật Nội bộ

Tài liệu này giải thích cách engine Compass quyết định những quy tắc nào tham gia vào một lượt hội thoại: tại sao việc khớp (matching) lại tồn tại, điều gì khiến nó trở thành một thách thức, hệ thống thuật ngữ mà mã nguồn sử dụng, và cách giai đoạn đánh giá hoạt động từ đầu đến cuối. Các liên kết mã nguồn được cung cấp dưới dạng tham chiếu module; phần thuật ngữ trong `matching/common.py` và `matching/evaluation_scheduler.py` là các bảng chú giải thuật ngữ chuẩn mực trong mã nguồn.

## 1. Động lực cho cơ chế khớp quy tắc (Matching)

Kho quy tắc (rule inventory) của một agent phát triển vượt xa mức có thể — hoặc nên — đưa vào trong một prompt duy nhất:

- **Khả năng tuân thủ hướng dẫn suy giảm theo dung lượng.** Các mô hình tuân theo mười chỉ dẫn tập trung tốt hơn nhiều so với hai trăm chỉ dẫn xung quanh. Việc khớp quy tắc giúp giữ prompt của mỗi lượt chỉ chứa các quy tắc thực sự chi phối lượt đó, được kết xuất cùng lý do (rationale) theo từng lượt, để sự chú ý của bộ phản hồi (responder) đặt đúng vào nơi quan trọng.
- **Chi phí và độ trễ tỷ lệ thuận với kích thước prompt.** Việc đưa toàn bộ kho quy tắc vào mỗi lượt sẽ nhân lên chi phí token mà không mang lại lợi ích hành vi nào.
- **Tính ổn định của prompt-cache.** System prompt của responder được lưu cache theo tiền tố (prefix-cached). Một tập hợp quy tắc được quản lý cẩn thận, thay đổi chậm rãi sẽ giữ cho tiền tố đó ổn định qua các lượt; việc xáo trộn quy tắc tùy tiện theo từng lượt sẽ phá vỡ hoàn toàn bộ nhớ cache.
- **Các thành phần gắn kèm (attachments) cần một bộ kích hoạt.** Công cụ (tools), câu trả lời soạn sẵn (canned responses), các trình xử lý (handlers), yêu cầu xét duyệt (review requests) và mức nỗ lực được kích hoạt (triggered effort) đều chỉ thực thi *khi một quy tắc khớp*. Khớp quy tắc là sự kiện làm cho cơ chế của một quy tắc có thể hành động được, chứ không chỉ đơn thuần hiển thị văn bản của nó.

Nhiệm vụ của matcher gói gọn trong một câu: **đặt đúng quy tắc trước mặt mô hình vào đúng thời điểm, với chi phí (chi phí AI) tỷ lệ thuận với mức độ quan trọng.**

### Hình thái của một lượt hội thoại (The shape of a turn)

Vị trí của matching trong quá trình engine xử lý một lượt hội thoại của khách hàng:

```text
preload            tải inventory + discovered set + statically-included set
  │                (trước warm-up, để các tiền tố prompt được cache giữ ổn định)
warm_up            làm nóng trước (prefill) các tiền tố prompt của evaluators/responder
  │
match_early        các code evaluator tất định ở pha EARLY (ví dụ: vị từ ngân sách)
  │                — trước bất kỳ tác vụ tính phí nào
fill               ┌ khớp quy tắc (tài liệu này)
  │                ├ gợi nhớ công cụ (tool recall)     (matching/tool_recaller.py)
  │                └ gợi nhớ thuật ngữ (glossary recall) (matching/glossary_recaller.py)
  │                cả ba chạy song song, sau đó là chọn công cụ (tool selection)
respond loop       responder sinh phản hồi; sau mỗi bước chạy công cụ,
  │                update() đánh giá lại các quy tắc bị kiểm soát bởi các công cụ
  │                vừa chạy (quan hệ REEVALUATION) và chọn lại công cụ
finalize           cắt tỉa tập quy tắc đã khám phá và session glossary
                   (sau phản hồi, để các cache miss rơi vào khoảng giữa các lượt)
```

Tài liệu này đề cập đến hộp **khớp quy tắc (rule matching)**; tool recall và glossary recall là các nhánh ngang hàng về mặt cấu trúc với các thiết kế recall/stickiness riêng.

## 2. Các thách thức của matching (tổng quan)

- **Chất lượng phán đoán so với chi phí.** Phán quyết của LLM rất chính xác nhưng tốn một lệnh gọi cho mỗi quy tắc trong mỗi lượt; bộ phân loại embedding gần như miễn phí nhưng lại không nhận biết được sắc thái — và mù lòa về mặt cấu trúc đối với một số loại điều kiện (xem các quy tắc tham chiếu chéo bên dưới). Engine liên tục phải phân xử giữa hai phương thức này.
- **Cuộc hội thoại có trạng thái (stateful).** Một quy tắc quan trọng cách đây ba lượt thường vẫn còn quan trọng ở hiện tại ("Tôi muốn hoàn tiền" không hết hạn khi khách hàng trả lời một câu hỏi tiếp theo). Mức độ liên quan phải có tính bám dính (sticky) — nhưng sự bám dính không giới hạn sẽ làm phình prompt, và việc loại bỏ bất cẩn sẽ gây ra hiện tượng chập chờn (flapping: một quy tắc rời đi rồi lại quay lại dựa trên trigger ban đầu của nó).
- **Các quy tắc phụ thuộc lẫn nhau.** Sự phụ thuộc (dependencies) kiểm soát quy tắc này dựa trên quy tắc khác; mức độ ưu tiên (priorities) phân xử giữa các quy tắc cùng khớp; các quy tắc tham chiếu chéo *có ý nghĩa* khác nhau tùy thuộc vào những gì phần còn lại của kho quy tắc thể hiện. Do đó, việc đánh giá từng quy tắc một cách cô lập đôi khi hoàn toàn sai lầm.
- **Mọi thứ phải suy thoái nhẹ nhàng (degrade gracefully).** Matching nằm trên đường dẫn quan trọng (critical path) của mỗi lượt. Các tối ưu hóa (lập lịch, caching, batching) phải luôn ở trạng thái dự phòng an toàn (fail open) về hành vi đơn giản hơn, không bao giờ để xảy ra một lượt hội thoại bị lỗi.

## 3. Thuật ngữ của matching

**Inventory / usable rules (Kho quy tắc / Quy tắc khả dụng)**
: Mọi quy tắc đang được bật và khả dụng cho agent trong lượt này (`state.usable_rules`).

**Discovered rules (Quy tắc đã khám phá)**
: Tập hợp làm việc của phiên (session working set): các quy tắc được thừa nhận trong lượt này hoặc lượt trước, được lưu trữ trong session metadata, được kết xuất mỗi lượt kèm lưu ý "có thể liên quan hoặc không — hãy sử dụng phán đoán của bạn."

**Pending admission (Chờ thừa nhận)**
: Các quy tắc mà lượt discovery mới vừa đánh giá là liên quan trong lượt này nhưng chưa vượt qua bước phân giải cuối cùng (`MatcherState.pending_discovered_rules`).

**Turn-matched rules (Quy tắc khớp theo lượt)**
: Các quy tắc có phán quyết tích cực theo từng lượt từ một evaluator. Được kết xuất nổi bật cùng lý lẽ (rationale); tất cả các attachments đều dựa trên điều này.

**Evaluation (Đánh giá)**
: Hành động phán xét một quy tắc (bởi bất kỳ evaluator nào). Tạo ra một phán quyết (verdict), không nhất thiết phải là một kết quả khớp (match).

**Evaluator (Bộ đánh giá)**
: Một thành phần phán xét các quy tắc cho lượt hiện tại: ranker, distiller, hoặc code (function) evaluator.

**Discovery / recall (Khám phá / Gợi nhớ)**
: Cơ chế dựa trên embedding giúp thừa nhận các quy tắc vào tập hợp discovered rules (xem [Rule Discovery](../rule-discovery.md) để biết chi tiết đầy đủ).

**Weight (Trọng số)**
: Mức độ quan trọng của quy tắc (LOW/MEDIUM/HIGH). Cùng với mức nỗ lực (effort), nó quyết định chiến lược đánh giá, miễn trừ cắt tỉa (pruning), và tỷ lệ hóa độ sâu lập luận của reviewer.

**Candidate (Ứng viên)**
: Một quy tắc sẽ thực sự được đánh giá trong lần gọi matcher này. Ngưỡng lập lịch tính toán trên số lượng ứng viên, không phải toàn bộ inventory.

**Cross-referential rule (Quy tắc tham chiếu chéo)**
: Một quy tắc có ý nghĩa phụ thuộc vào các quy tắc *khác* của agent, được đánh cờ qua `rule.metadata["references_other_policies"]` (được phân loại tại thời điểm build bởi `RuleRelativityProposer`; metadata của tác giả có quyền ghi đè).

**Attachment (Thành phần gắn kèm)**
: Bất kỳ cơ chế máy móc nào chỉ kích hoạt khi có một turn match: tools, dependencies, quan hệ priority (cả hai phía), labels, triggered effort, priority khác mặc định, review requests, match/discovery handlers, code evaluators, và một mục metadata nội bộ `evaluation_method` rõ ràng (`"rank"` hoặc `"distill"` — được đóng dấu bởi SDK cho các retriever gắn với quy tắc, và là cách để tác giả bắt buộc đưa ra phán quyết theo từng lượt).

**Static inclusion (Đưa vào tĩnh)**
: Cách xử lý đối với các quy tắc tham chiếu chéo *trần trụi* (không có attachments): luôn được kết xuất trong các chỉ dẫn miền với trọng số khai báo của chúng (quy tắc LOW mang ghi chú gợi ý, quy tắc HIGH giữ ghi chú trọng số cao), không bao giờ bị discovery hoặc rank.

**Policy context (Ngữ cảnh chính sách)**
: Tập hợp các quy tắc khác được kết xuất vào prompt đánh giá của một quy tắc tham chiếu chéo để các tham chiếu của nó có thể được phân giải.

**Policy landscape (Không gian chính sách)**
: Chế độ kích thước kho quy tắc, được phân tách bởi `MAX_FULL_POLICY_CONTEXT_RULES` (`matching/common.py`): nhỏ → ngữ cảnh chính sách chứa toàn bộ kho quy tắc, không cần thứ tự; lớn → ngữ cảnh bị giới hạn, việc đánh giá bị hoãn lại cho đến khi discovery báo cáo xong.

**Precondition / evidence / round (Điều kiện tiên quyết / Bằng chứng / Vòng đánh giá)**
: Thuật ngữ lập lịch — xem bảng giải thích ở đầu file `matching/evaluation_scheduler.py`.

## 4. Pha đánh giá (Evaluation phase)

### i. Tổng quan về đánh giá

Mỗi lượt, matcher (`compass/matcher.py`) thực hiện:

1. **Preloads (Tải trước)**: kho quy tắc (inventory), tập hợp đã khám phá (discovered set từ session metadata), và tập hợp đưa vào tĩnh (statically-included set: các quy tắc tham chiếu chéo trần trụi — được tính toán trước khi warm-up prompt để các tiền tố cache giữ ổn định).
2. **Selects candidates (Chọn ứng viên)**: các quy tắc LOW-weight và statically-included bị loại trừ (chúng được kết xuất vô điều kiện), ngoại trừ các quy tắc LOW có khả năng nâng cao effort hoặc đóng vai trò làm mục tiêu phụ thuộc (dependency targets) sẽ được đánh giá; các quy tắc được đánh giá bằng code sẽ chuyển hướng sang function evaluator; phần còn lại được phân nhóm theo chiến lược — RECALL (chỉ discovery) hoặc RANK (discovery *kèm theo* phán quyết LLM). Các quy tắc được đánh giá trong `match_early` (các code evaluator tất định pha EARLY) bị loại trừ ở đây — phán quyết của chúng đã được ghi lại trước khi bắt đầu bất kỳ tác vụ tính phí nào.
3. **Schedules (Lập lịch)**: evaluation scheduler xây dựng một kế hoạch (xem mục §v). Đối với hầu hết các lượt, kế hoạch chỉ là một lượt duy nhất; khi có các điều kiện tiên quyết, nó trở thành các vòng (rounds) bị giới hạn.
4. **Runs rounds (Chạy các vòng)**: trong một vòng, việc đánh giá bằng mã, discovery và các LLM evaluator đều được phân nhánh thực thi đồng thời. Giữa các vòng, các quy tắc mới được discovery thừa nhận sẽ chuyển vào `pending_discovered_rules` và kế hoạch sẽ quan sát kết quả của từng nguồn bằng chứng.
5. **Resolves (Phân giải - xem §vi) và records (Ghi nhận)**: mở rộng quan hệ kéo theo (entailment expansion), lọc phụ thuộc (dependency filtering) và phân xử mức độ ưu tiên (priority arbitration) tạo ra tập hợp turn-matched và session-admitted cuối cùng, sau đó được ghi vào trạng thái và session metadata.

### ii. "Được đánh giá" (Evaluated) so với "Khớp" (Matched)

*Đánh giá (Evaluation)* là hành động phán xét; *khớp (matching)* là một kết quả khả dĩ. Mọi kết quả khớp đều đến từ một sự đánh giá, nhưng hầu hết các đánh giá đều kết thúc bằng "lượt này không khớp" — và đó là hoạt động bình thường, không phải lỗi. Ngoài ra còn có kết quả thứ ba không thuộc hai loại trên: **thừa nhận phiên (session admission)**, nơi discovery coi một quy tắc là có liên quan đến cuộc hội thoại mà không khẳng định gì về lượt hiện tại. Việc phân biệt rõ ba trạng thái này (được đánh giá / khớp lượt này / được thừa nhận phiên) là điểm tựa tư duy hữu ích nhất khi đọc code hoặc log của matcher.

### iii. Quy tắc đã khám phá (Discovered) so với Quy tắc khớp theo lượt (Turn-matched)

#### a. Mục đích của discovery

Discovery trả lời câu hỏi "cuộc hội thoại có làm cho quy tắc này trở nên liên quan đến *phiên làm việc (session)* hay không?" — một phán đoán mang tính bám dính (sticky), chi phí thấp, dựa trên embedding (bộ phân loại được huấn luyện theo từng quy tắc trên các signals/anti-signals, với quyền ghi đè của pin; cơ chế đầy đủ nằm trong [Rule Discovery](../rule-discovery.md)). Các quy tắc đã khám phá được kết xuất trong mỗi lượt dưới dạng hướng dẫn phán đoán cho responder. Điều này mang lại cho engine nhận thức xung quanh (ambient awareness) với chi phí biên gần như bằng 0, và tính bám dính của nó chính là thứ giữ cho tiền tố prompt được lưu cache của responder ổn định qua các lượt.

#### b. Cắt tỉa (Pruning)

Sự bám dính không giới hạn sẽ làm phình prompt, do đó tập hợp discovered rules có giới hạn trên: khi vượt quá `_DISCOVERED_RULES_HIGH_WATER_MARK` (30), bộ cắt tỉa sẽ hỏi những thành viên nào vẫn còn quan trọng trong tương lai và đẩy những quy tắc cũ nhất ra ngoài để hạ về `_DISCOVERED_RULES_TARGET` (20). Các thành viên có trọng số HIGH và các quy tắc khớp trong lượt này được miễn trừ; việc cắt tỉa chạy tối đa một lần sau mỗi 10 tin nhắn của khách hàng để gom cụm các cache miss. Các quy tắc bị đẩy ra sẽ đi vào một **sổ cái loại trừ (eviction ledger)** cùng với chỉ số offset tại thời điểm loại trừ — chúng chỉ có thể được *thừa nhận lại* bởi nội dung hội thoại mới hơn offset đó, do đó cơ chế max-pool bám dính không thể làm sống lại chúng dựa trên trigger ban đầu (chống hiện tượng chập chờn - anti-flapping).

#### c. Các quy tắc khớp theo lượt (Turn-matched rules)

Một turn match là một phán quyết rõ ràng: *quy tắc này chi phối lượt này*. Các quy tắc khớp được hiển thị nổi bật kèm theo lý lẽ của evaluator, và mọi cơ chế máy móc đều kích hoạt từ chúng: các công cụ tham gia vào danh mục chào bán, canned responses trở thành tài liệu tham khảo phong cách và hướng dẫn đánh giá, các handler `on_matched` chạy, các yêu cầu xét duyệt được trang bị, mức nỗ lực được nâng cao, và các mức ưu tiên được phân xử.

Một trường hợp biên khi kết xuất: các lời nhắc theo bước (step reminders) thông thường tham chiếu đến một quy tắc khớp có tiêu đề bằng chính tiêu đề của nó, tin tưởng rằng toàn bộ nội dung của nó đã nằm trong system instructions trên toàn hệ thống. Nhưng những chỉ dẫn đó được xây dựng một lần, tại thời điểm bắt đầu lượt — và một quy tắc có thể khớp *lần đầu tiên* vào giữa lượt (công cụ `reevaluate_after` của nó vừa chạy xong) và chỉ được thừa nhận vào lúc đó. Đối với các bước còn lại của lượt đó, lời nhắc sẽ kết xuất toàn bộ nội dung của quy tắc trực tiếp (inline) thay vì tham chiếu theo tiêu đề mà mô hình không thể phân giải (`rendered_rule_ids` snapshot trong trạng thái response); từ lượt tiếp theo trở đi, việc thừa nhận bền vững sẽ đưa nội dung vào system instructions và lời nhắc quay lại dạng tham chiếu theo tiêu đề.

#### d. Trọng số quy tắc và ma trận chiến lược

Trọng số (Weight) là tuyên bố về mức độ quan trọng từ tác giả. Cùng với mức nỗ lực động (dynamic effort level) của lượt, nó lựa chọn chiến lược đánh giá (`_get_strategy`):

- **Mức nỗ lực MIN / LOW**: cả trọng số MEDIUM và HIGH đều dùng RECALL.
- **Mức nỗ lực MEDIUM**: trọng số HIGH được nâng lên RANK; trọng số MEDIUM giữ ở RECALL.
- **Mức nỗ lực HIGH / MAX**: cả trọng số MEDIUM và HIGH đều dùng RANK.
- **Trọng số LOW, ở mọi mức nỗ lực**: bị loại hoàn toàn khỏi matching và được kết xuất trong system instructions một cách vô điều kiện — không có gì phải quyết định, do đó không tốn chi phí để quyết định nó. Triggered effort trên một quy tắc LOW sẽ ép buộc đánh giá thực sự, vì kết quả khớp của nó làm thay đổi chi phí kinh tế của lượt; việc đóng vai trò là mục tiêu phụ thuộc (dependency target) cũng làm điều tương tự, vì phán quyết của nó kiểm soát quy tắc khác, cũng như việc tham gia vào quan hệ ưu tiên, vì sự triệt tiêu vận hành dựa trên các phán quyết.

Ba nhóm ghi đè (overrides) nằm trên ma trận:

- **Đường dẫn nhanh cho kho quy tắc nhỏ (Small-inventory fast path)** (`_SMALL_INVENTORY_THRESHOLD`, 5): khi có từ năm quy tắc khả dụng trở xuống, các quy tắc lẽ ra dùng RECALL sẽ bỏ qua hoàn toàn discovery và được thừa nhận hàng loạt (chiến lược NONE) — toàn bộ kho quy tắc vừa vặn trong chỉ dẫn của responder, vì vậy một quy tắc mà recaller từ chối cũng sẽ được kết xuất dù sao đi nữa, và một vòng gọi embedding chỉ mang lại thêm độ trễ.
- **Leo thang lên RANK, bất kể ma trận**: các quy tắc có gắn nhãn (labels), triggered effort, yêu cầu xét duyệt (review requests), match handlers, cờ tham chiếu chéo, đóng vai trò là **mục tiêu phụ thuộc (dependency targets)**, hoặc nằm ở **bất kỳ phía nào của một quan hệ ưu tiên (priority relationship)** đều luôn được xếp hạng (ranked) — các phán quyết khớp của chúng mang lại những hệ quả (phân tích số liệu, các bước tiếp theo bị kiểm soát, các đợt review được kích hoạt, triệt tiêu theo ưu tiên) mà embedding recall không thể tin cậy giao phó. Đối với priority, cả hai phía đều cần phán quyết: phía nguồn quyết định việc triệt tiêu có kích hoạt hay không, phía mục tiêu quyết định xem có cái gì để triệt tiêu hay không. Việc chỉ đơn thuần phụ thuộc vào quy tắc khác không tự động được leo thang lên RANK: quy tắc nguồn giữ chiến lược ma trận thông thường của nó trừ khi có lý do khác nâng cấp nó, trong khi mục tiêu được xếp hạng vì phán quyết của nó kiểm soát nguồn.
- **Leo thang công cụ nhạy cảm với effort**: một attachment công cụ đảm bảo ít nhất đạt mức RANK từ effort MEDIUM trở lên. Ở mức MIN và LOW, riêng công cụ không nâng quy tắc của nó vượt quá ma trận thông thường (hoặc đường dẫn nhanh kho quy tắc nhỏ), nhưng bất kỳ sự leo thang độc lập nào ở trên vẫn được áp dụng.

Weight cũng được tiêu thụ ngoài việc lựa chọn chiến lược: HIGH được miễn trừ cắt tỉa, và reviewer điều chỉnh độ sâu lập luận của nó tùy thuộc vào việc các quy tắc trọng số cao có khớp trong lượt hay không.

#### e. Điểm nhấn (Highlights) và lời nhắc chỉ dẫn (Instruction reminders)

Các evaluator trả về **highlights** cùng với một phán quyết khẳng định: các điểm cụ thể của một quy tắc (thường là dài) có liên quan *ngay lúc này*. Đối với các quy tắc phức tạp hoặc chỉ chứa nội dung, việc kết xuất quy tắc khớp trở thành một **lời nhắc chỉ dẫn (instruction reminder)** — `### Review the instructions under "<title>"` kèm theo các gạch đầu dòng highlight — hướng mô hình quay lại văn bản đầy đủ của quy tắc trong system instructions (đã cache) thay vì sao chép lại nó trong phần của lượt hội thoại. Điều này bảo toàn prefix cache, giữ cho prompt của lượt tập trung, và hướng sự chú ý vào phần hiện đang liên quan của một quy tắc lớn thay vì toàn bộ bức tường văn bản.

### iv. Các phương thức đánh giá (Evaluation methods)

Các phán quyết đến từ ba loại nguồn. **Code (function) evaluators** — các hàm Python callable được đăng ký qua SDK bằng `evaluation_func=` và được phân giải thông qua `RuleEvaluatorRegistry` — mang tính quyền uy tuyệt đối: một quy tắc có hàm này sẽ không bao giờ bị discovery hoặc đánh giá bằng LLM, code của tác giả sẽ tự quyết định. **Discovery** tạo ra các sự thừa nhận (admissions), không tạo phán quyết (§iii.a). Các **LLM evaluators** dưới đây tạo ra các phán quyết lượt cho các quy tắc hạng RANK; matcher hỗ trợ đa bộ đánh giá một cách tự nhiên (`_select_evaluator` là điểm nối định tuyến mà các lớp con mở rộng).

#### a. Các hàm đánh giá tùy chỉnh (Custom evaluation functions)

Truyền một hàm đánh giá bất đồng bộ khi tạo policy hoặc observation. Hàm nhận `RuleEvaluationContext` hiện tại và quy tắc đang được đánh giá, và phải trả về một `RuleEvaluation` với ID của quy tắc đó:

```python
import parlant.sdk as p


async def evaluate_refund_request(
    ctx: p.RuleEvaluationContext,
    policy: p.Policy,
) -> p.RuleEvaluation:
    message = ctx.session.interaction.last_customer_message
    is_relevant = bool(message and "refund" in message.content.lower())

    return p.RuleEvaluation(
        id=policy.id,
        is_relevant=is_relevant,
        reasoning=(
            "The customer requested a refund."
            if is_relevant
            else "The customer did not request a refund."
        ),
        highlights=(
            "Refunds require proof of purchase.",
            "Refund requests must be made within 30 days.",
        ) if is_relevant else (),
    )


await agent.create_policy(
    title="Refund policy",
    content=(
        "Refunds require proof of purchase. Refund requests must be made "
        "within 30 days. Opened consumable products cannot be refunded."
    ),
    evaluation_func=evaluate_refund_request,
)
```

`highlights` là tùy chọn. Đối với một phán quyết khẳng định cho một quy tắc trọng số MEDIUM hoặc HIGH, mỗi chuỗi trả về sẽ trở thành một gạch đầu dòng trong instruction reminder của quy tắc khớp được mô tả trong §iii.e. Hãy sử dụng nó để chọn lọc các phần của một quy tắc dài có ý nghĩa đối với lượt hiện tại; nó nên củng cố nội dung của quy tắc thay vì đưa vào các chỉ dẫn không liên quan. Một phán quyết phủ định không được kết xuất, vì vậy nó thường không trả về highlights nào.

Context cũng cung cấp quyền truy cập vào session, agent, customer, các biến đã tải, staged events, và `staged_tool_calls`, cho phép đánh giá tất định từ trạng thái ứng dụng hoặc kết quả công cụ. Do một evaluator tùy chỉnh mang tính quyết định tuyệt đối, quy tắc của nó bỏ qua discovery và đánh giá LLM.

#### b. Xếp hạng (Ranking)

`RuleRanker` (`matching/rule_ranker.py`) chấm điểm một quy tắc cho mỗi prompt theo thang điểm liên quan từ 1 đến 5, được thiết kế như một *vòng sàng lọc ban đầu* ("một giám khảo con người xem xét mọi thứ không hoàn toàn không liên quan") — điều này giúp nó tránh được các trường hợp âm tính giả (false negatives). Prompt của nó được chia thành tiền tố dùng chung ổn định qua các lượt (hướng dẫn, ví dụ vài lượt mẫu, danh tính — được prefill-warm và cache) và phần đuôi trực tiếp (lượt hiện tại, lập luận của agent, staged tool events, các thuật ngữ glossary của quy tắc, ngữ cảnh phụ thuộc, và — đối với các quy tắc tham chiếu chéo — ngữ cảnh chính sách). Các quy tắc được đánh giá là liên quan sẽ trở thành turn matches; sự cô lập theo từng quy tắc của ranker chính là lý do tại sao các quy tắc tham chiếu chéo cần phần policy-context.

#### c. Chưng cất (Distillation)

Một distiller là một `TurnEvaluator` tùy chọn đánh giá toàn bộ một lô quy tắc trong một request duy nhất, thay vì phân nhánh một request cho mỗi quy tắc như ranker làm. Cấu hình mặc định không liên kết distiller nào, vì vậy đây là một điểm nối mở rộng hơn là một thành phần bạn sẽ thấy bên dưới.

Một evaluator trả lời cả lô cùng lúc sẽ thông báo điều đó qua `evaluates_batch_in_one_request`, và điều đó làm thay đổi bài toán chi phí mà ma trận chiến lược được xây dựng dựa trên: việc phân nhánh theo từng quy tắc là thứ làm cho phán quyết trở nên đắt đỏ, vì vậy các quy tắc vốn bị phó mặc cho embedding recall nay trở nên đủ rẻ để đánh giá.

### v. Lập lịch đánh giá (Evaluation scheduling)

#### a. Động lực

Một số quy tắc không thể được đánh giá chính xác cho đến khi các phán đoán *khác* đã có kết quả:

- Phán quyết của một quy tắc **phụ thuộc (dependent)** sẽ vô nghĩa cho đến khi điều kiện phụ thuộc của nó cho thấy bằng chứng đang hoạt động — đánh giá cả hai cùng lúc sẽ lãng phí lệnh gọi của quy tắc phụ thuộc hoặc đánh giá nó dựa trên các tiền đề chưa hoàn chỉnh.
- Prompt của một quy tắc **tham chiếu chéo (cross-referential)** cần tập hợp đã khám phá *bao gồm cả những sự thừa nhận mới của lượt này* — vốn chỉ tồn tại sau khi discovery báo cáo kết quả.

Bộ lập lịch (scheduler) tồn tại để sắp xếp thứ tự các đánh giá như vậy — và không làm gì cả khi không cần sắp xếp thứ tự.

#### b. Ràng buộc

- **Có giới hạn (Bounded)**: tối đa `max_rounds` (mặc định 2) vòng; vòng cuối cùng cố tình bao gồm cả những ứng viên mà trạng thái vẫn chưa xác định, do đó các chu kỳ lặp và các chuỗi sâu sẽ suy thoái về dạng "cứ đánh giá đi" thay vì bị bỏ rơi trong im lặng.
- **Không tốn chi phí dưới ngưỡng**: việc chia pha chỉ kích hoạt khi số lượng ứng viên đạt đến `EvaluationSchedulingPolicy.threshold` (mặc định 8) — với một ngoại lệ: **các điều kiện tiên quyết bắt buộc (forcing preconditions)**, vốn đánh dấu các yêu cầu về tính đúng đắn (không phải tối ưu hóa) và cho phép kích hoạt chia pha bất kể số lượng, được ghi log khi sự bắt buộc làm thay đổi kết quả. Các provider phát ra chúng phải tự kiểm soát để việc ép buộc không bao giờ vô nghĩa (provider tham chiếu chéo bỏ qua hoàn toàn các không gian nhỏ, nơi ranker sử dụng toàn bộ inventory và việc chờ đợi không mang lại lợi ích gì).
- **Fail-open**: lỗi của provider sẽ suy thoái về đánh giá một lượt (one-pass); các ứng viên bị bỏ qua sẽ được ghi log, không bao giờ bị loại bỏ trong im lặng.
- **Tổng quát (Generic)**: scheduler không biết gì về rankers, distillers hay recall. Nó chỉ nhìn thấy ứng viên, điều kiện tiên quyết và bằng chứng. Các lý do sắp xếp thứ tự mới được thêm vào dưới dạng `EvaluationPreconditionProvider` tại gốc thành phần — dependencies và cross-references là hai provider hiện tại.

#### c. Cơ chế

Matcher đếm các nguồn bằng chứng dự kiến cho mỗi ứng viên và cung cấp bằng chứng ban đầu (các quy tắc đã khám phá bền vững, các kết quả khớp sớm tất định). `EvaluationScheduler.create_plan` thu thập các điều kiện tiên quyết từ tất cả các provider một cách đồng thời và trả về một `EvaluationPlan`. Trong mỗi vòng: plan chọn các ứng viên có điều kiện tiên quyết đã được thỏa mãn (vòng cuối cùng cũng lấy cả các trường hợp chưa rõ), sau đó matcher chụp nhanh trạng thái hiệu dụng của các mục tiêu cho mỗi đánh giá mô hình phụ thuộc. Một prompt xác định chỉ bao gồm các mục tiêu đã thỏa mãn; nếu bất kỳ mục tiêu nào vẫn chưa rõ, matcher sẽ cảnh báo và đưa tất cả các mục tiêu đã cấu hình vào dưới dạng ngữ cảnh dự phòng rõ ràng là chưa chắc chắn. Việc chuẩn bị prompt này không nâng cấp nguồn chỉ dùng recall lên RANK hoặc DISTILL. Matcher sau đó chạy đồng thời các evaluator của vòng đó và discovery (ở vòng 1), các thừa nhận mới đi vào trạng thái pending-discovered, và kết quả của từng nguồn được đưa ngược lại qua `plan.observe`. Bằng chứng khẳng định có tính bám dính (sticky); bằng chứng phủ định chỉ có tính kết luận một khi mọi nguồn dự kiến cho một quy tắc đã báo cáo đầy đủ. Máy trạng thái hoàn chỉnh được lập tài liệu ở đầu file `matching/evaluation_scheduler.py`.

### vi. Phân giải quy tắc (Rule resolution)

Sau tất cả các vòng, `RelationalResolver` (`compass/relational_resolver.py`) nắm giữ tiếng nói quyết định cuối cùng đối với những gì các evaluator đã tạo ra:

- **Mở rộng quan hệ kéo theo (Entailment expansion)** (`expand_entailment`): trước khi bất kỳ thứ gì bị lọc, các quan hệ ENTAILMENT sẽ kích hoạt các quy tắc bổ sung — một quy tắc khớp (hoặc được thừa nhận) sẽ kéo các mục tiêu kéo theo của nó vào cùng tập hợp, với cùng mức độ sử dụng mà nguồn kéo theo mạnh nhất của nó có (turn match sinh ra turn match; admission sinh ra admission). Bao đóng mang tính gián tiếp và duyệt qua các mục tiêu nhóm vào các thành viên của chúng. Việc mở rộng chạy *trước* cổng phụ thuộc (dependency gate), do đó một quy tắc được kéo theo cũng tự nó chịu sự kiểm soát của dependency và có thể thỏa mãn các dependency của các đánh giá khác trong cùng một lượt.
- **Lọc phụ thuộc (Dependency filtering)** (`filter_unmet_dependencies`): một đánh giá chỉ tồn tại nếu các phụ thuộc của nó được thỏa mãn — bởi một *kết quả khớp* khác trong cùng lượt này (các chuỗi trong cùng lượt được giải quyết theo thứ tự) hoặc bởi **sổ cái quy tắc đã khớp (matched-rule ledger)** của session (`compass.rules_ever_matched_in_session`): tập hợp các quy tắc đã từng khớp theo lượt ít nhất một lần trong session này. Sổ cái là một chốt cấp độ phán quyết — được ghi nhận *trước* khi phân giải priority (một kết quả khớp bị hạ mức ưu tiên vẫn được tính), không bao giờ bị xóa bởi việc cắt tỉa working-set. Việc thừa nhận của discovery **không thỏa mãn bất cứ điều gì**: recall cố tình được thiết kế rộng rãi, và việc để các kết quả dương tính giả ở cấp độ embedding mở khóa các quy tắc phụ thuộc sẽ biến `depend_on()` thành thứ trang trí. Một quy tắc có phụ thuộc chưa bao giờ được thỏa mãn sẽ bị loại bỏ *hoàn toàn* — bao gồm cả việc bị loại khỏi tập hợp đã khám phá — để nó tiếp tục được đánh giá mới trong mỗi lượt cho đến khi phụ thuộc của nó xuất hiện. Nhiều phụ thuộc được kết hợp bằng phép AND (`UNMET_DEPENDENCY_ALL`); những phụ thuộc được khai báo qua `depend_on_any` chia sẻ một `group_id` và tạo thành một nhóm OR, được thỏa mãn bởi bất kỳ một thành viên nào (`UNMET_DEPENDENCY_ANY`). Một mục tiêu nhóm phân giải theo cùng một cách: `GROUP_ANY` (`p.AnyOf`) cần một thành viên liên quan, trong khi một nhóm trần trụi cần *mọi* thành viên liên quan, và một nhóm rỗng coi như chưa thỏa mãn. Các phụ thuộc được khai báo trên một nhóm sẽ được kế thừa bởi các thành viên của nó, vì các id nguồn là quy tắc cộng với các nhóm của nó. Lưu ý thiết kế hai tầng có chủ đích: scheduler sử dụng dependencies chỉ để *sắp xếp thứ tự* đánh giá; resolver mới là nơi *thực thi* chúng. (Cả hai bước trên chia sẻ một điểm thắt nút trong matcher, `_resolve_admission_relationships`.)
- **Độ ưu tiên quan hệ (Relational priority)** (`resolve_priority_relationships`): trong số các turn matches, một kết quả khớp sẽ bị loại bỏ khi một quan hệ PRIORITY *trực tiếp* nhắm vào nó (hoặc một trong các nhóm của nó) và nguồn là một turn match khác (hoặc một nhóm có thành viên như vậy). Độ ưu tiên không lan truyền qua các thực thể trung gian không hoạt động (nguyên lý phục hồi - reinstatement principle), nhưng các nguồn được đánh giá dựa trên toàn bộ tập hợp trước khi lọc, vì vậy một quy tắc bị loại bỏ vẫn triệt tiêu các mục tiêu riêng của nó và các chuỗi sụp đổ trong một lượt duy nhất. Việc hạ mức ưu tiên *không* xếp tầng vào các phụ thuộc: một quy tắc bị hạ ưu tiên vẫn giữ trạng thái được thừa nhận và tiếp tục thỏa mãn các phụ thuộc của nó.
- **Phân xử độ ưu tiên số học (Numeric priority arbitration)** (`keep_highest_priority`): trong số những quy tắc sống sót sau phân giải quan hệ, chỉ mức ưu tiên số học cao nhất mới được giữ lại làm turn-matched. Các kết quả khớp được kéo theo (entailed matches) được miễn trừ — chúng có được sự kích hoạt là nhờ quy tắc kéo theo nó và không được triệt tiêu quy tắc đó. Các quy tắc bị vượt mặt sẽ bị hạ cấp xuống mức session admission (chúng có liên quan — chỉ là thua trong lượt này). Các cập nhật giữa lượt sẽ phân xử lại, chấp nhận sự phá vỡ prompt-prefix mà một kết quả khớp mạnh hơn giữa lượt gây ra.

Bởi vì một quy tắc bị hạ ưu tiên vẫn nằm trong working set đã khám phá, văn bản của nó vẫn xuất hiện trong toàn bộ tập chỉ dẫn của responder. Do đó, riêng việc loại bỏ khỏi turn-set không triệt tiêu được hành vi; responder sẽ kết xuất các quy tắc thua cuộc về mức ưu tiên của lượt này trong một phần đuôi trực tiếp rõ ràng: "OUTPRIORITIZED THIS TURN — do not act on these" (`turn_deprioritized_rules` trong trạng thái response), giữ cho system instructions có thể lưu cache không bị chạm tới. Ghi chú tương tự cũng áp dụng cho các chỉ dẫn *thường trực (standing)* bị vượt mặt bởi mức ưu tiên số học: khi một turn match chiến thắng ở mức priority > 0, mọi quy tắc được kết xuất có mức priority thấp hơn đều được liệt kê — bao gồm cả các quy tắc được thừa nhận bởi recall vốn chưa bao giờ nhận được phán quyết lượt, vì numeric priority là dữ liệu đã được khai báo và không cần phán quyết.

Các công cụ tham gia vào quá trình này thông qua **các quy tắc tạm thời (transient rules)**: một `ToolResult` có thể mang theo `rules=[{action, condition?, priority?, weight?}]`, mà bước làm mới sau đó của matcher sẽ chèn vào dưới dạng các turn matches ("Returned by tool 'x'"). Chúng chỉ tồn tại theo từng lượt — không bao giờ được lưu trữ, thừa nhận hay ghi vào sổ cái (cờ metadata đánh giá `transient` sẽ lọc chúng khỏi việc lưu trữ bền vững) — nhưng chúng cạnh tranh trong việc phân giải priority như bất kỳ kết quả khớp nào khác và được kết xuất đầy đủ trong các lời nhắc bước. Do đó, một quy tắc công cụ có mức ưu tiên cao ("tài khoản bị khóa — chỉ nói X") sẽ triệt tiêu các chỉ dẫn thường trực trong chính xác một lượt. Lưu ý đối với các agent mức effort MEDIUM: cache chỉ dẫn theo từng bước sẽ bị vô hiệu hóa khi có các tool events mới được đưa lên, do đó việc refresh thực hiện chèn quy tắc này (và đánh giá lại bị kiểm soát bởi công cụ) không bao giờ bị bỏ qua bởi tối ưu hóa caching.

Chỉ sau khi phân giải xong thì các kết quả mới được ghi nhận: turn matches vào trạng thái response, admissions vào tập hợp đã khám phá và session metadata — tại thời điểm đó các pending discoveries trở thành durable và chu kỳ sẵn sàng cho lượt tiếp theo.

## 5. Tổng hợp lại: Các quy tắc tham chiếu chéo từ đầu đến cuối

Các quy tắc tham chiếu chéo (cross-referential rules) vận dụng gần như mọi cơ chế ở trên, vì vậy chúng tạo thành một ví dụ tổng kết hoàn chỉnh. Một quy tắc như
*"khách hàng hỏi về một khả năng **không được hỗ trợ**"*
không thể được đánh giá một cách cô lập —
"được hỗ trợ" được định nghĩa bởi các quy tắc *khác* — và embedding recall yếu nhất về mặt cấu trúc trên chính hình thái này (một tập hợp phần bù không có vùng lân cận embedding ổn định). `RuleRelativityProposer` tại thời điểm build sẽ đánh cờ các quy tắc như vậy; quá trình matching sau đó định tuyến chúng dựa trên một câu hỏi duy nhất —
*có bất kỳ cơ chế máy móc nào treo vào kết quả khớp hay không?* — và, khi được xếp hạng, dựa trên kích thước không gian chính sách (policy-landscape size):

- **Không bị đánh cờ**: matching bình thường, theo ma trận chiến lược.
- **Bị đánh cờ, không có attachments ("trần trụi")**: được đưa vào tĩnh (statically included) — luôn được kết xuất trong các chỉ dẫn miền với trọng số khai báo của nó, không bao giờ bị discovery hoặc rank. Responder sẽ đánh giá nó cùng với các quy tắc xung quanh trong cùng một prompt — hoàn toàn miễn phí và miễn nhiễm với điểm mù của recall.
- **Bị đánh cờ + có attachments, không gian nhỏ** (inventory ≤ `MAX_FULL_POLICY_CONTEXT_RULES`): leo thang lên RANK; được đánh giá ở vòng 1 với **toàn bộ kho quy tắc (full inventory)** làm ngữ cảnh chính sách của nó. Không cần trì hoãn — toàn bộ bức tranh đã có sẵn trong prompt, do đó việc chờ đợi không mang lại lợi ích gì.
- **Bị đánh cờ + có attachments, không gian lớn**: leo thang lên RANK và **bị trì hoãn đến vòng lập lịch cuối cùng** (ép buộc chia pha nếu số lượng ứng viên chưa đủ kích hoạt, và ép chính sách một vòng thành hai vòng), để ngữ cảnh chính sách của nó — tập hợp đã khám phá, các quy tắc pending discovered của lượt này (recall), VÀ các quy tắc pending matched từ các vòng đánh giá trước — được lấp đầy khi prompt kết xuất. Các phán quyết của vòng trước rất quan trọng vì những gì recall bỏ sót chính là thứ mà ranker bắt được: một quy tắc mà chỉ ranker phát hiện ra vẫn phải hiển thị được đối với quy tắc bị trì hoãn.

Hai lưu ý. Một **code evaluator** trên một quy tắc có cờ và có attachment sẽ bỏ qua hoàn toàn ngữ cảnh chính sách LLM — các code evaluator không xây dựng prompt, do đó việc giải quyết các tham chiếu của quy tắc là nhiệm vụ của tác giả hàm đánh giá. Và ngữ cảnh chính sách được kết xuất tại bất kỳ nơi nào quy tắc được đánh giá.

Các bất biến thiết kế đáng ghi nhớ: việc trì hoãn không bao giờ vô nghĩa (nó chỉ tồn tại ở nơi ngữ cảnh bị giới hạn được sử dụng), và ngữ cảnh bị giới hạn không bao giờ bị cũ (nó chỉ được sử dụng ở nơi việc trì hoãn được đảm bảo). Cả hai điều này đều xuất phát từ việc ranker và cross-reference provider của scheduler chia sẻ cùng một ranh giới — `MAX_FULL_POLICY_CONTEXT_RULES` trong `matching/common.py` — thay vì mỗi bên dựa trên thước đo riêng của mình.
