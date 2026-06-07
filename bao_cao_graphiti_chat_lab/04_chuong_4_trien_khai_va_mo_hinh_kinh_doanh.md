# Chương 4. Triển khai và mô hình kinh doanh

## 4.1 Mục tiêu của giai đoạn triển khai thực nghiệm

Chương này mô tả cách Graphiti Chat Lab được đưa từ thiết kế sang một nguyên mẫu có thể chạy cục bộ, kiểm thử được và có hướng phát triển thành sản phẩm. Trong bối cảnh một hệ thống chat có bộ nhớ, “triển khai” không chỉ là khởi động server. Quan trọng hơn là phải chứng minh được ba điểm: hệ thống chạy ổn định trên máy phát triển, các quy tắc bộ nhớ hoạt động đúng trong các tình huống khó, và đầu ra của hệ thống đủ minh bạch để người dùng tin cậy.

Vì vậy, phần triển khai của dự án tập trung vào môi trường local-first. Cách làm này phù hợp với một lab thử nghiệm như Graphiti Chat Lab vì cho phép kiểm soát được toàn bộ chuỗi phụ thuộc: Python 3.12, `uv`, Neo4j, cliproxy hoặc Gemini endpoint tương thích OpenAI, và các chế độ embedding khác nhau. Khi mọi thành phần đều được cài đặt và cấu hình cục bộ, việc tái lập lỗi, chạy test, so sánh kết quả và đánh giá chất lượng trở nên đơn giản hơn nhiều so với việc triển khai thẳng lên cloud.

Mục tiêu triển khai thực nghiệm của đề tài không dừng ở “chạy được ứng dụng”, mà còn là kiểm tra những tình huống có rủi ro cao nhất đối với hệ thống memory:

- nhớ lịch ngày mai và truy xuất đúng theo ngày tuyệt đối;
- lưu temporal memory đúng cách, đặc biệt với mốc giờ trong tương lai;
- bảo toàn chiều của khoản nợ, không tráo giữa “ai nợ ai”;
- hủy lịch cũ mà không làm mất các fact còn hiệu lực;
- giới hạn số vòng tool-calling để tránh lặp vô hạn hoặc tăng chi phí không kiểm soát.

Đây cũng là các kịch bản được nhấn mạnh trong `plans/260606-graphiti-chat-lab/plan.md` và được phản ánh trực tiếp trong `tests/test_llm_client.py` và `tests/test_fact_filter.py`. Nói cách khác, phần triển khai ở chương này bám sát đúng những yêu cầu có giá trị nhất của sản phẩm thay vì chỉ mô tả chung chung về framework.

## 4.2 Quy trình triển khai cục bộ

### 4.2.1 Chuẩn bị môi trường và đồng bộ phụ thuộc

Dự án yêu cầu Python `>=3.12` và dùng `uv` làm công cụ duy nhất để quản lý môi trường, dependency và chạy ứng dụng. Đây là lựa chọn thực dụng vì `uv` giúp tái lập môi trường nhanh, phù hợp với một lab cần thử nghiệm lặp lại nhiều lần.

Quy trình cơ bản gồm các bước:

```sh
export UV_CACHE_DIR=.uv-cache
UV_CACHE_DIR=.uv-cache uv sync
```

`uv sync` đọc `pyproject.toml` để cài đúng bộ phụ thuộc của dự án, bao gồm FastAPI, Graphiti core, httpx, Jinja2, python-dotenv, sentence-transformers, transformers, Google Gen AI, OpenAI client và Uvicorn. Cache của `uv` được giữ trong `.uv-cache` ngay trong repository để tránh tạo artefact ngoài thư mục làm việc, đúng với quy ước của dự án.

Ở giai đoạn chạy thực tế, có hai lối khởi động được ghi nhận trong mã nguồn:

1. `./run.sh` để khởi động chuẩn theo kịch bản lab.
2. `UV_CACHE_DIR=.uv-cache uv run python main.py` để chạy nhanh khi dev, có bật `reload=True`.

`run.sh` phù hợp cho luồng khởi động lặp lại vì nó kiểm tra sự tồn tại của `.env`, tự copy từ `.env.example` nếu cần, chạy `uv sync`, rồi khởi động Uvicorn trên `0.0.0.0:8000`. Trong khi đó, `main.py` dùng `uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)`, phù hợp hơn khi muốn debug tại máy cá nhân.

### 4.2.2 Cấu hình file `.env`

File `.env` là điểm chốt cấu hình runtime của toàn bộ hệ thống. Trong `app/main.py`, ứng dụng gọi `load_dotenv()` ngay khi khởi tạo, sau đó `GraphitiSettings.from_env()` đọc và chuẩn hóa các biến môi trường. Cách làm này giúp việc thay đổi môi trường chạy không phải đụng vào code lõi.

