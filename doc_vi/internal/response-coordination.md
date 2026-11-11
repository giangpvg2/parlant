# Điều Phối Phản Hồi Trong Hàng Đợi (Queued Responses Within One Process)

MCN-453, thuộc MCN-427. Phạm vi thiết kế và triển khai được phê duyệt vào ngày 2026-11-08.
Source base: nhánh develop commit `cbe3311cf3a3a8282b94c7646410c8293d993068`.

## Quyết định và Giới hạn

Một bộ điều phối cục bộ theo tiến trình (process-local coordinator) kết hợp các yêu cầu phản hồi đã sẵn sàng, các background job đã đăng ký và các lượt trò chuyện thông thường của khách hàng cho một phiên hội thoại (session). Người dùng chấp nhận tính tương thích định tuyến dạng best-effort, rủi ro mất mát khi khởi động lại và khả năng xảy ra phản hồi cạnh tranh khi lưu lượng truy cập phân tán trên các pod riêng biệt. Tài liệu này thay thế cho đề xuất cross-pod/restart-safe được thảo luận trước đó vào ngày 2026-11-08.

Các kết quả tool đã hoàn tất và chi phí phát sinh vẫn giữ nguyên đường dẫn lưu trữ lịch sử/hạch toán bền vững hiện có. Hàng đợi và các đăng ký coroutine chỉ nằm trong bộ nhớ RAM (memory-only). Không có hàng đợi bền vững (durable queue), cơ chế thuê (lease), giao thức heartbeat/phục hồi, cơ chế transaction/outbox, quyền sở hữu từ xa, di chuyển event-offset hay tự động phát lại (replay) trong phiên bản V1 này.

## Giao ước SDK (SDK Contract)

```python
await agent.queue_response(session)

async def lookup_and_store() -> None:
    result = await lookup()
    await session.emit_tool_result(tool, result)

await agent.queue_response(session, after=lookup_and_store())
```

Lệnh `await` chỉ xác nhận việc lập lịch thành công, chứ không phải xác nhận văn bản phản hồi đã được sinh ra. Nếu bỏ qua tham số `session`, hệ thống sẽ tự động phân giải thành `Session.current`. Một coroutine truyền vào `after` được đăng ký trước khi kích hoạt và phải lưu kết quả trước khi kết thúc. Hãy đăng ký mọi job cần tham gia vào một batch; các task tùy ý và các job tương lai chưa được đăng ký sẽ vô hình đối với hệ thống điều phối.

Một job thất bại sẽ giải phóng trạng thái đăng ký của nó và được ghi log. Nó không tự ý bịa ra câu trả lời hay thử lại các công việc gây hậu quả lớn. Mã ứng dụng nên lưu lại kết quả lỗi nếu khách hàng cần một lời giải thích. Các job thành công khác vẫn tiếp tục bình thường. Một lượt sinh phản hồi thất bại sẽ giải phóng các yêu cầu của lần thử đó mà không thử lại vô tận; kết quả và chi phí đã hạch toán vẫn được lưu trữ bền vững cho các yêu cầu tường minh sau này.

## Điều gì xảy ra khi đang có một phản hồi tồn tại?

1. Một phản hồi ở foreground chỉ có thể đáp ứng các yêu cầu trong hàng đợi đối với các đầu vào (inputs) đã nằm trong snapshot của nó. Nó không chờ đợi các công việc đã đăng ký nhưng chưa hoàn thành.
2. Các kết quả mới xuất hiện trước khi văn bản trong hàng đợi hiển thị cho người dùng sẽ làm vô hiệu hóa câu trả lời chưa xuất bản và kích hoạt một lượt sinh phản hồi mới. Các job đã hoàn thành không bao giờ bị chạy lại.
3. Khi batch đã đăng ký hoàn tất xử lý, một phản hồi foreground chưa xuất bản văn bản cũng sẽ từ chối các kết quả đã sẵn sàng nhưng vắng mặt trong snapshot của nó; phản hồi kế tiếp trong hàng đợi sẽ tải lại lịch sử hội thoại. Trong khi các job vẫn đang chờ xử lý, một phản hồi ghi nhận ở foreground có thể tiếp tục mà không xóa các kết quả chưa được nhìn thấy.
4. Một khi văn bản đã hiển thị ra ngoài, nó sẽ được giữ nguyên. Các kết quả chưa được bao hàm sẽ tạo thành một phản hồi kế tiếp tự động, trừ khi một lượt tương tác mới của khách hàng đã kịp tích hợp chúng trước. Ba lệnh gọi không tạo ra ba phản hồi tiếp nối riêng lẻ, nhưng một câu trả lời đã hiển thị không thể hồi tố bao hàm các kết quả đến sau.
5. Một tin nhắn mới hơn từ khách hàng sẽ làm gián đoạn quá trình sinh phản hồi trong hàng đợi thông qua cơ chế dispatch phiên thông thường. Công việc đã đăng ký vẫn tồn tại kể cả khi lượt tương tác khởi sinh ra nó bị hủy.
6. Nếu một lượt tương tác của khách hàng đã trả lời các kết quả đã lưu trữ trong khi coroutine đã đăng ký của chúng vẫn đang hoàn tất việc ghi chép, thì việc coroutine này hoàn thành sau đó sẽ không tạo ra phản hồi dư thừa.

