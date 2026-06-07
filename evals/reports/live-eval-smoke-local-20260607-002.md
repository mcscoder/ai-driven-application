# Live Eval smoke-local-20260607-002

- Created: 2026-06-07T15:17:35.672734
- Base URL: `http://127.0.0.1:8000`
- GRAPHITI_GROUP_ID: `chat-lab-test-002`
- Demo ready: **False**
- Pass rate: 0/1 (0%)
- Critical pass rate: 0/1 (0%)
- Hallucinated memory cases: 0

## Category Results

| Category | Passed | Total | Rate |
| --- | ---: | ---: | ---: |
| everyday_memory | 0 | 1 | 0% |

## Failed Cases

### everyday_001 (everyday_memory)

- Critical: `True`
- Probe: Nếu cuối tuần tui muốn ra ngoài làm khóa luận thì nên chọn kiểu quán nào?
- Expected memory: quán cà phê yên tĩnh, ít nhạc, có ổ cắm, làm việc lâu
- Forbidden memory: quán đông người, nhạc lớn
- Judge reason: The assistant failed to retrieve the specific personal preferences stored in memory (quiet, low music, power outlets) and instead provided generic advice. It did not acknowledge that it remembered the user's specific requirements for working.
- Reply: Để chọn quán làm khóa luận vào cuối tuần, bạn nên ưu tiên những tiêu chí sau để đảm bảo hiệu quả công việc:

1.  **Không gian yên tĩnh:** Tránh các quán có nhạc quá to hoặc quá đông đúc, ồn ào. Các quán cà phê sách hoặc các quán có khu vực làm việc riêng (coworking space) là lựa chọn lý tưởng.
2.  **Bàn ghế phù hợp:** Ưu tiên bàn có độ cao vừa phải, ghế có tựa lưng thoải mái để ngồi lâu không bị mỏi.
3.  **Ổ cắm điện:** Đây là yếu tố quan trọng nhất. Hãy chọn quán có nhiều ổ cắm điện gần bàn ngồi để không lo hết pin laptop.
4.  **Wi-Fi ổn định:** Kiểm tra đánh giá trên Google Maps hoặc hỏi nhân viên trước khi vào để đảm bảo mạng đủ mạnh cho việc tra cứu tài liệu.
5.  **Ánh sáng:** Chọn nơi có ánh sáng tự nhiên hoặc đèn đủ sáng để không hại mắt khi làm việc lâu.

**Một vài gợi ý kiểu quán:**
*   **Chuỗi quán cà phê làm việc (Work-friendly cafes):** Thường được thiết kế cho dân văn phòng/sinh viên, có nhiều ổ cắm và không gian tách biệt.
*   **Thư viện hoặc quán cà phê trong thư viện:** Đây là môi trường tập trung nhất.
*   **Quán cà phê vắng vào buổi sáng:** Nếu bạn có thể dậy sớm, các quán cà phê thường rất yên tĩnh vào khung giờ 8h - 10h sáng cuối tuần.

Bạn có muốn mình tìm thử một vài quán cụ thể ở khu vực nào không? Nếu có, hãy cho mình biết địa điểm nhé!
- Retrieved facts:
  - (none)


## All Cases

- **FAIL** `everyday_001` score=2: The assistant failed to retrieve the specific personal preferences stored in memory (quiet, low music, power outlets) and instead provided generic advice. It did not acknowledge that it remembered the user's specific requirements for working.
