# Chương 2. Tổng Quan Tài Liệu Và Cơ Sở Lý Thuyết

Chương này trình bày cơ sở học thuật và bối cảnh thị trường cho đề tài Graphiti Chat Lab. Trọng tâm của chương không chỉ là mô tả các công nghệ được sử dụng, mà còn làm rõ vì sao bài toán “nhớ đúng, nhớ theo thời gian, và hủy đúng” là một nhu cầu thực tế trong các hệ thống chat hiện đại, đặc biệt khi triển khai cho tiếng Việt. Trên cơ sở đó, chương phân tích các mô hình lưu ngữ cảnh phổ biến, đánh giá SWOT, PESTEL và Porter Five Forces, xác định yêu cầu hệ thống, đồng thời tổng hợp các nền tảng lý thuyết cần thiết gồm graph database, embeddings, function calling và ASGI/FastAPI.

## 2.1. Tổng quan lĩnh vực

### 2.1.1. Sự chuyển dịch từ chatbot phản hồi sang trợ lý có bộ nhớ

Trong giai đoạn đầu của ứng dụng chat thông minh, mục tiêu chính của hệ thống là sinh ra câu trả lời có vẻ hợp lý trong từng lượt đối thoại riêng lẻ. Cách tiếp cận này phù hợp với các câu hỏi ngắn, có ngữ nghĩa cục bộ, nhưng nhanh chóng bộc lộ hạn chế khi người dùng bắt đầu yêu cầu hệ thống ghi nhớ các thông tin lặp lại theo thời gian. Các tình huống như ghi nhớ lịch hẹn, theo dõi khoản nợ, nhắc lại sở thích, hoặc cập nhật thay đổi kế hoạch đều đòi hỏi một lớp trí nhớ ổn định hơn lịch sử chat thuần.

Sự thay đổi lớn của lĩnh vực chatbot hiện nay là chuyển từ “trả lời đúng một lần” sang “duy trì ngữ cảnh qua nhiều phiên”. Ở mức độ sản phẩm, người dùng không còn chỉ kỳ vọng một chatbot biết nói, mà kỳ vọng một trợ lý có thể lưu thông tin, truy hồi lại thông tin phù hợp, và cập nhật trạng thái khi thông tin cũ không còn đúng. Điều này đặc biệt quan trọng đối với các ứng dụng cá nhân hóa, vì dữ liệu mà người dùng chia sẻ với hệ thống thường không phải là tri thức tĩnh, mà là các sự kiện sống động có vòng đời: phát sinh, còn hiệu lực, rồi bị thay thế hoặc hủy bỏ.

Về bản chất, bài toán này gần với quản lý tri thức có thời gian hơn là truy vấn văn bản đơn thuần. Nếu chỉ lưu lịch sử chat dưới dạng các đoạn văn dài, hệ thống sẽ gặp ba vấn đề cốt lõi. Thứ nhất, ngữ cảnh tăng dần khiến số token cần đưa vào mô hình trở nên không kiểm soát. Thứ hai, các câu nói phủ định hoặc thay đổi trạng thái rất khó được hiểu là một hành động cập nhật bộ nhớ. Thứ ba, việc truy hồi theo tương đồng ngữ nghĩa có thể kéo theo các fact cũ, fact đã hủy, hoặc fact gần giống nhưng sai chiều quan hệ.

Graphiti Chat Lab được xây dựng trên đúng bối cảnh đó. Theo mô tả trong `README.md` và `plans/260606-graphiti-chat-lab/plan.md`, mục tiêu của hệ thống là một ứng dụng chat web FastAPI độc lập, dùng Graphiti và Neo4j để lưu memory, dùng Gemini qua một lớp tương thích OpenAI-compatible để sinh phản hồi, đồng thời hiển thị rõ `retrieved_facts` cho người dùng. Cấu trúc này cho thấy đề tài không dừng ở việc thử nghiệm một chatbot, mà hướng đến một lớp memory có thể kiểm chứng được.

### 2.1.2. Đặc thù của bài toán tiếng Việt

Việt ngữ có một số đặc trưng khiến bài toán nhớ ngữ cảnh khó hơn so với nhiều ngôn ngữ có cấu trúc hình thái ổn định hơn. Thứ nhất, đại từ xưng hô thay đổi linh hoạt theo quan hệ xã hội và ngữ cảnh giao tiếp: “tôi”, “tao”, “mình”, “tớ”, “em”, “anh”, “chị” có thể cùng chỉ một chủ thể nhưng không thể xử lý như các từ đồng nghĩa đơn giản. Thứ hai, phủ định trong tiếng Việt thường được thể hiện bởi các từ như “không”, “hủy”, “huỷ”, hoặc cả một cấu trúc câu phủ định gián tiếp. Thứ ba, biểu đạt thời gian tương đối như “mai”, “ngày mai”, “chiều mai”, “hôm nay” phụ thuộc mạnh vào thời điểm hội thoại.

Từ góc nhìn hệ thống, các đặc điểm trên làm cho việc lưu và truy hồi memory không thể chỉ dựa vào matching từ khóa. Một hệ thống chỉ tìm kiếm theo văn bản dễ nhầm lẫn giữa “Tao nợ Nam 30k” và “Nam nợ tao 30k”, vì hai câu này có độ tương đồng bề mặt cao nhưng ý nghĩa quan hệ hoàn toàn trái ngược. Tương tự, khi người dùng nói “hủy lịch chơi game với anh Tú ngày mai”, hệ thống không chỉ cần hiểu đây là một hành động phủ định, mà còn phải gắn nó với đúng fact đã lưu trước đó, đúng ngày hiệu lực, và đúng trạng thái invalidation.

