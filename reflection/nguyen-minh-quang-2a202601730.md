# Nguyễn Minh Quang - 2A202601730

## Vai trò
Thiết kế, chỗ khó, nguyên tắc HAX/PAIR.

## Phần mình làm
Mình viết lát cắt một câu, non-goals, mức automation theo cost-of-error, 4 lớp chỗ khó, 8 kịch bản rủi ro, và phần nguyên tắc HAX/PAIR để spec không bị chung chung. Ngoài ra, mình tạo Google Form khảo sát người dùng, gửi cho học viên ngoài nhóm, và tổng hợp phản hồi thực tế để kiểm tra xem pain "khó tìm câu hỏi cũ / dễ hỏi trùng / không biết có nên đăng post mới không" có đúng với người dùng thật không.

Phần của mình là chỗ phải quyết định bot được phép làm gì, không được làm gì, khi nào phải hỏi lại hoặc từ chối, và kết quả khảo sát giúp mình không chỉ dựa vào suy đoán của nhóm khi viết các quyết định đó.

## AI hỗ trợ thế nào
AI giúp mình phác nhanh bảng kịch bản, gợi ý cách diễn đạt ngắn hơn, và rà lại câu hỏi khảo sát để tránh hỏi kiểu dẫn dắt. Nhưng toàn bộ quyết định thiết kế vẫn phải bám vào code thật và phản hồi thật: hai tool tách riêng, `status_label` không đáng tin, output phải có lối ra rõ ràng cho từng nhánh, và người dùng cần hiểu vì sao bot bảo họ xem post cũ hay đăng post mới.

## Bài học từ case fail
Case làm mình nhớ nhất là `P-1007`: nhãn nhìn như đã solved nhưng thread thực ra vẫn đang thử tiếp. Nếu chỉ nhìn nhãn hoặc title, bot sẽ trả lời sai rất tự tin. Bài học của mình là thiết kế an toàn không nằm ở chỗ câu chữ đẹp, mà ở chỗ luôn ép hệ thống đọc dữ liệu thật trước khi kết luận.

Từ khảo sát Google Form, mình cũng thấy một điểm quan trọng: người dùng không chỉ cần "câu trả lời nhanh", họ cần biết câu trả lời đó có đáng tin hay không và nên làm gì tiếp. Vì vậy phần thiết kế phải ưu tiên nguồn, trace, confidence, và next step thay vì chỉ tối ưu cho câu trả lời nghe mượt.
