# Nén Phiên Hội Thoại (Session Compaction)

Các phiên hội thoại kéo dài sẽ tích lũy lịch sử trò chuyện vô hạn. Tính năng compaction (nén) là cách Parlant giải quyết vấn đề đó: khi lịch sử tương tác của một phiên vượt quá một ngưỡng dung lượng nhất định, Parlant sẽ tóm tắt phần trước của cuộc trò chuyện thành một bản tóm tắt duy nhất lưu trữ bền vững và tiếp tục phiên hội thoại dựa trên bản tóm tắt đó. Kể từ thời điểm đó, mọi prompt mà Parlant xây dựng — để phản hồi, khớp rule, đánh giá review, cắt tỉa dữ liệu — chỉ nhìn thấy bản tóm tắt cùng với các sự kiện phát sinh sau thời điểm nén, thay vì toàn bộ lịch sử thô ban đầu.

Compaction được bật theo mặc định và không yêu cầu cài đặt thêm. Hướng dẫn này giải thích cách thức hoạt động, cách tinh chỉnh và cơ chế vận hành bên dưới — đủ để bạn dự đoán khi nào một phiên sẽ được nén, những gì còn tồn tại sau khi nén và cách debug khi cần.

## Động lực và Ý nghĩa

Ba áp lực lớn sẽ tích tụ dần khi một phiên hội thoại dài ra, và compaction giải tỏa toàn bộ các áp lực này:

- **Chi phí và độ trễ (Cost and Latency):** Mọi lệnh gọi mô hình trong một lượt tương tác — responder, xếp hạng rule song song, các review, truy vấn tìm kiếm rule — đều mang theo lịch sử tương tác, trực tiếp hoặc gián tiếp. Do đó, chi phí token sẽ tăng tuyến tính theo độ dài phiên, trên mọi lệnh gọi, ở mọi lượt tương tác. Vượt qua một giới hạn nhất định, bạn đang phải trả tiền cho cùng một đoạn hội thoại cũ kỹ hàng trăm lần lặp lại.
- **Chất lượng phản hồi (Response Quality):** Các mô hình chú ý kém tin cậy hơn trên các đoạn lịch sử quá dài; các chi tiết bị chôn vùi ở giữa một bản ghi khổng lồ rất dễ bị bỏ sót. Một bản tóm tắt có chủ đích, được viết dựa trên việc thấu hiểu các policy của agent, sẽ giữ lại các dữ kiện mang tính trụ cột dưới dạng thức mà mô hình thực sự chú ý tới.
- **Giới hạn ngữ cảnh (Context Limits):** Nếu không nén, một phiên hội thoại đủ dài cuối cùng sẽ tràn cửa sổ ngữ cảnh (context window) của mô hình và gây lỗi hoàn toàn.

Bản tóm tắt được viết rất cẩn trọng: nó được sinh ra với các chỉ dẫn rõ ràng để giữ lại chính xác những tài liệu mà lượt tương tác trong tương lai cần — các dữ kiện, cam kết, kết quả tool, các tác vụ chưa được giải quyết, trạng thái nhạy cảm với policy — và phân biệt rõ ràng giữa điều gì đã được xác nhận với điều gì chỉ là giả định.

## Các thuật ngữ chính

**Compaction marker (Dấu mốc nén)**
: Một sự kiện tin nhắn SYSTEM được lưu bền vững trong luồng sự kiện của phiên, mang nội dung tóm tắt và `metadata={"__parlant__": {"schema_version": 1, "source": "compacter"}}`. Nó vừa là bản ghi bền vững của bản tóm tắt, vừa là ranh giới phân tách "trước" và "sau": khi một lượt tương tác nạp phiên, mọi thứ trước dấu mốc cuối cùng sẽ được thay thế bằng bản tóm tắt của dấu mốc đó.