Một số biến quan trọng cần cấu hình đúng ngay từ đầu:

| Nhóm cấu hình | Biến môi trường | Vai trò trong hệ thống |
| --- | --- | --- |
| Neo4j | `NEO4J_URI` | Địa chỉ kết nối Bolt đến Neo4j, thường là `bolt://localhost:7687` trong môi trường local |
| Neo4j | `NEO4J_USER`, `NEO4J_PASSWORD` | Thông tin đăng nhập để Graphiti mở kết nối và tạo graph memory |
| LLM | `LLM_BASE_URL` | Endpoint tương thích OpenAI/Gemini; với project này phải bao gồm `/v1` |
| LLM | `LLM_API_KEY` | Khóa truy cập đến cliproxy hoặc backend tương thích |
| LLM | `LLM_MODEL`, `LLM_SMALL_MODEL` | Mô hình dùng cho sinh phản hồi và các tác vụ phụ |
| Embedding | `EMBEDDING_MODE` | Chọn `local`, `proxy` hoặc `gemini` |
| Embedding | `EMBEDDING_MODEL`, `EMBEDDING_DIM` | Tên model và số chiều vector embedding |
| Embedding | `EMBEDDING_PRELOAD` | Có tải sẵn model local khi khởi động hay không |
| Embedding | `GOOGLE_API_KEY` | Bắt buộc khi dùng `EMBEDDING_MODE=gemini` |
| Memory | `GRAPHITI_GROUP_ID` | Nhóm dữ liệu để tách phiên lab khỏi các nhóm khác |
| Memory | `RETRIEVAL_LIMIT` | Số kết quả tối đa cho một lượt truy vấn memory |
| Agent | `MEMORY_WRITE_MODE` | `exact`, `model` hoặc `both` để quyết định cách ghi nhớ |
| Agent | `AGENT_MAX_TOOL_ITERATIONS` | Giới hạn số vòng function-calling trong một request |
| Compatibility | `MEMORY_INGEST_BACKGROUND` | Biến giữ lại cho tương thích lịch sử, nhưng `/api/chat` hiện dùng tool writes đồng bộ |

Trong `GraphitiSettings.from_env()`, hệ thống còn có cơ chế fail-fast để tránh cấu hình sai âm thầm. Ví dụ, nếu `MEMORY_WRITE_MODE` không thuộc tập hợp hợp lệ thì ứng dụng sẽ báo lỗi ngay khi khởi động. Tương tự, nếu chọn `EMBEDDING_MODE=gemini` nhưng không có `GOOGLE_API_KEY`, phần khởi tạo embedder cũng sẽ dừng sớm. Với một lab memory, cách báo lỗi sớm này tốt hơn rất nhiều so với việc để hệ thống chạy lệch cấu hình rồi trả kết quả sai ở lúc demo.

Về chiến lược triển khai, có ba chế độ embedding chính:

- `proxy`: dùng endpoint embeddings tương thích OpenAI của cliproxy, phù hợp khi proxy đã hỗ trợ đầy đủ.
- `gemini`: gọi embedding của Google trực tiếp, phù hợp khi proxy không có embeddings nhưng có API key.
- `local`: dùng `sentence-transformers` và Qwen3 embedding để chạy độc lập với API ngoài.

Chế độ `local` rất có giá trị cho nguyên mẫu vì giảm phụ thuộc vào dịch vụ bên ngoài. Dù vậy, lần chạy đầu tiên có thể tải model về `.hf-cache/`, nên chấp nhận đánh đổi giữa thời gian khởi động ban đầu và khả năng vận hành không cần API key. Đây là một trade-off đúng với tinh thần thực nghiệm của đề tài.

### 4.2.3 Neo4j và lớp lưu trữ Graphiti

Neo4j là nền tảng lưu trữ chính của Graphiti Chat Lab. Lý do chọn Neo4j là vì bài toán bộ nhớ của dự án không chỉ là lưu text, mà là lưu các fact có quan hệ, có thời điểm hiệu lực và có trạng thái bị hủy. Graph memory cho phép biểu diễn các sự kiện như một đồ thị, từ đó hỗ trợ truy hồi theo quan hệ và theo trạng thái.

Trong `README.md`, phần hướng dẫn cài đặt Neo4j local được viết theo nhánh Debian/Ubuntu, yêu cầu Java 21 và Neo4j Community Edition. Điều này phù hợp với mục tiêu lab vì có thể dựng một môi trường local đủ gần với môi trường thật mà không cần hạ tầng phức tạp.

