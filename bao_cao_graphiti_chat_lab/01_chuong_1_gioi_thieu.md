# Chương 1. Giới thiệu

Chương này đặt nền tảng cho toàn bộ báo cáo bằng cách làm rõ bối cảnh hình thành đề tài, lý do lựa chọn, bài toán thực tiễn cần giải quyết, phạm vi triển khai, phương pháp thực hiện và tiêu chí đánh giá. Điểm trung tâm của đề tài không phải là một chatbot trả lời câu hỏi thông thường, mà là một prototype chat app có bộ nhớ dài hạn tiếng Việt, được xây dựng trên Graphiti + Neo4j, sử dụng Gemini-compatible tool calling, và công khai retrieved facts cùng tool trace để người dùng có thể kiểm chứng cách hệ thống tạo ra câu trả lời.

Từ góc nhìn sản phẩm, Graphiti Chat Lab được xem như một nguyên mẫu để kiểm chứng một giả thuyết rất cụ thể: nếu hệ thống chat có khả năng lưu nhớ có cấu trúc, hiểu được thời điểm, trạng thái hiệu lực, chiều quan hệ của thông tin, và cập nhật được khi người dùng thay đổi kế hoạch, thì nó sẽ hữu ích hơn đáng kể so với các chatbot chỉ dựa trên lịch sử hội thoại ngắn hạn. Các ví dụ như “ngày mai tôi có lịch gì không?”, “Minh nợ tao 60k”, hoặc “hủy lịch chơi game với anh Tú ngày mai” là những tình huống nhỏ nhưng phản ánh đúng nhu cầu thật của người dùng.

## 1.1 Bối cảnh hình thành đề tài

Trong vài năm gần đây, các ứng dụng hội thoại đã phát triển rất nhanh. Tuy nhiên, phần lớn hệ thống phổ biến vẫn tập trung vào khả năng sinh văn bản tự nhiên, trong khi bài toán nhớ đúng và nhớ lâu vẫn là điểm yếu. Ở mức sử dụng thực tế, người dùng không chỉ muốn một câu trả lời mượt mà; họ muốn hệ thống nhớ được mình đã nói gì, đã hẹn gì, đã nợ ai, ai nợ mình, và điều gì đã bị hủy hoặc thay đổi. Nói cách khác, giá trị thật của một trợ lý chat không chỉ nằm ở “nói hay”, mà nằm ở “nhớ đúng” và “sửa đúng”.

Vấn đề này trở nên rõ hơn trong các ngữ cảnh tiếng Việt. Người dùng thường diễn đạt thông tin với các mốc thời gian tương đối như “mai”, “ngày mai”, “chiều nay”, “2 giờ chiều”, hoặc dùng câu phủ định và câu hủy theo cách tự nhiên, không theo một mẫu cố định. Nếu hệ thống không chuẩn hóa được thời gian, không phân biệt được thông tin còn hiệu lực với thông tin đã bị thay đổi, hoặc không giữ được chiều quan hệ của các khoản nợ, thì câu trả lời sẽ dễ sai dù bề ngoài vẫn nghe hợp lý. Đây là loại sai rất nguy hiểm vì nó không dễ bị phát hiện ngay trong lần đầu kiểm tra.

Trong bối cảnh đó, đề tài Graphiti Chat Lab được lựa chọn để thử trả lời một yêu cầu thực tế: làm sao xây dựng một ứng dụng chat có thể nhớ các facts cá nhân một cách có cấu trúc, truy hồi theo ngữ cảnh thời gian, và cập nhật trạng thái khi người dùng nói “hủy”, “không”, hoặc “đổi lịch”. Hệ thống được tổ chức quanh FastAPI ở lớp web, `AssistantClient` ở lớp điều phối hội thoại, và `GraphitiMemory` ở lớp lưu trữ, nhưng mục tiêu của báo cáo ở chương này không phải mô tả kiến trúc chi tiết, mà là chỉ ra vì sao bài toán này đáng làm và đáng kiểm chứng.

## 1.2 Lý do chọn đề tài