Trong code, các yêu cầu ngôn ngữ này không phải là giả định trừu tượng mà đã được phản ánh trực tiếp. `app/graphiti_client.py` đặt `EXTRACTION_INSTRUCTIONS` theo hướng “preserve Vietnamese names and wording”, nhấn mạnh giữ nguyên chiều quan hệ nợ và không trích xuất câu hỏi thành fact. `app/llm_client.py` tiếp tục yêu cầu mô hình trả lời cùng ngôn ngữ với người dùng. `app/fact_filter.py` xử lý đồng thời các marker phủ định bằng tiếng Việt như “không”, “hủy”, “huỷ” và cả từ tiếng Anh “cancel”. Những chi tiết này cho thấy hệ thống được thiết kế có chủ đích cho môi trường tiếng Việt thay vì chỉ dịch nguyên mô hình tiếng Anh sang.

### 2.1.3. Vị trí của Graphiti Chat Lab trong bức tranh chung

Graphiti Chat Lab nằm ở giao điểm của ba xu hướng công nghệ: chatbot hội thoại, memory retrieval và graph-based reasoning. Nếu chatbot truyền thống tập trung vào sinh văn bản, thì memory retrieval tập trung vào tái sử dụng thông tin đã biết. Nếu vector RAG tập trung vào truy vấn các đoạn văn có liên quan, thì graph memory tập trung vào việc biểu diễn các thực thể, quan hệ và trạng thái qua thời gian. Đề tài này tận dụng cả ba lớp: hội thoại do Gemini xử lý, memory do Graphiti/Neo4j quản lý, và lớp điều phối tool-calling giúp mô hình tự quyết định khi nào cần nhớ hay hủy.

Điểm nổi bật của hệ thống là memory không được xem như một tệp nhật ký thụ động. Thay vào đó, memory được mô hình hóa như một tập fact có vòng đời, có thể thêm mới, truy hồi, lọc theo thời gian, và hủy mềm bằng cách đánh dấu `invalid_at`. Cách tiếp cận này phù hợp hơn với bài toán trợ lý cá nhân, vì thông tin người dùng lưu lại thường không bất biến. Một lịch hẹn hôm nay có thể bị hoãn sang ngày khác; một khoản nợ có thể được trả; một sở thích có thể thay đổi theo thời gian. Nếu chỉ lưu lịch sử chat hoặc lưu embedding trên văn bản thuần, hệ thống sẽ rất khó biểu diễn các trạng thái chuyển tiếp đó.

## 2.2. Nhu cầu thị trường và người dùng mục tiêu

### 2.2.1. Vấn đề thực tế cần giải quyết

Nhu cầu thị trường của một hệ thống chat có bộ nhớ không xuất phát từ nhu cầu “nói chuyện với AI” một cách chung chung, mà từ nhu cầu giảm thao tác lặp lại trong các tình huống thông tin cá nhân. Người dùng thường phải nhắc lại cùng một dữ liệu nhiều lần: lịch học, lịch làm, lịch hẹn, khoản nợ, món đồ đã mua, sở thích ăn uống, hoặc các điều chỉnh mới nhất của kế hoạch. Mỗi lần phải nhắc lại như vậy, trải nghiệm người dùng giảm xuống, độ tin cậy của chatbot giảm xuống, và giá trị ứng dụng thực tế giảm xuống.

Trong bối cảnh sản phẩm AI hiện nay, người dùng ngày càng ít chấp nhận một chatbot “nói hay nhưng quên nhanh”. Họ kỳ vọng hệ thống nhớ đúng bối cảnh, cho biết memory nào đang được dùng để trả lời, và có thể cập nhật khi thông tin cũ không còn phù hợp. Đây là điểm khác biệt quan trọng so với những chatbot chỉ dựa vào lịch sử hội thoại. Một memory assistant đáng tin không thể chỉ sinh ra câu trả lời trôi chảy; nó phải truy hồi đúng fact, xử lý được thay đổi trạng thái, và hiển thị được cơ sở cho câu trả lời.

Các manual evaluation cases trong `README.md` của dự án cho thấy nhu cầu này rất cụ thể. Ví dụ, hệ thống phải phân biệt được giữa “Minh nợ tao 60k” và “Tao nợ Nam 30k”, phải trả lời đúng câu “Ai nợ tao tiền?” và “Tao nợ ai?”, đồng thời xử lý được các sự kiện như “Có lịch chơi game với anh Tú lúc 3h chiều mai”. Những ví dụ này phản ánh nhu cầu thị trường rất thật: người dùng cần một trợ lý nhớ đúng nội dung, đúng chiều quan hệ, và đúng thời gian.

### 2.2.2. Phân khúc người dùng và nhu cầu cụ thể

Ở giai đoạn đầu, nhóm người dùng phù hợp nhất là những người có tần suất nhập thông tin lặp lại cao nhưng không muốn duy trì hệ thống phức tạp. Đó có thể là sinh viên cần ghi nhớ lịch học, lịch thi; người làm việc tự do cần theo dõi lịch hẹn, công nợ và kế hoạch dự án; hoặc các nhóm nhỏ cần một lớp ghi nhớ chung cho các cuộc trao đổi thường xuyên.

| Nhóm người dùng | Tình huống điển hình | Nhu cầu chính | Rủi ro nếu không có bộ nhớ có cấu trúc |
| --- | --- | --- | --- |
| Sinh viên | Hỏi lịch học, lịch thi, lịch gặp nhóm, deadline bài tập | Nhớ theo ngày, nhắc lại đúng sự kiện, tránh trùng lịch | Phải nhập lại nhiều lần, dễ bỏ sót lịch quan trọng |
| Người làm việc tự do | Theo dõi khách hàng, công nợ, lịch gặp, các thỏa thuận dịch vụ | Nhớ khoản nợ, mốc thời gian, trạng thái đã trả/chưa trả | Dễ nhầm chiều nợ, dễ quên thay đổi kế hoạch |
| Nhóm nhỏ/nhóm dự án | Lưu các quyết định, cuộc họp, thay đổi công việc | Tập trung thông tin đã thống nhất, truy hồi theo ngữ cảnh | Thông tin phân tán trong nhiều cuộc chat |
| Người dùng cá nhân | Ghi nhớ sở thích, thói quen, địa điểm, ưu tiên | Ghi nhớ dài hạn và trả lời cá nhân hóa | Trải nghiệm chat “không học được gì” từ phiên trước |

