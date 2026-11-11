# Chẩn Đoán và Đo Lường Từ Xa (Diagnostics and Telemetry)

Parlant cung cấp ba hình thức đo lường vận hành (telemetry) bổ trợ cho nhau:

- Các báo cáo chẩn đoán (diagnostic reports) cho các lượt tương tác và lỗi gần đây của engine;
- File log server cục bộ `parlant.log`;
- Tùy chọn xuất OpenTelemetry traces, logs, và metrics.

Báo cáo chẩn đoán là một tính năng duy nhất với hai kết quả (outcomes). Mọi lượt chạy của engine được lưu giữ đều có thể được xuất ra trong một file nén. Một báo cáo có kết quả là `error` sẽ chứa cùng dữ liệu bằng chứng trace như một báo cáo thành công, cộng thêm thông tin exception và traceback. Cả hai kết quả đều dùng chung định dạng và API.

## Cấu hình File System

`PARLANT_HOME` là thư mục cơ sở cho trạng thái lưu trữ bền vững của Parlant. Nếu không được đặt, Parlant mặc định dùng `./parlant-data` (tương đối theo thư mục làm việc của tiến trình server). Các file artifact telemetry sử dụng các giá trị mặc định sau:

| Loại Artifact | Biến môi trường ghi đè | Mặc định |
| --- | --- | --- |
| Báo cáo lỗi chẩn đoán | `PARLANT_ERROR_REPORTS_DIR` | `${PARLANT_HOME}/diagnostic-reports/errors` |
| File xuất trace tạm thời | `PARLANT_TRACE_REPORTS_DIR` | `${PARLANT_HOME}/diagnostic-reports/traces` |
| Log cục bộ | `PARLANT_LOGS_DIR` | `${PARLANT_HOME}/logs` |

File log cục bộ đang hoạt động là `${PARLANT_LOGS_DIR}/parlant.log`.

Biến môi trường đặc thù cho từng artifact sẽ được ưu tiên hơn `PARLANT_HOME` chỉ riêng cho artifact đó. Điều này cho phép bạn đặt báo cáo và log trên các ổ đĩa (volumes) có chính sách kích thước, lưu giữ, bảo mật hoặc vòng đời khác nhau:

```bash
export PARLANT_HOME=/var/lib/parlant
export PARLANT_ERROR_REPORTS_DIR=/mnt/restricted/parlant/errors
export PARLANT_TRACE_REPORTS_DIR=/mnt/diagnostics/parlant/traces
export PARLANT_LOGS_DIR=/var/log/parlant
```

Đường dẫn tương đối được phân giải theo thư mục làm việc của tiến trình server. Hãy thiết lập các biến này trước khi khởi động hoặc import server vì các đường dẫn runtime và logger cục bộ được cấu hình ngay khi khởi tạo module.

Các thư mục báo cáo lỗi và xuất tạm thời được tạo với quyền hạn chỉ dành cho chủ sở hữu (`0700`), và các file nén archive với quyền đọc/ghi chỉ dành cho chủ sở hữu (`0600`) khi hệ điều hành cho phép. Các thư mục và file log cục bộ cũng tuân theo cùng chính sách quyền hạn này.

## Báo cáo Chẩn đoán (Diagnostic Reports)

Tính năng báo cáo chẩn đoán được bật theo mặc định. Trong Python SDK:

```python
import parlant.sdk as p

async with p.Server(diagnostic_reports=True) as server:
    ...
```

Để tắt hoàn toàn việc thu thập và lưu trữ chẩn đoán:

```python
async with p.Server(diagnostic_reports=False) as server:
    ...
```

Chỉ các lượt tương tác của engine mới được đưa vào lịch sử chẩn đoán. Các trace HTTP thông thường như health check hay liệt kê danh sách sẽ bị hủy bỏ khi đối tượng sở hữu cuối cùng trong bộ nhớ kết thúc.

### Lưu trữ và Thời gian lưu giữ (Storage and Retention)