Lý do đầu tiên là tính thực dụng. Một người dùng bình thường không cần một chatbot “biết mọi thứ”; họ cần một công cụ nhớ được những thứ liên quan trực tiếp đến đời sống hằng ngày: lịch học, lịch làm việc, lịch hẹn, khoản nợ, những thay đổi đã thống nhất trước đó, hoặc các cam kết cá nhân. Những thông tin này có giá trị cao vì nếu quên hoặc nhớ sai, người dùng sẽ mất thời gian, thậm chí chịu hậu quả thực tế. Vì vậy, bài toán bộ nhớ dài hạn không phải một tính năng phụ, mà là lõi của trải nghiệm.

Lý do thứ hai là đề tài có tính giao thoa rõ giữa công nghệ và sản phẩm. Graphiti + Neo4j cho phép lưu trữ ngữ cảnh dưới dạng đồ thị có quan hệ và trạng thái thời gian; Gemini-compatible tool calling cho phép mô hình tự quyết định khi nào cần tìm kiếm, khi nào cần lưu, và khi nào cần hủy thông tin cũ; FastAPI cho phép đóng gói thành một dịch vụ web rõ ràng. Với tổ hợp này, đề tài không chỉ là một bài thử kỹ thuật, mà còn là một nguyên mẫu có thể trình diễn, quan sát, và mở rộng.

Lý do thứ ba là hệ thống có khả năng tạo ra giá trị minh bạch hơn so với chatbot đen hộp. Trong Graphiti Chat Lab, mỗi phản hồi không chỉ là một chuỗi văn bản mà còn đi kèm `retrieved_facts` và `tool_trace`. Điều đó có nghĩa là người dùng không phải đoán hệ thống đã dựa vào dữ liệu nào để trả lời. Với các tình huống như nợ tiền, lịch hẹn, hay hủy lịch, khả năng truy vết này đặc biệt quan trọng vì nó giúp người dùng kiểm tra được tính đúng đắn thay vì chỉ tin vào giọng văn của mô hình.

## 1.3 Vấn đề thực tiễn cần giải quyết

Nếu chỉ nhìn ở bề mặt, nhiều hệ thống chat hiện nay vẫn có thể trả lời khá tự nhiên. Nhưng khi đặt vào tình huống cụ thể, những giới hạn của bộ nhớ ngắn hạn lộ ra rất nhanh. Người dùng hỏi “ngày mai tôi có lịch gì không?” không chỉ muốn một câu trả lời chung chung; họ muốn biết đúng lịch của ngày mai, đúng mốc thời gian, đúng trạng thái còn hiệu lực, và không bị lẫn với các lịch khác. Tương tự, khi người dùng nói “Minh nợ tao 60k” hoặc “Tao nợ Nam 30k”, hệ thống phải giữ đúng chiều quan hệ giữa chủ nợ và con nợ, vì chỉ cần đảo chiều là ý nghĩa đã thay đổi hoàn toàn.

Trường hợp hủy lịch còn phức tạp hơn. Nếu người dùng từng nói “Có lịch chơi game với anh Tú lúc 3h chiều mai” rồi sau đó nói “hủy lịch chơi game với anh Tú ngày mai”, hệ thống không nên tạo ra một fact mới mơ hồ rồi để fact cũ vẫn còn nguyên. Thay vào đó, nó phải tìm đúng fact liên quan, đánh dấu nó là không còn hiệu lực, và khi truy hồi lại thì không được trả nó như một lịch còn sống. Đây là điểm khác biệt giữa một chatbot chỉ lưu văn bản và một hệ thống memory có logic.

Để mô tả ngắn gọn các vấn đề thực tiễn mà đề tài nhắm tới, có thể xem bảng sau:

**Bảng 1.1. Một số tình huống thực tiễn và yêu cầu xử lý tương ứng**

