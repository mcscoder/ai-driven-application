# Chương 3. Thiết kế và phát triển sản phẩm

Chương này trình bày thiết kế và cách hiện thực hóa Graphiti Chat Lab dựa trên mã nguồn thực tế trong các file `app/main.py`, `app/llm_client.py`, `app/graphiti_client.py`, `app/schemas.py` và `app/templates/index.html`. Điểm quan trọng của hệ thống là đây không phải một kiến trúc microservices phân tán, mà là một ứng dụng FastAPI dạng monolith có phân lớp rõ ràng. Mỗi lớp giữ đúng trách nhiệm của mình: lớp giao diện nhận và hiển thị dữ liệu, lớp API điều phối request, lớp assistant xử lý hội thoại và tool calling, lớp memory làm việc với Graphiti và Neo4j, còn lớp schema đóng vai trò hợp đồng dữ liệu giữa backend và frontend.

Mục tiêu thiết kế của sản phẩm là tạo ra một chatbot có bộ nhớ bền, có khả năng truy xuất đúng thông tin đã lưu, có thể ghi nhớ các sự kiện có yếu tố thời gian, và có thể công khai quá trình suy luận thông qua `retrieved_facts` và `tool_trace`. Đây là các năng lực cốt lõi mà một sản phẩm memory assistant cần có ngay từ phiên bản MVP.

## 3.1. Định hướng thiết kế sản phẩm

Graphiti Chat Lab được xây dựng như một nguyên mẫu hội thoại có trí nhớ, không phải một chatbot trả lời chung chung. Bài toán trung tâm của hệ thống là cho phép người dùng hỏi lại những thông tin đã trao đổi trước đó, chẳng hạn khoản nợ, kế hoạch, lịch hẹn, hoặc thay đổi, hủy bỏ một sự kiện đã lưu. Vì vậy, kiến trúc của hệ thống phải thỏa ba yêu cầu đồng thời:

- lưu được tri thức hữu ích từ các lượt chat trước;
- truy xuất được tri thức đó theo ngữ cảnh và theo thời gian;
- hiển thị được dấu vết xử lý để người dùng biết câu trả lời đến từ đâu.

Từ góc độ sản phẩm, thiết kế của repo cho thấy nhóm phát triển đã chọn hướng đi thực tế: giảm số lượng thành phần nhưng tăng độ rõ ràng của luồng xử lý. FastAPI được dùng làm lớp API, Graphiti và Neo4j làm lõi bộ nhớ, Gemini-compatible endpoint làm lớp sinh ngôn ngữ, và một giao diện HTML/CSS/JS tối giản để hiển thị kết quả. Cách làm này phù hợp với giai đoạn MVP vì có thể chạy cục bộ, dễ kiểm thử, và dễ quan sát hành vi hệ thống trong từng lượt chat.

Một đặc điểm đáng chú ý là hệ thống có ý thức rõ về thời gian. Trong mã nguồn, trợ lý luôn nhận được thời điểm hiện tại theo múi giờ địa phương `Asia/Ho_Chi_Minh`, sau đó dùng thông tin này để chuẩn hóa các cụm như “mai”, “ngày mai”, hoặc các lịch hẹn có mốc giờ cụ thể. Điều này giúp sản phẩm không chỉ nhớ nội dung, mà còn nhớ đúng ngữ cảnh thời gian của nội dung.

## 3.2. Kiến trúc tổng thể của hệ thống

Kiến trúc tổng thể có thể mô tả theo lớp như sau:

```text
Người dùng
    |
    v
Trình duyệt / app/templates/index.html
    |
    v
POST /api/chat (FastAPI trong app/main.py)
    |
    v
AssistantClient (app/llm_client.py)
    |
    +------------------------------+
    |                              |
    v                              v
MemoryToolbox                 Gemini-compatible LLM
    |                        (qua ChatCompletionsGraphitiClient)
    v                              |
GraphitiMemory (app/graphiti_client.py)
    |
    +--> Graphiti core
    +--> Neo4j
    +--> Embedder mode: proxy / gemini / local
    |
    v
retrieved_facts + tool_trace + reply
    |
    v
Frontend hiển thị lại cho người dùng
```

Kiến trúc này có thể chia thành năm khối chính.

**Bảng 3.1. Các lớp chính trong Graphiti Chat Lab**

| Lớp / mô-đun | Thành phần chính | Vai trò thiết kế |
| --- | --- | --- |
| Giao diện | `app/templates/index.html` | Nhận input, hiển thị câu trả lời, facts và trace |
| API | `app/main.py` | Khởi tạo ứng dụng, quản lý vòng đời, định tuyến `/` và `/api/chat` |
| Assistant | `AssistantClient` trong `app/llm_client.py` | Điều phối prompt, tool calling và vòng lặp phản hồi |
| Memory | `GraphitiMemory` trong `app/graphiti_client.py` | Kết nối Graphiti, Neo4j, embedding, truy xuất và ghi nhớ |
| Schema | `app/schemas.py` | Chuẩn hóa request/response và dữ liệu hiển thị |