Các lượt tương tác engine đã hoàn tất được lưu giữ dưới dạng các snapshot có giới hạn trong bộ nhớ tiến trình (RAM). Parlant không nén hoặc ghi trace thành công ra đĩa khi lượt chạy kết thúc. Nó chỉ tạo file ZIP nếu quản trị viên yêu cầu trace đó thông qua API export, lưu tạm trong `PARLANT_TRACE_REPORTS_DIR` trong lúc truyền dữ liệu và xóa ngay sau khi phản hồi xong. Việc nén ZIP chạy trong thread-pool của server để không làm nghẽn event loop bất đồng bộ. Lịch sử trong bộ nhớ này sẽ mất khi tiến trình kết thúc.

Các trường hợp lỗi được xử lý khác biệt: báo cáo của chúng được ghi ngay xuống đĩa và lưu giữ tại đó. Một archive lỗi được ghi vào `PARLANT_ERROR_REPORTS_DIR` ngay khi exception được bắt lại, sau đó hoàn thiện tại chỗ khi lượt tương tác kết thúc. Điều này giúp URI trong sự kiện lỗi có thể sử dụng được ngay lập tức và giúp dữ liệu chẩn đoán lỗi vẫn tồn tại sau khi server khởi động lại.

Chính sách lưu giữ là hợp của hai chính sách:

```text
chẩn đoán khả dụng = N lượt engine gần nhất trong bộ nhớ ∪ M archive lỗi gần nhất
```

- `N` là `PARLANT_TRACE_HISTORY_SIZE`, mặc định `32`.
- `M` is `PARLANT_ERROR_HISTORY_SIZE`, mặc định `8`.

Một lỗi được tính là một trong N lượt gần nhất và có một file archive bền vững trong thư mục lỗi; nó không bao giờ bị nhân bản trong thư mục trace. Một archive lỗi cũ hơn vẫn khả dụng nếu nó vẫn nằm trong top M kết quả lỗi gần nhất. Một trace thành công sẽ không còn khả dụng khi snapshot trong bộ nhớ của nó rời khỏi top N lượt gần nhất.

Cấu hình lưu giữ chỉ được điều khiển qua biến môi trường:

```text
PARLANT_TRACE_HISTORY_SIZE=64
PARLANT_ERROR_HISTORY_SIZE=16
```

Đặt trace history bằng `0` để chỉ lưu các lỗi bền vững. Đặt error history bằng `0` để loại bỏ cơ chế bảo vệ bổ sung này. Đặt cả hai bằng `0` sẽ tắt hoàn toàn tính năng chẩn đoán. Cả hai giá trị phải là số nguyên không âm.

### Export API

Debug API chỉ dành cho quản trị viên cung cấp cả hai kết quả:

```http
GET /debug/reports
GET /debug/reports?limit=10
GET /debug/reports?outcome=success
GET /debug/reports?outcome=error
GET /debug/reports/{trace_id}
```

Danh sách được sắp xếp từ mới nhất đến cũ nhất, bao gồm trace ID, session ID, kết quả (outcome), thời gian tạo/hoàn tất, dung lượng archive và URI tải xuống. Dung lượng archive là `null` đối với trace thành công nằm trong bộ nhớ vì chưa có file ZIP nào được tạo. `limit` tối thiểu là `1`. `outcome` chấp nhận `success` hoặc `error`.

`/healthz` cũng hiển thị các báo cáo gần nhất trong danh sách `diagnostic_reports` (trace ID, outcome, thời gian tạo, và URI tải xuống `/debug/reports/{trace_id}`), giúp người vận hành khi kiểm tra sức khỏe hệ thống có thể nhảy thẳng tới các lượt chạy gần nhất. Số lượng báo cáo được cấu hình bằng `PARLANT_HEALTHZ_REPORT_LINKS` (mặc định là 3; `0` sẽ ẩn phần này). Các liên kết này chỉ hiển thị cho người gọi có quyền `read_health_report`, và việc tải báo cáo vẫn đòi hỏi quyền debug API của quản trị viên.