Các phản hồi thuần túy chạy ngầm (background-only) sử dụng `engine.utter`: chỉ dùng responder, không khớp lại rule mới hoặc gọi tool mới. Tin nhắn của khách hàng sử dụng quy trình xử lý thông thường. Chế độ thủ công (manual mode) sẽ chặn văn bản trong hàng đợi cả ở khâu dispatch lẫn publication. Lệnh `Agent.utter()` tường minh vẫn hoạt động độc lập. Việc hủy một phản hồi đang hoạt động trong hàng đợi thông qua API sẽ hủy worker cục bộ của nó, bao gồm cả các job và yêu cầu đang chờ xử lý còn lại.

## Ranh giới triển khai (Implementation Boundaries)

- `core/response_coordination.py`: Quản lý trạng thái cục bộ, đăng ký batch, độ bao phủ đầu vào (input coverage), các rào chắn xuất bản (publication guards) và vòng đời worker do service quản lý. Các callback sinh phản hồi và lịch sử được inject vào giúp nó độc lập với mô hình hay cơ sở dữ liệu cụ thể.
- `core/app_modules/sessions.py`: Cơ chế dispatch thông thường bắt đầu/kết thúc một lượt chạy foreground; quá trình render trong hàng đợi tái sử dụng việc theo dõi trace utter, hạch toán chi phí, chẩn đoán diagnostics và trạng thái hủy độc lập. Việc chọn runtime-store tuân theo các tín hiệu phát ra từ engine.
- `core/engines/compass/engine.py`: Báo cáo lịch sử thực tế đã được nạp, bao gồm cả lịch sử được đại diện bởi bản tóm tắt nén (compaction summary). Thời điểm dispatch không đồng nghĩa với độ bao phủ (coverage).
- `CoordinatedEventEmitter`: Bảo vệ các tin nhắn ban đầu và mọi streaming updater được trả về tại ranh giới lưu trữ bền vững. Các placeholder rỗng không được tính là văn bản hiển thị. Các sự kiện trạng thái vẫn sẵn sàng cho các listener lắng nghe hủy/hoàn thành. Các kết quả tool của chính engine sẽ mở rộng độ bao phủ; các phát thải độc lập từ background thì không.
- `sdk.py`: Cung cấp API lập lịch/đăng ký, kế thừa ngữ cảnh và các giới hạn có thể thực thi. Không có endpoint HTTP queue nào hoặc thay đổi nào đối với prompt đã cache của responder.

Định danh sự kiện của khách hàng và fingerprint chuẩn hóa của kết quả tool được dùng để nhận diện đầu vào. Cùng một lock phiên sẽ tuần tự hóa các cập nhật ý định đầu vào và các thao tác ghi tin nhắn thực tế; không có việc kiểm tra tính mới riêng lẻ rồi sau đó thực hiện ghi cục bộ không được bảo vệ. Người dùng gửi đến sẽ giữ trạng thái trong khi chờ lock đó. Một worker đã hoàn tất sẽ rút lui mà không cần lệnh await xen giữa; các worker bị hủy sẽ giải phóng các job của mình trước khi nhả trạng thái. Các coroutine ứng dụng chưa khởi chạy sẽ bị đóng khi đăng ký thất bại hoặc khi bị hủy trước lúc bắt đầu.

### Sửa chữa các trường hợp biên (Edge Cases) — 2026-11-08

Đánh giá ban đầu về tính sẵn sàng merge đã được thay thế sau đợt kiểm tra các trường hợp biên. 27 bài kiểm tra bổ sung ban đầu gây ra 7 lỗi: 4 trường hợp core và 3 trường hợp live SDK. Các câu lệnh assertion của chúng vẫn giữ nguyên trong quá trình sửa lỗi.

