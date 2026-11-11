# Cấu Hình Container (Dependency Injection)

Parlant là một nền tảng đặc biệt, được thiết kế để mang lại sự linh hoạt tối đa cho các kỹ sư phần mềm. Hầu như bất kỳ bộ phận nào của Parlant server đều có thể được thay thế bằng triển khai của riêng bạn. Bạn có thể định tuyến log vào hạ tầng observability của công ty, lưu trữ phiên hội thoại vào cơ sở dữ liệu riêng, thực thi các quy tắc phân quyền tùy biến, hoặc tinh chỉnh sự đánh đổi giữa chi phí và độ trễ của Parlant. Tất cả những điều này không yêu cầu bạn phải fork mã nguồn hay can thiệp patch chắp vá. Bạn chỉ cần viết một class, liên kết (bind) nó tại một nơi duy nhất, và toàn bộ hệ thống sẽ tự động sử dụng nó.

Cơ chế đằng sau điều này là Dependency Injection (DI) Container của Parlant: mọi component — các engine, kho lưu trữ (stores), chính sách (policies), bộ ghi log (loggers) — đều được phân giải theo kiểu dữ liệu từ một đối tượng `Container` duy nhất, mà SDK sẽ chuyển giao cho bạn tại các thời điểm rõ ràng trong vòng đời của server. Hướng dẫn này bao gồm: khi nào container khả dụng, cách hoạt động của các liên kết binding và một sổ tay công thức tập hợp các thành phần thay thế phổ biến nhất trong thực tế.

## Động lực thiết kế

Điều làm cho việc thay thế tại một vị trí duy nhất trở nên khả thi là toàn bộ codebase tuân theo kiến trúc Hexagonal (Ports and Adapters): các component phụ thuộc vào các *ports* — các kiểu dữ liệu trừu tượng như `Logger`, `AuthorizationPolicy`, hay `SessionStore` — và không bao giờ phụ thuộc vào các triển khai cụ thể (concrete implementations). Container liên kết từng port với một triển khai cụ thể lúc khởi động, vì vậy khi bạn liên kết lại (rebind) `Logger` sang triển khai Datadog hoặc `SessionStore` sang cơ sở dữ liệu của bạn, phần còn lại của hệ thống vẫn hoạt động bình thường — không thành phần nào cần biết nó đang nói chuyện với triển khai cụ thể nào.

Một số cấu hình thường dùng có các tham số chuyên biệt trên `p.Server` (`models=`, `auth=`, `session_store=`...). Những tham số đó thực chất là các lối tắt cú pháp (shortcuts): bên dưới hậu trường chúng tạo ra các container binding. Các hook container chính là cơ chế tổng quát nền tảng cho tất cả các thiết lập đó.

## Nơi bạn tiếp cận Container

`p.Server` cung cấp hai hook vòng đời, và container vẫn có thể truy cập được tại thời gian chạy (runtime). Chúng phục vụ các mục đích khác nhau:

### `configure_container` — Thay thế các triển khai (Replace implementations)

Chạy trong lúc khởi động server, *trước khi* ứng dụng được lắp ráp hoàn chỉnh. Nó nhận container và trả về chính container đó (thường là sau khi đã rebind một số kiểu dữ liệu). Đây là hook dùng để hoán đổi triển khai — bất kỳ thứ gì được khởi tạo sau đó sẽ phân giải theo các binding của bạn:

```python
async def configure_container(container: p.Container) -> p.Container:
    container[p.CompassOptimizationPolicy] = MyOptimizationPolicy()
    return container


async with p.Server(configure_container=configure_container) as server:
    ...
```

### `initialize_container` — Thao tác trên Container đã hoàn thiện

Chạy *sau khi* container đã được chốt (finalized), với mọi liên kết binding đã sẵn sàng và mọi singleton đã sẵn sàng để phân giải. Khác với `configure_container`, hook này không thay đổi *triển khai nào* được liên kết — nó thao tác trên những đối tượng đã tồn tại sẵn. Nó không trả về giá trị nào; nó tồn tại cho các tác vụ cần các service đã phân giải: đăng ký listener, làm ấm cache, và **tinh chỉnh cấu hình runtime của các component đã hoàn thiện**.