### 3.2.1. Lớp giao diện

Lớp giao diện chỉ đảm nhiệm nhập và hiển thị, không chứa logic nghiệp vụ. Điều này thể hiện rõ trong template `index.html`: người dùng nhập câu nhắn vào một ô `textarea`, nhấn gửi, rồi JavaScript gọi `POST /api/chat`. Kết quả trả về được chia thành ba phần độc lập: phản hồi của assistant, danh sách `retrieved_facts`, và danh sách `tool_trace`.

### 3.2.2. Lớp API

Trong `app/main.py`, ứng dụng được khởi tạo bằng FastAPI kèm `lifespan`. Khi khởi động, hệ thống đọc cấu hình từ biến môi trường thông qua `GraphitiSettings.from_env()`, khởi tạo `GraphitiMemory`, gọi `initialize()`, rồi tạo `AssistantClient`. Khi tắt ứng dụng, `close()` được gọi để giải phóng tài nguyên Graphiti. Thiết kế này đảm bảo các tài nguyên như kết nối Neo4j và client HTTP được quản lý theo vòng đời ứng dụng, thay vì tạo ngẫu nhiên theo từng request.

### 3.2.3. Lớp assistant

`AssistantClient` là bộ điều phối trung tâm của một lượt chat. Nó không tự sinh bộ nhớ, không tự truy xuất graph, mà chỉ đóng vai trò điều phối giữa mô hình ngôn ngữ và bộ công cụ memory. Cách tách này giúp dễ kiểm soát chất lượng hành vi của agent, vì mọi tool call đều phải đi qua cùng một lớp logic.

### 3.2.4. Lớp memory

`GraphitiMemory` là lớp bao bọc Graphiti core. Lớp này chịu trách nhiệm cấu hình client Graphiti, chọn embedder, tạo chỉ mục, ghi episode, ghi manual fact, truy xuất edge, và hủy fact theo logic nghiệp vụ. Việc gom các thao tác này vào một lớp riêng giúp phần assistant chỉ cần làm việc với một abstraction duy nhất thay vì thao tác trực tiếp với Neo4j.

### 3.2.5. Hợp đồng dữ liệu

File `app/schemas.py` định nghĩa bốn kiểu dữ liệu chính: `ChatRequest`, `RetrievedFact`, `ToolTrace`, và `ChatResponse`. Đây là lớp hợp đồng giúp frontend và backend thống nhất về format dữ liệu. `ChatRequest` chỉ chứa trường `message`, còn `ChatResponse` trả về `reply`, `retrieved_facts`, và `tool_trace`. Thiết kế này phản ánh đúng tinh thần MVP: ít trường, rõ nghĩa, và dễ quan sát.

## 3.3. Luồng xử lý một request chat

Luồng xử lý một request chat bắt đầu từ trình duyệt và kết thúc ở chính trình duyệt, nhưng ở giữa là một vòng lặp có kiểm soát giữa mô hình ngôn ngữ và bộ nhớ.

```text
1. Người dùng nhập nội dung chat và nhấn Send
2. Trình duyệt gửi JSON { message } đến POST /api/chat
3. FastAPI parse dữ liệu bằng `ChatRequest`
4. `main.py` lấy `GraphitiMemory` và `AssistantClient` từ application state
5. `AssistantClient.reply()` tạo prompt có thời gian hiện tại
6. Mô hình sinh text hoặc function call
7. Nếu có function call, `MemoryToolbox` thực thi tool tương ứng
8. Kết quả tool được phản hồi ngược lại cho mô hình
9. Vòng lặp lặp lại tối đa `AGENT_MAX_TOOL_ITERATIONS`
10. Khi không còn tool call, hệ thống trả về `reply`, `retrieved_facts`, `tool_trace`
```

Trong `app/main.py`, code của endpoint rất mỏng: chỉ strip message, lấy memory và assistant từ `request.app.state`, gọi `assistant.reply(message, memory)`, rồi đóng gói kết quả vào `ChatResponse`. Điều này cho thấy toàn bộ logic nghiệp vụ đã được dời sang `AssistantClient` và `MemoryToolbox`, tránh làm endpoint phình to.

### 3.3.1. Chuẩn hóa thời gian trước khi gọi mô hình

Trước khi gửi prompt tới mô hình, `AssistantClient` luôn lấy thời gian địa phương hiện tại qua `now_factory`, sau đó ép múi giờ về `Asia/Ho_Chi_Minh` nếu cần. Giá trị này được đưa trực tiếp vào prompt dưới dạng ISO 8601, gồm cả `Current local datetime` và `Current local date`. Đây là một quyết định thiết kế quan trọng vì các câu hỏi về lịch, hẹn, hoặc “mai” chỉ có thể xử lý đúng khi mô hình biết ngày hiện tại một cách chính xác.

