# Tùy Biến Prompt (Prompt Customization)

Parlant tự động xây dựng các prompt riêng của nó — phục vụ việc phản hồi, khớp rule, đánh giá review, nén phiên hội thoại (compaction) — và đối với hầu hết các dự án triển khai, bạn không bao giờ cần phải bận tâm đến chúng. Tùy biến prompt chỉ dành cho những trường hợp hiếm hoi khi một prompt tích hợp sẵn diễn đạt điều gì đó mà bạn cần phải thay đổi theo cách khác.

Mọi prompt đều được ghép từ **các phần (sections) có tên và định dạng mẫu (template)**, và bạn tùy biến bằng cách can thiệp vào các section khi chúng được thêm vào: giữ nguyên, viết lại, hoặc loại bỏ từng phần, trong khi giữ nguyên vẹn mọi thứ khác. Bạn chọn prompt *nào* cần can thiệp thông qua tham số `prompts`, sử dụng cú pháp route key hoàn toàn tương tự như tham số `models` — các route quyết định mô hình nào được component gọi *và* builder prompt nào được sử dụng.

**Khi nào nên dùng.** Mọi hành vi mà một agent cần *thực hiện* đều nên thuộc về instructions, policies và canned responses. Những thứ đó hoạt động theo từng tình huống cụ thể, và đó là nơi hầu hết việc định hình hành vi diễn ra. Tùy biến prompt dành cho tầng nền tảng bên dưới: khi một nguyên tắc *tích hợp sẵn* — cách Parlant định hình chính bản thân công việc — xung đột với hệ thống của bạn (giọng văn thương hiệu, mức độ trang trọng, quy tắc ngôn ngữ, câu từ mang tính quy chuẩn pháp lý), hoặc khi cần loại bỏ các bản mẫu quy chuẩn của nền tảng.

**Sự đánh đổi.** Điều bạn nhận được là sự kiểm soát nhất quán và chính xác: bạn thay thế một section tại mọi nơi nó được sử dụng thông qua một API ổn định mà không cần phải fork mã nguồn Parlant. Điều bạn phải gánh vác là trách nhiệm làm chủ (ownership): câu từ tích hợp sẵn của Parlant đã được tinh chỉnh và kiểm thử kỹ lưỡng với các component của nó. Một section bị thay thế sẽ ngừng nhận các cải tiến từ bản phát hành gốc (upstream), và có thể làm thay đổi hành vi theo những cách mà chỉ các bài test của riêng bạn mới phát hiện ra. Vì vậy, hãy tùy biến cẩn trọng và giữ thay đổi ở mức tối thiểu: chỉ thay thế section nào thực sự không phù hợp với bạn, không nên thay thế tất cả. Hãy kiểm thử lại các cuộc trò chuyện bất cứ khi nào bạn thay đổi mô hình hoặc ghi đè prompt.

## Cách thức hoạt động

Toàn bộ cơ chế gồm có 2 phần:

- **Một prompt provider** — bất kỳ callable nào không nhận đối số và trả về một `PromptBuilder`. Một subclass hay một `lambda` đều hợp lệ. Bạn đăng ký nó dưới một route thông qua `prompts={...}`, và component được định tuyến sẽ xây dựng prompt thông qua nó.
- **`adapt_section`** — điểm ghi đè duy nhất được hỗ trợ trên builder của bạn. Component thêm các section như thường lệ, và `adapt_section` được gọi một lần cho mỗi section cùng với tên (`name`), mẫu template (`template`), và các thuộc tính (`props`) của nó. Nó trả về một trong 3 phán quyết:
  - `None` — giữ nguyên section không đổi (mặc định cho mọi phần bạn không can thiệp).
  - một chuỗi `str` — thay thế template của section. Hãy giữ lại mọi `{placeholder}` mà template gốc sử dụng; Parlant sẽ cung cấp giá trị cho chúng thông qua `props`. Một placeholder bị bỏ sót đồng nghĩa với việc nội dung bị mất, và một placeholder thiếu sẽ báo lỗi ngay khi build prompt.
  - `p.VETO` — loại bỏ hoàn toàn section đó.

**LƯU Ý:** **Không** ghi đè trực tiếp hàm `add_section`. Chữ ký hàm của nó thuộc phạm vi nội bộ và có thể tự do thay đổi; `adapt_section` mới là điểm mở rộng ổn định, và nó nhận đầy đủ mọi thứ bạn cần — bao gồm cả `props`, cho các trường hợp thay thế phụ thuộc vào nội dung thực tế của section.

## Ví dụ thực tế: Tùy biến chỉ dẫn chung của riêng bạn

Trường hợp tùy biến phổ biến nhất trên thực tế là thay thế **general instructions của responder** — các nguyên tắc cấp nền tảng mà mọi câu trả lời đều tuân theo. Chúng mã hóa các mặc định phù hợp với hầu hết các trường hợp nhưng không phải tất cả: ví dụ: *"hãy ngắn gọn, tự nhiên và tránh quá lịch sự"* (một agent ngân hàng cá nhân cao cấp có thể được kỳ vọng phải trang trọng và nhã nhặn), *"tránh dùng dấu gạch ngang em dash"* (thương hiệu của bạn có thể ưa chuộng chúng), hoặc *"luôn trả lời bằng ngôn ngữ trong tin nhắn gần nhất của khách hàng"* (một doanh nghiệp có quy định pháp lý bắt buộc chỉ được trả lời bằng một ngôn ngữ duy nhất). Việc ghi đè section sẽ thay thế các quy tắc mặc định đó bằng quy tắc của riêng bạn:

```python
import parlant.sdk as p


class MyResponderPrompt(p.PromptBuilder):
    def adapt_section(self, name, template, props):
        if name == p.PromptSections.Responder.TASK_DESCRIPTION:
            return MY_GENERAL_INSTRUCTIONS  # template thay thế
        return None  # giữ nguyên mọi thứ khác


server = p.Server(
    models={"*": "openai"},
    prompts={"react": MyResponderPrompt},
)
```

`react` là route của responder; tên các section được lấy từ registry `p.PromptSections` (cả hai đều được giải thích chi tiết bên dưới).

## Chọn prompt nào để tùy biến

**Theo route.** Các key sử dụng cú pháp selector hoàn toàn giống như `models`: route cụ thể, ký tự đại diện namespace (`"matching.*"`), route toàn cục `"*"`, và các điều kiện lọc effort (`"matching.rank[effort=high]"`, `"matching.*[effort>=medium]"`). Trong một phạm vi scope, selector cụ thể nhất sẽ thắng: một route cụ thể thắng ký tự đại diện namespace, ký tự đại diện namespace thắng `"*"`, và một điều kiện effort chặt chẽ hơn sẽ thắng điều kiện lỏng hơn.

Các route mang prompt bao gồm:

`react`
: Responder. Cả system instructions và per-turn instructions của nó đều được build thông qua provider của route này.

`matching.rank`
: Đánh giá rule theo từng lượt (rule ranker) **và** lược bớt các rule được phát hiện (rule pruner). Cả hai dùng chung một route; các provider phân biệt chúng bằng tên section (`p.PromptSections.Ranker` so với `p.PromptSections.Pruner`).

`review.message` / `review.tools`
: Đánh giá tin nhắn và lời gọi tool.

`compaction`
: Nén phiên hội thoại (xem [Nén Phiên Hội Thoại](compaction.md)).

**LƯU Ý:** Các route embedding và tokenizer không chứa prompt; cấu hình provider cho chúng sẽ không có tác dụng.

**Theo scope.** Các provider có thể đăng ký trên toàn server (như trên) hoặc theo từng agent, và phạm vi agent sẽ được ưu tiên cao hơn (ghi đè cấu hình ở cấp server):

```python
agent = await server.create_agent(
    id="my-agent",
    name="Support Agent",
    instructions="...",
    prompts={"matching.rank[effort=high]": MyCarefulRankerPrompt},
)
```

## Tra cứu tên các section

Mỗi tên section đều là API ổn định và đã được đăng ký. Mỗi component hiển thị một enum `PromptSections` ngay bên cạnh prompt của nó, và SDK tập hợp chúng dưới một namespace duy nhất — do đó tính năng tự động gợi ý code (autocomplete) với `p.PromptSections` sẽ hiển thị đầy đủ registry:

- `p.PromptSections.Responder` — các chỉ dẫn hệ thống (system) và theo từng bước (per-step)
- `p.PromptSections.Ranker` — đánh giá rule theo từng lượt
- `p.PromptSections.Pruner` — lược bớt các rule được khám phá
- `p.PromptSections.Reviewer` — cả hai prompt đánh giá review (`.MESSAGE_*` / `.TOOLS_*`)
- `p.PromptSections.Compacter` — nén phiên hội thoại
- `p.PromptSections.MatchingCommon` — các đoạn prompt dùng chung cho nhiều prompt (các thuật ngữ rule, reasoning của agent)

Hãy so sánh theo các hằng số enum, không nên dùng chuỗi ký tự thô. Bộ kiểm thử trong repository đảm bảo không prompt nào chứa tên chưa đăng ký, nên các enum này là đầy đủ. Các section được thêm bởi các helper chung của builder (danh tính agent, thuật ngữ glossary, lịch sử tương tác, v.v.) mang tên `BuiltInSection` của `p.PromptBuilder`. `adapt_section` cũng nhìn thấy những section đó, vì vậy bạn có thể viết lại hoặc dùng `p.VETO` đối với chúng theo cùng một cách.

## Các quy tắc cần tuân thủ

- **Đảm bảo tính tất định (deterministic):** Các prompt được tách thành phần tiền tố cố định được cache và phần đuôi biến động trực tiếp, và prompt cache sử dụng khóa theo từng byte chính xác. Một prompt provider có kết quả thay đổi giữa các lần gọi (do timestamp, sắp xếp ngẫu nhiên, closure biến đổi) sẽ âm thầm vô hiệu hóa tính năng prompt caching và làm tăng chi phí. Hãy tùy biến *cách prompt diễn đạt*, không phải *nội dung theo từng lần gọi* — Parlant sẽ cung cấp nội dung theo từng lần gọi thông qua props.
- **Provider chạy mỗi khi xây dựng prompt:** Giữ cho mã nguồn nhẹ và chạy nhanh; hãy thực hiện mọi khâu chuẩn bị tốn kém tài nguyên tại thời điểm import.
- **Log theo vết (trace logging) được giữ tự động:** Parlant gắn listener `on_build` của nó vào bất kỳ đối tượng nào mà provider của bạn trả về — bạn không cần phải chuyển tiếp thủ công bất cứ thứ gì, và các listener của riêng bạn sẽ được kết hợp cùng chứ không bị ghi đè.