Bảng trên cho thấy một điểm chung: giá trị không nằm ở việc chatbot biết nhiều, mà ở việc nó nhớ đúng những gì người dùng đã nói trong những tình huống có tác động thực tế. Khi một hệ thống có thể nhớ ai nợ ai, hôm nay có lịch gì, hay người dùng thích kiểu quán nào, nó đã vượt khỏi vai trò trả lời câu hỏi để trở thành công cụ hỗ trợ ra quyết định hằng ngày.

### 2.2.3. Cơ hội thị trường ở góc nhìn sản phẩm

Từ góc nhìn khởi nghiệp, bài toán memory assistant có một số tín hiệu thuận lợi. Trước hết, mô hình giao tiếp bằng chat đã trở nên quen thuộc với người dùng phổ thông, nên rào cản học cách sử dụng thấp. Thứ hai, nhu cầu về các công cụ ghi nhớ cá nhân hoặc ghi nhớ nhóm đang tăng cùng với xu hướng số hóa quy trình làm việc. Thứ ba, một hệ thống có thể giải thích được memory đang dùng sẽ có lợi thế niềm tin so với các sản phẩm “hộp đen”.

Với Graphiti Chat Lab, cơ hội thị trường không nằm ở việc cạnh tranh trực diện với các nền tảng trợ lý đa năng quy mô lớn, mà nằm ở một ngách cụ thể: memory layer cho hội thoại cá nhân, chú trọng tiếng Việt, thời gian, và khả năng hủy facts. Ngách này có đủ nhu cầu thực tế, nhưng cũng còn đủ khoảng trống để một nguyên mẫu nhỏ chứng minh giá trị.

## 2.3. So sánh các cách lưu ngữ cảnh trong hệ thống chat

### 2.3.1. Lịch sử chat thuần

Cách đơn giản nhất để giữ ngữ cảnh là đưa toàn bộ lịch sử hội thoại vào prompt. Ưu điểm của phương án này là dễ triển khai, không cần thêm hạ tầng lưu trữ đặc biệt, và gần như không cần xây lớp truy hồi phức tạp. Tuy nhiên, hạn chế lớn nhất là lịch sử chat tăng rất nhanh, dẫn đến giới hạn token, tăng chi phí, và làm mô hình bị nhiễu bởi các thông tin cũ không còn liên quan.

Quan trọng hơn, lịch sử chat thuần không có cơ chế trạng thái. Nếu người dùng nói “mai tôi đi chơi game với anh Tú” rồi sau đó nói “hủy lịch đó”, việc phản hồi chính xác không chỉ phụ thuộc vào việc hai câu này có nằm trong cùng context hay không, mà còn phụ thuộc vào việc hệ thống có hiểu rằng câu sau là hành động làm vô hiệu câu trước hay không. Với lịch sử chat thuần, toàn bộ trách nhiệm đó đổ lên prompt và khả năng suy luận nhất thời của mô hình, nên tính ổn định không cao.

### 2.3.2. Vector RAG trên văn bản

Vector RAG giải quyết được một phần vấn đề bằng cách lưu các đoạn văn dưới dạng embeddings và truy xuất các đoạn gần ngữ nghĩa với câu hỏi. Phương pháp này phù hợp khi dữ liệu là tri thức tĩnh, khi mục tiêu là tìm đoạn văn liên quan, và khi không cần mô hình hóa quan hệ có cấu trúc quá phức tạp. Đối với nhiều hệ thống hỏi đáp tài liệu, đây là lựa chọn hợp lý.

Tuy nhiên, với memory cá nhân, vector RAG vẫn thiếu hai yếu tố quan trọng. Một là thiếu lớp trạng thái. Một fact đã bị hủy vẫn có thể được truy hồi nếu nó giống về mặt ngữ nghĩa. Hai là thiếu ngữ nghĩa quan hệ. Câu “Tao nợ Nam 30k” và “Nam nợ tao 30k” có thể được vector hóa gần nhau vì dùng chung nhiều từ, nhưng bản chất logic lại khác nhau. Để xử lý đúng, hệ thống phải biết chủ thể nào là debtor, chủ thể nào là creditor, và fact đó còn hiệu lực hay không. Nếu không có cấu trúc bổ sung, vector RAG khó đảm bảo điều đó.

### 2.3.3. Graph memory với Graphiti và Neo4j

Graph memory sử dụng property graph để lưu các thực thể, quan hệ và thuộc tính thời gian. Trong Graphiti Chat Lab, các memory episode được đưa vào Graphiti, được lưu trên Neo4j, và sau đó được truy xuất theo nhóm, theo ngữ cảnh, hoặc theo ngày. Bản chất của phương án này là chuyển memory từ một tập văn bản sang một đồ thị có trạng thái. Đó là bước thay đổi rất quan trọng đối với bài toán nhớ lâu.

Điểm mạnh nhất của graph memory là khả năng biểu diễn vòng đời của fact. Một fact không chỉ “có” hoặc “không có”, mà còn có thể “đang hiệu lực”, “đã bị hủy”, hoặc “chỉ hiệu lực trong một khoảng thời gian cụ thể”. Trong code, điều này được phản ánh bằng các thuộc tính như `valid_at` và `invalid_at`, cùng cơ chế lọc facts đang hoạt động trong `app/fact_filter.py`. Hệ thống không xóa vật lý thông tin cũ; thay vào đó, nó đánh dấu invalidation để vẫn giữ được dấu vết lịch sử nhưng không dùng fact đó làm căn cứ trả lời nếu nó không còn hợp lệ.