Mục đích cuối cùng đó là trường hợp phổ biến nhất. Rất nhiều component để lộ các cài đặt thông thường — các thuộc tính bạn gán hoặc các hàm setter bạn gọi — giúp điều chỉnh hành vi của chúng mà không cần phải thay thế toàn bộ component. Bởi vì `initialize_container` chạy sau khi khởi tạo, instance bạn phân giải ở đây chính là *cùng một singleton* mà Parlant sẽ dùng, do đó cài đặt bạn thay đổi trên nó sẽ có hiệu lực lâu dài. Ví dụ: nâng số lượng câu trả lời soạn sẵn mà responder và reviewer đưa ra mỗi lượt (xem [Phản Hồi Soạn Sẵn](canned-responses.md)):

```python
from parlant.core.engines.compass.responder.responder import Responder
from parlant.core.engines.compass.reviewer import Reviewer


async def initialize_container(container: p.Container) -> None:
    # Số lượng câu trả lời soạn sẵn tối đa hiển thị mỗi lượt — dùng làm tham chiếu phong cách
    # cho responder và làm chỉ dẫn review cho reviewer. Cả hai mặc định là 5.
    container[Responder].max_canned_responses = 8
    container[Reviewer].max_canned_responses = 3

    # Đoạn văn bản cứu cánh cuối cùng hiển thị nếu tin nhắn của agent vẫn bị chặn bởi kiểm duyệt
    # qua mọi lần thử lại (xem [Kiểm Duyệt](moderation.md)).
    container[Responder].moderation_fallback = (
        "Xin lỗi, tôi không thể phản hồi yêu cầu này lúc này. Tôi có thể giúp gì khác cho bạn không?"
    )


async with p.Server(initialize_container=initialize_container) as server:
    ...
```

Ngược lại, việc rebind các kiểu dữ liệu tại hook này là một sai lầm: các component đã phân giải dependency từ trước vẫn sẽ giữ nguyên instance mà chúng đã nhận được, vì vậy một lệnh `container[X] = ...` muộn màng sẽ không đến được với chúng. Hãy thay đổi *triển khai nào* được bind trong `configure_container` (trước khi khởi tạo); thay đổi *cài đặt thiết lập* của một component đã khởi tạo trong `initialize_container` (sau khi khởi tạo).

### Truy cập Runtime — `server.container`

Bên trong khối `async with`, lệnh `server.container[SomeType]` phân giải bất kỳ kiểu dữ liệu nào đã được bind. Hữu ích để kết nối ứng dụng của bạn với các dịch vụ đang chạy — ví dụ: đăng ký nhận báo cáo sử dụng tài nguyên (xem [Báo Cáo Sử Dụng](usage-reports.md)).

### Không phải là thay thế component: Engine Hooks

