# Metadata của Session và Event (Session and Event Metadata)

## Tóm tắt tổng quan

Metadata của ứng dụng luôn nằm ở cấp cao nhất (top level) của metadata trong session và event. Các chú thích (annotations) do Parlant sở hữu và lưu trữ bền vững sẽ nằm dưới object dành riêng `__parlant__`. Trong suốt một lượt tương tác (turn), Compass sẽ lưu tạm (stage) các thay đổi session nội bộ trong bộ nhớ và commit chúng cùng nhau với cơ chế bảo vệ compare-and-swap (CAS) khi quá trình xử lý hoàn tất.

## Phân định quyền sở hữu (Ownership)

Một session với đầy đủ dữ liệu có cấu trúc tổng thể như sau:

```json
{
  "application_key": "thuộc quyền sở hữu của ứng dụng",
  "__parlant__": {
    "schema_version": 1,
    "auth": {
      "guest_instance_id": "guest-instance-id"
    },
    "compass": {
      "input_checkpoint": {
        "event_id": "event-id",
        "offset": 12,
        "modified_utc": "2026-07-28T10:29:59+00:00",
        "content_sha256": "hex-encoded-sha256"
      },
      "needs_rebuild": false,
      "discovered_rule_ids": ["rule-id"],
      "evicted_discovered_rules": {
        "old-rule-id": 8
      },
      "last_discovered_rule_pruning_offset": 8,
      "session_terms": {
        "term-id": 12
      }
    },
    "usage": {
      "records": {},
      "baselines": {}
    },
    "voice": {
      "channel": "room-id",
      "participant": "participant-id"
    }
  }
}
```

Một event có thể chứa các chú thích của ứng dụng bên cạnh các chú thích nội bộ của Parlant đặc thù cho từng loại event:

```json
{
  "application_annotation": "thuộc quyền sở hữu của ứng dụng",
  "__parlant__": {
    "schema_version": 1,
    "diagnostic_report_uri": "/debug/reports/trace-id",
    "source": "compacter",
    "reasoning": true,
    "provider_data": {},
    "voice": {
      "speculative": false,
      "spoken_text": "Các từ ngữ thực tế đã phát qua giọng nói"
    }
  }
}
```

Ví dụ về event ở trên là dạng tổng hợp đầy đủ để tham khảo. Hầu hết các loại event chỉ chứa một hoặc hai trường nội bộ trong số đó.

## Sử dụng metadata của ứng dụng

Tạo các session và event với các key thông thường ở cấp cao nhất:

```python
session = await client.sessions.create(
    agent_id=agent_id,
    metadata={"account_tier": "gold"},
)

await client.sessions.create_event(
    session_id=session.id,
    kind="message",
    source="customer",
    message="Hello",
    metadata={"channel": "web"},
)
```

Các API cập nhật sử dụng các thao tác `set` và `unset` ở cấp cao nhất. Chúng giữ nguyên cả các key của ứng dụng không được nhắc đến lẫn namespace nội bộ:

```python
await client.sessions.update(
    session_id=session.id,
    metadata={
        "set": {"account_tier": "platinum"},
        "unset": ["temporary_flag"],
    },
)
```

Object `__parlant__` có thể đọc được vì client và giao diện tích hợp cần sử dụng một số chú thích nội bộ, nhưng ứng dụng không được phép ghi đè lên nó. Các thao tác tạo session, tạo event, cập nhật qua API/SDK và cập nhật tunnel sẽ từ chối mọi nỗ lực `set` hoặc `unset` đối với nó. Không sử dụng các tên bên dưới object này làm nơi lưu trữ của ứng dụng.

Lưu ý sự khác biệt giữa metadata này với thuộc tính `metadata` cùng tên trên một *kết quả công cụ (tool result)* (`result.metadata`, nằm lồng bên trong một tool event). Đó là một kênh riêng biệt chỉ dành cho frontend — không phải là metadata của event được mô tả ở đây — và là cách chuẩn để một tool trả về file hoặc dữ liệu UI cho frontend. Xem thêm [Nội Dung Đa Phương Tiện (Rich Content)](../rich-content.md).

## Hành vi của Compass trong một lượt tương tác (Turn)

Compass nạp một snapshot metadata có phiên bản và tạo ra một `SessionMetadataWorkspace`. Các tính năng rule discovery, gợi nhớ glossary, hạch toán ngân sách, hooks và các helper SDK cùng tiến trình sẽ chia sẻ view chỉ đọc động của workspace này. Các đột biến nội bộ sẽ nối tiếp các thao tác có định kiểu (typed operations) vào một nhật ký trong bộ nhớ (in-memory journal) và không thực hiện bất kỳ thao tác I/O nào với database.