| Tiêu chí | Lịch sử chat thuần | Vector RAG | Graphiti/Neo4j |
| --- | --- | --- | --- |
| Bảo toàn ngữ cảnh dài hạn | Kém, dễ vượt token | Tốt hơn lịch sử chat | Tốt, vì tách memory khỏi prompt |
| Biểu diễn thời gian | Không có lớp thời gian riêng | Phải tự gắn metadata | Có thể gắn `valid_at`, `invalid_at` rõ ràng |
| Xử lý phủ định/hủy | Phụ thuộc vào prompt | Dễ kéo nhầm fact cũ | Có cơ chế invalidation mềm |
| Phân biệt quan hệ như “A nợ B” | Dễ nhầm chiều | Có thể nhầm nếu chỉ dựa embedding | Tốt hơn vì có thể lưu fact có cấu trúc |
| Giữ ngữ cảnh tiếng Việt | Dễ bị nhiễu bởi đại từ và biến thể | Trung bình, phụ thuộc embedding | Tốt hơn khi kết hợp extraction rules |
| Khả năng giải thích | Thấp | Trung bình | Cao hơn nhờ retrieved facts và trace |

### 2.3.4. So sánh theo kịch bản thực tế

Để đánh giá sát hơn, cần xem hệ thống phản ứng thế nào trong các tình huống thực tế thay vì chỉ nhìn vào mô hình kỹ thuật.

| Kịch bản | Lịch sử chat thuần | Vector RAG | Graphiti/Neo4j |
| --- | --- | --- | --- |
| “Minh nợ tao 60k” rồi hỏi “Ai nợ tao tiền?” | Phải đọc lại nhiều lượt chat, dễ bỏ sót | Có thể tìm thấy câu gần nhất nhưng dễ lẫn với “tao nợ Nam” | Lưu được chiều quan hệ chính xác, truy hồi đúng fact |
| “Có lịch chơi game với anh Tú lúc 3h chiều mai” rồi nói “hủy lịch đó” | Phải tự suy luận từ hai câu text | Có thể vẫn trả về fact cũ do similarity cao | Có thể gắn `invalid_at`, giữ lịch sử nhưng không dùng fact đã hủy |
| Hỏi “Mai tao có gì?” | Không có cơ chế chuẩn hóa ngày | Phụ thuộc metadata và hậu xử lý | Có thể lọc theo ngày, kết hợp valid/invalid |
| Hỏi “Tao thích kiểu quán nào?” | Dễ bị pha nhiễu bởi các đoạn chat khác | Có thể truy hồi theo ngữ nghĩa | Graphiti lưu fact sở thích như memory bền vững |

Bảng so sánh cho thấy Graphiti/Neo4j phù hợp hơn cho bài toán nhớ theo thời gian vì nó không chỉ tìm đoạn văn gần nghĩa, mà còn bảo toàn logic của fact. Đối với một hệ thống phải phân biệt giữa đúng và sai chiều quan hệ, giữa còn hiệu lực và đã bị hủy, và giữa hôm nay với ngày mai, điểm mạnh đó có ý nghĩa quyết định.

### 2.3.5. Kết luận so sánh

Nếu bài toán chỉ là hỏi đáp tài liệu, vector RAG có thể đủ. Nhưng Graphiti Chat Lab không phải hệ thống hỏi đáp tài liệu; đây là hệ thống memory cá nhân. Đối với memory cá nhân, điều quan trọng nhất không phải là “có tìm thấy một đoạn văn giống câu hỏi hay không”, mà là “fact đó còn hiệu lực không, có đúng chiều quan hệ không, và có phù hợp với mốc thời gian hay không”. Chính vì vậy, Graphiti/Neo4j là lựa chọn phù hợp hơn rõ rệt so với lịch sử chat thuần và vector RAG đơn lẻ.

## 2.4. Phân tích SWOT

SWOT cho phép nhìn hệ thống từ bốn chiều: điểm mạnh, điểm yếu, cơ hội và thách thức. Với một sản phẩm ở giai đoạn nguyên mẫu như Graphiti Chat Lab, phân tích SWOT có giá trị vì nó giúp xác định lợi thế cốt lõi cần giữ lại và các rủi ro cần giảm thiểu trước khi mở rộng.

| Yếu tố | Phân tích cụ thể đối với Graphiti Chat Lab |
| --- | --- |
| Strengths - Điểm mạnh | Sử dụng Graphiti và Neo4j để lưu memory có cấu trúc; hỗ trợ truy xuất theo thời gian; có cơ chế đánh dấu `invalid_at` thay vì xóa cứng; hiển thị `retrieved_facts` và `tool_trace` để tăng minh bạch; hỗ trợ tiếng Việt thông qua hướng dẫn trích xuất fact và lọc phủ định; có thể chạy cục bộ với nhiều chế độ embedding |
| Weaknesses - Điểm yếu | Phụ thuộc vào chất lượng LLM và embeddings; logic ngôn ngữ tự nhiên vẫn cần heuristic cho các tình huống mơ hồ; chưa có lớp xác thực người dùng hoặc phân quyền; quy mô thử nghiệm còn nhỏ; độ ổn định production chưa được kiểm chứng |
| Opportunities - Cơ hội | Nhu cầu về trợ lý có memory cá nhân và nhóm nhỏ ngày càng lớn; có thể đóng gói thành memory layer hoặc memory API; phù hợp với ngách tiếng Việt; có thể phát triển thành công cụ ghi nhớ lịch, công nợ và thói quen; dễ mở rộng sang các ứng dụng chat khác |
| Threats - Thách thức | Cạnh tranh từ các nền tảng AI lớn tích hợp memory; chi phí sử dụng mô hình và hạ tầng có thể tăng; yêu cầu bảo mật dữ liệu cá nhân cao; các thay đổi từ nhà cung cấp LLM hoặc embedding có thể ảnh hưởng hệ thống; chất lượng hồi quy ngữ nghĩa khó bảo đảm nếu dữ liệu đầu vào quá nhiễu |

Từ SWOT có thể rút ra một kết luận quan trọng: lợi thế cạnh tranh của đề tài không nằm ở việc cạnh tranh tốc độ sinh văn bản, mà nằm ở chất lượng bộ nhớ có cấu trúc. Nếu hệ thống chứng minh được rằng nó nhớ đúng, hủy đúng, và giải thích được quyết định của mình, thì nó có một vị trí thị trường rõ ràng dù quy mô ban đầu còn nhỏ.

