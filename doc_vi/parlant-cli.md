# Giao Diện Dòng Lệnh Parlant (The Parlant CLI)

Lệnh `parlant` đảm nhiệm 4 công việc chính: tạo dự án mới, trả lời các câu hỏi về Parlant dựa trên tài liệu hiện hành, sao chép widget chat vào ứng dụng của bạn và điều khiển Parlant Dashboard.

CLI được đóng gói sẵn cùng package Python `parlant`. Không cần cài đặt gì thêm:

```sh
pip install parlant
parlant --version
```

Mọi câu lệnh đều tự giải thích chức năng và hiển thị các ví dụ mẫu ở cuối phần trợ giúp:

```sh
parlant --help
parlant dashboard --help
parlant dashboard session view --help
```

Tài liệu này giới thiệu mục đích của các câu lệnh và cách chúng kết hợp với nhau. Sử dụng cờ `--help` để xem chính xác các cờ tham số.

## Khởi tạo một dự án (Starting a Project)

`parlant init` khởi tạo một dự án hoàn chỉnh mà bạn có thể chạy được ngay:

```sh
parlant init my-agent
```

Lệnh sẽ hỏi bạn sử dụng package manager nào (uv, pip, poetry hoặc conda) và tạo dự án phù hợp: các dependency, script `run.sh` và `run.cmd`, cùng cấu hình kiểm thử pytest. Bạn có thể bỏ qua câu hỏi bằng cờ `--package-manager`.

Có ba mẫu dự án (scaffolds) có sẵn:
- `basic` (mặc định): Cung cấp cấu trúc khung cơ bản, không chứa code mẫu.
- `retail-store`: Một agent hỗ trợ khách hàng với 2 miền nghiệp vụ: đơn hàng (orders) và khiếu nại (disputes).
- `lead-gen`: Agent cho website giúp trả lời thắc mắc của khách truy cập, sàng lọc khách hàng tiềm năng, chấm điểm bằng code và đặt lịch hẹn với nhân viên bán hàng.

```sh
parlant init my-agent --scaffold retail-store --package-manager uv
parlant init my-agent --scaffold lead-gen --package-manager uv
```

Sau đó:

```sh
cd my-agent
cp .env.example .env     # điền API key mô hình của bạn vào đây
./run.sh
```

Thư mục đích `DESTINATION` mặc định là thư mục hiện tại. Chạy `parlant init` không có tham số thư mục sẽ yêu cầu xác nhận trước. Một thư mục đã có sẵn vẫn hợp lệ: lệnh chỉ từ chối đối với từng file riêng lẻ mà nó có nguy cơ ghi đè. Cờ `--force` sẽ ghi đè lên các file đó.

Dự án cũng được tạo kèm file `AGENTS.md`. File này chỉ dẫn cho các AI coding agent biết Parlant là gì, cách bố trí dự án, và hướng dẫn tra cứu `parlant docs query` thay vì tự đoán các quy ước của framework. Nếu bạn đã có sẵn file `AGENTS.md`, lệnh `init` sẽ từ chối ghi đè lên nó.

## Tra cứu thông tin về Parlant

`parlant docs query` trả lời các câu hỏi dựa trên tài liệu hiện hành của Parlant và trích dẫn rõ nguồn gốc. Nó không bao giờ tự đoán: khi tài liệu không đề cập đến một nội dung nào đó, lệnh sẽ nêu rõ thay vì tự bịa ra câu trả lời:

```sh
parlant docs query "How do I add a tool to an agent?"
```

Truyền cờ `--context` kèm theo những gì bạn đang xây dựng, những gì bạn đã thử và đoạn mã nguồn liên quan. Câu trả lời sẽ cụ thể tương ứng với ngữ cảnh bạn cung cấp:

```sh
parlant docs query "Why is my policy not matching?" --context "$(cat domains/orders/domain.py)"
```

Đây chính là lệnh mà file `AGENTS.md` hướng dẫn các coding agent sử dụng, và bạn cũng nên tự mình dùng trước khi đưa ra một quyết định thiết kế kiến trúc:

```sh
parlant docs query "Should this be a policy or an observation?" --context "The rule is: never quote a price to an unpaid account."
```

Cờ `--json` trả về toàn bộ phản hồi dạng JSON — câu trả lời, trích dẫn, phiên bản tài liệu và lượng token sử dụng — dành cho các chương trình tự động:

```sh
parlant docs query "How do I test agent behavior?" --json
```

