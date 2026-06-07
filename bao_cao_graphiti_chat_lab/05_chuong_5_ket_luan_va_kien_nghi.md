# Chương 5. Kết Luận Và Kiến Nghị

## 5.1 Kết quả chính đạt được

Đề tài Graphiti Chat Lab đã hoàn thành mục tiêu xây dựng một nguyên mẫu ứng dụng chat có bộ nhớ dài hạn, trong đó bộ nhớ không còn được hiểu như một chuỗi lịch sử hội thoại thuần túy mà trở thành một lớp dữ liệu có cấu trúc, có khả năng truy hồi, cập nhật và vô hiệu hóa theo ngữ cảnh sử dụng. Xét trên mặt kiến trúc, hệ thống được tổ chức theo một luồng xử lý tương đối rõ ràng: `app/main.py` khởi tạo vòng đời ứng dụng FastAPI và gắn các thành phần hạ tầng vào `app.state`, `app/llm_client.py` điều phối mô hình ngôn ngữ theo cơ chế tool-calling, `app/graphiti_client.py` quản lý lớp bộ nhớ Graphiti/Neo4j, còn `app/fact_filter.py` đảm nhiệm các quy tắc lọc fact theo thời gian và trạng thái hiệu lực. Cách phân lớp này giúp nguyên mẫu có thể vận hành end-to-end, nhưng vẫn giữ được biên tách tương đối sạch giữa giao diện, điều phối hội thoại và lưu trữ bộ nhớ.

Kết quả đầu ra của một lượt chat cũng được chuẩn hóa thành ba thành phần có ý nghĩa vận hành rõ ràng gồm `reply`, `retrieved_facts` và `tool_trace`. Đây là một lựa chọn thiết kế quan trọng vì nó biến quá trình suy luận của trợ lý từ một hộp đen thành một chuỗi thao tác có thể kiểm chứng. Người dùng không chỉ nhận được câu trả lời cuối cùng, mà còn quan sát được hệ thống đã truy xuất những fact nào, đã gọi tool nào, và mỗi tool đã tạo ra thay đổi gì trong luồng xử lý. Trong bối cảnh một sản phẩm liên quan đến trí nhớ cá nhân, tính minh bạch này có giá trị thực tiễn cao vì nó tăng độ tin cậy, giảm cảm giác “AI đoán mò”, đồng thời tạo nền tảng cho kiểm thử và đánh giá sau này.

Về năng lực nghiệp vụ, hệ thống đã chứng minh được bốn khả năng cốt lõi. Thứ nhất, trợ lý có thể tìm kiếm tri thức liên quan trước khi trả lời, thay vì phản hồi ngay trên ngữ cảnh ngắn hạn. Thứ hai, hệ thống có thể lưu các phát biểu bền vững của người dùng theo nhiều chế độ khác nhau, bao gồm lưu nguyên văn câu nói, lưu fact do mô hình trích xuất, hoặc kết hợp cả hai. Thứ ba, hệ thống có thể hủy hoặc vô hiệu hóa thông tin cũ khi người dùng cập nhật hoặc phủ định một kế hoạch, một cuộc hẹn hay một khoản nợ. Thứ tư, hệ thống có thể diễn giải các mốc thời gian tương đối ở mức đủ dùng cho các kịch bản phổ biến, đặc biệt là nhóm câu hỏi xoay quanh “mai”, “ngày mai”, “hôm nay” và các diễn đạt thời gian gần.

Trong `app/llm_client.py`, logic tool-calling được tổ chức theo vòng lặp có giới hạn, với tham số `AGENT_MAX_TOOL_ITERATIONS` để tránh việc mô hình đi vào vòng gọi công cụ không dứt. Bộ công cụ gồm `search_memory`, `cancel_matching_facts`, `remember_current_message` và `remember_fact`, được mở hoặc khóa theo `MEMORY_WRITE_MODE` là `exact`, `model` hoặc `both`. Cấu hình này tạo ra một điểm cân bằng hợp lý giữa an toàn dữ liệu và tính linh hoạt. Ở chế độ `exact`, hệ thống ưu tiên lưu nguyên văn tin nhắn để giảm rủi ro diễn giải sai. Ở chế độ `model`, hệ thống ưu tiên lưu fact ngắn gọn, có cấu trúc. Ở chế độ `both`, hệ thống có thể tự chọn cách lưu phù hợp hơn với ngữ cảnh temporal, ví dụ tự chuẩn hóa ngày tương đối thành ngày tuyệt đối khi gặp câu mô tả lịch hẹn.