### 3.3.2. Vòng lặp tool calling

`AssistantClient.reply()` tạo một danh sách `contents` theo định dạng Gemini-compatible, sau đó gửi tới hàm `_generate()`. Nếu phản hồi của mô hình chứa `functionCall`, hàm `_extract_function_calls()` sẽ tách từng call ra, `MemoryToolbox.call()` sẽ thực thi tương ứng, và kết quả được đẩy lại cho mô hình dưới dạng `functionResponse`.

Khi có danh sách tool declarations, request tới mô hình bật `toolConfig` ở chế độ `AUTO`. Nói cách khác, assistant không ép mô hình phải dùng tool ở mọi lượt, mà cho phép mô hình tự quyết định khi nào cần truy xuất hoặc cập nhật memory.

Vòng lặp này có hai lớp bảo vệ:

- `AGENT_MAX_TOOL_ITERATIONS` giới hạn số vòng, tránh trường hợp mô hình lặp vô hạn;
- nếu hết vòng lặp mà vẫn còn tool call, hệ thống yêu cầu mô hình tạo câu trả lời cuối chỉ dựa trên kết quả đã có, không gọi thêm công cụ.

Thiết kế này phù hợp với một sản phẩm thực nghiệm vì nó cân bằng giữa tính linh hoạt của agent và tính kiểm soát của backend.

### 3.3.3. Kết quả trả về cho frontend

Khi mô hình đã chốt câu trả lời, `AssistantClient` trả về một `AgentResult` gồm ba thành phần:

- `reply`: nội dung trả lời cuối cùng;
- `retrieved_facts`: danh sách fact đã được truy xuất trong suốt lượt xử lý;
- `tool_trace`: danh sách dấu vết các tool call đã thực thi.

Frontend không cần tự suy diễn lại quá trình bên trong. Nó chỉ render ba khối dữ liệu này lên giao diện, nhờ vậy người dùng có thể đọc câu trả lời và kiểm tra tính hợp lệ của câu trả lời ngay bên cạnh.

## 3.4. Thiết kế bộ nhớ

Phần bộ nhớ là trung tâm của toàn bộ sản phẩm. Nếu không có bộ nhớ, Graphiti Chat Lab chỉ là một chatbot kết nối LLM. Khi có bộ nhớ, sản phẩm mới tạo được giá trị khác biệt: truy vấn lại thông tin cũ, lưu trạng thái dài hạn, và xử lý các sự kiện có yếu tố thời gian.

`GraphitiMemory` giữ vai trò lớp bao bọc cho Graphiti core. Nó được khởi tạo từ `GraphitiSettings`, sau đó tạo `Graphiti` client với ba thành phần chính:

- `ChatCompletionsGraphitiClient` làm LLM client cho Graphiti;
- `Embedder` được chọn theo `EMBEDDING_MODE`;
- `PassthroughReranker` làm reranker tạm thời với mọi điểm số bằng nhau.

### 3.4.1. Cấu hình và vòng đời bộ nhớ

Cấu hình của memory được đọc từ biến môi trường. Một số tham số quan trọng là:

- `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`: kết nối CSDL đồ thị;
- `GRAPHITI_GROUP_ID`: gom dữ liệu của cùng một sản phẩm vào một không gian logic;
- `RETRIEVAL_LIMIT`: giới hạn số kết quả trả về mỗi lần tìm kiếm;
- `EMBEDDING_MODE`: chọn nguồn embedding;
- `EMBEDDING_PRELOAD`: quyết định có nạp sẵn model local hay không;
- `MEMORY_WRITE_MODE`: xác định chiến lược ghi nhớ;
- `AGENT_MAX_TOOL_ITERATIONS`: giới hạn số vòng tool calling của assistant.

Ở tầng LLM, `GraphitiSettings` còn tách riêng `llm_model` và `llm_small_model` để truyền vào `LLMConfig` của Graphiti. Cách tách này giúp lớp memory có đủ thông tin cho cả mô hình chính và mô hình phụ mà Graphiti core có thể cần trong các tác vụ nội bộ.

Khi khởi động, `initialize()` gọi `build_indices_and_constraints()` để Graphiti chuẩn bị chỉ mục và ràng buộc cần thiết. Nếu chế độ embedding là `local` và `EMBEDDING_PRELOAD` bật, model local sẽ được tải sớm bằng `LocalQwenEmbedder.load_model()`. Cách làm này giảm độ trễ ở lượt chat đầu tiên, vốn thường là lượt người dùng cảm nhận rõ nhất.

### 3.4.2. Hai dạng lưu trữ chính

Trong code hiện tại, bộ nhớ được tổ chức thành hai dạng chính: episode và manual temporal fact.