Engine hooks đăng ký *các callback hành vi* dựa trên các sự kiện của engine (tin nhắn được tạo, cuộc gọi tool được đánh giá, v.v.) thay vì thay thế triển khai, và chúng sử dụng cùng cơ chế này: phân giải `container[p.CompassHooks]` trong `initialize_container` và nối các callback của bạn vào danh sách hook. Hãy dùng hook khi bạn muốn quan sát hoặc can thiệp vào một lượt tương tác; hãy rebind một port khi bạn muốn có một triển khai khác cho một component. Xem [Đánh Giá Tool & Tin Nhắn](review.md#observing-reviews-with-engine-hooks) để xem ví dụ thực tế.

## Cơ chế liên kết (Binding Mechanics)

Container ánh xạ *kiểu dữ liệu (types)* tới các triển khai. Các dạng bạn sẽ thực tế sử dụng:

```python
# Bind một instance — mọi lượt phân giải đều nhận chính xác object này.
container[p.CompassOptimizationPolicy] = MyOptimizationPolicy()

# Bind một class dưới dạng singleton khởi tạo lười (lazy-constructed singleton)
# (các dependency trong hàm __init__ của nó sẽ tự động được phân giải từ container).
container[p.RateLimiter] = p.Singleton(MyRateLimiter)

# Bind một factory — chạy lại ở mỗi lượt phân giải.
container[p.Logger] = lambda c: build_logger()
```

Hai quy tắc vàng cần nhớ:

- Phân giải dựa trên kiểu dữ liệu chính xác. Hãy bind vào *port* (kiểu trừu tượng mà các component yêu cầu), không bind vào subclass của bạn:
  `container[p.CompassOptimizationPolicy] = MyOptimizationPolicy()`,
  tuyệt đối không dùng `container[MyOptimizationPolicy] = ...`.
- Bind sớm. Các singleton nắm bắt dependency của chúng khi được tạo lần đầu, đó là lý do việc hoán đổi triển khai thuộc về `configure_container` chứ không phải muộn hơn.

Các liên kết binding được kiểm tra tính hợp lệ ngay khi khai báo: việc bind một instance không phải là thể hiện thực tế của port sẽ ném ra lỗi `TypeError` ngay lập tức, giúp phát hiện lỗi sai ngay khi khởi động với thông báo rõ ràng. Các callable factory nhận chính đối tượng `p.Container`, cho phép factory tự phân giải các dependency của riêng nó.

## Sổ tay công thức thực tế (Cookbook)

Những thành phần được các hệ thống triển khai rebind phổ biến nhất:

### Tinh chỉnh Engine: Optimization Policy

`p.CompassOptimizationPolicy` tập hợp các cài đặt chi phí và độ trễ của Parlant tại một nơi: thời gian chờ request-hedging theo từng model route, độ trễ xử lý các tin nhắn liên tiếp, ngân sách thử lại của review, và ngưỡng để prefill tiền tố prompt dùng chung. Kế thừa class này, ghi đè những gì bạn cần và rebind:

```python
class MyOptimizationPolicy(p.CompassOptimizationPolicy):
    def get_max_review_restarts(self, effort: p.Effort) -> int:
        if effort >= p.Effort.HIGH:
            return 8
        return super().get_max_review_restarts(effort)


async def configure_container(container: p.Container) -> p.Container:
    container[p.CompassOptimizationPolicy] = MyOptimizationPolicy()
    return container
```

Xem [Làm Việc Với Phiên Hội Thoại](sessions.md#consecutive-message-processing-delay) để biết ngữ nghĩa độ trễ xử lý và [Đánh Giá Tool & Tin Nhắn](review.md#the-retry-budget) để biết ngữ nghĩa ngân sách thử lại.

#### Khi nào việc Prefill mang lại lợi ích kinh tế

Một số quá trình đánh giá phát tán (fan-out) một yêu cầu cho mỗi rule, mỗi yêu cầu đều lặp lại cùng một tiền tố prompt. Parlant có thể làm ấm (warm) tiền tố đó trước, nhờ đó các lượt gọi lặp lại sẽ đến dưới dạng đọc cache (cache reads) thay vì gửi toàn bộ prompt đầy đủ.

Bản thân việc làm ấm cũng là một yêu cầu, và các provider thường tính phí cho một thao tác *ghi cache* cao hơn token đầu vào thông thường — vì vậy việc làm ấm để chỉ phục vụ một vài yêu cầu có thể tốn kém hơn là không làm ấm. Hàm `get_min_prefill_fan_out` trả về số lượng yêu cầu tối thiểu để việc làm ấm bắt đầu có lãi:

```python
class MyOptimizationPolicy(p.CompassOptimizationPolicy):
    def get_min_prefill_fan_out(self, hints: dict = {}) -> int:
        return 3   # chi phí ghi cache của provider này rẻ; làm ấm sớm hơn
```

Mặc định là 5. Trả về `0` để tắt hoàn toàn tính năng prefill. Mỗi bộ đánh giá được xem xét trên độ mở rộng fan-out của chính nó.

### Các kho lưu trữ (Stores)

Các kho lưu trữ phổ biến đều có các lối tắt tham số trong constructor — `session_store=`, `customer_store=`, và `variable_store=` trên `p.Server` — chấp nhận `"transient"`, `"local"`, chuỗi kết nối MongoDB, hoặc một instance store. Việc truyền một instance sẽ tự động tạo một container binding bên dưới hậu trường:

```python
async with p.Server(session_store=MySessionStore()) as server:
    ...
```

Đối với các store không có lối tắt constructor, hãy bind port trực tiếp trong `configure_container` (`p.SessionStore`, `p.CustomerStore`, `p.ContextVariableStore` được export sẵn; các store port khác nằm dưới `parlant.core.*`).

### Quản lý Mô hình: Rate Limits và Secrets

Việc *định tuyến mô hình* không thuộc phạm vi container — các mô hình được cấu hình qua tham số `models={...}` (xem [Cấu hình Model và Provider](providers.md)). Hai mối quan tâm liền kề thuộc về container gồm:

- **Giới hạn tốc độ (Rate limiting)** — `p.RateLimiter` quản lý tính đồng thời và thông lượng cho các yêu cầu mô hình. `p.BasicRateLimiter` là mặc định; bạn có thể rebind để tích hợp bộ giới hạn phân tán qua Redis.
- **Bảo mật bí mật (Secrets)** — thông tin xác thực mô hình dài hạn được biểu diễn dưới dạng `p.SecretRef("locator")` bên trong đối số `ModelConfig`; `SecretRef` chỉ lưu định danh locator, không bao giờ chứa credential thực tế. Port `p.SecretLoader` sẽ phân giải các locator này dựa trên hệ thống quản lý bí mật của bạn (Vault, AWS Secrets Manager, GCP Secret Manager, v.v.):

```python
class VaultSecretLoader(p.SecretLoader):
    async def load(self, ref: p.SecretRef) -> str:
        return await my_vault.read(ref.key)


async def configure_container(container: p.Container) -> p.Container:
    container[p.SecretLoader] = VaultSecretLoader()
    return container


async with p.Server(
    models={
        "*": "openai",
        "react": p.ModelConfig(
            "openai:gpt-5.4",
            args={"api_key": p.SecretRef("models/openai/api-key")},
        ),
    },
    configure_container=configure_container,
) as server:
    ...
```

### Ghi Log (Logging)

Mọi log đều đi qua port `p.Logger` — console, file `logs.jsonl`, và các file nén báo cáo lỗi chẩn đoán đều đi qua nó (xem [Chẩn Đoán](diagnostics.md)). Hãy rebind nó để đưa log vào hệ sinh thái giám sát của bạn; các triển khai thường bọc (wrap) logger hiện có thay vì thay thế hoàn toàn để giữ lại các sink tích hợp sẵn.

### Phân quyền (Authorization)

`p.Server(auth=...)` chấp nhận một `AuthConfig` hoặc một `p.AuthorizationPolicy` hoàn chỉnh — cũng là một lối tắt phía trên container binding. Các policy tùy chỉnh được hướng dẫn chi tiết trong [Xác Thực](auth.md).

### Ngưỡng Sức Khỏe Hệ Thống (Health Thresholds)

`p.HealthThresholds` nắm giữ mọi mốc giới hạn đằng sau trạng thái `/healthz`: độ trễ lượt tương tác engine và tỷ lệ thành công, độ trễ yêu cầu mô hình theo từng route, và độ trễ của event loop. Bind giá trị của bạn để tinh chỉnh chúng; xem [Chẩn Đoán](diagnostics.md#status-thresholds).

```python
async def configure_container(container: p.Container) -> p.Container:
    container[p.HealthThresholds] = p.HealthThresholds(
        engine=p.EngineHealthThresholds(degraded_p95_ms=45_000.0),
    )
    return container
```

### Nén phiên (Compaction)

Nén phiên hội thoại được cấu hình bằng cách *gọi hàm* trên `Compacter` đã bind thay vì rebind nó — theo phong cách tùy biến của `initialize_container` (`container[Compacter].set_policy({...})`). Xem [Nén Phiên Hội Thoại](compaction.md#cấu-hình-nén-configuring-compaction).

## Những gì *KHÔNG* cấu hình qua Container

Ba thành phần trông giống DI nhưng đã có các tham số chuyên biệt phù hợp hơn:

- **Model routing** — tham số `models={...}` trên `p.Server` / `create_agent`. Xem [providers.md](providers.md).
- **Prompt customization** — các provider theo route `prompts={...}`. Xem [Tùy Biến Prompt](prompt-customization.md).
- **Callbacks theo từng Rule** — `on_matched=` / `on_discovered=` và các trigger review theo rule là tham số khi tạo rule, không phải container binding. Xem [Đánh Giá Tool & Tin Nhắn](review.md).

## Lưu ý về tính ổn định (Stability)

Các kiểu dữ liệu được export từ `parlant.sdk` (mọi thứ truy cập được qua `p.X`) là các container key ổn định — chúng là API chính thức, và việc rebind chúng được hỗ trợ đầy đủ. Bất cứ thứ gì import từ `parlant.core.*` hoặc `parlant.adapters.*` là nội bộ: chúng có thể hoạt động như một container key hôm nay, nhưng vị trí và cấu trúc của chúng có thể thay đổi giữa các bản phát hành. Hãy ưu tiên các port được export chính thức, và chuẩn bị tinh thần cập nhật các import từ `parlant.core` khi nâng cấp phiên bản Parlant.