Trong `app/graphiti_client.py`, lớp `GraphitiMemory` đã đóng vai trò là trung tâm của bộ nhớ ứng dụng. Lớp này khởi tạo Graphiti với Neo4j, một client LLM tương thích OpenAI/Gemini, bộ embedding có thể thay đổi theo môi trường và một reranker tối giản. Hệ thống hỗ trợ ba hướng embedding gồm `proxy`, `gemini` và `local`, trong đó chế độ `local` sử dụng `LocalQwenEmbedder` để giảm phụ thuộc vào dịch vụ ngoài khi thử nghiệm. Ngoài các episode được ghi theo luồng chat, hệ thống còn hỗ trợ manual temporal fact thông qua `add_manual_fact`, `manual_facts_for_date` và `invalidate_matching_manual_facts`. Cách thiết kế này đặc biệt hữu ích cho các lịch hẹn và sự kiện có ngày giờ rõ ràng, vì nó cho phép truy vấn theo ngày mà không phải suy diễn mơ hồ từ văn bản thuần.

Từ góc độ kiểm thử, các test trong `tests/test_llm_client.py` và `tests/test_fact_filter.py` đã xác nhận nhiều đường đi quan trọng của hệ thống. Bộ test không dừng ở mức giao diện mà chạm trực tiếp vào các quy tắc nghiệp vụ có nguy cơ lỗi cao như chọn tool theo chế độ ghi nhớ, truy vấn memory theo ngày, hủy lịch, giữ lại fact còn hiệu lực và giới hạn số vòng tool-calling. Điều này cho thấy dự án không chỉ dừng ở mức demo giao diện mà đã có một lớp kiểm chứng kỹ thuật tối thiểu cho các hành vi cốt lõi.

## 5.2 Đóng góp của đề tài

Đóng góp của Graphiti Chat Lab không nằm ở việc tạo ra một mô hình ngôn ngữ mới hay một thuật toán truy hồi hoàn toàn mới, mà nằm ở việc hiện thực hóa một kiến trúc bộ nhớ chat có tính ứng dụng cao cho ngôn ngữ tiếng Việt. Đề tài cho thấy để xây dựng một trợ lý có trí nhớ đáng tin cậy, chỉ dùng lịch sử chat hoặc chỉ dùng truy xuất văn bản thuần là chưa đủ. Hệ thống cần ít nhất ba lớp chức năng phối hợp với nhau: lớp truy hồi để tìm fact phù hợp, lớp trạng thái để theo dõi fact nào còn hiệu lực hoặc đã bị hủy, và lớp giải thích để người dùng biết vì sao câu trả lời được tạo ra.

Có thể khái quát các đóng góp chính của đề tài theo bốn nhóm như sau.

| Nhóm đóng góp | Nội dung cụ thể | Ý nghĩa thực tiễn |
| --- | --- | --- |
| Kiến trúc hệ thống | Phân tách rõ `FastAPI`, `AssistantClient`, `GraphitiMemory` và lớp lọc fact | Giảm độ rối của codebase, giúp từng lớp có thể kiểm thử độc lập |
| Điều phối hội thoại | Xây dựng vòng lặp tool-calling với giới hạn số vòng, hỗ trợ search, save và cancel | Làm cho trợ lý có khả năng hành động chứ không chỉ sinh văn bản |
| Xử lý bộ nhớ thời gian | Hỗ trợ manual temporal fact, chuẩn hóa ngày tương đối và truy vấn theo ngày | Phù hợp với các bài toán lịch hẹn, công nợ, kế hoạch và nhắc việc |
| Minh bạch và kiểm thử | Trả về `retrieved_facts` và `tool_trace`, đồng thời có unit test cho các rule quan trọng | Tăng độ tin cậy và tạo nền tảng cho đánh giá sau này |

Xét ở mức độ hệ thống, đề tài còn cung cấp một mẫu triển khai thực tế cho bài toán memory layer trong ứng dụng chat. Thay vì để LLM tự ghi nhớ một cách mơ hồ, dự án đặt bộ nhớ vào một cấu trúc có thể quản trị: facts được truy xuất bằng Graphiti, thông tin thời gian được gắn `valid_at` và `invalid_at`, các sự kiện có ngày giờ cụ thể có thể lưu riêng dưới dạng manual fact, và các cập nhật mới có thể vô hiệu hóa dữ liệu cũ. Mô hình này phù hợp với các sản phẩm cần “nhớ đúng” hơn là chỉ “nói hay”.