Khi ứng dụng khởi động, `app/main.py` tạo `GraphitiSettings`, rồi khởi tạo `GraphitiMemory`. Trong `GraphitiMemory.initialize()`, hệ thống xây dựng index và constraint trước khi nhận request đầu tiên. Đây là bước rất quan trọng vì memory retrieval chỉ ổn định khi schema của graph đã sẵn sàng.

Thiết kế dữ liệu trong `app/graphiti_client.py` chia ra hai lớp lưu trữ chính:

1. Episode theo dòng chat: `add_user_message()` và `add_memory_fact()` đưa nội dung vào Graphiti như một phần của luồng hội thoại.
2. Manual temporal fact: `add_manual_fact()` lưu fact có ngày giờ cụ thể, kèm `valid_at`, `valid_date`, `invalid_at` và `created_at`.

Cách tách này giải quyết đúng vấn đề mà bài toán lịch hẹn gặp phải. Một câu như “chiều mai 2 giờ đi chơi game với anh Tú” cần vừa giữ nguyên ý nghĩa hội thoại, vừa được chuẩn hóa thành một fact có thời điểm rõ ràng để truy vấn theo ngày. Nếu chỉ lưu như text thuần, hệ thống sẽ rất khó lọc đúng vào ngày mai.

Lớp lưu trữ cũng có cơ chế hủy:

- `invalidate_matching_facts()` cập nhật `invalid_at` cho các cạnh `RELATES_TO` khớp điều kiện;
- `invalidate_matching_manual_facts()` cập nhật `invalid_at` cho các cạnh `MANUAL_FACT`;
- `should_cancel_fact()` và `filter_active_facts_for_date()` đảm bảo fact đã hủy không còn được xem là active.

Điểm đáng chú ý là `group_id` được dùng để cô lập dữ liệu của lab. Điều này giúp tránh lẫn fact giữa các lần chạy khác nhau, đặc biệt khi test nhiều kịch bản liên tiếp.

### 4.2.4 Khởi động ứng dụng và kiểm tra giao diện

Sau khi Neo4j sẵn sàng và `.env` đã được cấu hình, ứng dụng có thể được chạy bằng một trong hai cách:

```sh
./run.sh
```

hoặc:

```sh
UV_CACHE_DIR=.uv-cache uv run python main.py
```

Khi server hoạt động, trang chủ mở tại `http://127.0.0.1:8000`. Trong `app/main.py`, endpoint `GET /` trả về giao diện HTML từ `app/templates/index.html`, còn `POST /api/chat` là nơi xử lý hội thoại.

Giao diện người dùng được thiết kế theo hướng rất thực dụng: bên trái là khung chat, bên phải là vùng hiển thị `Retrieved Facts` và `Tool Trace`. Cách bố trí này quan trọng vì nó biến quá trình trả lời của AI thành một chuỗi có thể quan sát. Người dùng không chỉ đọc câu trả lời cuối mà còn thấy được hệ thống đã nhớ gì và đã gọi tool nào.

Với một lab memory, điều này mang ý nghĩa sản phẩm rất lớn. Nó giúp:

- debug nhanh khi kết quả không như mong đợi;
- giải thích vì sao hệ thống trả lời như vậy;
- phân biệt giữa lỗi truy hồi, lỗi ghi nhớ và lỗi sinh ngôn ngữ;
- tạo niềm tin cho người dùng khi cần kiểm tra lại thông tin cũ.

## 4.3 Kiểm thử các kịch bản quan trọng

Phần kiểm thử của dự án không cố phủ hết mọi nhánh logic, mà tập trung vào các điểm dễ sai nhất và có giá trị sản phẩm cao nhất. Hai nhóm test chính là `tests/test_fact_filter.py` và `tests/test_llm_client.py`.

`tests/test_fact_filter.py` kiểm thử các hàm lọc thuần liên quan đến thời gian và trạng thái. Bộ test này dùng thời điểm cố định `2026-06-06T12:00:00+07:00` để tránh kết quả thay đổi theo ngày thực tế. Đây là một lựa chọn rất đúng cho các bài toán có “ngày mai”, vì nếu không khóa mốc thời gian thì test sẽ thiếu tính lặp lại.

`tests/test_llm_client.py` dùng `httpx.MockTransport` để giả lập phản hồi từ LLM, đồng thời dùng `FakeMemory` để tách phần logic agent khỏi Graphiti thật. Nhờ vậy, các test có thể kiểm tra chính xác từng hành vi: tool nào được mở, tool nào được gọi, input nào được truyền, và kết quả nào được ghi lại trong `tool_trace`.

### 4.3.1 Nhớ lịch ngày mai