| Tình huống người dùng | Rủi ro nếu dùng chatbot thông thường | Cách Graphiti Chat Lab cần xử lý |
| --- | --- | --- |
| Hỏi lịch theo mốc tương đối như “ngày mai” | Dễ trả lời mơ hồ hoặc lẫn ngày | Chuẩn hóa sang ngày tuyệt đối và truy hồi đúng facts của ngày đó |
| Ghi nhớ khoản nợ | Dễ nhầm chiều nợ hoặc chỉ nhớ con số | Giữ nguyên quan hệ debtor/creditor/amount |
| Hủy hoặc đổi lịch | Dễ để lại mâu thuẫn giữa lịch cũ và lịch mới | Tìm fact tương ứng và cập nhật trạng thái hủy |
| Kiểm tra lại câu trả lời | Người dùng không biết hệ thống dựa vào đâu | Hiển thị `retrieved_facts` và `tool_trace` |

Nhìn từ góc độ này, vấn đề thực tiễn của đề tài không chỉ là “làm chatbot”, mà là làm một lớp bộ nhớ hội thoại có khả năng vận hành trong các tình huống rất đời thường nhưng dễ sai nhất. Chính những tình huống đó tạo ra khoảng trống thị trường cho một trợ lý có trí nhớ thật.

## 1.4 Mục tiêu tổng quát và mục tiêu cụ thể

Mục tiêu tổng quát của đề tài là xây dựng một prototype chat app có bộ nhớ dài hạn, đủ rõ ràng để kiểm thử trong môi trường thật và đủ có cấu trúc để định hướng phát triển thành sản phẩm. Prototype này phải hỗ trợ tiếng Việt, xử lý được lịch hẹn, công nợ, và các thao tác hủy/cập nhật lịch, đồng thời trả về phần giải thích gồm retrieved facts và tool trace để người dùng quan sát được logic bên trong.

Từ mục tiêu tổng quát đó, đề tài được chia thành các mục tiêu cụ thể sau:

1. Xây dựng một ứng dụng web chat tối giản bằng FastAPI, với một endpoint trung tâm là `POST /api/chat`.
2. Tách rõ vai trò giữa lớp giao diện, lớp điều phối hội thoại và lớp lưu trữ bộ nhớ để dễ kiểm thử và dễ mở rộng.
3. Tích hợp Graphiti với Neo4j nhằm lưu và truy xuất memory dưới dạng graph có quan hệ và trạng thái thời gian.
4. Thiết kế cơ chế Gemini-compatible tool calling để mô hình có thể tự chọn giữa tìm kiếm, lưu nhớ, hoặc hủy memory cũ.
5. Hỗ trợ nhiều chính sách ghi nhớ qua `memory_write_mode` gồm `exact`, `model` và `both`, để có thể so sánh cách lưu nguyên văn với cách lưu facts được chuẩn hóa.
6. Chuẩn hóa các trường hợp thời gian tương đối như “mai” và “ngày mai” thành ngày tuyệt đối trong bối cảnh local time.
7. Bảo đảm chiều quan hệ của các khoản nợ được giữ nguyên, tránh đảo từ “A nợ B” sang “B nợ A”.
8. Hiển thị `retrieved_facts` và `tool_trace` như một phần của kết quả trả về nhằm tăng tính minh bạch.
9. Kiểm thử những rule dễ lỗi nhất như lọc facts theo ngày, hủy lịch, giới hạn số vòng gọi tool, và chọn đúng chế độ ghi nhớ.

Các mục tiêu trên không phải là danh sách tính năng rời rạc, mà là một chuỗi logic dẫn từ nhu cầu người dùng đến hiện thực kỹ thuật. Nếu một trong các mục tiêu này không đạt, hệ thống sẽ mất giá trị cốt lõi. Ví dụ, nếu truy hồi đúng nhưng không hủy được lịch cũ, người dùng vẫn bị trả lời sai; nếu lưu được memory nhưng không hiển thị nguồn gốc, hệ thống sẽ thiếu tính tin cậy; nếu tool calling hoạt động nhưng không giới hạn vòng lặp, quá trình trả lời sẽ thiếu kiểm soát.

Để cho thấy mục tiêu và hiện thực code gắn với nhau như thế nào, có thể nhìn theo bảng sau:

**Bảng 1.2. Mục tiêu đề tài và dấu hiệu hiện thực trong code**