### Khả năng hiển thị của Endpoint Health

`/healthz` luôn trả về `200` với trường trạng thái `status` ở cấp cao nhất, do đó các bộ cân bằng tải (load balancers) và probe kiểm tra uptime có thể hoạt động mà không cần xác thực. Mọi chi tiết sâu hơn — kiểm tra từng component, phân vị độ trễ (latency percentiles), các nhóm lỗi và liên kết báo cáo — chỉ hiển thị cho người gọi được cấp quyền `read_health_report`.

Một archive lỗi ban đầu có thể tải xuống ngay từ event URI của nó, nhưng chưa xuất hiện trong danh sách liệt kê cho đến khi manifest của nó được hoàn tất. Endpoint tải xuống trả về `application/zip` với tên file `{trace_id}.zip`.

Ví dụ:

```bash
curl -H "Authorization: Bearer $PARLANT_ADMIN_TOKEN" \
  "$PARLANT_URL/debug/reports?outcome=error"

curl -fL -H "Authorization: Bearer $PARLANT_ADMIN_TOKEN" \
  -o report.zip \
  "$PARLANT_URL/debug/reports/6658572371514ad7897b3bef729a4603"
```

### Metadata của sự kiện lỗi

Khi một lỗi engine được bắt lại, sự kiện trạng thái (status event) phát ra sẽ chứa một URI dùng được ngay lập tức:

```json
{
  "metadata": {
    "__parlant__": {
      "schema_version": 1,
      "diagnostic_report_uri": "/debug/reports/6658572371514ad7897b3bef729a4603"
    }
  }
}
```

### Nội dung của file Archive

Mỗi file ZIP hoàn chỉnh bao gồm:

- `manifest.json`: Phiên bản schema, trace/session ID, phiên bản Parlant, timestamp, kết quả, độ hoàn chỉnh, tóm tắt exception và danh sách thành viên;
- `trace.json`: Dòng thời gian span cục bộ độc lập với exporter;
- `logs.jsonl`: Các lượt gọi logger ứng dụng định tuyến qua `container[Logger]` trong khi trace đang hoạt động;
- `session.json` và `events.jsonl`: Trạng thái phiên bền vững nếu khả dụng.

Các báo cáo lỗi có thêm file `traceback.txt` chứa toàn bộ traceback định dạng đầy đủ. Báo cáo thành công không tạo exception hay traceback giả mạo.

Đặc biệt, việc thu thập log chẩn đoán độc lập với mức log đầu ra của server: các lệnh gọi TRACE và DEBUG vẫn được ghi vào `logs.jsonl` ngay cả khi `parlant.log` hoặc OpenTelemetry được cấu hình ở mức INFO.

## Endpoint Kiểm Tra Sức Khỏe (Health Endpoint)

`GET /healthz` báo cáo trường `status` ở cấp cao nhất và một object `checks` chứa chi tiết từng component:

- `engine`: Tỷ lệ thành công và thời lượng phân vị p95 của các lượt gần đây.
- `nlp`: Tỷ lệ thành công và độ trễ p50/p95 của các yêu cầu mô hình, theo từng route model, kèm phân rã theo từng agent bên trong mỗi route.
- `event_loop`: Tỷ lệ thời gian event loop bị trễ (lagging) trong 5 phút gần nhất và mức lag đỉnh điểm. Lag nghĩa là có tác vụ đang chặn loop (thường là một tool chạy đồng bộ synchronous).
- `tunnel`: Trạng thái kết nối tới Parlant Dashboard (chỉ áp dụng cho các dự án managed).

Mỗi component có trạng thái `healthy`, `degraded` hoặc `unhealthy`. Trạng thái cấp cao nhất là trạng thái tồi nhất trong số chúng. Mục `engine` và `nlp` cũng liệt kê trường `reasons` nêu rõ ngưỡng nào bị vi phạm cùng giá trị quan sát được.