**Bảng 3.2. Hai dạng lưu trữ trong bộ nhớ**

| Dạng lưu | Cách ghi | Mục đích sử dụng |
| --- | --- | --- |
| Episode thông thường | `add_user_message()` hoặc `add_memory_fact()` gọi `_add_episode()` | Lưu các thông tin bền vững, quan hệ, mô tả, và facts tổng quát |
| Manual temporal fact | `add_manual_fact()` tạo quan hệ `MANUAL_FACT` với `valid_at`, `valid_date`, `invalid_at` | Lưu sự kiện có thời điểm rõ ràng như lịch hẹn, deadline, hoặc kế hoạch theo ngày |

Episode thông thường được Graphiti xử lý bằng `add_episode()` cùng bộ `EXTRACTION_INSTRUCTIONS`. Chỉ dẫn này yêu cầu giữ nguyên tên riêng tiếng Việt, giữ hướng của các khoản nợ, và không trích xuất facts từ câu hỏi. Nhờ đó, Graphiti có thể biến câu chat thành các mẩu tri thức có cấu trúc thay vì chỉ lưu chuỗi văn bản thô.

Manual temporal fact là một nhánh lưu trữ đặc biệt dành cho dữ liệu thời gian. Khi nội dung được nhận diện là có yếu tố thời điểm rõ ràng, hệ thống lưu nó vào quan hệ `MANUAL_FACT` giữa hai nút `ManualMemory`. Quan hệ này có các thuộc tính:

- `fact`: nội dung sự kiện;
- `valid_at`: thời điểm hiệu lực;
- `valid_date`: ngày hiệu lực dạng `YYYY-MM-DD`;
- `invalid_at`: thời điểm bị hủy hoặc hết hiệu lực;
- `created_at`: thời điểm ghi vào hệ thống;
- `group_id`: khóa phân vùng dữ liệu.

Thiết kế này đặc biệt hữu ích cho các câu hỏi kiểu “ngày mai tôi có lịch gì không?”. Thay vì phải suy luận từ câu văn tự do, hệ thống chỉ cần tìm các manual fact có `valid_date` đúng ngày mục tiêu và còn hiệu lực.

### 3.4.3. Truy xuất và lọc fact

GraphitiMemory có hai cơ chế truy xuất:

1. `search_edges(message)` truy vấn Graphiti theo ngữ nghĩa bằng `group_ids` và `num_results`;
2. `manual_facts_for_date(target_date)` truy vấn trực tiếp các manual fact theo ngày.

Sau khi lấy dữ liệu, hệ thống chuyển edge thành `RetrievedFact` qua `edges_to_facts()`, rồi lọc theo trạng thái hiệu lực bằng các hàm từ `app/fact_filter.py`. Cụ thể:

- `filter_active_facts()` loại bỏ fact đã hết hiệu lực;
- `filter_active_facts_for_date()` giữ lại fact đúng ngày được hỏi;
- `should_cancel_fact()` quyết định một fact có nên bị hủy theo ngữ cảnh hiện tại hay không.

Lớp lọc này dùng múi giờ địa phương `Asia/Ho_Chi_Minh`, nên các so sánh ngày không bị lệch do múi giờ hệ thống. Đây là chi tiết nhỏ nhưng rất quan trọng đối với bài toán lịch hẹn và deadline.

### 3.4.4. Hủy và thay thế memory

Trong hệ thống này, memory không bị xóa cứng. Thay vào đó, fact bị đánh dấu `invalid_at` để giữ lịch sử. Với edge Graphiti, hàm `invalidate_matching_facts()` cập nhật `invalid_at` lên quan hệ `RELATES_TO` thông qua Cypher. Với manual fact, `invalidate_matching_manual_facts()` cập nhật `invalid_at` trên quan hệ `MANUAL_FACT`.

Thiết kế soft-delete này có ba lợi ích:

- vẫn giữ được lịch sử thay đổi;
- tránh làm mất dấu dữ liệu đã từng tồn tại;
- cho phép các truy vấn tương lai hiểu được fact nào còn hiệu lực.

Đây là lựa chọn hợp lý cho một sản phẩm memory assistant, vì cùng một nội dung có thể được sửa hoặc hủy ở nhiều thời điểm khác nhau.

### 3.4.5. Dedupe và thứ tự ưu tiên

Khi `MemoryToolbox` thu thập facts, các fact được gom vào `retrieved_facts` và dedupe theo bộ khóa `(fact, valid_at, invalid_at)`. Điều này tránh lặp kết quả nếu một lượt chat gọi `search_memory` nhiều lần với các biến thể truy vấn khác nhau.

Ngoài ra, với truy vấn theo ngày, manual facts được ưu tiên rõ ràng hơn vì đây là dữ liệu đã được gắn thời điểm cụ thể. Đây là quyết định thiết kế phù hợp với các use case lịch trình và nhắc việc.