Với định hướng khởi nghiệp và đổi mới sáng tạo, đóng góp quan trọng nhất của đề tài là chứng minh được một hướng sản phẩm có tính ngách nhưng rõ nhu cầu. Trợ lý chat có trí nhớ cá nhân không cạnh tranh trực diện với mọi chatbot trên thị trường, mà nhắm vào nhóm người dùng có nhu cầu lưu, hỏi lại và cập nhật thông tin theo thời gian. Đây là điểm khác biệt có giá trị thương mại vì nó gắn trực tiếp với hành vi sử dụng lặp lại của người dùng.

## 5.3 Hạn chế và nguyên nhân

Mặc dù đã đạt được nguyên mẫu có thể vận hành, hệ thống vẫn còn một số hạn chế quan trọng cần nhìn nhận thẳng thắn. Các hạn chế này không phải là lỗi đơn lẻ, mà phản ánh đúng bản chất của một dự án ở giai đoạn nguyên mẫu, ưu tiên kiểm chứng giá trị cốt lõi hơn là hoàn thiện toàn bộ lớp sản phẩm. Việc nhận diện rõ hạn chế là cần thiết để tránh đánh giá quá mức khả năng hiện tại của hệ thống.

| Hạn chế | Biểu hiện trong dự án | Tác động |
| --- | --- | --- |
| Phụ thuộc vào mô hình và dịch vụ ngoài | Hệ thống cần LLM tương thích Gemini/OpenAI, Graphiti, Neo4j và các backend embedding | Nếu dịch vụ chậm, đổi API, giới hạn quota hoặc lỗi mạng, toàn bộ luồng chat có thể bị ảnh hưởng |
| Chưa có xác thực và phân tách đa người dùng | Ứng dụng chưa có cơ chế login, phân quyền hay tách không gian nhớ theo từng tài khoản | Chưa phù hợp để lưu dữ liệu cá nhân thật trong môi trường nhiều người dùng |
| Xử lý thời gian tương đối còn hẹp | Logic hiện tại chủ yếu bao phủ các trường hợp như “mai”, “ngày mai”, “hôm nay”, một số mô tả giờ và buổi | Các diễn đạt phức tạp hơn như “thứ sáu tuần sau”, “đầu tháng”, “hai ngày nữa” vẫn chưa được bao phủ đầy đủ |
| Bộ benchmark còn nhỏ | Kiểm thử hiện tại chủ yếu là unit test và kịch bản tay cho các trường hợp quan trọng | Chưa đủ dữ liệu để khẳng định độ chính xác, độ bao phủ và khả năng tổng quát hóa ở quy mô lớn |
| Năng lực vận hành còn ở mức prototype | Chưa có logging chuẩn hóa, tracing hệ thống, cơ chế retry, quota hoặc giám sát vận hành | Khó triển khai ổn định dưới tải thật hoặc trong môi trường nhiều người dùng |

Hạn chế phụ thuộc mô hình ngoài là hệ quả trực tiếp của việc lựa chọn kiến trúc tích hợp LLM và Graphiti theo hướng tận dụng các thành phần có sẵn. Cách làm này phù hợp với giai đoạn khám phá vì giúp tiết kiệm thời gian xây dựng nền tảng từ đầu, nhưng về lâu dài làm tăng phụ thuộc vào hệ sinh thái của nhà cung cấp. Ngay cả khi đã có `LocalQwenEmbedder` để giảm bớt phụ thuộc ở lớp embedding, hệ thống vẫn còn phụ thuộc vào LLM ngoại vi và dịch vụ Neo4j, nên chưa thể coi là độc lập hoàn toàn.

Hạn chế về xác thực và đa người dùng là điểm cần được xem là ưu tiên cao nhất nếu sản phẩm muốn đi theo hướng thực tế. Hiện tại, cấu hình `GRAPHITI_GROUP_ID` chỉ tạo ra một namespace mức môi trường, chứ chưa phải cơ chế tách người dùng hay tách tenant. Điều này có nghĩa là nếu triển khai cho nhiều người, bộ nhớ có nguy cơ bị trộn lẫn hoặc khó kiểm soát quyền truy cập. Với một hệ thống chứa dữ liệu cá nhân như lịch hẹn, công nợ hay kế hoạch, đây là khoảng trống sản phẩm không thể bỏ qua.