| Mục tiêu | Thành phần code liên quan | Dấu hiệu kiểm chứng |
| --- | --- | --- |
| Xử lý request chat | `app/main.py` | Endpoint `POST /api/chat` trả `reply`, `retrieved_facts`, `tool_trace` |
| Điều phối hành vi LLM | `app/llm_client.py` | `AssistantClient.reply()` lặp tool-calling có kiểm soát |
| Lưu và truy xuất memory | `app/graphiti_client.py` | `GraphitiMemory`, `GraphitiSettings`, `search_edges`, `add_episode` |
| Lọc facts theo trạng thái | `app/fact_filter.py` | `filter_active_facts`, `filter_active_facts_for_date`, `should_cancel_fact` |
| Kiểm thử quy tắc cốt lõi | `tests/test_llm_client.py`, `tests/test_fact_filter.py` | Các case “ngày mai”, nợ, hủy lịch, giới hạn tool |

## 1.5 Đối tượng nghiên cứu, phạm vi triển khai và giả định

Đối tượng nghiên cứu của đề tài là các tương tác hội thoại mang tính cá nhân hoặc nhóm nhỏ, trong đó thông tin cần được nhớ không chỉ ở dạng hội thoại ngắn hạn mà còn ở dạng facts có thể truy hồi và cập nhật. Người dùng mục tiêu có thể là sinh viên, người làm việc độc lập, hoặc các nhóm nhỏ cần hỏi lại lịch, nợ, kế hoạch, hoặc các cam kết đã nói trước đó. Đây là nhóm người dùng phù hợp với một nguyên mẫu có bộ nhớ dài hạn vì họ thường xuyên lặp lại các thông tin loại này trong chat.

Phạm vi công nghệ của đề tài được giới hạn ở một prototype chạy được cục bộ, sử dụng FastAPI cho lớp web, Graphiti + Neo4j cho bộ nhớ đồ thị, và một mô hình Gemini-compatible cho lớp sinh câu trả lời và gọi tool. Hệ thống chưa đặt mục tiêu giải quyết bài toán xác thực người dùng, phân quyền phức tạp, đa tenant ở quy mô lớn, hay tối ưu chi phí vận hành production. Việc giới hạn này là chủ ý, vì giai đoạn đầu của một đề tài định hướng khởi nghiệp cần chứng minh giá trị lõi trước khi mở rộng.

Trong phạm vi nghiệp vụ, đề tài tập trung vào ba nhóm thông tin có ý nghĩa cao và dễ sinh lỗi nếu xử lý bằng chatbot thông thường. Nhóm thứ nhất là lịch hẹn và lịch trình, đặc biệt là các biểu đạt thời gian tương đối như “ngày mai” hoặc “chiều mai”. Nhóm thứ hai là khoản nợ, nơi chiều quan hệ phải được giữ tuyệt đối chính xác. Nhóm thứ ba là thao tác hủy, đổi, hoặc vô hiệu hóa thông tin cũ, vốn đòi hỏi hệ thống phải không chỉ nhớ mà còn hiểu trạng thái của memory.

Để tránh mở rộng quá sớm, đề tài làm việc dựa trên một số giả định:

- Người dùng chấp nhận giao tiếp bằng tiếng Việt tự nhiên, có thể không hoàn toàn chuẩn hóa về dấu hoặc cấu trúc câu.
- Các thông tin cần nhớ có thể được biểu diễn dưới dạng facts ngắn gọn nhưng vẫn giữ đủ ngữ nghĩa.
- Môi trường chạy có sẵn Neo4j và endpoint LLM phù hợp với cấu hình trong biến môi trường.
- Hệ thống ưu tiên tính đúng, tính kiểm chứng và tính minh bạch hơn là sự “khéo nói” của câu trả lời.
- Một nhóm logic hoặc một không gian dữ liệu chung là đủ cho giai đoạn prototype, chưa cần cơ chế đa tài khoản hoàn chỉnh.

Những giả định này giúp giảm độ phức tạp, nhưng không làm mất tính thực tiễn của đề tài. Ngược lại, chúng giúp báo cáo tập trung vào điều quan trọng nhất: liệu một trợ lý chat có bộ nhớ đồ thị có thực sự hữu ích trong các tình huống đời thường hay không.

## 1.6 Ý nghĩa thực tiễn và giá trị ứng dụng