*Lưu ý bảo mật:* Câu hỏi và ngữ cảnh được gửi đến dịch vụ tài liệu của Parlant và nhà cung cấp mô hình của nó (với các dữ liệu nhạy cảm được che giấu để nhân viên xem xét). Không đưa credentials, dữ liệu khách hàng hoặc nội dung từ file `.env` vào đây.

## Widget Chat

`parlant widget init` sao chép mã nguồn của widget chat vào ứng dụng của bạn. Đây là thao tác copy file thông thường, do đó không cần chuỗi công cụ Node.js, và bạn toàn quyền chỉnh sửa bản sao này: thay đổi giao diện, đổi giao thức truyền tải, thêm các widget tool riêng:

```sh
parlant widget init ./web/chat
```

Thư mục `DESTINATION` mặc định là `parlant-chat`. Bản sao ghi lại phiên bản Parlant nguồn vì lớp transport của nó giao tiếp với API HTTP của phiên bản đó. Hãy chạy lại với cờ `--force` sau khi nâng cấp phiên bản Parlant.

Để xem thử widget hoạt động thực tế trước khi tích hợp, bạn có thể chạy môi trường thử nghiệm playground kết nối với một agent mẫu:

```sh
parlant widget playground
parlant widget playground --port 8000
```

Lệnh playground này yêu cầu có `npm` và API key mô hình.

## Bảng Điều Khiển Dashboard

Các lệnh quản lý dashboard nằm dưới nhóm `parlant dashboard`. Chúng được tích hợp sẵn trong repo này, đi kèm với package Python và không cần trình cài đặt riêng.

### Đăng nhập (Signing in)

```sh
parlant dashboard auth login
```

Bạn phê duyệt máy tính này trên trình duyệt cho một hoặc nhiều workspace. Mỗi workspace có phiên đăng nhập riêng, và workspace đầu tiên bạn chọn sẽ trở thành active.

```sh
parlant dashboard auth status
parlant dashboard workspace list
parlant dashboard workspace use WORKSPACE_ID
```

Lệnh `workspace use` thiết lập workspace mặc định cho các lệnh sau, giúp bạn không phải truyền `--workspace` mỗi lần. Bất kỳ lệnh nào cũng chấp nhận `--workspace` để ghi đè và `--project` để chọn dự án cần thao tác.

Trên máy không có trình duyệt (headless/SSH), cờ `--no-browser` sẽ in ra URL để bạn mở ở nơi khác. Khi một lệnh cần quyền hạn mà phiên đăng nhập chưa có, `--reauthorize` sẽ yêu cầu cấp thêm quyền mà không làm mất phiên đăng nhập hiện có.

```sh
parlant dashboard auth logout
parlant dashboard auth logout --all
```

### Kết nối dự án tự vận hành (Self-hosted)

Một dự án chạy trên máy của bạn kết nối với dashboard thông qua token dự án. Lệnh `project connect` sẽ lưu token đó vào file `.env` của thư mục:

```sh
parlant dashboard project connect ./my-agent
```

Lệnh `parlant init --dashboard` thực hiện cả hai việc cùng lúc: tạo dự án trên dashboard trước, đảm bảo dashboard chấp nhận rồi mới ghi file cục bộ và kết nối.

```sh
parlant init my-agent --dashboard --yes
```

Sau khi server của bạn khởi động:

```sh
parlant dashboard project check
parlant dashboard project confirm
```

### Tạo một dự án (Creating a project)

```sh
parlant dashboard project create
```

Khi chạy đơn lẻ, lệnh sẽ hướng dẫn bạn từng bước thiết lập. Đối với dịch vụ lưu trữ do Parlant quản lý (managed hosting), lệnh kết nối với GitHub, chọn repository và nhánh (branch). Quá trình kiểm tra setup check sẽ tự động chạy và hiển thị những gì nó phát hiện: lệnh run, lệnh build, phân loại repo, và các cảnh báo về biến môi trường hay secret còn thiếu.

Để tự động hóa (automation trong CI/CD), hãy truyền các tham số và xác nhận bằng `--yes`:

```sh
parlant dashboard project create \
  --kind managed --name MyAgent \
  --repo example/agent --branch main \
  --run-command 'python agent.py' \
  --build-command 'uv sync --frozen' \
  --build-env BUILD_MODE=production \
  --run-env APP_ENV=production \
  --secret API_KEY=MY_API_KEY \
  --yes
```

`--secret` nhận tên biến môi trường cục bộ để lấy giá trị, chứ không phải giá trị bí mật trực tiếp.

Nếu lệnh bị gián đoạn, hãy tái sử dụng request ID được in ra trước đó:

```sh
parlant dashboard project create --request-id PRINTED_REQUEST_ID --yes
```

