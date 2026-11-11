# Bộ Nhớ (Memory)

Một agent cần hai loại bộ nhớ rất khác nhau. Nó cần nhớ **cuộc trò chuyện hiện tại** — những gì vừa được nói cách đây ít phút, bao gồm cả những gì đã diễn ra trước đó trong một phiên hội thoại dài. Và nó cần nhớ **khách hàng này** — các dữ kiện bền vững, sở thích và lịch sử cần được truyền từ cuộc trò chuyện này sang cuộc trò chuyện khác, ngay cả khi một agent khác tiếp nhận cuộc trao đổi.

Parlant cung cấp sẵn loại bộ nhớ thứ nhất cho bạn. Bạn sẽ tự mình kết nối loại bộ nhớ thứ hai, và tài liệu hướng dẫn này sẽ chỉ ra cách thực hiện điều đó, sử dụng [mem0](https://github.com/mem0ai/mem0) — một thư viện bộ nhớ mã nguồn mở — làm ví dụ thực tế.

## Hai loại bộ nhớ

**Session Memory (Bộ nhớ phiên) được tích hợp sẵn.** Ở mỗi lượt tương tác, Parlant sẽ nạp lịch sử tương tác của phiên vào prompt, nhờ đó agent luôn nhìn thấy toàn bộ diễn biến cuộc trò chuyện cho đến thời điểm hiện tại. Khi một phiên phát triển vượt quá một ngưỡng dung lượng, Parlant sẽ nén phần trước đó thành một bản tóm tắt bền vững và tiếp tục hoạt động dựa trên bản tóm tắt đó — agent vẫn "nhớ" được phần mở đầu của một cuộc trò chuyện dài mà không phải trả phí cho toàn bộ bản ghi thô (xem [Nén Phiên Hội Thoại](compaction.md)). Toàn bộ cơ chế này không đòi hỏi code hay cấu hình gì thêm; đó là cách mọi phiên hội thoại mặc định vận hành.

**Customer Memory (Bộ nhớ khách hàng) là chủ đề chính của hướng dẫn này.** Session Memory sẽ kết thúc khi phiên hội thoại kết thúc. Điều nó không thể làm là nhớ lại trong cuộc trò chuyện vào *ngày mai* rằng khách hàng này bị dị ứng đậu phộng, thích liên lạc qua email hơn điện thoại, hoặc đang trong quá trình đổi trả hàng bắt đầu từ tuần trước — đặc biệt nếu cuộc trò chuyện ngày mai diễn ra với một agent hoàn toàn khác. Đó chính là **Customer Memory**: tri thức bền vững về một *khách hàng* cụ thể, tồn tại xuyên suốt qua các session và các agent. Parlant không đi kèm một kho lưu trữ bộ nhớ cố định cho việc này — bạn tự mang kho lưu trữ của riêng mình — nhưng Parlant cung cấp sẵn hai điểm kết nối bạn cần để tích hợp.

## Động lực thiết kế

Tại sao Parlant lại yêu cầu bạn tự mang kho lưu trữ bộ nhớ thay vì đóng gói sẵn một giải pháp? Bởi vì Customer Memory đặt ra những câu hỏi hóc búa về sản phẩm và tính tuân thủ pháp lý (compliance): bạn được phép lưu giữ dữ liệu gì, trong bao lâu, lưu ở đâu, xóa theo yêu cầu như thế nào và chia sẻ giữa các agent trong tổ chức ra sao. Một framework không nên đưa ra những quyết định đó thay bạn. Vì vậy, Parlant không tự lưu trữ dữ liệu này. Thay vào đó, nó chia công việc thành hai phần rõ ràng:

- **Truy xuất bộ nhớ (Memory retrieval)** — trước khi agent phản hồi, lấy các ký ức liên quan đến thời điểm hiện tại và đặt chúng vào trước mặt mô hình.
- **Cập nhật bộ nhớ (Memory update)** — khi cuộc hội thoại hé lộ những điều đáng ghi nhớ, ghi chúng vào kho lưu trữ của bạn.

Bằng cách trỏ cả hai nửa này vào hệ thống bộ nhớ bạn chọn — mem0, một cơ sở dữ liệu vector, hoặc CRM của chính bạn — với khóa định danh là khách hàng (`customer`), agent sẽ có được một trí nhớ dài hạn bền vững.

## Cách thức hoạt động trong Parlant

### Chìa khóa: Định danh khách hàng (Customer Identity)

Một `Customer` trong Parlant là một thực thể toàn cục với `id` ổn định. Một `Session` chỉ đơn thuần *tham chiếu* tới một `customer_id` (và một `agent_id`) — khách hàng không thuộc sở hữu độc quyền của bất kỳ session hay agent nào. Do đó, **bộ nhớ sử dụng khóa `customer.id` đương nhiên sẽ trải rộng xuyên suốt mọi session và mọi agent** trò chuyện với khách hàng đó. Bạn có thể để Parlant tự sinh id, hoặc gán id của riêng bạn (ví dụ id từ CRM) để đồng bộ giữa các hệ thống:

```python
customer = await server.create_customer(name="Alex", id="crm-42")
```

Bên trong cả hai điểm kết nối bên dưới, bạn đọc khách hàng hiện tại qua `p.Customer.current.id`. Đó là giá trị bạn truyền cho kho lưu trữ bộ nhớ làm user key. (`p.Customer.current`, `p.Session.current`, và `p.Agent.current` đều hợp lệ ở bất kỳ đâu bên trong một lượt tương tác — hooks, retrievers, field providers — mà không cần phải truyền đối tượng context qua lại.)

### Truy xuất bộ nhớ — sử dụng Retriever

Một **retriever** là một async function gắn vào một agent, chạy trong quá trình chuẩn bị lượt tương tác và nạp thêm ngữ cảnh vào prompt. Đây là vị trí tự nhiên nhất để lấy lại ký ức: nó nhận đối tượng khách hàng và tin nhắn mới nhất, nhờ đó có thể truy vấn kho lưu trữ của bạn và trả về những gì tìm thấy.

```python
async def recall(ctx: p.RetrieverContext) -> p.RetrieverResult | None:
    if msg := ctx.interaction.last_customer_message:
        if facts := mem0_store.search(msg.content, user_id=p.Customer.current.id):
            return p.RetrieverResult(data="Memory about this customer:\n" + "\n".join(facts))
    return None

await agent.attach_retriever(recall)
```

`RetrieverResult.data` (bất kỳ giá trị nào tuần tự hóa được thành JSON) được đưa vào prompt của lượt đó dưới dạng ngữ cảnh truy xuất. Trả về `None` nếu không muốn thêm gì. Các retriever được kích hoạt song song ngay khi bắt đầu khâu chuẩn bị và được await trước khi sinh phản hồi, vì vậy retriever có thể thoải mái `await` (hoặc ủy thác) một lệnh gọi dịch vụ bên ngoài.

### Cập nhật bộ nhớ — một Hook chạy sau khi Agent phản hồi

Để *ghi* ký ức, bạn cần một hàm callback nhìn thấy được **toàn bộ cuộc trao đổi** — những gì khách hàng đã nói và những gì agent đã trả lời. Một nửa những gì đáng nhớ chỉ xuất hiện trong câu trả lời của agent: agent xác nhận cuộc hẹn, báo giá hoặc hứa sẽ gọi lại. Một callback chạy trước khi agent trả lời sẽ không thể thấy bất kỳ thông tin nào trong số đó.

Các **engine hooks** của Parlant cung cấp đúng thời điểm đó. `on_messages_emitted` được kích hoạt một lần cho mỗi lượt tương tác, sau khi tất cả những gì agent nói đã đến được với khách hàng, và trao cho bạn danh sách các tin nhắn đó. Bạn đăng ký nó trên container (xem [Engine Hooks](hooks.md)):

```python
async def initialize_container(container: p.Container) -> None:
    hooks = container[p.CompassHooks]

    async def remember(
        ctx: p.EngineContext,
        messages: Sequence[str],
        exc: Exception | None,
    ) -> p.CompassHookResult:
        if (customer_message := ctx.interaction.last_customer_message) and messages:
            await memory.add(
                [
                    {"role": "user", "content": customer_message.content},
                    {"role": "assistant", "content": "\n".join(messages)},
                ],
                user_id=ctx.customer.id,
                run_id=ctx.session.id,
            )

        return p.CompassHookResult.CALL_NEXT

    hooks.on_messages_emitted.append(remember)


async with p.Server(initialize_container=initialize_container) as server:
    ...
```

Một lượt tương tác có thể gửi đi nhiều hơn một tin nhắn — ví dụ tin nhắn mở đầu (preamble) trước khi gọi tool rồi sau đó mới đến tin nhắn trả lời chính — vì vậy payload là một danh sách, được nối lại ở đây thành nửa phản hồi của trợ lý trong cuộc trao đổi.

Ba nguyên tắc giúp mẫu thiết kế này hoạt động tin cậy:

- **Lưu trữ cả hai phía của cuộc trao đổi:** Đây là điều mem0 yêu cầu: hàm `add` nhận một danh sách có thứ tự các lượt `user`/`assistant`, và tính năng trích xuất dữ kiện của nó sẽ đọc cả hai vai trò. Câu trả lời chính là thứ giải mã các đại từ tham chiếu trong tin nhắn của khách hàng — ví dụ thực tế của mem0 lưu *"User's dog Biscuit turned 5"* từ một tin nhắn khách hàng chỉ nói *"He turned 5 today"*, bởi vì lượt trao đổi xung quanh đã xác định rõ "he" là ai. Nếu chỉ gửi nửa tin nhắn của khách hàng, bạn sẽ mất cả các dữ kiện agent đã tuyên bố lẫn ngữ cảnh giúp nửa tin nhắn của khách hàng có thể hiểu được sau này.
- **Chỉ truyền các tin nhắn mới, không truyền toàn bộ cuộc trò chuyện:** Một lớp bộ nhớ tốt sẽ tự quản lý chuỗi thông tin của nó và kéo ngữ cảnh cũ thông qua khóa định danh, vì vậy việc gửi lại toàn bộ lịch sử ở mỗi lượt là lãng phí và cuối cùng sẽ làm tràn cửa sổ ngữ cảnh. Hướng dẫn của mem0 nêu rõ: chỉ gửi các lượt mới và để hệ thống tự phân giải phần còn lại.
- **Để lớp bộ nhớ tự quyết định điều gì đáng lưu:** mem0 thực hiện việc trích xuất riêng — tự đánh giá điều gì quan trọng, loại bỏ các mục trùng lặp với những gì nó đã biết, và không lưu gì khi không có thông tin mới. Bạn giao cho nó cuộc trao đổi; nó tự quyết định điều gì cần giữ. (Để chỉ ghi vào những thời điểm cụ thể nhằm tiết kiệm chi phí ghi, hãy đặt điều kiện cho hook dựa trên một rule — xem phần [Lưu ý](#lưu-ý)).

Đó là toàn bộ mô hình: `recall` thực hiện đọc, `remember` thực hiện ghi, cả hai đều lấy `customer.id` làm khóa.

## Hướng dẫn thực hành: mem0

[mem0](https://github.com/mem0ai/mem0) là một lớp bộ nhớ sử dụng LLM để trích xuất các dữ kiện quan trọng từ một cuộc trò chuyện, tạo vector embedding cho chúng và truy xuất các dữ kiện liên quan theo yêu cầu. Nó khớp nối tự nhiên với 2 điểm kết nối ở trên.

### Cài đặt

```bash
pip install mem0ai
```

Bộ nhớ self-hosted chạy ngay trong tiến trình của bạn. Theo mặc định, nó sử dụng OpenAI cho cả việc trích xuất dữ kiện lẫn embeddings và một vector store cục bộ nhúng sẵn — vì vậy nó chỉ cần một biến `OPENAI_API_KEY` mà không cần cơ sở dữ liệu bên ngoài. (Điều này độc lập với mô hình mà *agent* của bạn đang sử dụng). mem0 cung cấp một client bất đồng bộ là `AsyncMemory`, bạn có thể `await` trực tiếp. Hãy chỉ định rõ mô hình — mô hình chat mặc định của mem0 có thể từ chối mức nhiệt độ thấp (low temperature) mà nó sử dụng nội bộ:

```python
from mem0 import AsyncMemory

memory = AsyncMemory.from_config({
    "llm": {"provider": "openai", "config": {"model": "gpt-4o-mini", "temperature": 0.1}},
    "embedder": {"provider": "openai", "config": {"model": "text-embedding-3-small"}},
})
```

Giao diện của mem0 rất nhỏ gọn. Hàm `memory.add(messages, user_id=...)` lưu trữ các dữ kiện đã trích xuất, trong đó `messages` là danh sách có thứ tự gồm các lượt `{"role": "user" | "assistant", "content": ...}` — cùng cấu trúc mà các chat API sử dụng. Và `memory.search(query, filters={"user_id": ...}, limit=...)` trả về các kết quả phù hợp dưới dạng `{"results": [{"memory": "...", "score": 0.49, ...}, ...]}`.

### Tích hợp vào một Agent

Sử dụng `AsyncMemory` để các lệnh gọi mem0 có thể await một cách mượt mà bên trong retriever bất đồng bộ và callback:

```python
import asyncio
from collections.abc import Sequence

import parlant.sdk as p
from mem0 import AsyncMemory

memory = AsyncMemory.from_config({
    "llm": {"provider": "openai", "config": {"model": "gpt-4o-mini", "temperature": 0.1}},
    "embedder": {"provider": "openai", "config": {"model": "text-embedding-3-small"}},
})


# Cập nhật bộ nhớ — khi agent đã trả lời, chuyển cho mem0 toàn bộ cuộc trao đổi;
# nó sẽ trích xuất và lưu bất cứ điều gì đáng nhớ (và không lưu gì nếu không có thông tin mới).
async def initialize_container(container: p.Container) -> None:
    hooks = container[p.CompassHooks]

    async def remember(
        ctx: p.EngineContext,
        messages: Sequence[str],
        exc: Exception | None,
    ) -> p.CompassHookResult:
        if (customer_message := ctx.interaction.last_customer_message) and messages:
            await memory.add(
                [
                    {"role": "user", "content": customer_message.content},
                    {"role": "assistant", "content": "\n".join(messages)},
                ],
                user_id=ctx.customer.id,  # sở hữu bộ nhớ (xuyên suốt các session)
                run_id=ctx.session.id,  # giới hạn ngữ cảnh trích xuất của mem0 cho session này
            )

        return p.CompassHookResult.CALL_NEXT

    hooks.on_messages_emitted.append(remember)


async def main() -> None:
    async with p.Server(initialize_container=initialize_container) as server:
        agent = await server.create_agent(
            id="my-agent",
            name="Support",
            instructions="You are a helpful assistant. Use what you know about the customer.",
        )

        # Truy xuất bộ nhớ — lấy các ký ức của khách hàng liên quan đến tin nhắn mới nhất của họ.
        async def recall(ctx: p.RetrieverContext) -> p.RetrieverResult | None:
            if msg := ctx.interaction.last_customer_message:
                hits = await memory.search(msg.content, filters={"user_id": p.Customer.current.id})
                if facts := [h["memory"] for h in hits["results"]]:
                    return p.RetrieverResult(data="Memory about this customer:\n" + "\n".join(facts))
            return None

        await agent.attach_retriever(recall)


if __name__ == "__main__":
    asyncio.run(main())
```

### Lợi ích nhận được

Khi gắn cho một khách hàng cùng một `id` duy nhất qua nhiều cuộc trò chuyện, hai điểm kết nối sẽ phối hợp nhịp nhàng xuyên suốt các session và các agent. Trong một session, khách hàng chia sẻ: *"Tôi bị dị ứng với đậu phộng"* — hook `remember` kích hoạt và mem0 lưu lại: *"Alex is allergic to peanuts."* Trong một session sau đó hoàn toàn riêng biệt, khách hàng đó hỏi: *"bạn có thể gợi ý món ăn nhẹ nào không?"* — `recall` tìm kiếm trong mem0, phát hiện ra thông tin dị ứng, đưa vào prompt, và agent tự động đề xuất các món không chứa đậu phộng. Không có trạng thái cuộc trò chuyện nào được chia sẻ trực tiếp giữa hai session; ký ức được kế thừa thành công bởi vì cả hai session đều sử dụng chung một customer id.

## Lưu ý

- **Nên ủy thác tác vụ ghi ra background:** `on_messages_emitted` chạy sau khi câu trả lời đã đến tay khách hàng, vì vậy một tác vụ ghi chậm sẽ không làm chậm những gì họ nhìn thấy. Tuy nhiên, nó vẫn giữ cho lượt tương tác mở cho đến khi trả về, và `memory.add` sử dụng LLM bên dưới (để trích xuất dữ kiện), do đó trong môi trường production bạn nên khởi chạy nó dưới dạng một background task thay vì await trực tiếp tuần tự.
- **Hook áp dụng trên toàn server, không theo từng agent:** Một callback gắn vào `CompassHooks` sẽ kích hoạt cho mọi lượt của mọi agent. Nếu chỉ có một agent cần ghi nhớ, hãy kiểm tra `ctx.agent.id` ở đầu hook và return sớm nếu không khớp.
- **Giới hạn phạm vi với các key chính xác:** `user_id=customer.id` là thứ làm cho ký ức thuộc về khách hàng và trải dài qua mọi session và agent — do đó lệnh `search` chỉ cần lọc theo khóa này. Khi gọi `add`, hãy truyền thêm `run_id=session.id`: nó giới hạn *ngữ cảnh trích xuất* của mem0 (các tin nhắn trước đó mà nó dùng để phân giải đại từ tham chiếu) trong session hiện tại, đó là lý do tại sao chỉ cần gửi các lượt mới là đủ. mem0 cũng chấp nhận `agent_id` nếu bạn muốn tạo bộ nhớ riêng tư cho một agent duy nhất.
- **Chủ động chọn thời điểm lưu:** Ghi ở mọi lượt và để mem0 tự trích xuất là giải pháp mặc định đơn giản và mạnh mẽ nhất. Nếu chi phí ghi bộ nhớ là mối bận tâm, hãy để Parlant quyết định thời điểm ghi: tạo một observation cho những khoảnh khắc đáng nhớ và chỉ cho phép hook ghi khi observation đó được khớp trong lượt này:

  ```python
  memorable = await agent.create_observation(
      condition="the customer shares a personal fact, preference, or constraint",
  )

  # ...bên trong hook:
  if not any(m.rule.id == memorable.id for m in ctx.state.ordinary_rule_matches):
      return p.CompassHookResult.CALL_NEXT
  ```
- **Session Memory là độc lập và tự động:** Toàn bộ hướng dẫn này nói về *Customer Memory*; cuộc trò chuyện đang diễn ra và bản tóm tắt nén của nó luôn luôn hiện diện độc lập (xem [Nén Phiên Hội Thoại](compaction.md)).
- `on_messages_emitted` chỉ là một trong nhiều điểm vòng đời, và retriever được xây dựng dựa trên cùng một cơ chế bên dưới — xem [Engine Hooks](hooks.md) để biết danh sách đầy đủ.
