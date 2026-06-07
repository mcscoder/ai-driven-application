# Phụ Lục

## Phụ lục A. Cấu hình môi trường quan trọng

| Biến môi trường | Vai trò |
| --- | --- |
| `NEO4J_URI` | Địa chỉ kết nối Neo4j |
| `NEO4J_USER` / `NEO4J_PASSWORD` | Thông tin xác thực Neo4j |
| `LLM_BASE_URL` | Endpoint tương thích OpenAI/Gemini, cần có `/v1` |
| `LLM_API_KEY` | Khóa truy cập mô hình |
| `LLM_MODEL` | Tên model chính |
| `LLM_SMALL_MODEL` | Model nhỏ hơn cho tác vụ phụ nếu cần |
| `EMBEDDING_MODE` | `local`, `proxy`, hoặc `gemini` |
| `EMBEDDING_MODEL` | Tên embedding model |
| `EMBEDDING_DIM` | Số chiều vector embedding |
| `EMBEDDING_PRELOAD` | Có tiền tải model local khi khởi động hay không |
| `MEMORY_WRITE_MODE` | `exact`, `model`, hoặc `both` |
| `AGENT_MAX_TOOL_ITERATIONS` | Giới hạn số vòng function calling |
| `GRAPHITI_GROUP_ID` | Nhóm dữ liệu của phiên lab |
| `RETRIEVAL_LIMIT` | Số kết quả memory tối đa cho một lượt truy vấn |

## Phụ lục B. API mẫu

**Request**

```bash
curl -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Mai tôi có lịch gì không?"}'
```

**Response kỳ vọng**

```json
{
  "reply": "Ngày mai bạn có ...",
  "retrieved_facts": [
    {
      "fact": "toi co lich choi game voi anh Tu luc 2 gio chieu",
      "valid_at": "2026-06-07T14:00:00+07:00",
      "invalid_at": null,
      "score": null
    }
  ],
  "tool_trace": [
    {
      "name": "search_memory",
      "arguments": {
        "query": "lich ngay mai",
        "date": "2026-06-07"
      },
      "result": "retrieved 1 active fact(s)"
    }
  ]
}
```

## Phụ lục C. Kịch bản kiểm thử chính

1. Kiểm thử lọc facts theo ngày mai.
2. Kiểm thử hủy lịch và cập nhật trạng thái invalid.
3. Kiểm thử giữ lại facts còn hiệu lực khi `invalid_at` nằm trong tương lai.
4. Kiểm thử chế độ lưu `exact`, `model` và `both`.
5. Kiểm thử giới hạn số vòng tool-calling.
6. Kiểm thử truy hồi từ manual temporal facts thay vì tìm toàn graph khi đã có ngày cụ thể.
7. Kiểm thử giữ đúng chiều quan hệ nợ.

## Phụ lục D. Ghi chú triển khai

- Ứng dụng có thể chạy bằng `uv` và `uvicorn` trong môi trường Python 3.12 trở lên.
- Trang chủ hiển thị một giao diện chat đơn giản, phục vụ trình diễn nguyên mẫu.
- Phần memory backend dựa trên Neo4j và Graphiti nên cần chuẩn bị database trước khi chạy.
- Nếu dùng embedding local, lần chạy đầu tiên có thể tải mô hình về cache nội bộ của dự án.