## 3.5. Thiết kế tool calling

Tool calling là lớp kết nối giữa tư duy của mô hình và dữ liệu thật của hệ thống. Nếu không có lớp này, mô hình chỉ có thể trả lời bằng suy diễn. Với tool calling, mô hình có thể đọc, ghi và hủy memory theo các hành động cụ thể của người dùng.

### 3.5.1. Prompt điều khiển hành vi agent

`AssistantClient` sử dụng một system prompt cố định để điều hướng hành vi của mô hình. Prompt này yêu cầu mô hình:

- gọi `search_memory` trước khi trả lời các câu hỏi liên quan đến trí nhớ;
- chuyển các cụm thời gian tương đối thành ngày tuyệt đối trước khi xử lý;
- chỉ lưu các facts có căn cứ từ tin nhắn hiện tại;
- gọi `cancel_matching_facts` trước khi thay thế hoặc hủy thông tin cũ;
- giữ đúng hướng của khoản nợ;
- trả lời bằng cùng ngôn ngữ với người dùng.

Nhờ prompt này, hành vi của mô hình được định hướng theo nghiệp vụ thay vì trả lời hoàn toàn tự do. Đây là cách triển khai thực dụng, phù hợp với nguyên mẫu có memory semantics.

### 3.5.2. MemoryToolbox và phạm vi công cụ

`MemoryToolbox` là lớp thực thi tool thật sự. Nó nhận `memory`, `user_message`, `write_mode`, và `now`, sau đó quyết định tool nào được phép gọi. Nếu một tool không nằm trong `allowed_tool_names`, toolbox trả lỗi ngay thay vì cố thực thi.

**Bảng 3.3. Các tool trong hệ thống**

| Tool | Vai trò | Khi nào được dùng |
| --- | --- | --- |
| `search_memory` | Tìm facts liên quan trong Graphiti memory | Khi người dùng hỏi lại thông tin đã nhớ |
| `remember_current_message` | Lưu nguyên văn thông điệp hiện tại | Khi cấu hình `MEMORY_WRITE_MODE=exact` hoặc `both` |
| `remember_fact` | Lưu một fact được mô hình trích xuất | Khi cấu hình `MEMORY_WRITE_MODE=model` hoặc `both` |
| `cancel_matching_facts` | Hủy hoặc vô hiệu hóa facts liên quan | Khi người dùng sửa, xóa, hoặc phủ định thông tin cũ |

`search_memory` là tool quan trọng nhất cho truy xuất. Nếu có tham số `date`, toolbox ưu tiên tìm manual facts theo ngày trước. Nếu không có `date`, hệ thống tìm edge bằng truy vấn ngữ nghĩa, lọc fact đang hoạt động, rồi trả lại danh sách `RetrievedFact`.

`cancel_matching_facts` được thiết kế để xử lý các mệnh lệnh như “không phải vậy nữa”, “hủy lịch đó”, hoặc “đổi sang ngày khác”. Nó không xóa trực tiếp mà đánh dấu `invalid_at`, nhờ đó lịch sử memory vẫn còn để truy vết.

### 3.5.3. Ba chế độ ghi nhớ `exact`, `model`, `both`

Một điểm quan trọng của thiết kế là `MEMORY_WRITE_MODE` không cố định. Hệ thống hỗ trợ ba chế độ:

**Bảng 3.4. Chế độ ghi nhớ của hệ thống**

| Chế độ | Hành vi ghi nhớ | Ý nghĩa thiết kế |
| --- | --- | --- |
| `exact` | Chỉ cho phép `remember_current_message` | Lưu nguyên văn câu nói của người dùng, giảm diễn giải ngoài ý muốn |
| `model` | Chỉ cho phép `remember_fact` | Để mô hình trích xuất fact ngắn gọn, phù hợp cho lưu tri thức bền |
| `both` | Cho phép cả hai cơ chế | Kết hợp ưu điểm của lưu nguyên văn và lưu fact đã chuẩn hóa |

Trong chế độ `both`, hệ thống có xử lý riêng cho memory mang tính thời gian. Nếu message hoặc fact có yếu tố lịch hẹn, hàm `_save_temporal_manual_fact()` sẽ cố gắng chuyển nội dung đó thành manual temporal fact thay vì chỉ lưu vào episode thông thường. Điều này làm tăng độ chính xác cho các truy vấn theo ngày.

Về mặt sản phẩm, `exact` phù hợp khi cần bảo toàn nguyên văn, `model` phù hợp khi cần dữ liệu gọn và chuẩn hóa, còn `both` là lựa chọn thực dụng nhất cho MVP vì nó hỗ trợ cả tri thức chung lẫn sự kiện có thời gian.

### 3.5.4. Dấu vết xử lý và khả năng kiểm toán