**Session summary (Bản tóm tắt phiên)**
: Văn bản của compaction marker gần nhất, được nạp vào `state.session_summary` ở mỗi lượt và được đưa vào prompt của mọi component bên cạnh các sự kiện diễn ra sau dấu mốc.

**Compaction policy (Chính sách nén)**
: Một cặp tham số theo từng mức effort gồm `token_threshold` (khi nào nén) và `detail_level` (mức độ chi tiết giữ lại). Parlant chọn policy theo mức dynamic effort của lượt tương tác (xem [Nỗ Lực Thích Ứng](adaptive-effort.md)).

**Detail level (Mức độ chi tiết)**
: `LOW`, `MEDIUM`, hoặc `HIGH` — quyết định mức độ nén mạnh hay nhẹ của bản tóm tắt. Xem chi tiết bên dưới.

## Khi nào quá trình nén được kích hoạt

Compaction chạy **sau khi** phản hồi của lượt tương tác đã được gửi đi, như một phần của giai đoạn hoàn tất (`finalize`) của engine. Người dùng không bao giờ phải chờ đợi quá trình này.

Tại giai đoạn finalize, Parlant ước tính số lượng token của lịch sử tương tác (các sự kiện kể từ lần nén trước, bao gồm cả câu trả lời vừa gửi đi) và so sánh nó với `token_threshold` của policy ứng với mức effort của lượt. Giá trị mặc định:

- Mức effort `MIN` / `LOW`: nén ở khoảng 24.000 tokens, mức chi tiết `LOW`.
- Mức effort `MEDIUM`: nén ở khoảng 32.000 tokens, mức chi tiết `MEDIUM`.
- Mức effort `HIGH`: nén ở khoảng 48.000 tokens, mức chi tiết `HIGH`.
- Mức effort `MAX`: nén ở khoảng 64.000 tokens, mức chi tiết `HIGH`.

Mức effort cao hơn sẽ chấp nhận một lịch sử thô dài hơn trước khi nén, và giữ lại nhiều thông tin hơn khi thực hiện nén. Điều này hoàn toàn khớp với ý nghĩa của effort: effort cao hơn sẽ chi tiêu nhiều hơn để giảm thiểu việc mất mát thông tin.

Lưu ý rằng mức effort được tham chiếu là mức effort *động* (dynamic effort), do đó một triggered effort từ một rule được khớp có thể thay đổi policy nào được áp dụng cho một lượt nhất định.

Những gì bạn quan sát thấy trong session khi compaction được kích hoạt:

1. Một sự kiện trạng thái (status event): `Compacting session`.
2. Một sự kiện tin nhắn SYSTEM do "System" tạo ra chứa bản tóm tắt, với `metadata.__parlant__.source == "compacter"` — chính là compaction marker. Các giao diện frontend không muốn hiển thị bản tóm tắt có thể lọc dựa trên trường metadata này.

Compaction được thiết kế theo nguyên tắc nỗ lực tối đa (best-effort): nếu việc tạo bản tóm tắt gặp lỗi, lỗi sẽ được ghi log và lượt tương tác hiện tại không bị ảnh hưởng — vì phản hồi đã được gửi đi từ trước. Lịch sử vẫn vượt ngưỡng, nên Parlant sẽ tự động thử lại ở cuối lượt tương tác tiếp theo.

## Các mức độ chi tiết (Detail Levels)

Mức độ chi tiết định hình các chỉ dẫn tóm tắt và lượng tài nguyên suy luận mà mô hình đầu tư:

- **LOW** — nén mạnh mẽ. Chỉ giữ lại các dữ kiện bền vững, mục tiêu tích cực của người dùng, các kết quả tool quan trọng, các tác vụ chưa hoàn thành và trạng thái nhạy cảm với policy. Mức suy luận tối thiểu.
- **MEDIUM** — bao gồm tất cả những gì LOW giữ, cộng thêm các điểm ra quyết định chính, các xác nhận, từ chối, và đủ trình tự thời gian để giải thích phiên đã đạt tới trạng thái hiện tại như thế nào. Mức suy luận thấp.
- **HIGH** — giữ lại các dữ kiện chính xác, các định danh (identifiers), sở thích, xác nhận, từ chối, các lệnh gọi tool và kết quả tóm tắt, các điểm chưa rõ ràng chưa được giải quyết, các chi tiết nhạy cảm với policy, và trạng thái mới nhất của mọi yêu cầu đang xử lý. Mức suy luận trung bình.

Dù ở mức độ nào, mô hình tóm tắt luôn được chỉ thị không bao giờ bịa đặt dữ kiện, không bao giờ đưa suy luận ẩn vào, và phải viết một bản tóm tắt thay thế hoàn toàn mọi bản tóm tắt trước đó.

## Cấu hình nén (Configuring Compaction)

Bảng policy nằm trên component `Compacter` và được thay thế bằng code thông qua các hook container của SDK. Hàm `set_policy` nhận một bảng ánh xạ hoàn chỉnh — mỗi mục tương ứng với một mức effort — và thực hiện kiểm tra tính hợp lệ:

```python
import parlant.sdk as p
from parlant.core.engines.compass.compacter import (
    Compacter,
    CompactionDetail,
    CompactionPolicy,
)


async def initialize(container: p.Container) -> None:
    container[Compacter].set_policy(
        {
            p.Effort.MIN: CompactionPolicy(
                token_threshold=16_000, detail_level=CompactionDetail.LOW
            ),
            p.Effort.LOW: CompactionPolicy(
                token_threshold=16_000, detail_level=CompactionDetail.LOW
            ),
            p.Effort.MEDIUM: CompactionPolicy(
                token_threshold=24_000, detail_level=CompactionDetail.MEDIUM
            ),
            p.Effort.HIGH: CompactionPolicy(
                token_threshold=32_000, detail_level=CompactionDetail.HIGH
            ),
            p.Effort.MAX: CompactionPolicy(
                token_threshold=48_000, detail_level=CompactionDetail.HIGH
            ),
        }
    )


async def main() -> None:
    async with p.Server(initialize_container=initialize) as server:
        ...
```

Hướng dẫn tinh chỉnh:

- **Ngưỡng thấp hơn** sẽ nén sớm hơn: giảm chi phí cho các phiên dài, nhưng tần suất gọi tóm tắt nhiều hơn và làm mất sớm lịch sử nguyên văn.
- **Ngưỡng cao hơn** sẽ giữ lại nhiều lịch sử thô hơn: độ trung thực tốt hơn cho các cuộc trò chuyện đòi hỏi trích dẫn nhiều, nhưng chi phí trên mỗi lượt tăng tuyến tính.
- **Detail level** là nút điều chỉnh độ trung thực/chi phí *bên trong* một lần nén. Nếu các phiên của bạn chứa nhiều mã định danh và yêu cầu đang xử lý (mã đơn hàng, trạng thái yêu cầu bồi thường), hãy ưu tiên chi tiết `HIGH` ngay cả ở các mức effort thấp hơn.

Mô hình tóm tắt được chọn thông qua routing dưới route `"compaction"` (việc ước lượng token sử dụng route `"tokenizer"`), do đó nó có thể trỏ tới một mô hình khác với responder thông qua service cấu hình mô hình, giống như bất kỳ route nào khác.

## Cơ chế hoạt động bên dưới (Under the Hood)

### Quá trình nạp: Marker chia tách phiên hội thoại

Khi một lượt tương tác bắt đầu, Parlant xây dựng dữ liệu tương tác đang xử lý bằng cách quét tuần tự các sự kiện của phiên. Mỗi khi gặp một compaction marker, nó sẽ loại bỏ tất cả những gì đã tích lũy trước đó và nạp bản tóm tắt của marker vào `state.session_summary`. Kết quả là: dữ liệu tương tác đang làm việc luôn là "bản tóm tắt gần nhất + mọi sự kiện diễn ra sau marker gần nhất". Bản thân sự kiện marker không phải là một phần của tương tác — nó là một ranh giới, không phải là một tin nhắn thoại.