### Xem thông tin dự án

```sh
parlant dashboard project list
parlant dashboard project describe PROJECT_ID
parlant dashboard agent list
parlant dashboard agent view AGENT_ID
```

### Triển khai (Deploying)

Dự án managed được triển khai từng lượt (attempt). Lệnh `deploy` sẽ build commit mới nhất trên nhánh đã cấu hình (hoặc commit chính xác bạn chỉ định):

```sh
parlant dashboard deploy
parlant dashboard deploy --commit COMMIT_SHA
```

Theo dõi và quản lý quá trình deploy:

```sh
parlant dashboard deployment list
parlant dashboard deployment view ATTEMPT_ID
parlant dashboard deployment logs ATTEMPT_ID --channel build --follow
parlant dashboard deployment stop ATTEMPT_ID
```

`deployment logs` hỗ trợ các kênh: `build` (mặc định), `deployment` (quá trình khởi động lên live) hoặc `runtime` (log của app đang chạy trực tiếp).

### Quản lý Secrets

Secrets là một phần trong cấu hình lưu trữ của dự án:

```sh
parlant dashboard secret list
parlant dashboard secret set STRIPE_API_KEY=value
parlant dashboard secret unset STRIPE_API_KEY
```

Để tránh lưu giá trị vào lịch sử shell, bạn có thể truyền qua stdin:

```sh
printf %s "$STRIPE_API_KEY" | parlant dashboard secret set STRIPE_API_KEY
```

Giá trị tối đa là 64 KiB. Dự án đang chạy sẽ giữ các secret mà nó đã khởi động cùng, vì vậy hãy chạy `parlant dashboard deploy` để áp dụng các thay đổi secret mới.

### Kiểm tra các Phiên hội thoại (Reading Sessions)

```sh
parlant dashboard session list
parlant dashboard session list --agent AGENT_ID --limit 20
parlant dashboard session view SESSION_ID
parlant dashboard session summary SESSION_ID
parlant dashboard session events SESSION_ID --kind tool
```

`session view` hiển thị phiên dưới dạng các lượt tương tác (turns). `session events` hiển thị luồng sự kiện thô (raw event stream), hữu ích khi bạn cần kiểm tra chi tiết các lệnh gọi tool hoặc thứ tự sự kiện.

Khi agent hành xử không đúng như kỳ vọng, lệnh `session inspect` giúp phân tích tại sao lượt tương tác đó lại diễn ra như vậy:

```sh
parlant dashboard session inspect SESSION_ID --turn TURN_ID
parlant dashboard session inspect SESSION_ID --turn TURN_ID --include-logs
```

Xem trace từ phía engine:

```sh
parlant dashboard trace view TRACE_ID
```

### Báo cáo sử dụng và Logs

```sh
parlant dashboard analytics view --range last-7-days
parlant dashboard analytics labels --range last-30-days
parlant dashboard logs
```

## Định dạng đầu ra cho lập trình (Output for programs)

Các lệnh hỗ trợ cờ `--json` sẽ in kết quả sạch ra stdout và các thông báo khác ra stderr:

```
parlant init
parlant docs query
parlant dashboard auth login | logout | status
parlant dashboard workspace list | use
parlant dashboard project check | confirm | connect | create | list
```

Khi có lỗi, đầu ra sẽ có định dạng: `{"error": {"code": ..., "message": ...}}` kèm theo mã thoát (exit code) tương ứng.

## Giới hạn mức sử dụng CLI của Workspace (Allowances)

Một số thao tác đọc từ dashboard được gom chung hạn ngạch giữa các thành viên, credential và dự án trong một workspace, bao gồm 3 hạn mức: đọc trace, đọc log và inspect.

Các lệnh tiêu tốn hạn ngạch:

```sh
parlant dashboard trace view TRACE_ID
parlant dashboard session inspect SESSION_ID --turn TURN_ID
parlant dashboard logs
parlant dashboard deployment logs ATTEMPT_ID
```

Khi hết hạn ngạch, lệnh sẽ thông báo loại hạn ngạch đã hết, giới hạn, số lượng còn lại, thời điểm làm mới và thoát với mã trạng thái **7**.

## Bảng mã thoát (Exit Codes)

| Mã lỗi | Ý nghĩa |
| --- | --- |
| 0 | Thành công |
| 1 | Lệnh thất bại; thông báo nêu rõ lý do |
| 2 | Cú pháp dòng lệnh sai (sai cờ, thiếu đối số) |
| 7 | Đạt giới hạn hạn ngạch CLI hoặc giới hạn thời lượng stream log của Workspace |