## 2.5. Phân tích PESTEL

PESTEL giúp đặt sản phẩm vào bối cảnh vĩ mô rộng hơn. Với một sản phẩm AI, đặc biệt là sản phẩm xử lý dữ liệu cá nhân như lịch trình, công nợ, và sở thích, việc nhìn ra bối cảnh chính sách, xã hội, công nghệ và pháp lý là rất cần thiết.

| Thành phần | Phân tích đối với Graphiti Chat Lab |
| --- | --- |
| Political - Chính trị | Chuyển đổi số và ứng dụng AI đang được quan tâm rộng rãi trong giáo dục, doanh nghiệp và dịch vụ; điều này tạo môi trường thuận lợi cho các nguyên mẫu AI có giá trị thực tế |
| Economic - Kinh tế | Doanh nghiệp và cá nhân đều có xu hướng tìm công cụ giảm chi phí thao tác lặp lại, giảm thời gian nhập lại thông tin, và giảm sai sót trong quản lý lịch/nợ |
| Social - Xã hội | Người dùng quen với giao diện chat, thích cách tương tác tự nhiên, và ngày càng kỳ vọng AI hiểu bối cảnh cá nhân thay vì trả lời chung chung |
| Technological - Công nghệ | Sự phát triển của graph database, embeddings, function calling và ASGI tạo nền tảng hạ tầng phù hợp cho một hệ thống memory có tính thực tiễn |
| Environmental - Môi trường | Việc có tùy chọn embedding cục bộ giúp giảm phụ thuộc vào cloud và có thể giảm chi phí compute trong một số kịch bản thử nghiệm nội bộ |
| Legal - Pháp lý | Dữ liệu cá nhân, lịch cá nhân và công nợ là thông tin nhạy cảm; hệ thống cần chú ý quyền riêng tư, quản lý truy cập, lưu trữ và xóa dữ liệu theo chính sách phù hợp |

PESTEL cho thấy sản phẩm có môi trường công nghệ thuận lợi nhưng đồng thời chịu áp lực lớn về quyền riêng tư và quản trị dữ liệu. Điều đó giải thích vì sao thiết kế hiện tại nhấn mạnh khả năng kiểm soát trạng thái fact, lưu vết tool calls, và tách rõ dữ liệu memory với phần phản hồi hội thoại.

## 2.6. Phân tích Porter Five Forces

Porter Five Forces được sử dụng để đánh giá áp lực cạnh tranh và mức độ hấp dẫn của một ngách thị trường. Trong bối cảnh Graphiti Chat Lab, phân tích này giúp xác định hệ thống nên cạnh tranh bằng điều gì và không nên cạnh tranh bằng điều gì.

| Lực lượng cạnh tranh | Mức độ tác động | Nhận định đối với đề tài |
| --- | --- | --- |
| Cạnh tranh nội bộ ngành | Cao | Có nhiều chatbot, trợ lý cá nhân và công cụ ghi chú đang cùng tranh giành sự chú ý của người dùng |
| Đối thủ tiềm ẩn | Trung bình đến cao | Rào cản kỹ thuật để xây dựng chatbot AI đã giảm, nên các sản phẩm mới có thể xuất hiện nhanh |
| Sản phẩm thay thế | Cao | Note app, calendar app, task manager, RAG chatbot và trợ lý tổng quát đều có thể thay thế một phần nhu cầu |
| Quyền lực khách hàng | Cao | Người dùng có thể chuyển đổi công cụ rất nhanh nếu sản phẩm không cho thấy lợi ích rõ ràng |
| Quyền lực nhà cung cấp | Trung bình | Hệ thống phụ thuộc vào LLM, embedding model và Neo4j; thay đổi chi phí hoặc API của nhà cung cấp có thể ảnh hưởng đến vận hành |

Phân tích trên cho thấy thị trường không dễ dàng. Điều này buộc sản phẩm phải có sự khác biệt rõ ràng. Với Graphiti Chat Lab, sự khác biệt không phải là “chat hay hơn”, mà là “nhớ chính xác hơn”, “hủy có kiểm soát hơn”, và “giải thích tốt hơn”. Đây là định vị phù hợp với một sản phẩm ngách, có thể chứng minh giá trị bằng một số use case cụ thể thay vì cố bao phủ toàn bộ thị trường trợ lý AI.

## 2.7. Xác định yêu cầu hệ thống

### 2.7.1. Yêu cầu chức năng

Từ code hiện có và các kịch bản kiểm thử trong `README.md` cũng như `tests/test_llm_client.py`, có thể tổng hợp các yêu cầu chức năng cốt lõi của hệ thống như sau:

1. Hệ thống phải nhận được tin nhắn người dùng qua một API rõ ràng.
2. Hệ thống phải có khả năng truy xuất các fact liên quan trước khi trả lời.
3. Hệ thống phải lưu được thông tin người dùng mới chia sẻ dưới dạng memory.
4. Hệ thống phải xử lý được các thay đổi hoặc hủy bỏ của một fact cũ.
5. Hệ thống phải phân biệt memory theo ngày, đặc biệt với các truy vấn tương đối như “mai” hoặc “ngày mai”.
6. Hệ thống phải trả về câu trả lời cùng danh sách `retrieved_facts` và `tool_trace` để người dùng kiểm tra.
7. Hệ thống phải cho phép bật/tắt các kiểu memory write theo cấu hình.
8. Hệ thống phải hạn chế số vòng tool-calling để tránh vòng lặp vô hạn.