Đây là kịch bản quan trọng nhất của một trợ lý có bộ nhớ thời gian. Trong `tests/test_fact_filter.py`, các test như `test_tomorrow_filter_keeps_only_target_date`, `test_tomorrow_filter_removes_canceled_schedule`, `test_tomorrow_filter_hides_invalidated_schedule` và `test_tomorrow_filter_keeps_schedule_with_future_expiry` kiểm tra trực tiếp cách lọc fact cho câu hỏi có yếu tố “ngày mai”.

Các test này cho thấy hệ thống không chỉ tìm kiếm theo từ khóa. Nó còn:

- chuyển mốc tương đối “ngày mai” thành ngày tuyệt đối;
- giữ lại fact có `valid_at` đúng ngày cần hỏi;
- loại các fact đã bị hủy hoặc đã hết hiệu lực;
- vẫn cho phép fact còn hiệu lực nhưng có `invalid_at` trong tương lai tiếp tục xuất hiện.

Trong `tests/test_llm_client.py`, case `test_search_memory_filters_active_facts_by_requested_date` đi xa hơn một bước. Nó kiểm tra cách agent tạo chuỗi truy vấn memory cho câu hỏi “ngày mai tôi có cần làm gì không?”. Dữ liệu test cho thấy hệ thống sẽ thử nhiều biến thể query, chẳng hạn query gốc, query gắn ngày cụ thể, và cả một truy vấn tổng quát về lịch trình trong ngày đó. Kết quả cuối cùng chỉ giữ lại fact đúng ngày và đúng trạng thái active.

Ngoài ra, `test_search_memory_uses_manual_facts_for_dated_recall` chứng minh rằng khi đã có temporal fact được lưu thủ công, hệ thống có thể truy xuất trực tiếp từ danh sách fact theo ngày thay vì phải quét toàn graph. Đây là một tối ưu rất đáng giá cho các câu hỏi lịch hẹn ngắn gọn, vì nó giảm nhiễu và tăng độ chính xác.

### 4.3.2 Nợ đúng chiều

Đây là một case nghiệp vụ đặc biệt quan trọng, dù hiện tại chưa có một unit test riêng trong thư mục `tests/`. Ràng buộc này đã được chốt ở hai nơi:

- `AGENT_SYSTEM_PROMPT` trong `app/llm_client.py`, nơi hệ thống được nhắc phải bảo toàn chiều nợ;
- `EXTRACTION_INSTRUCTIONS` trong `app/graphiti_client.py`, nơi hướng dẫn trích xuất nợ phải ghi rõ ai là chủ nợ, ai là con nợ, và số tiền.

Trong `plans/260606-graphiti-chat-lab/plan.md`, phần manual eval còn đặt ra đúng cặp ví dụ:

- `Minh nợ tao 60k`
- `Tao nợ Nam 30k`

và yêu cầu câu trả lời cho các truy vấn như “Ai nợ tao tiền?” hoặc “Tao nợ ai?” không được chứa fact ngược chiều. Nói cách khác, đây là một tiêu chí chất lượng bắt buộc cho sản phẩm, vì sai chiều nợ thì câu trả lời có thể gây hiểu nhầm nghiêm trọng.

Ở mức triển khai hiện tại, cách đánh giá phù hợp nhất là:

1. seed các fact nợ vào memory;
2. hỏi lại bằng hai kiểu truy vấn đối xứng;
3. kiểm tra `retrieved_facts` xem có lẫn fact ngược chiều hay không;
4. kiểm tra câu trả lời cuối có bám vào fact đã truy hồi hay chỉ nói theo suy đoán.

Vì đây là ngưỡng rủi ro cao của một trợ lý cá nhân, trường hợp này nên được giữ như một test case thủ công bắt buộc trong demo, ngay cả khi sau này có thêm unit test tự động riêng.

### 4.3.3 Lưu temporal memory

Kịch bản lưu temporal memory phản ánh đúng sự khác nhau giữa “nhớ nguyên văn” và “nhớ đã chuẩn hóa”. Trong `tests/test_llm_client.py`, `test_exact_write_tool_saves_current_message_before_reply` kiểm tra chế độ `exact`: khi mô hình chọn `remember_current_message`, hệ thống lưu nguyên văn tin nhắn của người dùng trước khi trả lời.

Quan trọng hơn, `test_model_write_tool_saves_temporal_memory_as_current_message_in_both_mode` kiểm tra chế độ `both`. Khi tin nhắn chứa yếu tố thời gian như “chieu 2 gio ngay mai toi di choi game voi anh Tu”, hệ thống không chỉ lưu text. Nó còn chuẩn hóa thành temporal fact có thời điểm tuyệt đối, ví dụ `2026-06-07T14:00:00+07:00`, rồi lưu vào `manual_facts`.

Điều này có hai ý nghĩa:

- về mặt trải nghiệm, người dùng chỉ cần nói theo cách tự nhiên;
- về mặt lưu trữ, hệ thống giữ được một bản ghi có thể truy vấn chính xác theo ngày giờ.

Nếu xét theo nghiệp vụ, đây là một bước tiến quan trọng so với chatbot thông thường, vốn thường chỉ “nhớ” theo dạng log text. Graphiti Chat Lab đang hướng tới một memory có thể dùng lại, lọc lại và hủy lại, chứ không phải chỉ giữ transcript.

### 4.3.4 Hủy lịch và cập nhật trạng thái

Hủy lịch là nơi nhiều hệ thống chat memory dễ sai nhất. Người dùng không chỉ muốn thêm thông tin, mà còn muốn xóa hoặc thay đổi thông tin đã lưu. Với Graphiti Chat Lab, case này được xử lý theo cả hai nhánh: nhánh edge trong graph và nhánh manual temporal fact.

Trong `tests/test_fact_filter.py`, các test `test_tomorrow_filter_removes_canceled_schedule` và `test_tomorrow_filter_hides_invalidated_schedule` cho thấy một fact đã bị hủy sẽ không còn xuất hiện trong kết quả lọc. `test_tomorrow_filter_keeps_schedule_with_future_expiry` lại xác nhận rằng fact chưa hết hạn vẫn còn hiệu lực, tức hệ thống không hủy nhầm.

Trong `tests/test_llm_client.py`, `test_cancel_matching_facts_invalidates_active_dated_edges` kiểm tra đầy đủ vòng lặp tool-calling cho lệnh hủy. Mô hình gọi `cancel_matching_facts`, hệ thống tìm các edge khớp, đánh dấu invalid, rồi ghi nhận vào `tool_trace` với kết quả `invalidated 1 matching fact(s)`.

Đây là case rất quan trọng về sản phẩm vì một trợ lý có memory mà không xóa được lịch cũ sẽ nhanh chóng mất niềm tin của người dùng. Với các use case như lịch hẹn, công việc, hoặc nợ, “hủy đúng” đôi khi còn quan trọng hơn “nhớ đúng”.

### 4.3.5 Giới hạn số vòng tool iteration

Case `test_tool_iteration_limit_gets_final_no_tool_answer` kiểm tra một điểm an toàn rất đáng giá: hệ thống phải dừng đúng ngưỡng khi tool-calling đi quá xa. Trong test này, `max_tool_iterations=1`, mô hình được phép gọi tool một lần rồi buộc phải chuyển sang câu trả lời cuối cùng mà không gọi thêm tool.

Ý nghĩa của cơ chế này không chỉ là tránh bug vòng lặp. Nó còn là biện pháp kiểm soát:

- latency của một request chat;
- số lần gọi sang LLM;
- chi phí tính toán;
- rủi ro model “mải gọi tool” nhưng không chốt câu trả lời.

Trong kiến trúc hiện tại, khi chạm ngưỡng, `AssistantClient` còn thêm một yêu cầu nội bộ để mô hình trả lời từ kết quả tool đã có thay vì tiếp tục tìm thêm tool. Đây là một thiết kế an toàn, vì nó buộc hệ thống phải đóng vòng lặp và trả kết quả hữu ích cho người dùng.

### 4.3.6 Bảng tổng hợp kết quả kiểm thử

| Kịch bản kiểm thử | Nguồn kiểm thử / ràng buộc | Kết quả mong đợi | Kết quả quan sát trong bộ test |
| --- | --- | --- | --- |
| Nhớ lịch ngày mai | `tests/test_fact_filter.py`, `tests/test_llm_client.py` | Chỉ giữ fact có `valid_at` đúng ngày mục tiêu và còn hiệu lực | Đạt |
| Lưu temporal memory | `test_exact_write_tool_saves_current_message_before_reply`, `test_model_write_tool_saves_temporal_memory_as_current_message_in_both_mode` | Lưu nguyên văn ở `exact`, lưu fact chuẩn hóa ở `both` | Đạt |
| Hủy lịch | `test_cancel_matching_facts_invalidates_active_dated_edges` và các test lọc canceled fact | Fact bị hủy không còn xuất hiện trong kết quả active | Đạt |
| Nợ đúng chiều | `AGENT_SYSTEM_PROMPT`, `EXTRACTION_INSTRUCTIONS`, `plan.md` | Không tráo chiều nợ giữa “A nợ B” và “B nợ A” | Đang được bảo đảm ở mức rule và manual eval, cần xác nhận trong demo |
| Giới hạn tool iteration | `test_tool_iteration_limit_gets_final_no_tool_answer` | Chặn vòng lặp tool quá dài, vẫn trả lời cuối từ kết quả hiện có | Đạt |