Mỗi lần tool được gọi, `AssistantClient` tạo một `ToolTrace` gồm `name`, `arguments`, và `result`. Danh sách này được trả ra frontend qua `ChatResponse`. Đây không phải chi tiết trang trí, mà là một cơ chế quan trọng để kiểm toán hành vi agent.

`tool_trace` cho phép người dùng thấy:

- assistant đã gọi tool nào;
- tool đó nhận tham số gì;
- kết quả tóm tắt của mỗi lần gọi là gì.

Nhờ vậy, sản phẩm minh bạch hơn một chatbot hộp đen thông thường. Trong bối cảnh memory assistant, minh bạch là yếu tố rất quan trọng để tạo niềm tin.

### 3.5.5. Giới hạn vòng lặp

Biến môi trường `AGENT_MAX_TOOL_ITERATIONS` quy định số vòng tối đa mà assistant được phép gọi tool trong một lượt chat. Khi đạt giới hạn, hệ thống không tiếp tục gọi thêm công cụ mà yêu cầu mô hình trả lời dựa trên những gì đã thu thập được.

Cơ chế này bảo vệ hệ thống khỏi vòng lặp không dứt và giảm nguy cơ chi phí xử lý tăng quá mức. Đây là một quyết định kỹ thuật cần thiết khi triển khai agent có tool calling.

## 3.6. Thiết kế mô hình ngôn ngữ và embedding

Phần mô hình ngôn ngữ của Graphiti Chat Lab được thiết kế để tương thích với endpoint Gemini-compatible, đồng thời vẫn tận dụng được Graphiti core và các lớp schema có cấu trúc.

### 3.6.1. `ChatCompletionsGraphitiClient`

`ChatCompletionsGraphitiClient` kế thừa từ `OpenAIClient` của `graphiti_core`, nhưng ghi đè phương thức structured completion để gọi đến endpoint `generateContent` của Gemini-compatible API. Đây là một adapter quan trọng vì Graphiti core mong đợi một client kiểu OpenAI, trong khi backend thực tế đang dùng một API tương thích Gemini.

Trong adapter này:

- `messages` được chuyển sang body theo định dạng Gemini;
- `response_model` được biến thành `responseSchema` để đảm bảo đầu ra có cấu trúc;
- phản hồi JSON được validate lại bằng Pydantic trước khi trả về cho Graphiti core;
- số token đầu vào và đầu ra được đọc từ `usageMetadata`.

Thiết kế này giúp lớp memory của Graphiti vẫn hoạt động theo giao diện mà thư viện mong đợi, nhưng không khóa sản phẩm vào một nhà cung cấp duy nhất.

### 3.6.2. Cấu hình sinh nội dung

Khi gọi mô hình để sinh phản hồi, `AssistantClient` dùng các tham số cố định sau:

- `temperature = 0.2` để giảm độ ngẫu nhiên;
- `maxOutputTokens = 4096` để đủ không gian cho câu trả lời dài;
- `thinkingConfig = {"thinkingBudget": 0}` để giữ đường đi xử lý gọn và nhất quán.

Các giá trị này cho thấy mục tiêu của hệ thống không phải là sinh văn bản sáng tạo, mà là tạo phản hồi có kiểm soát và bám sát dữ liệu memory.

### 3.6.3. Ba chế độ embedding

Phần embedding cũng được thiết kế linh hoạt để phục vụ các môi trường triển khai khác nhau.

**Bảng 3.5. Chế độ embedding và vai trò**

| Chế độ | Lớp sử dụng | Nguồn embedding | Điều kiện sử dụng |
| --- | --- | --- | --- |
| `proxy` | `OpenAIEmbedder` | Đi qua `LLM_BASE_URL` và `LLM_API_KEY` | Là chế độ mặc định của hệ thống |
| `gemini` | `GeminiEmbedder` | Gọi trực tiếp API của Google | Cần có `GOOGLE_API_KEY` |
| `local` | `LocalQwenEmbedder` | `sentence-transformers` chạy cục bộ | Phù hợp khi muốn giảm phụ thuộc mạng |

Trong code, `proxy` là chế độ mặc định. Điều này cho phép nhóm phát triển tái sử dụng cùng một endpoint gateway cho cả sinh văn bản và embedding, miễn là backend proxy hỗ trợ các API tương thích.

Ở chế độ `gemini`, hệ thống yêu cầu `GOOGLE_API_KEY`. Nếu thiếu khóa này, `GraphitiMemory` ném lỗi ngay khi khởi tạo. Thiết kế fail-fast này phù hợp cho môi trường phát triển vì giúp phát hiện cấu hình sai sớm.

Ở chế độ `local`, hệ thống chuyển sang `LocalQwenEmbedder`. Đây là lớp embedder tự triển khai bằng `sentence-transformers`, chạy trên thread nền để không chặn event loop của FastAPI. `create()` và `create_batch()` đều chuyển sang `asyncio.to_thread()` để giữ tính bất đồng bộ ở tầng API.