### Ngưỡng trạng thái (Status Thresholds)

Các mốc giới hạn nằm trong đối tượng `HealthThresholds` được bind trên container. Hãy cấu hình lại trong `configure_container` nếu muốn thay đổi:

| Hạng mục | Ngưỡng | Degraded | Unhealthy |
| --- | --- | --- | --- |
| `engine` | Tỷ lệ thành công dưới | 0.95 | 0.80 |
| `engine` | Độ trễ lượt p95 đạt hoặc vượt | 30 s | 60 s |
| `nlp` | Tỷ lệ thành công dưới | 0.95 | 0.80 |
| `nlp` | Độ trễ yêu cầu p50 đạt hoặc vượt | 20 s | 30 s |
| `nlp` | Độ trễ yêu cầu p95 đạt hoặc vượt | 45 s | 60 s |
| `event_loop` | Mức lag tích lũy đạt 1% cửa sổ thời gian (3s) | 200 ms | 500 ms |

Bốn route trên đường dẫn phản hồi có các ngưỡng ghi đè chặt chẽ hơn:

| Route | p50 degraded / unhealthy | p95 degraded / unhealthy |
| --- | --- | --- |
| `matching.rank` | 8 s / 12 s | 15 s / 20 s |
| `matching.distill` | 8 s / 12 s | 15 s / 20 s |
| `review.message` | 10 s / 15 s | 20 s / 25 s |
| `review.tools` | 10 s / 15 s | 20 s / 25 s |

Ví dụ tùy chỉnh ngưỡng:

```python
import parlant.sdk as p


async def configure_container(container: p.Container) -> p.Container:
    container[p.HealthThresholds] = p.HealthThresholds(
        nlp=p.NLPHealthThresholds(
            degraded_p95_ms=90_000.0,
            unhealthy_p95_ms=120_000.0,
            routes={
                **p.default_nlp_route_thresholds(),
                "review.message": p.RouteThresholds(
                    degraded_p95_ms=40_000.0,
                    unhealthy_p95_ms=60_000.0,
                ),
            },
        ),
        event_loop=p.EventLoopHealthThresholds(
            degraded_lag_ms=100.0,
            unhealthy_lag_ms=250.0,
        ),
    )
    return container


async def main() -> None:
    async with p.Server(configure_container=configure_container) as server:
        ...
```

## Log Cục Bộ và Xoay Vòng Log (Rotation)

Parlant ghi log server cục bộ vào:

```text
${PARLANT_LOGS_DIR}/parlant.log
```

Tính năng xoay vòng log theo kích thước được bật mặc định:

| Cài đặt | Biến môi trường | Mặc định |
| --- | --- | --- |
| Dung lượng file đang hoạt động tối đa | `PARLANT_LOG_ROTATION_MAX_BYTES` | `10485760` (10 MiB) |
| Số lượng bản backup xoay vòng | `PARLANT_LOG_ROTATION_BACKUP_COUNT` | `5` |

Khi bản ghi tiếp theo đẩy `parlant.log` vượt quá dung lượng cấu hình, logger sẽ xoay vòng trước khi ghi:

```text
parlant.log      file hiện tại
parlant.log.1    bản backup mới nhất
parlant.log.2
...
parlant.log.5    bản backup cũ nhất
```

Bản backup cũ nhất sẽ bị xóa khi có lượt xoay vòng mới vượt quá số lượng backup cấu hình. Đặt kích thước tối đa bằng `0` để tắt tính năng xoay vòng.

Nếu `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT` được cấu hình, log ứng dụng sẽ được gửi qua OpenTelemetry thay vì ghi xuống file cục bộ.

## OpenTelemetry

Parlant tự động kích hoạt các exporter OpenTelemetry khi các biến endpoint chuẩn được cấu hình:

- `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`
- `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT`
- `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT`

Báo cáo chẩn đoán không phụ thuộc vào OpenTelemetry exporter bên ngoài; span timeline cục bộ và buffer log vẫn hoạt động song song độc lập.