Giá trị thực tiễn rõ nhất của đề tài là giảm việc người dùng phải lặp lại thông tin. Nếu một lịch hẹn đã được ghi nhớ đúng, người dùng không cần nhắn lại nhiều lần ở các phiên chat khác nhau. Nếu một khoản nợ đã được lưu với chiều quan hệ chính xác, hệ thống có thể trả lời lại ngay khi được hỏi. Nếu một lịch đã bị hủy, hệ thống có thể tránh trả lời bằng dữ liệu cũ. Từng lợi ích này nhỏ, nhưng cộng lại sẽ tạo nên một trải nghiệm trợ lý cá nhân đáng tin cậy hơn.

Giá trị thứ hai là khả năng giải thích. Trong nhiều ứng dụng AI hiện nay, người dùng không biết câu trả lời được tạo ra từ đâu. Graphiti Chat Lab cố ý làm khác bằng cách trả về `retrieved_facts` và `tool_trace` cùng với `reply`. Điều đó biến một câu trả lời từ trạng thái “đúng hoặc sai mà không biết” sang trạng thái “có thể kiểm tra”. Với các bài toán liên quan đến lịch, nợ và cam kết cá nhân, việc kiểm tra nguồn gốc thông tin là cực kỳ quan trọng.

Giá trị thứ ba là khả năng định hướng sản phẩm. Prototype này có thể phát triển thành nhiều hướng khác nhau: trợ lý ghi nhớ cá nhân, trợ lý cho nhóm nhỏ, lớp memory-as-a-service cho ứng dụng chat, hoặc công cụ hỗ trợ quản lý công việc cá nhân. Điểm mạnh của đề tài là không chỉ trình diễn một công nghệ mới, mà còn mô tả được một ngách sản phẩm có nhu cầu rõ, dễ thử nghiệm, và có thể mở rộng dần sau khi đã chứng minh được giá trị cốt lõi.

## 1.7 Phương pháp thực hiện

Đề tài được thực hiện theo hướng phân rã bài toán trước, sau đó mới hiện thực từng phần nhỏ và kiểm thử ngay trên các tình huống rủi ro cao. Cách làm này phù hợp với một hệ thống AI ứng dụng, vì nếu chỉ xây theo cảm tính thì rất dễ bỏ sót các lỗi liên quan đến thời gian, phủ định, và cập nhật trạng thái. Phần code hiện tại phản ánh đúng tinh thần đó: các module được tách riêng, các rule quan trọng được viết test riêng, và các hành vi cần ổn định đều được mô phỏng bằng case cụ thể.

Về quy trình, đề tài đi qua bốn bước chính. Bước một là phân tích nhu cầu và xác định các tình huống sử dụng có giá trị cao, ví dụ hỏi lịch ngày mai, ghi nợ, và hủy lịch. Bước hai là thiết kế kiến trúc mức module để tách `main`, `llm_client`, `graphiti_client`, và `fact_filter` thành các phần có trách nhiệm rõ ràng. Bước ba là hiện thực prototype với các tool cần thiết để mô hình có thể search, remember và cancel. Bước bốn là kiểm thử bằng các unit test tập trung vào hành vi dễ sai nhất.

Những kiểm thử trong `tests/test_llm_client.py` và `tests/test_fact_filter.py` cho thấy phương pháp này không dừng ở mô tả ý tưởng. Chẳng hạn, hệ thống phải:

- giữ đúng lịch cho câu hỏi “ngày mai tôi có lịch gì không?”,
- lưu được khoản nợ nhưng không đảo chiều quan hệ nợ,
- hủy được lịch đã lưu thay vì tạo mâu thuẫn mới,
- giữ lại facts còn hiệu lực khi ngày hẹn chưa tới,
- và dừng đúng lúc khi vòng gọi tool đạt giới hạn cấu hình.

Phương pháp thực hiện ở đây có thể xem là một biến thể thực dụng của test-driven development: trước hết xác định rõ hành vi cần đạt, sau đó viết/điều chỉnh code để đáp ứng hành vi đó. Điều quan trọng không phải là dùng một tên quy trình “đẹp”, mà là đảm bảo rằng các tình huống có xác suất lỗi cao nhất đều có dấu kiểm chứng cụ thể.

