# Hot Reload (Tải lại Nhanh)

Chỉnh sửa script của agent không nhất thiết phải khởi động lại thủ công. Khi tính năng hot reload được bật — và nó được bật theo mặc định — server sẽ theo dõi thư mục chứa script của bạn và tự động khởi động lại ngay khi bạn lưu một file Python:

```
Hot reload: change detected (/home/dev/my_agent.py); restarting the server
Hot reload: restarting...
```

Chỉ cần lưu file của bạn, chuyển sang giao diện chat UI, làm mới trang (refresh) và trò chuyện với agent đã được cập nhật. Bạn không cần phải làm thêm thao tác nào khác.

## Cách thức hoạt động

`p.Server(hot_reload=True)` (mặc định) sẽ theo dõi đệ quy **thư mục chứa script khởi chạy (entry script)** của bạn để phát hiện các thay đổi đối với file Python. Khi có thay đổi đầu tiên, nó sẽ:

1. Ghi log file nào đã kích hoạt quá trình reload.
2. Tắt server theo quy trình hoàn toàn giống như khi bấm Ctrl-C — các công việc đang xử lý dở (in-flight) được hoàn tất, các background task dừng lại, các port được giải phóng.
3. Thay thế tiến trình hiện tại bằng một lượt chạy mới của câu lệnh gốc (`uv run my_agent.py`, `python my_agent.py --whatever` — toàn bộ argv được giữ nguyên vẹn). Tiến trình và PID vẫn giữ nguyên; server bên trong nó sẽ khởi động lại hoàn toàn mới.

Script của bạn sau đó sẽ thực thi lại từ đầu: các agent và policy được tạo lại chính xác như trong bất kỳ lần khởi động lại nào. Do quá trình đánh chỉ mục rule (rule indexing) được lưu cache trên đĩa (`indexing_cache.json` trong thư mục home của Parlant, mặc định là `./parlant-data` trừ khi bạn đặt biến `PARLANT_HOME`), nên việc đánh giá lại các policy không thay đổi diễn ra rất nhanh. Thời gian reboot chủ yếu chỉ phụ thuộc vào thời gian khởi động thông thường của server.

## Những điều tính năng này chủ ý KHÔNG làm

- **Không vá lỗi trực tiếp trong tiến trình (in-process patching):** Toàn bộ script sẽ được chạy lại từ đầu. Đây chính là mục đích thiết kế: mọi loại chỉnh sửa — đổi tên agent, xóa policy, thay đổi tool, đổi thư viện import — đều được xử lý chính xác vì không sử dụng cơ chế so sánh diff hay patch chắp vá.
- **Không giám sát vòng lặp sự cố (crash-loop supervision):** Nếu chỉnh sửa của bạn làm script bị crash ngay trong lúc khởi động, tiến trình sẽ thoát (exit) — sẽ không còn gì chạy để theo dõi bản sửa lỗi của bạn nữa. Hãy sửa file và khởi động lại một lần bằng tay.

## Khi nào tính năng tự tắt

- **Không có script khởi chạy dưới dạng file thực tế (No file-backed entry script):** trong môi trường REPL, Jupyter notebook hoặc embedded interpreter, không có file nào cụ thể để theo dõi (và việc re-exec sẽ khởi động lại host), do đó watcher sẽ tự động tắt.
- **Tắt tường minh:** `p.Server(hot_reload=False)`.

Trong môi trường production (môi trường sản xuất), không yêu cầu cấu hình đặc biệt nào: nếu các file trong container không bao giờ thay đổi, chi phí duy nhất chỉ là một file watcher ở trạng thái nhàn rỗi (idle). Bạn có thể thiết lập `hot_reload=False` để loại bỏ hoàn toàn chi phí đó.

## Lưu ý

- Thư mục gốc theo dõi là thư mục chứa *script của bạn* — nếu bạn chạy một script nằm trong một repository lớn hơn, các chỉnh sửa ở bất kỳ file Python nào trong cây thư mục đó đều kích hoạt reload, bao gồm cả các chỉnh sửa đối với Parlant được checkout cục bộ.
- Chỉ những thay đổi ở file `.py` mới kích hoạt reload (thông qua bộ lọc Python của `watchfiles`); việc chỉnh sửa các file dữ liệu, file prompt trên đĩa hoặc file `.env` sẽ không kích hoạt reload.
- Mỗi vòng đời tiến trình chỉ reload một lần: sau lần thay đổi đầu tiên, tiến trình hiện tại đã bắt đầu tắt, và tiến trình mới sẽ khởi chạy watcher riêng của nó.
