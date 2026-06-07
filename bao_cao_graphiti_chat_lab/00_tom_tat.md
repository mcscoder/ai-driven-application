# Tóm Tắt

Graphiti Chat Lab là một nguyên mẫu ứng dụng chat web được xây dựng để kiểm chứng bài toán bộ nhớ dài hạn cho trợ lý hội thoại tiếng Việt. Thay vì chỉ dựa vào lịch sử chat ngắn hạn, hệ thống lưu các facts và episode vào Graphiti trên Neo4j, sau đó truy hồi theo ngữ cảnh thời gian trước khi sinh phản hồi cuối cùng. Cách tiếp cận này giúp hệ thống nhớ được các thông tin có giá trị lâu dài như lịch hẹn, khoản nợ, sở thích, hoặc những thay đổi kế hoạch mà người dùng muốn hủy hoặc cập nhật về sau.

Về mặt kỹ thuật, dự án tổ chức theo ba lớp chính. Lớp giao diện là một trang web tối giản hiển thị vùng chat, `retrieved_facts` và `tool_trace` để người dùng quan sát quá trình hệ thống xử lý. Lớp điều phối là `AssistantClient`, nơi mô hình Gemini-compatible được gọi theo vòng lặp tool-calling để tự quyết định khi nào cần search, remember hoặc cancel memory. Lớp bộ nhớ là `GraphitiMemory`, chịu trách nhiệm kết nối Neo4j, tạo index, lưu episode, lưu manual temporal fact cho các sự kiện có ngày giờ rõ ràng và truy xuất facts theo ngữ cảnh.

Kết quả của dự án là một prototype có thể chạy cục bộ, hỗ trợ tiếng Việt, có khả năng lưu và truy hồi các phát biểu bền vững của người dùng, đồng thời giải thích được nguồn gốc của câu trả lời. Điều này làm giảm hiện tượng quên ngữ cảnh, hạn chế trả lời nhầm bằng dữ liệu cũ, và tạo nền tảng rõ ràng cho các hướng phát triển như trợ lý cá nhân, trợ lý cho nhóm nhỏ, hoặc một lớp memory-as-a-service cho các ứng dụng chat khác.

Đặc biệt, hệ thống được thiết kế với ý thức rõ về thời gian và trạng thái. Các mốc tương đối như “mai” hay “ngày mai” được chuẩn hóa thành ngày tuyệt đối để truy hồi, các câu khẳng định về nợ được giữ đúng chiều quan hệ, và các thao tác hủy lịch có thể đánh dấu dữ liệu cũ là không còn hiệu lực thay vì xóa trắng lịch sử. Đây là điểm khác biệt cốt lõi khiến Graphiti Chat Lab phù hợp với bài toán thực tế hơn so với các chatbot chỉ dựa vào lịch sử tin nhắn thuần hoặc truy hồi văn bản ngữ nghĩa đơn giản.

**Từ khóa:** Graphiti, Neo4j, FastAPI, memory assistant, tiếng Việt, tool calling, temporal fact.