Nhìn tổng thể, bộ test hiện có không chạy theo kiểu “số lượng lớn”, nhưng lại đánh đúng điểm yếu thực sự của sản phẩm. Các case được chọn đều liên quan trực tiếp đến niềm tin của người dùng: nhớ đúng, hủy đúng, giữ đúng chiều nợ, và không để agent lặp vô hạn.

## 4.4 Đánh giá kết quả và hiệu quả

### 4.4.1 Độ đúng và độ ổn định của truy hồi

Kết quả quan sát từ bộ test cho thấy hệ thống có khả năng truy hồi theo ngữ cảnh thời gian tốt hơn cách làm RAG văn bản thuần. Lý do là Graphiti Chat Lab không chỉ tìm fact giống ngữ nghĩa, mà còn có lớp lọc theo ngày, theo trạng thái active/inactive, và theo ý định hủy.

Khi người dùng hỏi về “ngày mai”, hệ thống chuyển câu hỏi thành một mốc ngày cụ thể, rồi chỉ giữ các fact có `valid_at` nằm đúng ngày đó. Khi fact đã bị hủy, `invalid_at` làm nhiệm vụ loại bỏ fact khỏi luồng trả lời. Cách này làm giảm đáng kể khả năng trả lời bằng dữ liệu cũ.

Đối với các use case lịch hẹn, đây là tiêu chí rất quan trọng. Người dùng không quan tâm hệ thống “trả lời nghe có vẻ hợp lý”, mà quan tâm nó có nhớ đúng lịch ngày mai hay không. Bộ test hiện có cho thấy pipeline hiện tại đã đi đúng hướng.

### 4.4.2 Hiệu quả của temporal memory

Phần temporal memory là điểm sáng của dự án. Khi `MEMORY_WRITE_MODE=both`, agent có thể lưu song song hai thứ:

- một biểu diễn bền vững để truy vấn lại;
- một bản ghi thời gian chuẩn hóa để phục vụ lịch hẹn và nhắc việc.

Điều này giúp hệ thống vừa mềm dẻo ở đầu vào, vừa chặt chẽ ở đầu ra. Người dùng có thể nói theo ngôn ngữ tự nhiên như “chiều mai 2 giờ”, nhưng hệ thống vẫn biến nó thành một giá trị có ngày giờ tuyệt đối để truy vấn sau này.

Hiệu quả của cách làm này thấy rõ ở case `test_search_memory_uses_manual_facts_for_dated_recall`: một khi temporal fact đã được lưu chuẩn, truy vấn ngày cụ thể không còn cần quét toàn bộ graph. Nó chỉ cần lấy đúng các fact theo ngày đó. Đây là một tối ưu tốt cho cả tốc độ lẫn độ chính xác.

### 4.4.3 Kiểm soát chi phí và độ trễ

Một hệ thống chat memory có thể dễ tăng chi phí nếu vòng tool-calling không được kiểm soát. Trong Graphiti Chat Lab, `AGENT_MAX_TOOL_ITERATIONS` là giới hạn rất quan trọng. Nó đặt trần cho số lần mô hình có thể gọi tool trước khi phải chốt câu trả lời.

Cơ chế này đem lại ba lợi ích sản phẩm:

1. giảm nguy cơ loop vô hạn;
2. tạo độ trễ dự đoán được hơn;
3. khóa chi phí LLM ở mức hợp lý cho một request.

Ngoài ra, việc hệ thống viết memory theo kiểu synchronous trước khi trả response cũng giúp giảm lỗi “trả lời xong mới ghi nhớ”. Điều này tăng tính nhất quán, dù có thể làm tăng nhẹ thời gian phản hồi. Với một nguyên mẫu cần độ chính xác và tính giải thích, trade-off này là hợp lý.

### 4.4.4 Tính minh bạch và khả năng tin cậy

Khác biệt lớn nhất của hệ thống này so với một chatbot thông thường là nó không che giấu toàn bộ quá trình suy luận. `retrieved_facts` cho người dùng biết hệ thống đã dựa vào thông tin nào, còn `tool_trace` cho biết từng tool đã làm gì. Điều đó giúp:

- người dùng phát hiện ngay nếu memory bị thiếu;
- nhóm phát triển kiểm tra nhanh khi tool chọn sai;
- dễ diễn giải cho người dùng cuối trong buổi demo hoặc pilot.

Trong các sản phẩm AI, niềm tin thường đến từ khả năng giải thích chứ không chỉ từ chất lượng ngôn ngữ. Graphiti Chat Lab chọn đúng hướng này.

### 4.4.5 Nhận xét về các chế độ embedding và lưu trữ