| Mã yêu cầu | Mô tả yêu cầu | Hiện thực trong code | Dấu hiệu kiểm thử |
| --- | --- | --- | --- |
| FR-01 | Nhận message từ người dùng | `POST /api/chat` trong `app/main.py`, schema `ChatRequest` trong `app/schemas.py` | Hệ thống trả về `ChatResponse` gồm reply, facts và trace |
| FR-02 | Truy xuất memory liên quan | `AssistantClient.reply()` gọi tool `search_memory` | `tests/test_llm_client.py` kiểm tra search theo query và theo ngày |
| FR-03 | Lưu memory mới | `remember_current_message` và `remember_fact` trong `MemoryToolbox` | Test xác nhận các chế độ `exact`, `model`, `both` |
| FR-04 | Hủy memory cũ | `cancel_matching_facts`, `invalidate_matching_facts`, `invalidate_matching_manual_facts` | Test kiểm tra invalidation đúng fact lịch |
| FR-05 | Lọc fact theo ngày và trạng thái hiệu lực | `filter_facts_for_message`, `filter_active_facts_for_date` trong `app/fact_filter.py` | `tests/test_fact_filter.py` kiểm tra ngày mai, hủy lịch, invalidation |
| FR-06 | Hỗ trợ tiếng Việt và tương đối thời gian | `AGENT_SYSTEM_PROMPT`, `EXTRACTION_INSTRUCTIONS`, logic `mai/ngày mai` | Các test dùng câu tiếng Việt và mốc ngày tuyệt đối |
| FR-07 | Hiển thị trace cho người dùng | `ChatResponse.tool_trace`, cấu trúc `ToolTrace` | Test xác nhận tên tool và kết quả từng lần gọi |
| FR-08 | Giới hạn vòng lặp tool | `AGENT_MAX_TOOL_ITERATIONS` trong `GraphitiSettings` và `AssistantClient` | Test `test_tool_iteration_limit_gets_final_no_tool_answer` |

### 2.7.2. Yêu cầu phi chức năng

Ngoài các chức năng trực tiếp, hệ thống còn phải đáp ứng các yêu cầu phi chức năng quan trọng.

| Nhóm yêu cầu | Nội dung cụ thể | Ý nghĩa đối với hệ thống |
| --- | --- | --- |
| Khả năng triển khai | Chạy được dưới dạng ứng dụng web FastAPI, khởi động tài nguyên qua lifespan | Dễ demo, dễ đóng gói, phù hợp MVP |
| Khả năng cấu hình | Điều khiển bằng biến môi trường như `NEO4J_URI`, `EMBEDDING_MODE`, `MEMORY_WRITE_MODE` | Dễ chuyển môi trường thử nghiệm, local hoặc proxy |
| Tính nhất quán thời gian | Xử lý timezone `Asia/Ho_Chi_Minh`, chuẩn hóa ngày tương đối | Tránh lệch ngày khi hỏi “mai” hoặc “ngày mai” |
| Tính minh bạch | Trả về `retrieved_facts` và `tool_trace` | Người dùng thấy được căn cứ của câu trả lời |
| Tính ổn định | Giới hạn tool iteration và kiểm tra embedding dimension | Giảm rủi ro vòng lặp vô hạn và lỗi vector sai kích thước |
| Hỗ trợ tiếng Việt | Giữ nguyên tên riêng, chiều quan hệ, phủ định và cách diễn đạt | Phù hợp với dữ liệu hội thoại thực tế |
| Khả năng kiểm thử | Các quy tắc lọc fact phải có test riêng | Tăng độ tin cậy khi mở rộng tính năng |

### 2.7.3. Từ yêu cầu đến giá trị sản phẩm

Nhìn từ góc độ sản phẩm, các yêu cầu trên không chỉ là yêu cầu kỹ thuật mà còn là yêu cầu giá trị. Nếu hệ thống không truy xuất đúng memory, người dùng sẽ không tin. Nếu hệ thống không hủy được fact cũ, nó sẽ trả lời sai ở những tình huống quan trọng. Nếu hệ thống không hiển thị được trace, người dùng khó kiểm tra và khó chấp nhận việc AI “nhớ theo cách của nó”.

Chính vì vậy, Graphiti Chat Lab chọn cách hiện thực yêu cầu theo hướng rõ ràng và kiểm chứng được: memory được lưu có cấu trúc, facts có vòng đời, date được chuẩn hóa, và tool-calling được giới hạn. Tất cả điều đó giúp đề tài đi đúng tinh thần một nguyên mẫu có thể phát triển thành sản phẩm.

## 2.8. Cơ sở lý thuyết

### 2.8.1. Graph database và mô hình thuộc tính

Graph database là mô hình lưu trữ dữ liệu dưới dạng nút và cạnh, trong đó mỗi nút và cạnh đều có thể gắn thuộc tính. Khác với bảng quan hệ vốn phù hợp cho dữ liệu có cấu trúc cố định theo hàng-cột, graph database đặc biệt hiệu quả khi cần biểu diễn quan hệ giữa các thực thể, nhất là các quan hệ nhiều chiều, thay đổi theo thời gian, hoặc cần truy vết lịch sử.

Đối với memory cá nhân, các thực thể không tồn tại độc lập. Một khoản nợ luôn gắn với người nợ, người được nợ, thời điểm phát sinh và trạng thái hiện tại. Một lịch hẹn luôn gắn với người tham gia, thời gian, và tình trạng còn hiệu lực hay đã hủy. Property graph vì thế là lựa chọn phù hợp hơn vì có thể lưu trực tiếp cả thực thể lẫn các thuộc tính trạng thái.

Neo4j là một hệ quản trị graph database phổ biến, và Graphiti tận dụng Neo4j để xây dựng lớp memory của ứng dụng. Trong `app/graphiti_client.py`, `GraphitiMemory` khởi tạo client, gọi `build_indices_and_constraints()` khi khởi động, và dùng các thao tác `search`, `add_episode`, `execute_query` để lưu và truy xuất dữ liệu. Đặc biệt, phần invalidation không xóa facts, mà gán `invalid_at`, nhờ đó hệ thống bảo toàn được lịch sử và vẫn có thể loại bỏ các fact không còn đúng khỏi ngữ cảnh trả lời.