### 3.6.4. `LocalQwenEmbedder` và `EMBEDDING_PRELOAD`

`LocalQwenEmbedder` là lớp embedder local quan trọng nhất trong sản phẩm. Nó có ba đặc điểm chính:

- nạp model qua `SentenceTransformer`;
- mã hóa query và document ở hai đường riêng;
- kiểm tra kích thước vector để khớp `EMBEDDING_DIM`.

Khi encode query, lớp này ưu tiên `prompt_name="query"`. Nếu model không hỗ trợ prompt name đó, hệ thống rơi về `QWEN_QUERY_PROMPT` để vẫn tạo embedding hợp lệ. Đây là một chi tiết kỹ thuật nhỏ nhưng rất hữu ích khi làm việc với nhiều biến thể model.

`EMBEDDING_PRELOAD` điều khiển việc tải sớm model local khi khởi động. Nếu bật và embedder đang ở chế độ `local`, `initialize()` sẽ gọi `load_model()`. Nhờ đó, latency của lượt chat đầu tiên giảm xuống và lỗi tải model được phát hiện trước khi người dùng bắt đầu tương tác.

### 3.6.5. Kết nối giữa LLM và memory

LLM của assistant và LLM của Graphiti không hoàn toàn là một. `AssistantClient` trực tiếp gọi endpoint Gemini-compatible để sinh câu trả lời và function call. Trong khi đó, Graphiti core dùng `ChatCompletionsGraphitiClient` như một client chuyên dụng để xử lý các tác vụ structured completion phục vụ memory extraction và retrieval logic.

Đây là cách tách khá hợp lý: lớp assistant tối ưu cho hội thoại và tool use, còn lớp Graphiti tối ưu cho việc tạo và truy xuất tri thức có cấu trúc.

## 3.7. Thiết kế giao diện người dùng

Giao diện người dùng của Graphiti Chat Lab được thiết kế tối giản, ưu tiên khả năng quan sát hơn là hiệu ứng thị giác. Toàn bộ interface nằm trong một trang `index.html`, được render bởi `Jinja2Templates`.

### 3.7.1. Bố cục màn hình

Màn hình chính chia thành hai cột:

- cột trái là khung chat;
- cột phải là vùng hiển thị `Retrieved Facts` và `Tool Trace`.

Ngay cả trong bản mẫu hiện tại, giao diện đã thể hiện rõ triết lý sản phẩm: câu trả lời không đứng một mình, mà luôn đi kèm với dữ liệu đã truy xuất và các thao tác đã thực thi.

### 3.7.2. Cách hiển thị kết quả

Sau khi gửi request, JavaScript trong trang thực hiện ba việc:

1. thêm tin nhắn user vào vùng chat;
2. gọi `fetch("/api/chat")`;
3. nhận JSON và render lại ba phần `reply`, `retrieved_facts`, `tool_trace`.

Hàm `renderFacts()` hiển thị từng fact kèm metadata `valid_at`, `invalid_at`, và `score` nếu có. Hàm `renderTrace()` hiển thị tên tool, arguments dưới dạng JSON, và `result` tóm tắt. Cả hai hàm đều dùng `textContent`, không dùng `innerHTML`, nên tránh được nhiều rủi ro chèn HTML không mong muốn.

### 3.7.3. Thiết kế phản hồi trên màn hình nhỏ

CSS của giao diện dùng lưới hai cột trên màn hình rộng và tự chuyển sang một cột khi chiều ngang nhỏ hơn `820px`. Đây là một lựa chọn thực tế cho prototype vì người dùng có thể thao tác trên laptop hoặc điện thoại mà không vỡ bố cục.

### 3.7.4. Tính minh bạch của giao diện

Phần `Retrieved Facts` và `Tool Trace` là điểm khác biệt quan trọng của UI. Nhiều chatbot chỉ hiển thị câu trả lời cuối; ở đây, người dùng được xem thêm dữ kiện mà hệ thống đã dùng để tạo ra câu trả lời. Điều này rất phù hợp với một sản phẩm memory assistant, nơi tính đúng đắn và khả năng kiểm tra quan trọng không kém tốc độ phản hồi.

## 3.8. Công nghệ sử dụng và vai trò

**Bảng 3.6. Công nghệ chính trong Graphiti Chat Lab**