Một thao tác ghi metadata tường minh từ SDK thông qua hook vẫn được lưu trữ bền vững ngay lập tức. Workspace sẽ rebase session được trả về và phát lại các thao tác nội bộ đã lưu tạm, nhờ đó cả hai thay đổi đều hiển thị rõ ràng. Khi lượt tương tác hoàn tất bình thường, Compass áp dụng nhật ký này vào phiên bản sửa đổi (revision) mới nhất được lưu trữ và thực hiện một bản cập nhật metadata có điều kiện. Một lượt tương tác không có thay đổi sẽ không thực hiện cập nhật metadata nội bộ. Khi xảy ra xung đột phiên bản sửa đổi, Compass đọc lại session, phát lại các thao tác đã lưu tạm trên snapshot mới và thử commit lại trong một số lần giới hạn.

```text
API event     Compass          Workspace              Session store
    |            |                 |                         |
    |----------->| nạp session     |                         |
    |            |---------------->| snapshot gốc + revision |
    |            | khớp / gợi nhớ  |                         |
    |            |---------------->| lưu tạm typed operations|
    |            | SDK user set ---------------------------->|
    |            |                 |<---- kết quả rebase ----|
    |            | phản hồi        |                         |
    |<--- ready -|                 |                         |
    |            | commit journal  |---- CAS revision ------>|
    |            |                 |<--- session đã commit --|
```

Sự kiện kết thúc `ready` biểu thị quá trình stream phản hồi đã kết thúc. Quá trình nén sau phản hồi (post-response compaction), cắt tỉa (pruning), thu thập mức độ sử dụng và commit metadata vẫn có thể đang tiếp tục hoàn tất. Ranh giới bền vững nội bộ là việc hoàn tất của `CompassEngine.process()`. Một lượt tương tác kế tiếp trong cùng một tiến trình server sẽ đợi quá trình hoàn tất đó; một thao tác đọc bên ngoài không liên quan được thực hiện ngay sau khi thấy sự kiện `ready` có thể tạm thời nhìn thấy snapshot nội bộ trước đó trong chốc lát.

## Xử lý sự cố và Phục hồi (Failure and Recovery)

Khi một lượt tương tác bị hủy hoặc thất bại, Compass sẽ loại bỏ trạng thái thích ứng (adaptive state) mà nó đã lưu tạm trong lượt đó. Lượng tài nguyên sử dụng đã phát sinh vẫn có thể được giữ lại thông qua một commit chuyên biệt cho hạch toán chi phí. Các thao tác ghi SDK công khai và các sự kiện đã phát ra đã có hiệu lực bên ngoài, vì vậy chúng không bị rollback.

Checkpoint đầu vào của Compass xác định tin nhắn khách hàng gần nhất mà trạng thái thích ứng của nó đã được commit. Nó bao gồm event ID, offset và mã hash của văn bản đã tiêu thụ để phát hiện việc chỉnh sửa bản ghi âm giọng nói trực tiếp ngay cả khi ID và offset của nó không đổi. Việc xóa event sẽ đánh dấu session là `needs_rebuild`; một checkpoint event bị thiếu cũng sẽ được phát hiện ở lần nạp tiếp theo. Khi đó, Compass sẽ xóa các tập làm việc thích ứng có giới hạn của nó và tái tạo lại chúng từ tương tác đã nén còn tồn tại và các đầu vào tiếp theo của khách hàng.

## Tính an toàn khi cập nhật Event

Các chú thích nội bộ của event được đưa vào trong lần tạo ban đầu của event bất cứ khi nào có thể. Các chú thích xác nhận giọng nói và phân phối đến sau sẽ sử dụng bản vá compare-and-swap theo phiên bản metadata. Các thao tác set/unset event công khai cũng sử dụng cơ chế revision tương tự, đảm bảo rằng chú thích ứng dụng, cờ đầu cơ (speculative flag) và cập nhật văn bản đã nói (spoken-text) không thể âm thầm ghi đè lẫn nhau.

Metadata kết quả tool tuân theo cùng quy tắc sở hữu: metadata kết quả do tool tạo ra nằm ở cấp cao nhất, trong khi lỗi công cụ do Parlant tạo ra được lưu tại `result.metadata.__parlant__.error_details`.