Từ góc nhìn lý thuyết, đây là một thiết kế dựa trên nguyên lý “giữ lịch sử, loại khỏi hiện tại”. Nguyên lý này đặc biệt hữu ích trong chatbot có memory, vì dữ liệu cũ vẫn cần được lưu cho mục đích kiểm tra, nhưng không phải lúc nào cũng nên dùng để trả lời câu hỏi hiện tại.

### 2.8.2. Embeddings và truy xuất ngữ nghĩa

Embedding là biểu diễn văn bản thành vector số trong không gian nhiều chiều. Các văn bản có nghĩa gần nhau sẽ có vector gần nhau hơn so với các văn bản không liên quan. Nhờ đó, hệ thống có thể truy xuất không chỉ theo từ khóa trùng khớp, mà còn theo độ tương đồng ngữ nghĩa.

Trong bài toán memory, embeddings rất quan trọng vì người dùng thường không đặt câu hỏi theo đúng từ ngữ đã lưu. Chẳng hạn, một fact có thể được lưu dưới dạng “Tôi thích quán cà phê yên tĩnh để làm việc”, nhưng câu hỏi lại là “Tao thích kiểu quán nào?”. Nếu chỉ tìm theo chuỗi ký tự, hệ thống sẽ khó bắt được liên hệ này. Nếu dùng embeddings, hệ thống có cơ hội truy xuất fact phù hợp dù câu hỏi và câu lưu không trùng chữ.

Tuy nhiên, embeddings không phải giải pháp đủ nếu đứng một mình. Nó giỏi đo độ gần nghĩa, nhưng không giỏi biểu diễn chiều quan hệ, trạng thái hiệu lực, hay logic phủ định. Vì thế, Graphiti Chat Lab dùng embeddings như một lớp hỗ trợ cho truy xuất, còn logic về vòng đời fact được xử lý bằng `valid_at`, `invalid_at` và các bộ lọc trạng thái.

Trong `app/graphiti_client.py`, hệ thống hỗ trợ ba chế độ embedding:

1. `proxy`: dùng `OpenAIEmbedder` qua `LLM_BASE_URL` khi proxy hỗ trợ `/v1/embeddings`.
2. `gemini`: dùng `GeminiEmbedder` trực tiếp với `GOOGLE_API_KEY`.
3. `local`: dùng `LocalQwenEmbedder` dựa trên `sentence-transformers`.

Chế độ `local` còn có bước chuẩn hóa truy vấn bằng `QWEN_QUERY_PROMPT` và kiểm tra kích thước vector qua `EMBEDDING_DIM`. Điều này cho thấy tác giả không chỉ dùng embeddings như một hộp đen, mà còn kiểm soát chất lượng đầu ra ở mức kỹ thuật.

### 2.8.3. Function calling và điều phối tool

Function calling là cơ chế cho phép mô hình ngôn ngữ không chỉ sinh câu trả lời tự do, mà còn phát tín hiệu gọi một hàm với tên và tham số xác định. Đây là bước rất quan trọng trong các hệ thống agentic, vì nó chuyển mô hình từ vai trò “người nói” sang vai trò “người ra quyết định bước tiếp theo”.

Trong `app/llm_client.py`, `AssistantClient` triển khai vòng lặp tool-calling: mô hình nhận prompt hệ thống, nội dung người dùng, và danh sách tool được khai báo; nếu mô hình trả về `functionCall`, hệ thống thực thi tool tương ứng, ghi lại kết quả vào `ToolTrace`, rồi gửi `functionResponse` ngược trở lại cho mô hình. Chu trình này lặp tối đa `AGENT_MAX_TOOL_ITERATIONS` lần. Nếu mô hình không còn yêu cầu gọi tool, hệ thống trả lời cuối cùng cho người dùng.

Cơ chế này có ba lợi ích chính. Thứ nhất, nó giảm rủi ro hallucination vì mô hình phải dựa vào tool kết quả thật thay vì tự bịa memory. Thứ hai, nó tách rõ hành vi đọc memory và ghi memory, nên dễ kiểm soát. Thứ ba, nó cho phép hệ thống ghi trace của từng lần gọi tool, từ đó tăng tính minh bạch.

Trong dự án, các tool được chia thành các nhóm theo chế độ ghi nhớ. `MEMORY_WRITE_MODE=exact` cho phép lưu nguyên văn thông điệp hiện tại. `MEMORY_WRITE_MODE=model` cho phép lưu fact đã được mô hình chuẩn hóa. `MEMORY_WRITE_MODE=both` mở cả hai đường. Cấu hình này rất phù hợp với giai đoạn thử nghiệm, vì nó cho phép so sánh hai chiến lược ghi nhớ khác nhau trên cùng một nền tảng.

### 2.8.4. ASGI và FastAPI trong hệ thống chat

ASGI (Asynchronous Server Gateway Interface) là giao diện chuẩn cho các ứng dụng web bất đồng bộ trong Python. FastAPI là framework ASGI hiện đại, phù hợp với các ứng dụng cần xử lý nhiều tác vụ I/O như gọi mô hình ngôn ngữ, truy cập database và phục vụ giao diện web đồng thời.

Trong Graphiti Chat Lab, FastAPI được dùng làm lớp HTTP trung tâm. `app/main.py` khai báo `lifespan` để khởi tạo `GraphitiMemory`, build indices, mở kết nối cần thiết và sau đó giải phóng tài nguyên khi ứng dụng dừng. Endpoint `/api/chat` nhận request, gọi `AssistantClient.reply()`, và trả về `ChatResponse`. Phần giao diện tĩnh được render bằng `Jinja2Templates`, nên hệ thống vừa có API rõ ràng vừa có trang demo trực tiếp.

Về mặt lý thuyết, kiến trúc này phù hợp với hệ thống chat vì các thao tác như gọi LLM, truy xuất Neo4j và tải mô hình embedding đều là các thao tác I/O hoặc compute bên ngoài, không nên xử lý đồng bộ đơn tuyến. ASGI giúp tối ưu hiệu quả tài nguyên và giúp ứng dụng giữ được cấu trúc rõ ràng cho mục đích nghiên cứu lẫn trình diễn.