Hạn chế trong xử lý thời gian tương đối cũng là vấn đề đáng chú ý. Ở lớp `llm_client.py`, việc chuẩn hóa ngày mới tập trung vào các từ khóa gần như “mai” và “ngày mai”, kết hợp với quy tắc nhận diện giờ và buổi để suy ra `valid_at`. Ở lớp `fact_filter.py`, logic lọc fact theo message cũng mới xử lý được một số mốc gần và một số mẫu cancellation đơn giản. Điều này đủ cho các test case đã xây dựng, nhưng chưa đủ cho các diễn đạt tự nhiên đa dạng trong tiếng Việt. Nếu không cải thiện, hệ thống sẽ gặp rủi ro sai lệch khi người dùng diễn đạt thời gian ở nhiều cấp độ tinh vi hơn.

Cuối cùng, việc chưa có benchmark lớn là hạn chế ảnh hưởng trực tiếp đến giá trị học thuật và giá trị thương mại của đề tài. Các unit test hiện tại chứng minh đúng đắn của một số quy tắc cụ thể, nhưng chưa cho biết hệ thống hoạt động tốt đến mức nào trên tập dữ liệu lớn, nhiều phong cách nói khác nhau, nhiều loại nhiễu ngôn ngữ và nhiều tình huống tranh chấp fact. Vì vậy, kết quả hiện tại nên được hiểu là bằng chứng kỹ thuật ban đầu, chưa phải là bằng chứng định lượng ở quy mô sản phẩm.

## 5.4 Bài học kinh nghiệm

Từ quá trình xây dựng Graphiti Chat Lab, có thể rút ra một số bài học kinh nghiệm quan trọng cho các phiên bản tiếp theo cũng như cho các dự án tương tự.

**Thứ nhất, bộ nhớ tốt không đồng nghĩa với truy hồi tốt.** Nếu hệ thống chỉ biết tìm vector tương đồng mà không quản lý được trạng thái sống còn của fact, nó rất dễ trả lại dữ liệu cũ, dữ liệu đã bị hủy hoặc dữ liệu không còn phù hợp theo thời gian. Vì vậy, lớp bộ nhớ cần được thiết kế như một hệ quản lý vòng đời thông tin, không chỉ là một kho lưu văn bản.

**Thứ hai, thiết kế tool phải đi cùng với thiết kế prompt.** Trong `app/llm_client.py`, hệ thống không chỉ khai báo các tool mà còn mô tả rất rõ mục đích sử dụng của từng tool trong `AGENT_SYSTEM_PROMPT`. Thực tế cho thấy nếu prompt mơ hồ, mô hình dễ gọi sai công cụ hoặc gọi tool quá nhiều lần. Ngược lại, khi prompt và tool contract được thiết kế đồng bộ, hành vi của agent ổn định hơn và dễ kiểm thử hơn.

**Thứ ba, xử lý thời gian nên được đưa về lớp quyết định có tính xác định cao.** Các câu hỏi liên quan đến lịch hẹn, nhắc việc hay công nợ thường có sai khác rất nhỏ về thời gian nhưng lại tạo ra khác biệt rất lớn về nghĩa. Vì vậy, việc chuẩn hóa ngày tương đối và lọc fact theo `valid_at`/`invalid_at` là quyết định đúng. Nếu cố gắng để LLM tự suy diễn mọi thứ bằng ngôn ngữ tự nhiên, hệ thống sẽ khó ổn định và khó kiểm chứng.

**Thứ tư, kiểm thử semantic quan trọng hơn kiểm thử giao diện ở giai đoạn đầu.** Các test trong `tests/test_llm_client.py` và `tests/test_fact_filter.py` tập trung vào những hành vi dễ sai nhất như chọn write mode, lọc fact theo ngày, hủy lịch và giới hạn vòng tool-calling. Đây là cách kiểm thử phù hợp với một hệ thống memory, vì lỗi của nó thường không nằm ở cú pháp mà nằm ở nghĩa và trạng thái. Một giao diện chạy được nhưng trả sai fact vẫn là một hệ thống thất bại.

