# Quản Lý Khách Hàng (Customer Management)

Khách hàng (customer) là định danh mà Parlant lưu giữ cho một người dùng cuối (end user). Mọi phiên hội thoại đều thuộc về một khách hàng, các tool đọc thông tin khách hàng hiện tại để thực thi hành động thay mặt họ, và các rule bạn tạo ra có thể được giới hạn phạm vi áp dụng cho từng nhóm khách hàng cụ thể.

Một bản ghi khách hàng chứa các trường:

- **`id`** — mã định danh ổn định. Bạn nên ưu tiên sử dụng ID mà hệ thống hiện tại của bạn đã có (ID từ CRM hoặc database người dùng của bạn), giúp khách hàng duy trì một danh tính duy nhất xuyên suốt các hệ thống triển khai và tích hợp.
- **`name`** — tên hiển thị.
- **`metadata`** — các cặp key-value chuỗi ký tự mà các tool và hook có thể đọc (ví dụ: email, gói dịch vụ, ngôn ngữ ưa thích).
- **`groups`** — danh sách nhóm mà khách hàng là thành viên, dùng để giới hạn phạm vi rule và lọc khách hàng. Bạn định nghĩa các nhóm bằng code (`server.create_group`), và gán khách hàng vào nhóm khi chạy; các ID như `grp_vip` xuất phát từ các định nghĩa đó.
- **`kind`** — `real` (người thật) hoặc `persona` (nhân vật giả lập kiểm thử). Mặc định là `real`. Xem phần [Personas](#personas) bên dưới.

## Khách hàng vãng lai (Guest Customer)

Luôn có một khách hàng đặc biệt được tích hợp sẵn: **guest**. Đối tượng này sở hữu tất cả các cuộc trò chuyện ẩn danh (xem [Xác Thực](auth.md) để hiểu cách hoạt động của định danh guest).

Guest là một khách hàng thực sự (`real`), không phải là một persona. Các phiên hội thoại của guest mang lưu lượng truy cập thực tế từ những người dùng chưa đăng nhập, vì vậy Parlant đối xử với dữ liệu của guest cẩn trọng như bất kỳ khách hàng có tên tuổi nào.

## Personas (Nhân vật giả lập kiểm thử)

Một persona là một khách hàng đại diện thay thế cho người dùng thật trong quá trình bạn kiểm thử hệ thống. Bạn kiểm thử trên persona để đảm bảo các đợt test không bao giờ chạm vào dữ liệu của người thật, và không bao giờ kích hoạt tool thực tế thay mặt người thật.

Đánh dấu khách hàng là persona khi tạo mới:

```python
import parlant.sdk as p

async with p.Server() as server:
    agent = await server.create_agent(
        name="Support Agent",
        description="Helps customers with orders and returns.",
    )

    test_customer = await server.create_customer(
        id="persona_returns_flow",
        name="Dana Levi (test)",
        metadata={"email": "dana@example.test", "plan": "pro"},
        kind=p.CustomerKind.PERSONA,
    )

    print(test_customer.kind)  # CustomerKind.PERSONA
```

Hai quy tắc bất biến áp dụng cho mọi persona:

**Một persona không thể đổi ngược lại thành người thật, và một khách hàng thật không thể chuyển thành persona.** Loại khách hàng (`kind`) chỉ được thiết lập một lần duy nhất khi tạo. Không có trường nào cho phép cập nhật lại nó. Việc vô tình chuyển một khách hàng đang hoạt động thành persona là sai lầm nguy hiểm mà tính năng này sinh ra để ngăn chặn. Nếu bạn chọn nhầm, hãy xóa khách hàng đó và tạo lại.

**Không ai có thể đăng nhập dưới danh nghĩa persona.** Một JWT của khách hàng có `sub` là một persona sẽ bị từ chối, do đó không người dùng cuối nào có thể được phục vụ dưới danh nghĩa persona. Chỉ có quản trị viên (admin) mới có thể mở một phiên hội thoại với persona. Xem [Xác Thực](auth.md#personas-and-authentication).

### Kiểm tra xem khách hàng có phải là Persona không

```python
customer = await server.get_customer(id="persona_returns_flow")

if customer.is_persona:
    print(f"{customer.name} an toàn để kiểm thử")

print(customer.kind)  # CustomerKind.PERSONA
```

`is_persona` là dạng viết tắt của việc so sánh `kind`. Nó trả về `False` cho bất kỳ đối tượng nào không phải là persona tường minh.

### Liệt kê danh sách Personas

Cả API và store đều hỗ trợ bộ lọc `kind`:

```bash
curl "http://localhost:8800/customers?kind=persona" \
  -H "Authorization: Bearer $PARLANT_ADMIN_API_KEY"
```

Danh sách lọc theo `persona` không bao giờ chứa guest. Danh sách lọc theo `real` hoặc không lọc đều chứa guest.

## Khởi tạo khách hàng (Provisioning Customers)

Khởi tạo (provisioning) là việc đảm bảo bản ghi khách hàng đã tồn tại trước khi cần dùng đến. Có 4 cách thực hiện:

### 1. Tích hợp trực tiếp cơ sở dữ liệu khách hàng của bạn (Khuyên dùng)

Hệ thống của bạn gần như chắc chắn đã có sẵn bảng `users`. Đừng sao chép nó vào Parlant. Thay vào đó, hãy triển khai interface `CustomerStore` trên chính cơ sở dữ liệu của bạn và chuyển nó cho server:

```python
from parlant.core.customers import Customer, CustomerId, CustomerStore


class MyCustomerStore(CustomerStore):
    """Cung cấp dữ liệu khách hàng trực tiếp từ database người dùng hiện có của bạn."""

    def __init__(self, db: MyDatabase) -> None:
        self._db = db

    async def read_customer(self, customer_id: CustomerId) -> Customer:
        user = await self._db.users.get(customer_id)

        return Customer(
            id=customer_id,
            name=user.full_name,
            metadata={"plan": user.plan},
            groups=[],
            creation_utc=user.created_at,
            modified_utc=user.updated_at,
        )

    # ... các phương thức còn lại của CustomerStore


async with p.Server(customer_store=MyCustomerStore(db)) as server:
    ...
```

Với cách này, không cần bước đồng bộ hay sao chép dữ liệu nào: Parlant đọc khách hàng trực tiếp từ database của bạn theo thời gian thực. Thay đổi gói dịch vụ trong database sẽ có hiệu lực ngay ở lượt trò chuyện tiếp theo.

Lưu ý:
- Store của bạn phải nhận biết và xử lý trường hợp `CustomerStore.GUEST_ID` (vì guest không có dòng nào trong database của bạn):

```python
async def read_customer(self, customer_id: CustomerId) -> Customer:
    if customer_id == CustomerStore.GUEST_ID:
        return Customer(
            id=CustomerStore.GUEST_ID,
            name="Guest",
            metadata={},
            groups=[],
            creation_utc=GUEST_CREATION_UTC,
            modified_utc=GUEST_CREATION_UTC,
        )
    user = await self._db.users.get(customer_id)
    ...
```

### 2. Tự động khởi tạo (Auto-provisioning)

Nếu khách hàng truy cập Parlant qua app với một mã JWT do backend của bạn tạo ra, hãy bật tính năng tự động tạo bản ghi khi có token hợp lệ đầu tiên từ một khách hàng chưa biết:

```bash
export PARLANT_AUTH_AUTO_PROVISION_CUSTOMERS=true
```

Hoặc thiết lập `auto_provision_customers=True` trong `AuthConfig`. ID sẽ lấy từ claim `sub` của token, và tên lấy từ claim `name`.

### 3. Khởi tạo trước qua API (Pre-provisioning)

Tạo khách hàng tường minh khi backend cần họ tồn tại trước khi mở chat (ví dụ để gửi tin nhắn chủ động như thông báo giao hàng):

```http
POST /customers
Content-Type: application/json

{
  "id": "crm-90211",
  "name": "Dana Cohen",
  "metadata": {"email": "dana@example.com", "plan": "pro"},
  "groups": ["grp_vip"]
}
```

### 4. Khởi tạo bằng code khi khởi động (In code at startup)

Phù hợp cho danh sách người dùng cố định (công cụ nội bộ hoặc demo):

```python
await server.create_customer(
    id="crm-90211",
    name="Dana Cohen",
    metadata={"email": "dana@example.com", "plan": "pro"},
)
```

## Đọc và Tìm kiếm Khách hàng

Đọc một khách hàng:

```http
GET /customers/{customer_id}
```

Liệt kê danh sách khách hàng:

```http
GET /customers?limit=25&sort=asc
```

Các bộ lọc hữu ích:
- `name_prefix`: Tìm kiếm tiền tố không phân biệt hoa thường phục vụ công cụ hỗ trợ và gợi ý khi gõ (`GET /customers?name_prefix=dan`).
- `min_modified_utc`: Chỉ lấy những khách hàng thay đổi sau một mốc thời gian, dùng cho các tiến trình đồng bộ dữ liệu.

## Cập nhật Khách hàng

`PATCH /customers/{customer_id}` cập nhật tên, thêm/bớt metadata và nhóm độc lập:

```http
PATCH /customers/{customer_id}
Content-Type: application/json

{
  "metadata": {
    "set": {"plan": "enterprise"},
    "unset": ["trial_ends"]
  },
  "groups": {
    "add": ["grp_vip"]
  }
}
```

Trong SDK:

```python
vip = await server.create_group(name="VIP")

customer = await server.get_customer(id="crm-90211")
await customer.groups.add(vip)      # idempotent (an toàn khi gọi nhiều lần)
await customer.groups.remove(vip)

if vip in customer.groups:          # kiểm tra thành viên
    ...
```

## Giới hạn phạm vi Rule theo Nhóm khách hàng

Tư duy thiết kế đáng tin cậy gồm hai phần:
Đầu tiên, tạo một **observation** xác định tư cách thành viên nhóm bằng một hàm code Python chính xác (`evaluation_func`), tuyệt đối không để mô hình tự suy đoán.
Sau đó, các policy chỉ áp dụng cho nhóm đó sẽ phụ thuộc vào observation này:

```python
vip = await server.create_group(name="VIP")

vip_customer = await agent.create_observation(
    condition="The customer is a VIP",
    evaluation_func=vip.includes_current_customer,
)

await agent.create_policy(
    content=(
        "When the customer reports a problem, offer to connect them "
        "to the priority support line"
    ),
    dependencies=[vip_customer],
)

await agent.create_policy(
    content=(
        "When the customer completes a purchase, mention the yearly "
        "VIP anniversary gift"
    ),
    dependencies=[vip_customer],
)
```

Đối với khách hàng không thuộc VIP, observation trả về `false` và cả hai policy phụ thuộc sẽ hoàn toàn không tham gia vào cuộc hội thoại.

## Xóa Khách hàng (Quyền được lãng quên - GDPR)

Xóa vĩnh viễn khách hàng và toàn bộ các phiên trò chuyện của họ:

```http
DELETE /sessions?customer_id=crm-90211
DELETE /customers/crm-90211
```

Lưu ý: Hãy xóa các session trước, sau đó xóa khách hàng. Thao tác này là vĩnh viễn và không thể khôi phục. Khách hàng guest không thể bị xóa; các phiên của guest có thể xóa theo từng session hoặc bằng `DELETE /sessions?customer_id=guest`.

## Đọc thông tin Khách hàng từ Tool

Bên trong một lượt tương tác, `p.Customer.current` là khách hàng của phiên đang hoạt động:

```python
@p.tool
async def get_account_summary() -> p.ToolResult:
    plan = await p.Customer.current.metadata.get("plan")
    summary = await billing.summarize(p.Customer.current.id, plan=plan)
    return p.ToolResult(data=summary)
```