Bởi vì marker là một sự kiện phiên được lưu bền vững, điều này hoàn toàn tất định (deterministic) qua các lần khởi động lại và giữa các tiến trình khác nhau: bất kỳ instance engine nào khi nạp phiên đều tái hiện cùng một góc nhìn đã nén.

### Trong suốt lượt tương tác: Mọi thành phần đều thấy Summary + Suffix

Bản tóm tắt không chỉ dành riêng cho responder. Mỗi component render nó theo cách riêng, luôn đi kèm với các sự kiện sau marker:

- **Vòng lặp phản hồi (response loop)** chèn một tin nhắn hệ thống ("Phần trước của phiên này đã được nén thành bản tóm tắt sau…") giữa chỉ dẫn hệ thống và lịch sử chat.
- **Reviewer**, **rule ranker**, và **rule pruner** đều render một section Session Summary trong prompt của chúng.
- **Các truy vấn khám phá của matcher** (gợi nhớ rule, gợi nhớ tool, phát hiện glossary) gắn thêm `Session summary: …` vào văn bản truy vấn mà chúng embed — nhờ đó việc gợi nhớ dựa trên điều gì đó đã thảo luận trước thời điểm nén vẫn hoạt động bình thường.

### Kích hoạt: Trình tự Finalize

Sau khi phản hồi được phát ra, Parlant chạy một chuỗi finalize được bảo vệ khỏi việc bị hủy, theo thứ tự sau:

1. **Refresh (Làm mới)** tương tác từ store, đảm bảo việc kiểm tra nhìn thấy câu trả lời vừa được gửi đi.
2. **Check (Kiểm tra)**: định dạng tương tác thành các dòng sự kiện JSON (loại trừ các sự kiện trạng thái status), ước tính token bằng tokenizer được định tuyến, so sánh với ngưỡng policy. Quá trình kiểm tra ghi log ở mức debug (`Compaction check: effort=…, tokens=…, threshold=…, needed=…`).
3. **Compact (Nén)** nếu cần thiết, cập nhật `state.session_summary` trong tiến trình và lưu bền vững sự kiện marker.
4. **Prune (Cắt tỉa)** tập làm việc của discovered-rule và glossary — việc này chủ ý diễn ra *sau* khi nén, để bộ cắt tỉa đánh giá độ cũ kỹ dựa trên bản tóm tắt mới thay vì lịch sử thô.
5. **Warm up (Làm ấm)** cache prompt cho lượt tiếp theo — bước cuối cùng, để các phần tiền tố được nạp sẵn phản ánh chính xác trạng thái đã nén.

Các bước 4–5 nằm sau cổng kiểm soát chi phí nền (background cost gate), nhưng bản thân compaction được miễn trừ khỏi cổng này: vì việc nén giúp *giảm* chi phí trong tương lai, nên việc chặn nén trong một sự kiện chi phí sẽ là phản tác dụng.

Trình tự này giải thích tại sao compaction không bao giờ làm chậm trải nghiệm của người dùng. Toàn bộ chuỗi xử lý diễn ra giữa các lượt tương tác. Compaction cũng làm thay đổi cấu trúc tiền tố prompt, gây ra cache miss tốn kém — nhưng bước làm ấm (warm-up) sẽ hấp thụ chúng trước khi tin nhắn tiếp theo của khách hàng tới.

### Prompt thực hiện nén

Bản tóm tắt được sinh ra bởi một lượt gọi dạng cấu trúc (schematic generation) duy nhất trên route `"compaction"`. Prompt bao gồm, theo thứ tự:

1. **Mô tả tác vụ (Task description)** — tóm tắt để lượt tương lai có thể tiếp tục chính xác; không trả lời người dùng; không bịa đặt dữ kiện; không để lộ suy luận ẩn; giữ lại dữ kiện, yêu cầu, cam kết, chi tiết nhạy cảm với policy, lời gọi tool và kết quả, xác nhận, từ chối, câu hỏi chưa giải quyết, thông tin còn thiếu, tác vụ còn lại; phân biệt dữ kiện đã xác nhận với giả định; thay thế hoàn toàn bản tóm tắt trước đó.
2. **Định dạng đầu ra (Output format)** — một JSON object với một trường duy nhất là `summary`.
3. **Chỉ dẫn mức độ chi tiết (Detail-level instructions)** — theo `detail_level` của policy.
4. **Toàn bộ chỉ dẫn hệ thống của agent** — định danh, khách hàng, biến ngữ cảnh, thuật ngữ glossary và toàn bộ danh mục rule (bao gồm cả các rule tham chiếu chéo được đưa vào tĩnh). Đây là điều làm cho bản tóm tắt *nhận biết được policy*: bộ tóm tắt biết chi tiết nào agent có nghĩa vụ phải hành động, nhờ đó nó biết cái gì tuyệt đối không được bỏ rơi.
5. **Bản tóm tắt phiên trước đó**, nếu có — các lần nén nối tiếp nhau dạng chuỗi, và mỗi bản tóm tắt mới sẽ bao hàm bản trước đó.
6. **Toàn bộ lịch sử tương tác** dưới dạng các sự kiện JSON.

Lệnh sinh này mang một gợi ý cache prompt theo từng session (mang khóa `<session_id>.compacter`, với điểm ngắt cache ở phần header lịch sử tương tác), do đó các lần nén lặp lại của cùng một phiên sẽ tái sử dụng tiền tố chỉ dẫn đã được cache và chỉ phải trả phí cho phần đuôi lịch sử mới.

### Nén nối tiếp (Chained compactions)

Không có gì đặc biệt xảy ra ở lần nén thứ hai, thứ ba hay thứ N: bản tóm tắt tích lũy từ trước là một phần của prompt nén, mô hình gộp nó vào bản tóm tắt mới và marker mới trở thành điểm chia tách của phiên. Các marker cũ và các sự kiện trước thời điểm nén vẫn nằm nguyên vẹn trong session store — compaction không bao giờ xóa lịch sử; nó chỉ thay đổi những gì Parlant nạp vào góc nhìn làm việc (working view).

## Gỡ lỗi (Debugging)

- **"Tại sao phiên này chưa được nén?"** — Kiểm tra debug log tìm các dòng `Compaction check:`; chúng in ra số lượng token ước tính, ngưỡng đang kích hoạt và mức effort đã chọn ngưỡng đó. Hãy nhớ rằng bước kiểm tra chạy sau khi đã gửi phản hồi, vì vậy một phiên vượt ngưỡng giữa lượt sẽ chỉ được nén ở cuối lượt đó, chứ không phải trong lúc đang xử lý.
- **"Tại sao agent quên mất thông tin X sau khi nén?"** — Tìm sự kiện marker trong phiên (tin nhắn SYSTEM, `metadata.__parlant__.source == "compacter"`) và đọc bản tóm tắt: thông tin X hoặc là không tồn tại qua khâu tóm tắt (hãy cân nhắc tăng `detail_level` hoặc tăng ngưỡng) hoặc là ngay từ đầu chưa từng xuất hiện trong lịch sử. Toàn bộ prompt nén có thể xem được ở mức trace log (`Compacter prompt:`).
- **"Compaction failed"** — Tìm dòng `Session compaction failed after response generation` trong error log; bản thân lượt tương tác không bị ảnh hưởng và Parlant sẽ tự động thử lại ở cuối lượt tiếp theo.