**Thứ năm, tính minh bạch là một phần của sản phẩm, không phải chỉ là công cụ debug.** Việc trả về `retrieved_facts` và `tool_trace` không đơn thuần nhằm phục vụ nhà phát triển. Ở mức sản phẩm, người dùng cũng cần biết hệ thống dựa trên dữ liệu nào để trả lời, đặc biệt khi câu trả lời ảnh hưởng đến lịch, trách nhiệm cá nhân hoặc các thay đổi quan trọng. Tính minh bạch vì thế nên được xem là một tính năng chính thức của sản phẩm.

**Thứ sáu, phải chấp nhận và kiểm soát trade-off thay vì cố tối ưu mọi thứ cùng lúc.** Chế độ `exact` an toàn nhưng kém linh hoạt; chế độ `model` linh hoạt hơn nhưng dễ phụ thuộc vào khả năng diễn giải của mô hình; chế độ `both` là thỏa hiệp hợp lý cho nguyên mẫu nhưng làm tăng độ phức tạp của luồng ghi nhớ. Việc có sẵn ba chế độ cho thấy hệ thống đã được thiết kế theo tư duy lựa chọn chiến lược, thay vì ép toàn bộ use case đi theo một hướng duy nhất.

## 5.5 Kiến nghị phát triển

Để Graphiti Chat Lab tiến từ nguyên mẫu sang một sản phẩm có thể thử nghiệm ở quy mô rộng hơn, cần ưu tiên một số kiến nghị phát triển sau.

1. **Bổ sung xác thực, phân quyền và tách không gian nhớ theo người dùng.** Đây là yêu cầu bắt buộc nếu hệ thống xử lý dữ liệu cá nhân thật. Mỗi tài khoản cần có không gian nhớ riêng, có cơ chế cấp quyền rõ ràng và có khả năng xóa hoặc xuất dữ liệu khi cần.

2. **Nâng cấp logic thời gian và luật hủy fact.** Hệ thống nên hỗ trợ thêm các biểu đạt thời gian tự nhiên như “thứ sáu tuần sau”, “đầu tháng”, “cuối tuần”, “chiều nay” hoặc “hai ngày nữa”. Đồng thời, bộ luật hủy fact nên được cải thiện để giảm nhầm lẫn khi người dùng thay đổi kế hoạch một phần chứ không xóa hoàn toàn.

3. **Xây dựng bộ benchmark lớn hơn và có cấu trúc hơn.** Tập benchmark nên bao phủ ít nhất bốn nhóm: truy hồi fact, cập nhật/hủy fact, câu hỏi thời gian tương đối và trường hợp có nhiều nhiễu ngôn ngữ. Bộ dữ liệu này sẽ giúp đo chính xác hơn chất lượng của truy hồi, chất lượng của agent và chất lượng của memory lifecycle.

4. **Bổ sung lớp quan sát hệ thống và cơ chế chịu lỗi.** Khi đưa vào thử nghiệm thật, hệ thống cần có logging chuẩn hóa, metrics, tracing, retry với backoff, timeout hợp lý và thông báo lỗi thân thiện hơn. Điều này đặc biệt quan trọng vì các thành phần ngoại vi như LLM, embedding và Neo4j đều có thể phát sinh lỗi theo thời gian.

5. **Tăng cường khả năng quản trị bộ nhớ.** Người dùng nên có giao diện để xem, sửa, xóa hoặc gắn nhãn cho memory đã lưu. Về mặt sản phẩm, tính năng này giúp người dùng tin hệ thống hơn và giảm rủi ro lưu sai thông tin.

6. **Đánh giá thêm nhiều cấu hình mô hình và embedding.** Ngoài cấu hình hiện tại, hệ thống nên được thử nghiệm với nhiều mô hình khác nhau để đo tác động của chất lượng model lên truy hồi và suy luận. Đây là hướng cần thiết nếu sản phẩm muốn giảm phụ thuộc vào một nhà cung cấp duy nhất.

## 5.6 Roadmap sản phẩm trong tương lai

Lộ trình phát triển hợp lý cho Graphiti Chat Lab nên đi theo hướng tăng dần độ hoàn thiện của sản phẩm trước, rồi mới mở rộng tính năng và mô hình kinh doanh sau. Cách tiếp cận này phù hợp với một sản phẩm khởi nghiệp vì nó giảm rủi ro đầu tư sớm vào những thành phần chưa được thị trường xác nhận.