| Công nghệ | Vai trò trong hệ thống | Ghi chú triển khai |
| --- | --- | --- |
| FastAPI | Xây dựng API `/` và `/api/chat` | Là lớp điều phối chính của backend |
| Uvicorn | ASGI server | Chạy ứng dụng FastAPI trong môi trường dev hoặc deploy |
| Jinja2 | Render `index.html` | Phục vụ giao diện web đơn trang |
| `httpx` | Gọi HTTP tới LLM endpoint | Hỗ trợ bất đồng bộ và dễ kiểm thử |
| `graphiti-core` | Lõi memory graph | Tạo, truy xuất và quản lý memory trên Neo4j |
| Neo4j | CSDL đồ thị | Lưu quan hệ, episode và manual fact |
| `OpenAIClient` trong `graphiti-core` | Base client cho adapter Graphiti | Được kế thừa và ghi đè trong `ChatCompletionsGraphitiClient` |
| Gemini-compatible API | Sinh nội dung và embedding ở chế độ tương thích | Phục vụ `ChatCompletionsGraphitiClient` và `GeminiEmbedder` |
| `sentence-transformers` | Chạy embedding local | Dùng trong `LocalQwenEmbedder` |
| `transformers` | Hỗ trợ hệ sinh thái model local | Là nền tảng cho các model embedding và NLP |
| `python-dotenv` | Nạp biến môi trường | Cho phép cấu hình bằng file `.env` |
| Pydantic | Định nghĩa schema request/response | Dùng trong `app/schemas.py` |

Từ bảng trên có thể thấy công nghệ được chọn đều phục vụ trực tiếp cho mục tiêu sản phẩm. Không có lớp công nghệ nào được đưa vào chỉ để làm đẹp kiến trúc. Đây là một điểm phù hợp với tinh thần MVP.

## 3.9. Xây dựng MVP

MVP của Graphiti Chat Lab tập trung vào các chức năng cốt lõi nhất, đủ để chứng minh tính khả thi của sản phẩm:

- nhận tin nhắn chat từ người dùng;
- truy xuất memory theo ngữ nghĩa hoặc theo ngày;
- lưu thông tin bền vững vào Graphiti;
- lưu sự kiện có thời gian bằng manual temporal fact;
- hủy hoặc vô hiệu hóa memory khi người dùng thay đổi ý;
- hiển thị `retrieved_facts` và `tool_trace` để người dùng kiểm tra kết quả.

MVP này chưa cố bao phủ toàn bộ một nền tảng hội thoại quy mô lớn. Nó chưa có các thành phần như phân quyền người dùng, quản trị dashboard, multi-tenant isolation, hay pipeline đồng bộ phức tạp. Thay vào đó, sản phẩm chọn đúng phần quan trọng nhất: chứng minh rằng một chatbot có memory bền, có xử lý thời gian, và có trace minh bạch là khả thi trên một stack gọn.

### 3.9.1. Giá trị nổi bật của MVP

Giá trị nổi bật của MVP nằm ở chỗ nó xử lý được các tình huống mà chatbot thông thường dễ sai:

- hỏi lại thông tin đã lưu trước đó;
- hỏi lịch cho một ngày tương đối như “mai”;
- sửa hoặc hủy một lịch cũ;
- giữ đúng chiều của quan hệ nợ;
- lưu được tri thức bền mà không cần người dùng lặp lại quá nhiều.

Những tình huống này chính là lý do tồn tại của một memory assistant. Nếu không xử lý tốt các ca này, sản phẩm sẽ chỉ là một giao diện chat khác.

### 3.9.2. Mức độ sẵn sàng phát triển tiếp

Thiết kế hiện tại cũng đã mở sẵn đường cho phát triển tiếp theo. Vì frontend, assistant, memory, và schema được tách rõ, nhóm phát triển có thể thay đổi từng phần mà không phải viết lại toàn bộ hệ thống. Ví dụ, có thể thay embedder, đổi LLM endpoint, hoặc mở rộng cách lọc fact mà vẫn giữ nguyên hợp đồng `ChatResponse`.

Đây là dấu hiệu của một MVP được làm đúng: nhỏ, chạy được, nhưng không khóa chặt khả năng mở rộng về sau.

## 3.10. Kết luận chương

Thiết kế của Graphiti Chat Lab cho thấy một hướng tiếp cận rõ ràng và thực dụng đối với bài toán chatbot có bộ nhớ. Hệ thống được tổ chức theo kiến trúc monolith phân lớp, trong đó `AssistantClient` điều phối hội thoại, `MemoryToolbox` thực thi hành động, `GraphitiMemory` quản lý bộ nhớ đồ thị, còn giao diện người dùng hiển thị lại cả kết quả lẫn dấu vết xử lý.

Các cơ chế như `memory_write_mode` với ba giá trị `exact`, `model`, `both`, bộ nhớ temporal dạng `manual temporal fact`, `retrieved_facts`, `tool_trace`, `AGENT_MAX_TOOL_ITERATIONS`, `EMBEDDING_PRELOAD`, `LocalQwenEmbedder`, và `ChatCompletionsGraphitiClient` không chỉ là chi tiết kỹ thuật riêng lẻ, mà hợp thành một thiết kế thống nhất phục vụ đúng mục tiêu sản phẩm: một MVP memory assistant có khả năng truy xuất, ghi nhớ, và giải thích hành vi của mình.