Ở góc độ vận hành, hệ thống cho phép chọn ba chế độ embedding là `local`, `proxy`, và `gemini`. Đây là thiết kế thực dụng vì mỗi môi trường sẽ có một bài toán khác nhau:

- môi trường lab nội bộ ưu tiên `local` để không phụ thuộc API key;
- môi trường demo nhanh có thể dùng `proxy`;
- môi trường có Google API key có thể dùng `gemini` trực tiếp.

Mặc dù vậy, trade-off cũng rõ ràng: `local` tiện cho kiểm thử nhưng có chi phí tải model ban đầu; `proxy` gọn nhưng phụ thuộc vào khả năng của cliproxy; `gemini` đơn giản ở phía client nhưng đòi hỏi cấu hình key ngoài. Việc hỗ trợ nhiều mode trong cùng một codebase làm cho dự án linh hoạt hơn khi bước sang giai đoạn pilot.

## 4.5 Mô hình kinh doanh và định hướng thương mại hóa

### 4.5.1 Định vị sản phẩm

Về bản chất, Graphiti Chat Lab không nên được định vị là “một chatbot khác”. Điểm bán hàng thực sự của nó là memory layer có cấu trúc cho hội thoại cá nhân và nhóm nhỏ. Điều này đặc biệt phù hợp với các tình huống:

- người dùng cần nhớ lịch;
- người dùng cần quản lý nợ hoặc cam kết;
- nhóm nhỏ cần hỏi lại ngữ cảnh cũ mà không phải lục toàn bộ log chat;
- các ứng dụng khác muốn dùng một lớp memory sẵn có thay vì tự xây từ đầu.

Nói cách khác, sản phẩm có thể được kể như một “bộ nhớ có thể truy vấn, giải thích và hủy” thay vì một AI chat chung chung. Cách định vị này sắc nét hơn, dễ bán hơn và phù hợp với cách một sản phẩm khởi nghiệp tìm ngách.

### 4.5.2 Business Model Canvas rút gọn

| Khối canvas | Nội dung đề xuất cho Graphiti Chat Lab |
| --- | --- |
| Phân khúc khách hàng | Sinh viên, freelancer, người làm việc tự do, nhóm nhỏ, doanh nghiệp nhỏ, nhà phát triển cần memory layer |
| Giá trị cốt lõi | Ghi nhớ dài hạn có cấu trúc, truy hồi theo thời gian, hủy lịch cũ, giữ đúng chiều nợ, trả về `retrieved_facts` và `tool_trace` |
| Kênh phân phối | Web app demo, API, bản on-premise, pilot theo nhóm, tài liệu tích hợp cho developer |
| Quan hệ khách hàng | Tự phục vụ qua UI, onboarding đơn giản, hỗ trợ kỹ thuật trực tiếp cho gói pilot và enterprise |
| Dòng doanh thu | Thuê bao theo người dùng, phí API theo mức sử dụng, license theo tổ chức, triển khai riêng cho khách hàng doanh nghiệp |
| Nguồn lực chính | Neo4j, Graphiti core, LLM endpoint, embedding model, prompt/tool policy, đội ngũ kỹ thuật và đánh giá nghiệp vụ |
| Hoạt động chính | Tối ưu truy hồi, tinh chỉnh memory policy, theo dõi chất lượng, vận hành hạ tầng, hỗ trợ tích hợp |
| Đối tác chính | Nhà cung cấp LLM, nhà cung cấp proxy, Neo4j, hạ tầng cloud, đối tác pilot |
| Cơ cấu chi phí | Chi phí inference, embeddings, Neo4j, lưu trữ, vận hành, giám sát, bảo trì và hỗ trợ người dùng |

Canvas trên cho thấy mô hình kinh doanh của Graphiti Chat Lab không phụ thuộc vào việc “bán một chatbot” mà phụ thuộc vào việc bán một năng lực nền tảng: nhớ đúng và giải thích được. Đây là hướng rất hợp lý nếu muốn chuyển từ nguyên mẫu lab sang một sản phẩm có doanh thu.

### 4.5.3 Các gói thương mại hóa khả thi

Từ canvas trên, có thể chia lộ trình thương mại hóa thành ba lớp.

**1. Bản cá nhân hoặc demo miễn phí**

Gói này phù hợp với sinh viên, người dùng cá nhân, hoặc nhóm muốn thử sản phẩm. Mục tiêu chính là tạo thói quen sử dụng và thu thập phản hồi ban đầu. Trong gói này, hệ thống có thể chạy local, dùng một số giới hạn nhỏ về số fact và số lượt hỏi.

**2. Gói thuê bao cho nhóm nhỏ**

