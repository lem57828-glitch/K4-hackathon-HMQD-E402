"""Mining evidence — Đường B (rubric R1).

Đếm hai thứ trên 1.261 câu hỏi thật của học viên trong chatlog VLearn tutor:

  1. CÂU HỎI LẶP — cụm câu hỏi gần trùng nhau do >=2 học viên KHÁC NHAU đặt.
     Đây là proxy đo được cho pain "câu hỏi đã có người hỏi rồi" ở khu hỏi đáp.
  2. PHÂN LOẠI INTENT — logistics / khái niệm / chào-hỏi-lạc-đề, để biết loại
     câu hỏi nào lặp nhiều nhất và loại nào sai thì đắt.

Chạy:  python evidence/mining/mine_chatlog.py            (in ra bảng)
       python evidence/mining/mine_chatlog.py --dump-clusters 25

Phương pháp (để người khác kiểm lại được — xem MINING-LOG.md §Phương pháp đếm):
  - Chỉ lấy dòng role == "student" (1.261 dòng).
  - Bỏ tiền tố ngữ cảnh do VLearn tự chèn: '(Trang N, đoạn được chọn: "...")'.
    Phần còn lại là chữ học viên tự gõ. Nếu sau khi bỏ tiền tố mà rỗng thì lấy
    lại chính đoạn bôi đen (học viên chỉ bôi đen mà không gõ gì).
  - Chuẩn hoá: bỏ dấu, lowercase, bỏ ký tự không phải chữ/số, bỏ stopword tiếng
    Việt, giữ token >= 2 ký tự.
  - Hai câu hỏi là "gần trùng" khi Jaccard(token_set) >= 0.60 và mỗi câu có
    >= 2 token sau chuẩn hoá. Gom bằng union-find.
  - Một cụm được tính là LẶP THẬT khi có >= 2 message và >= 2 user_id khác nhau
    (cùng một người hỏi lại 2 lần không phải bằng chứng cho "hỏi trùng người khác").
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = ROOT / "data" / "vlearn-pack" / "chatlog" / "chat_history_anonymized_for_hackathon.csv"

SIM_THRESHOLD = 0.60
MIN_TOKENS = 2

STOPWORDS = {
    "la", "va", "cua", "cho", "co", "khong", "duoc", "nay", "gi", "the", "nao",
    "minh", "ban", "toi", "em", "anh", "chi", "voi", "trong", "tren", "ve", "thi",
    "ma", "mot", "nhu", "de", "hay", "hoac", "nhung", "o", "a", "ta", "no", "ho",
    "can", "phai", "se", "da", "dang", "bi", "boi", "tu", "den", "ra", "vao",
    "giai", "thich", "doan", "boi", "den", "trang", "chon", "duoc", "sao", "vi",
    "tai", "lam", "biet", "hieu", "noi", "vay", "day", "kia", "roi", "nhe", "nha",
    "cai", "nhi", "cung", "hon", "rat", "qua", "lai", "moi", "them", "chut", "xin",
}

# Nhãn intent. Từ khoá 1 chữ khớp theo TOKEN (nguyên từ) để tránh bắt nhầm chữ
# nằm trong từ khác ("hi" trong "giải thích"). Từ khoá nhiều chữ khớp theo cụm.
INTENT_RULES: list[tuple[str, tuple[str, ...]]] = [
    (
        "logistics",
        (
            "deadline", "nop bai", "nop o dau", "link", "zoom", "meet", "may gio",
            "o dau", "o daau", "bai tap", "lab", "tai lieu", "form", "diem danh",
            "cham diem", "lich hoc", "buoi sau", "chieu nay", "nghi hoc", "the sinh vien",
            "phong to", "full man", "download", "tai ve", "han chot", "recording",
        ),
    ),
    (
        "chao_hoi_lac_de",
        (
            "hello", "heloo", "helo", "hi", "hii", "chao", "ban la ai", "ban la model",
            "dep trai", "xinh", "cam on", "thanks", "test", "haha", "ban ten gi",
            "may la ai", "ban co nguoi yeu",
        ),
    ),
]

# Template do VLearn sinh khi học viên bấm nút, không phải chữ học viên tự gõ.
TEMPLATE_CLICK = re.compile(r"^giai thich doan boi den o trang \d+", re.I)


def fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.lower())
    stripped = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return stripped.replace("đ", "d").replace("Đ", "d")


SELECTION_PREFIX = re.compile(r"^\(Trang\s+\d+,\s*đoạn được chọn:\s*(?P<sel>.*?)\)\s*", re.S)


def strip_selection(content: str) -> tuple[str, str]:
    """Bỏ tiền tố ngữ cảnh VLearn tự chèn.

    Trả về (text, source) với source ∈ {typed, template_click, selection_only}:
      - typed           : học viên tự gõ câu hỏi
      - template_click  : học viên bấm nút "Giải thích đoạn bôi đen" -> VLearn sinh câu
      - selection_only  : chỉ bôi đen, không gõ gì (text = đoạn bôi đen)
    Tách nhãn này ra vì cụm trùng của template_click chỉ chứng minh "nhiều người
    bôi đen cùng một đoạn slide", yếu hơn bằng chứng "nhiều người tự gõ cùng một câu".
    """
    raw = content.strip()
    match = SELECTION_PREFIX.match(raw)
    if not match:
        source = "template_click" if TEMPLATE_CLICK.match(fold(raw)) else "typed"
        return raw, source
    typed = raw[match.end():].strip()
    if not typed:
        return match.group("sel").strip().strip('"'), "selection_only"
    source = "template_click" if TEMPLATE_CLICK.match(fold(typed)) else "typed"
    return typed, source


def tokens(text: str) -> set[str]:
    folded = fold(text)
    raw = re.findall(r"[a-z0-9]+", folded)
    return {token for token in raw if len(token) >= 2 and token not in STOPWORDS}


def classify_intent(text: str) -> str:
    folded = fold(text)
    word_set = set(re.findall(r"[a-z0-9]+", folded))
    for label, keywords in INTENT_RULES:
        for keyword in keywords:
            if " " in keyword:
                if keyword in folded:
                    return label
            elif keyword in word_set:
                return label
    return "khai_niem"


class UnionFind:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))

    def find(self, node: int) -> int:
        while self.parent[node] != node:
            self.parent[node] = self.parent[self.parent[node]]
            node = self.parent[node]
        return node

    def union(self, left: int, right: int) -> None:
        root_left, root_right = self.find(left), self.find(right)
        if root_left != root_right:
            self.parent[root_right] = root_left


def jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def load_questions() -> list[dict]:
    with CSV_PATH.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    questions = []
    for row in rows:
        if row["role"] != "student":
            continue
        text, source = strip_selection(row["content"] or "")
        questions.append({
            "message_id": row["message_id"],
            "user_id": row["user_id"],
            "conversation_id": row["conversation_id"],
            "text": text,
            "source": source,
            "tokens": tokens(text),
            "intent": classify_intent(text),
        })
    return questions


def build_clusters(questions: list[dict]) -> list[list[int]]:
    """Gom cụm gần trùng. Chặn nến bằng inverted index trên token để khỏi so O(n^2) mù."""
    union = UnionFind(len(questions))
    postings: dict[str, list[int]] = defaultdict(list)
    for index, question in enumerate(questions):
        if len(question["tokens"]) < MIN_TOKENS:
            continue
        for token in question["tokens"]:
            postings[token].append(index)

    checked: set[tuple[int, int]] = set()
    for indices in postings.values():
        if len(indices) > 400:  # token quá phổ biến -> bỏ, không mang tin
            continue
        for position, left in enumerate(indices):
            for right in indices[position + 1:]:
                pair = (left, right)
                if pair in checked:
                    continue
                checked.add(pair)
                if jaccard(questions[left]["tokens"], questions[right]["tokens"]) >= SIM_THRESHOLD:
                    union.union(left, right)

    groups: dict[int, list[int]] = defaultdict(list)
    for index, question in enumerate(questions):
        if len(question["tokens"]) < MIN_TOKENS:
            continue
        groups[union.find(index)].append(index)
    return [members for members in groups.values() if len(members) >= 2]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dump-clusters", type=int, default=0, help="in N cụm lặp lớn nhất")
    args = parser.parse_args()

    questions = load_questions()
    clusters = build_clusters(questions)

    multi_user_clusters = []
    for members in clusters:
        users = {questions[index]["user_id"] for index in members}
        if len(users) >= 2:
            multi_user_clusters.append((members, users))

    total = len(questions)
    duplicated_messages = sum(len(members) for members, _ in multi_user_clusters)
    scorable = sum(1 for question in questions if len(question["tokens"]) >= MIN_TOKENS)

    source_counts: dict[str, int] = defaultdict(int)
    for question in questions:
        source_counts[question["source"]] += 1

    print(f"Tổng câu hỏi học viên (role=student)      : {total}")
    print("Nguồn câu hỏi                             : "
          + " · ".join(f"{label}={source_counts[label]}"
                       for label in ("typed", "template_click", "selection_only")))
    print(f"Câu hỏi đủ dài để so trùng (>= {MIN_TOKENS} token) : {scorable}")
    print(f"Cụm gần trùng (>=2 message)               : {len(clusters)}")
    print(f"Cụm lặp THẬT (>=2 user khác nhau)         : {len(multi_user_clusters)}")
    print(f"Message nằm trong cụm lặp thật            : {duplicated_messages}"
          f"  ({duplicated_messages / total:.1%} tổng câu hỏi)")

    # Bằng chứng lõi: chỉ tính cụm mà MỌI message đều do học viên tự gõ.
    typed_clusters = [
        (members, users) for members, users in multi_user_clusters
        if all(questions[index]["source"] == "typed" for index in members)
    ]
    typed_messages = sum(len(members) for members, _ in typed_clusters)
    typed_total = source_counts["typed"]
    print(f"  ├ trong đó cụm 100% tự gõ               : {len(typed_clusters)} cụm"
          f" · {typed_messages} message ({typed_messages / typed_total:.1%} câu tự gõ)")
    print(f"  └ cụm có message từ template/bôi đen    : {len(multi_user_clusters) - len(typed_clusters)} cụm")

    intent_all: dict[str, int] = defaultdict(int)
    for question in questions:
        intent_all[question["intent"]] += 1
    intent_dup: dict[str, int] = defaultdict(int)
    for members, _ in multi_user_clusters:
        for index in members:
            intent_dup[questions[index]["intent"]] += 1

    print("\nPhân loại intent (toàn bộ / trong cụm lặp thật):")
    for label in ("khai_niem", "logistics", "chao_hoi_lac_de"):
        share = intent_dup[label] / intent_all[label] if intent_all[label] else 0
        print(f"  {label:18s} {intent_all[label]:5d} / {intent_dup[label]:5d}"
              f"   ({share:.1%} câu loại này bị hỏi lặp)")

    if args.dump_clusters:
        ranked = sorted(multi_user_clusters, key=lambda item: len(item[0]), reverse=True)
        print(f"\n=== {args.dump_clusters} cụm lặp lớn nhất ===")
        for rank, (members, users) in enumerate(ranked[: args.dump_clusters], start=1):
            sources = {questions[index]["source"] for index in members}
            print(f"\n[Cụm {rank}] {len(members)} message · {len(users)} user"
                  f" · intent={questions[members[0]]['intent']} · source={'+'.join(sorted(sources))}")
            for index in members[:6]:
                question = questions[index]
                snippet = " ".join(question["text"].split())[:110]
                print(f"   {question['message_id']} {question['user_id']} | {snippet}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