| Giai đoạn | Trọng tâm | Hạng mục ưu tiên | Kết quả mong đợi |
| --- | --- | --- | --- |
| Giai đoạn 1: Củng cố MVP | Ổn định chức năng cốt lõi | Hoàn thiện xác thực cơ bản, chuẩn hóa cấu hình, cải thiện xử lý lỗi, bổ sung logging và health check | Một nguyên mẫu đủ an toàn để demo và pilot nhỏ |
| Giai đoạn 2: Nâng chất lượng bộ nhớ | Tăng độ chính xác của recall và update | Mở rộng xử lý thời gian, cải thiện luật hủy fact, bổ sung benchmark, đo precision/recall và độ nhất quán của memory | Hệ thống nhớ đúng hơn, ít sai lệch hơn trong các tình huống thực tế |
| Giai đoạn 3: Đa người dùng và quản trị | Chuẩn bị cho sử dụng nhóm hoặc tổ chức | Thiết kế tài khoản, phân quyền, tách tenant, dashboard quản trị, cơ chế export/delete memory | Sẵn sàng cho thử nghiệm trong môi trường có nhiều người dùng |
| Giai đoạn 4: Thương mại hóa và mở rộng hệ sinh thái | Đưa sản phẩm thành dịch vụ | Đóng gói triển khai, API/SDK, giám sát vận hành, tích hợp lịch, CRM hoặc công cụ chat khác | Hình thành lớp memory-as-a-service có khả năng tạo doanh thu |

Nếu nhìn theo trình tự phát triển sản phẩm, lộ trình này có thể được diễn giải ngắn gọn như sau: từ nguyên mẫu nội bộ, chuyển sang pilot kiểm chứng, sau đó mở rộng đa người dùng, và cuối cùng là thương mại hóa dưới dạng dịch vụ hoặc API. Trật tự này quan trọng vì Graphiti Chat Lab không nên đi quá nhanh vào mở rộng tính năng khi các vấn đề nền tảng như quyền riêng tư, độ chính xác thời gian và benchmark vẫn chưa được giải quyết đầy đủ.

Ở góc nhìn sản phẩm, giá trị dài hạn của Graphiti Chat Lab không nằm ở việc trở thành một chatbot tổng quát cạnh tranh trực tiếp với các hệ thống sinh ngôn ngữ phổ biến, mà nằm ở lớp bộ nhớ có cấu trúc, minh bạch và có thể kiểm soát. Nếu làm tốt roadmap trên, hệ thống có thể trở thành một lớp memory bổ trợ cho nhiều ứng dụng chat khác nhau, từ trợ lý cá nhân, trợ lý nhóm nhỏ cho đến các dịch vụ doanh nghiệp cần lưu ngữ cảnh người dùng theo thời gian.

## 5.7 Kết luận chung

Từ toàn bộ quá trình nghiên cứu, thiết kế, triển khai và kiểm thử, có thể khẳng định rằng Graphiti Chat Lab đã đạt được mục tiêu của một khóa luận theo định hướng khởi nghiệp và đổi mới sáng tạo: giải quyết một bài toán thực tế, xây dựng được nguyên mẫu khả thi, có các cơ chế kiểm thử cho những hành vi cốt lõi và có một lộ trình sản phẩm rõ ràng trong tương lai. Điểm mạnh nhất của đề tài không phải là tạo ra một mô hình AI mới, mà là chứng minh được cách tổ chức một hệ thống chat có bộ nhớ dài hạn theo hướng có thể kiểm chứng và có thể phát triển thành sản phẩm.

Tuy nhiên, để chuyển từ nguyên mẫu sang sản phẩm thực sự, hệ thống vẫn cần giải quyết các giới hạn đã nêu ở trên, đặc biệt là xác thực người dùng, phân tách dữ liệu đa người dùng, cải thiện xử lý thời gian tương đối và xây dựng benchmark quy mô lớn hơn. Đây là những bước không thể bỏ qua nếu mục tiêu không chỉ là trình diễn công nghệ mà còn là đưa sản phẩm vào môi trường sử dụng thật.

Với nền tảng hiện có, Graphiti Chat Lab có tiềm năng phát triển thành một dịch vụ memory layer chuyên biệt cho các ứng dụng chat tiếng Việt. Nếu tiếp tục đầu tư theo roadmap đã đề xuất, dự án có thể tiến từ một nguyên mẫu học thuật sang một sản phẩm có khả năng thử nghiệm thị trường, qua đó hoàn thành đầy đủ mục tiêu kỹ thuật lẫn mục tiêu định hướng thương mại hóa của đề tài.