Đây là hướng phù hợp nhất trong giai đoạn đầu thương mại hóa. Nhóm nhỏ thường cần ghi nhớ lịch, công việc, hoặc cam kết giữa các thành viên. Giá trị của hệ thống lúc này không nằm ở AI trả lời hay, mà ở việc không làm mất ngữ cảnh quan trọng. Doanh thu có thể tính theo số tài khoản hoạt động hoặc theo mức sử dụng API.

**3. Gói doanh nghiệp hoặc on-premise**

Nếu một tổ chức quan tâm đến dữ liệu nội bộ, phương án on-premise có thể hấp dẫn hơn. Khi đó, Graphiti Chat Lab có thể được đóng gói thành lớp memory cho hệ thống chat nội bộ, trợ lý bán hàng, hoặc trợ lý CSKH. Gói này thường có biên lợi nhuận tốt hơn nhưng đòi hỏi nhiều công sức triển khai và hỗ trợ kỹ thuật hơn.

### 4.5.4 Lợi thế cạnh tranh có thể giữ lại

Để không bị hòa lẫn vào thị trường chatbot đông đúc, sản phẩm cần giữ lại một số lợi thế cứng:

- memory graph thay vì chỉ log text;
- truy hồi theo ngày và theo trạng thái hiệu lực;
- hủy thông tin cũ thay vì chỉ append thêm;
- phản hồi có thể kiểm chứng bằng retrieved facts;
- hỗ trợ tiếng Việt và các biểu đạt thời gian tự nhiên.

Nếu duy trì được các lợi thế này, Graphiti Chat Lab có thể đi vào một ngách rõ ràng: “memory assistant” cho hội thoại cá nhân và nhóm nhỏ. Đây là ngách đủ hẹp để làm tốt, nhưng vẫn đủ lớn để thương mại hóa.

### 4.5.5 Rủi ro thương mại hóa và hướng giảm thiểu

Rủi ro lớn nhất của sản phẩm là dữ liệu sai ngữ cảnh. Nếu nhớ sai lịch hoặc đổi sai chiều nợ, người dùng sẽ mất tin cậy rất nhanh. Vì vậy, product-market fit của giải pháp này phụ thuộc nhiều vào chất lượng memory hơn là vào độ hoa mỹ của câu trả lời.

Rủi ro thứ hai là chi phí mô hình và hạ tầng. Đây là lý do hệ thống hỗ trợ nhiều chế độ embedding và có `AGENT_MAX_TOOL_ITERATIONS` để khống chế chi phí hội thoại. Rủi ro thứ ba là quyền riêng tư dữ liệu; với lịch cá nhân và khoản nợ, đây là loại thông tin có độ nhạy cao, nên khi bước sang thương mại hóa cần bổ sung xác thực, phân quyền và tách tenant rõ ràng.

Giải pháp giảm thiểu tốt nhất hiện tại là giữ sản phẩm ở quy mô lab/pilot trước, ghi nhận phản hồi, rồi mới mở rộng sang multi-user và cloud deployment. Đây là cách đi an toàn và đúng với tinh thần “kiểm chứng trước, mở rộng sau”.

## 4.6 Kết luận chương

Kết quả triển khai thực nghiệm cho thấy Graphiti Chat Lab đã đi qua được các bước quan trọng để chuyển từ ý tưởng thành nguyên mẫu có thể dùng thử: cấu hình môi trường bằng `.env`, đồng bộ phụ thuộc bằng `uv`, khởi tạo Neo4j và Graphiti, chạy ứng dụng FastAPI, hiển thị `retrieved_facts` và `tool_trace`, rồi kiểm thử các kịch bản khó như nhớ lịch ngày mai, lưu temporal memory, hủy lịch, giữ đúng chiều nợ và giới hạn vòng tool-calling.

Ở góc độ sản phẩm, hệ thống đã thể hiện được một hướng đi rõ ràng: không bán “chatbot tổng quát”, mà bán “memory layer có cấu trúc và có thể kiểm chứng”. Đây là hướng có tính thực tiễn, vì nó bám đúng các nhu cầu mà người dùng thật gặp phải trong đời sống và công việc hằng ngày.

Ở góc độ thương mại hóa, mô hình kinh doanh khả thi nhất trước mắt là đi từ bản demo cá nhân sang pilot nhóm nhỏ, rồi tiến dần tới thuê bao hoặc API cho các ứng dụng cần bộ nhớ hội thoại. Nếu tiếp tục hoàn thiện xác thực, phân quyền và đánh giá chất lượng ở quy mô lớn hơn, Graphiti Chat Lab có cơ sở để trở thành một sản phẩm memory-as-a-service thay vì chỉ dừng ở mức nguyên mẫu nghiên cứu.