- Đối soát đầu vào của yêu cầu với dữ liệu store mới dưới khóa xuất bản (publication lock), thay vì diễn giải một snapshot mô hình cũ hơn như bằng chứng của việc xóa dữ liệu. Loại bỏ các yêu cầu đã bị hủy bỏ và giữ lại các kết quả vẫn còn liên quan. Xác thực trước khi sinh phản hồi và trước lần xuất bản hiển thị đầu tiên, mà không cần đọc lại toàn bộ lịch sử cho từng streaming chunk tiếp theo.
- Các đăng ký đồng thời sẽ cùng await tác vụ cài đặt worker. Một worker bị hủy trước khi bước vào coroutine của nó không thể sở hữu công việc mới của ứng dụng; quá trình đăng ký sẽ đóng công việc chưa bắt đầu đó và giải phóng trạng thái hàng đợi.
- Theo dõi các bản sao của các chunk thực sự đã được lưu bền vững bởi mỗi message handle. Hoàn tất một luồng stream bị gián đoạn bằng tiền tố đã commit đó cộng với ký tự kết thúc của nó, chỉ bỏ qua rào chắn văn bản cũ (stale-text guard) cho lần ghi đóng luồng này. Không flush bộ đệm trực tiếp của loop, nơi có thể đã chứa chunk tiếp theo chưa được xuất bản. Các sự kiện bị thiếu sau khi xóa không yêu cầu ghi thay thế; các lỗi đóng luồng khác được ghi log.
- Hàm `generateContent` của Gemini không thể bắt đầu lịch sử bằng một function response không có cặp gọi hàm trước đó. Hãy render các kết quả bên ngoài đứng đầu dưới dạng ngữ cảnh văn bản mà không tự bịa ra các lệnh gọi tool hay chữ ký hàm. Cơ chế replay gọi/kết quả native thông thường vẫn giữ nguyên; Interactions API vẫn giữ mã hóa hiện có.

Lỗi hồi quy khi sinh lại trực tiếp (live regeneration) ban đầu dừng lại ở lỗi giao thức Gemini; bản sửa lỗi adapter cho phép nó vượt qua các assertion về hàng đợi. Một kiểm tra tập trung về mã hóa ngoại tuyến đã thất bại trước khi sửa, trong khi một đối chứng native replay đã vượt qua. Bài test đóng gói payload hiện tại hiện cung cấp các lệnh gọi khớp nhau, giữ nguyên các assertion payload phản hồi ban đầu.

## Theo vết (Trace) và Hạch toán Chi phí

Mỗi câu trả lời trong hàng đợi được sinh ra sẽ có một trace mới và một bản ghi mức độ sử dụng mô hình (model-usage record), sử dụng đường dẫn export session-operation hiện có. Yêu cầu đang chờ xử lý mới nhất khi quá trình sinh bắt đầu sẽ cung cấp ngữ cảnh kế thừa từ lượt khởi sinh. Các yêu cầu đến sau đã được bao hàm bởi phản hồi đang chạy đó sẽ không làm thay đổi nguồn gốc trace của nó. Nếu không có lượt khởi sinh, câu trả lời sẽ sở hữu một lượt mới.

Mỗi kết quả tool vẫn giữ nguyên tham chiếu trace và lượt ban đầu của nó. Một phản hồi khách hàng ở foreground sở hữu mức sử dụng tài nguyên phản hồi thông thường của nó. Không sao chép bản ghi mô hình kết hợp vào từng job đóng góp: một phản hồi được sinh ra chỉ bị tính phí một lần. Không có cơ chế biểu diễn lượt đa cha (multi-parent turn) mới trong Dashboard. Các liên kết trace native và `__parlant__.turn_trace_id` tiếp tục thông qua cơ chế export/ingestion hiện có.

## Kiểm thử và Bằng chứng (Tests and Evidence)

Các bài kiểm thử và tiêu chuẩn triển khai đã được phê duyệt trước vào ngày 2026-11-08, bao gồm quyết định chỉ dùng responder. 10 trường hợp core ban đầu đã thất bại trên engine chưa thay đổi do coordinator chưa tồn tại. Baseline SDK với mô hình thực tế đầu tiên đã thất bại do thiếu API `Agent.queue_response`. Hai bài test hồi quy sau đó đã tái tạo lỗi chuyển giao trong khi sinh (handoff-during-generation) và lỗi hoàn thành sau một lượt đã trả lời (completion-after-an-already-answering-turn) trước khi các bản sửa lỗi được áp dụng.

`tests/core/stable/test_response_coordination.py` kiểm tra việc gom nhóm cục bộ, các batch đã đăng ký, độ bao phủ foreground, các thay đổi trước/sau xuất bản, sự gián đoạn, rào chắn streaming updater, thu hồi trạng thái nhàn rỗi, các session độc lập, các lỗi job/sinh phản hồi và tắt server. Các async barrier có kiểm soát và callback ghi nhận kiểm tra tính chuẩn xác về thời gian mà không cần mock SDK hay model.

`tests/sdk/test_queued_responses.py` kế thừa từ `SDKTest` và kiểm thử qua các đường dẫn HTTP, engine và model thực tế. Các semantic assertion đánh giá độ bao phủ kết quả phù hợp; các assertion chính xác kiểm tra số lượng tin nhắn, chế độ thủ công, việc hủy, chi phí lưu trữ, ngữ cảnh session hiện tại và quy kết trace. Các bài test kiểm tra việc phát thải session và hạch toán utter độc lập giúp bảo vệ tính tương thích ngược.

Quá trình xác minh cục bộ vào ngày 2026-11-08 sử dụng môi trường all-extras độc lập, không phải môi trường checkout chia sẻ. Không có kết nối production hay áp dụng của người dùng cuối nào nằm trong các bài kiểm tra này. Trình theo dõi workspace và Linear chứa kết quả chạy thực tế; một lần chạy cục bộ thành công không phải là bằng chứng triển khai production.