## 1.8 Câu hỏi nghiên cứu, tiêu chí đánh giá và kết cấu báo cáo

Để tránh biến đề tài thành một bản mô tả sản phẩm chung chung, quá trình thực hiện cần trả lời một số câu hỏi nghiên cứu cụ thể. Câu hỏi thứ nhất là: làm thế nào biểu diễn memory của người dùng sao cho đủ ngắn gọn để mô hình xử lý, nhưng vẫn đủ giàu ngữ nghĩa để truy xuất lại sau này? Câu hỏi thứ hai là: làm thế nào để mô hình ngôn ngữ biết khi nào cần search, khi nào cần remember, và khi nào cần cancel? Câu hỏi thứ ba là: làm thế nào để xử lý chính xác các biểu đạt thời gian tương đối trong tiếng Việt, đặc biệt là “mai” và “ngày mai”? Câu hỏi thứ tư là: làm thế nào để người dùng nhìn thấy nguồn gốc của câu trả lời thay vì chỉ nhận kết quả cuối?

Từ các câu hỏi này, hệ thống được đánh giá theo những tiêu chí sau:

1. **Độ đúng của truy hồi**: khi hỏi về lịch, nợ, hoặc thói quen, hệ thống phải trả về facts liên quan và không bỏ sót các facts quan trọng.
2. **Độ đúng của thời gian**: các biểu đạt như “ngày mai” phải được chuẩn hóa thành mốc ngày tuyệt đối phù hợp với local time.
3. **Độ đúng của quan hệ**: với khoản nợ, hệ thống phải phân biệt rõ ai nợ ai, không được đảo chiều.
4. **Độ đúng của hủy/cập nhật**: facts đã bị hủy không được tiếp tục xuất hiện như dữ liệu còn hiệu lực.
5. **Tính minh bạch**: câu trả lời phải kèm `retrieved_facts` và `tool_trace` để người dùng hiểu vì sao hệ thống trả lời như vậy.
6. **Tính ổn định của điều phối**: tool-calling không được chạy vô hạn, mà phải dừng hợp lý theo cấu hình `AGENT_MAX_TOOL_ITERATIONS`.

Các tiêu chí này vừa là tiêu chí kỹ thuật, vừa là tiêu chí sản phẩm. Một ứng dụng memory assistant chỉ có giá trị khi nó không những nói được mà còn nhớ đúng, sửa đúng và giải thích được. Vì vậy, đánh giá của đề tài không nên dừng ở việc “có chạy hay không”, mà phải đi sâu vào các tình huống mà chatbot thường sai.

Về kết cấu báo cáo, tài liệu được tổ chức theo logic từ nhu cầu đến giải pháp, rồi từ giải pháp đến triển khai và định hướng sản phẩm:

- **Chương 1. Giới thiệu**: trình bày bối cảnh, lý do chọn đề tài, mục tiêu, phạm vi, giả định, ý nghĩa, phương pháp và tiêu chí đánh giá.
- **Chương 2. Tổng quan tài liệu và cơ sở lý thuyết**: làm rõ bối cảnh công nghệ, nhu cầu thị trường và các khái niệm nền tảng liên quan.
- **Chương 3. Thiết kế và phát triển sản phẩm**: mô tả kiến trúc, thành phần hệ thống, luồng xử lý, và cách hiện thực prototype.
- **Chương 4. Triển khai và mô hình kinh doanh**: trình bày kết quả triển khai, thử nghiệm, đánh giá và hướng thương mại hóa ban đầu.
- **Chương 5. Kết luận và kiến nghị**: tổng kết kết quả, nêu hạn chế và định hướng phát triển tiếp theo.

Kết cấu này phù hợp với một đề tài định hướng khởi nghiệp vì nó không chỉ mô tả công nghệ, mà còn giữ liên kết chặt với giá trị sử dụng và khả năng phát triển sản phẩm. Đó cũng là lý do Graphiti Chat Lab được chọn làm đề tài: nó đủ nhỏ để làm prototype, nhưng đủ thật để trả lời một bài toán ứng dụng có nhu cầu rõ ràng.
