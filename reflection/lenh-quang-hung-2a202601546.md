# Lệnh Quang Hưng - 2A202601546

## Vai trò
Kiểm thử, golden set, runner baseline, README glue.

## Phần mình làm
Mình dựng `eval/golden_set_v0.json`, `eval/run_eval.py`, `eval/README.md`, và phần hướng dẫn chạy baseline trong `codebase/README.md`. Mục tiêu của mình là biến ý tưởng "đo lượt đầu" thành artifact thật: có case, có pass/fail, có latency, có trace, có summary.

## AI hỗ trợ thế nào
AI hỗ trợ mình phác khung scorer và format report, nhưng rule chấm phải do mình tự đặt lại cho khớp đúng 4 nhánh của assistant. Mình đặc biệt chú ý để runner không giấu `warnings` hay `JSON repair`, vì cái đó là tín hiệu chất lượng chứ không phải lỗi phụ.

## Bài học từ case fail
Fail rõ nhất là lúc thử smoke run mà thiếu `OPENROUTER_API_KEY`, runner phải dừng sớm. Ban đầu đây là một thất bại nhỏ, nhưng nó dạy mình rằng baseline chỉ có giá trị khi chạy lại được và artifact sạch. Ngoài ra, case `OpenRouter 401` cũng nhắc nhóm rằng một quyết định sai ở lượt đầu có thể kéo lệch cả bộ đánh giá, nên quality bar phải chốt trước rồi mới đo.