### 2.8.5. Cơ chế thời gian và hủy fact

Trong bài toán memory hội thoại, thời gian là một trục ngữ nghĩa quan trọng không kém nội dung. Một fact có thể đúng hôm nay nhưng sai ngày mai. Do đó, hệ thống cần phân biệt giữa “thông tin đã tồn tại trong lịch sử” và “thông tin đang có hiệu lực”.

`app/fact_filter.py` triển khai đúng logic này. Hàm `filter_facts_for_message()` trước hết suy ra `target_date` từ ngữ cảnh người dùng. Nếu câu hỏi có chứa “mai” hoặc “ngày mai”, hệ thống chuyển ngày đó thành ngày tuyệt đối theo múi giờ `Asia/Ho_Chi_Minh`. Sau đó, nó lọc các fact có `valid_at` đúng ngày, đồng thời loại bỏ fact đã hết hiệu lực hoặc fact có dấu hiệu là một câu hủy. Nhóm helper `should_cancel_fact()` và `filter_active_facts_for_date()` tiếp tục đảm bảo rằng các fact đã bị invalidation không quay trở lại ngữ cảnh trả lời.

Các kiểm thử trong `tests/test_fact_filter.py` cho thấy logic này được xác nhận cụ thể bằng bốn tình huống:

1. Hỏi về “ngày mai” thì chỉ giữ lại fact đúng ngày mục tiêu.
2. Nếu có câu hủy lịch, fact tương ứng phải bị loại khỏi kết quả.
3. Nếu fact đã bị invalidated từ trước, nó không được hiển thị như fact còn hiệu lực.
4. Nếu invalidation nằm ở tương lai sau thời điểm truy vấn, fact vẫn còn hiệu lực cho đến thời điểm đó.

Những kiểm thử này rất quan trọng về mặt lý thuyết vì chúng chuyển khái niệm “đúng theo thời gian” thành hành vi có thể kiểm tra. Nói cách khác, hệ thống không chỉ mô tả rằng nó có memory theo thời gian, mà còn chứng minh được điều đó bằng các ràng buộc cụ thể.

### 2.8.6. Vì sao Graphiti/Neo4j phù hợp hơn lịch sử chat thuần và vector RAG

Nếu nhìn từ nguyên lý hệ thống, ưu thế của Graphiti/Neo4j đến từ việc nó giải quyết đồng thời ba lớp vấn đề: lưu trữ, truy xuất và trạng thái. Lịch sử chat thuần chỉ giải quyết lưu trữ thô; vector RAG giải quyết truy xuất ngữ nghĩa; còn Graphiti/Neo4j kết hợp được cả truy xuất ngữ nghĩa lẫn biểu diễn trạng thái và quan hệ.

Điểm khác biệt then chốt là mức độ “có cấu trúc” của memory. Với lịch sử chat thuần, hệ thống phải đọc lại một chuỗi văn bản dài mỗi lần trả lời. Với vector RAG, hệ thống có thể tìm các đoạn liên quan, nhưng vẫn phải tự suy luận xem đoạn đó còn hiệu lực không. Với Graphiti/Neo4j, thông tin về nội dung, người liên quan, thời gian và trạng thái được lưu trong cùng một mô hình đồ thị, nhờ đó việc lọc và truy hồi có thể bám theo logic nghiệp vụ thay vì chỉ theo similarity.

Điều này đặc biệt quan trọng trong ba loại truy vấn:

1. Truy vấn theo thời gian: “Mai tôi có gì?”, “Tuần sau tôi rảnh không?”
2. Truy vấn theo trạng thái: “Lịch này còn không?”, “Cái đó đã hủy chưa?”
3. Truy vấn theo quan hệ: “Ai nợ tôi tiền?”, “Tôi nợ ai?”

Với các truy vấn này, vector RAG thường chỉ cho biết “đoạn nào giống câu hỏi”, còn Graphiti/Neo4j có thể cung cấp “fact nào còn hiệu lực, fact nào đã bị hủy, và fact nào mang đúng chiều quan hệ”. Chính khả năng đó khiến Graphiti phù hợp hơn cho bài toán nhớ theo thời gian, hủy facts, và giữ ngữ cảnh tiếng Việt có cấu trúc.

## 2.9. Tiểu kết chương

Chương 2 đã cho thấy đề tài Graphiti Chat Lab có cơ sở nhu cầu rõ ràng và cơ sở kỹ thuật phù hợp. Ở cấp độ thị trường, người dùng thực sự cần một trợ lý có thể ghi nhớ lịch, công nợ và sở thích cá nhân, thay vì chỉ sinh câu trả lời trôi chảy. Ở cấp độ kỹ thuật, lịch sử chat thuần và vector RAG chưa đủ để xử lý trọn vẹn các tình huống có thời gian, phủ định, chiều quan hệ và trạng thái hủy.

Phân tích SWOT, PESTEL và Porter Five Forces cho thấy sản phẩm có cơ hội tốt ở một ngách rõ ràng, nhưng cũng đối mặt với cạnh tranh cao và yêu cầu dữ liệu cá nhân nhạy cảm. Các yêu cầu hệ thống được xác định từ chính code hiện có và các kiểm thử trong repo, giúp kết nối chặt chẽ giữa bài toán nghiên cứu và cách hiện thực. Cuối cùng, các nền tảng lý thuyết về graph database, embeddings, function calling và ASGI/FastAPI tạo thành khung kỹ thuật phù hợp để triển khai nguyên mẫu.

Từ kết quả của chương này, có thể khẳng định rằng lựa chọn Graphiti/Neo4j cho memory, Gemini-compatible function calling cho điều phối hội thoại, và FastAPI cho lớp phục vụ là một tổ hợp hợp lý cho bài toán trợ lý chat nhớ theo thời gian trong tiếng Việt. Các chương tiếp theo sẽ dựa trên nền tảng đó để mô tả kiến trúc, triển khai và đánh giá sản phẩm.
