# V-Ask — Vietnamese Personal AI

Trợ lý cá nhân dùng Streamlit, OpenAI Python SDK và NVIDIA Nemotron qua Nebius Token Factory. Chat/ghi chú được lưu trong SQLite cục bộ; tài liệu tải lên được trích xuất và tìm kiếm cục bộ. Chỉ các đoạn liên quan mới được gửi tới Nebius khi đặt câu hỏi.

## Cấu trúc

```text
v-ask-visual-assistant/
├── app.py                 # Giao diện Streamlit và điều phối
├── config.py              # Cấu hình ứng dụng
├── llm_client.py          # OpenAI SDK → Nebius Token Factory
├── memory.py              # Chat và ghi chú trong SQLite
├── rag.py                 # Đọc PDF/TXT, chia đoạn, tìm kiếm cục bộ
├── desktop_actions.py     # Mở ứng dụng allowlist và YouTube
├── requirements.txt
├── .env.example
└── .streamlit/config.toml
```

## Chạy ứng dụng

1. Cài Python 3.10 trở lên, tạo môi trường ảo và cài thư viện:

   ```bash
   python -m venv .venv
   # Windows: .venv\Scripts\activate
   # macOS/Linux: source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Tạo biến môi trường `NEBIUS_API_KEY` bằng API key từ Nebius Token Factory. Có thể tùy chỉnh `NEBIUS_MODEL` theo model ID Nemotron được bật trong tài khoản. Tránh commit key vào Git.
3. Khởi chạy:

   ```bash
   streamlit run app.py
   ```

SQLite mặc định ở `data/vask.sqlite3`; thư mục `data/` bị gitignore. Đổi vị trí bằng `VASK_DATA_DIR`. Mỗi máy chạy app dùng bộ nhớ riêng.

## RAG và riêng tư

PDF/TXT được trích xuất trong tiến trình Streamlit và lưu trong session hiện tại, không ghi nội dung tài liệu xuống đĩa. Bộ truy hồi từ khóa chọn tối đa năm đoạn liên quan; các đoạn đó cùng lịch sử chat gần nhất sẽ được gửi đến Nebius để sinh câu trả lời. Tài liệu không được nhúng hay gửi toàn bộ. Không tải lên nội dung nhạy cảm nếu không muốn đoạn trích rời khỏi thiết bị.

## Desktop actions

Hành động không chạy lệnh shell tùy ý. `desktop_actions.py` có allowlist mẫu (Notepad, Calculator) có thể chỉnh theo máy. Giao diện cung cấp nút xác nhận cho thao tác mở ứng dụng hoặc tìm trên YouTube. Chức năng mở trình duyệt dùng truy vấn tìm kiếm; nó không tự phát video.

## Chia việc cho 2 thành viên

| Thành viên | Phạm vi sở hữu | Các file chính |
|---|---|---|
| A — AI, bộ nhớ và RAG | Gọi Nebius; thiết kế prompt; schema/truy vấn SQLite; đọc, chia đoạn và truy hồi PDF/TXT; xử lý lỗi provider. Giao tiếp qua API `answer(messages, context)`, `memory.*`, `extract_text()` và `retrieve()`. | `llm_client.py`, `memory.py`, `rag.py`, `config.py`, `requirements.txt` |
| B — Sản phẩm và tích hợp máy tính | Streamlit UI, luồng tải file, hiển thị lịch sử/ghi chú, UX xác nhận hành động desktop, README và cấu hình giao diện. Tích hợp module A qua public function, tránh sửa implementation nội bộ của chúng. | `app.py`, `desktop_actions.py`, `.streamlit/`, `README.md`, `.gitignore` |

### Quy ước Git để tránh xung đột

- Làm trên branch riêng: `feature/ai-memory-rag` và `feature/streamlit-actions`.
- Không cùng sửa `app.py` hoặc `memory.py`; thay đổi giao diện do B giữ, logic lưu trữ do A giữ.
- Giữ chữ ký public function ổn định; nếu cần đổi, báo qua issue/PR trước khi tích hợp.
- Mỗi nhánh commit riêng, mở PR vào `main`; tích hợp A trước để B gọi được API đã ổn định.
