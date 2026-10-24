"""แบ่งเอกสารเป็น chunk พร้อม metadata (เวิร์กช็อป 1)

แต่ละ chunk เป็น dict ที่มีอย่างน้อย:
chunk_id ("<doc_id>#<ลำดับ>"), doc_id, title, section, status, effective_date, text
"""
from rag.ingest import load_docs

MAX_CHARS = 600


def _sections(body: str) -> list[tuple[str, str]]:
    """แยก body ตามบรรทัดที่ขึ้นต้นด้วย '## ' คืน [(ชื่อหัวข้อ, เนื้อหา)] ข้ามส่วนก่อนหัวข้อแรก (หัวเรื่อง #)"""
    sections, name, lines = [], None, []
    for line in body.splitlines():
        if line.startswith("## "):
            if name is not None:
                sections.append((name, "\n".join(lines).strip()))
            name, lines = line[3:].strip(), []
        elif name is not None:
            lines.append(line)
    if name is not None:
        sections.append((name, "\n".join(lines).strip()))
    return [(n, b) for n, b in sections if b]


def _split(text: str, max_chars: int) -> list[str]:
    """ตัดตามบรรทัดให้แต่ละท่อนไม่เกิน max_chars (บรรทัดที่ยาวเกินจะถูกตัดตามตัวอักษร)"""
    parts, cur = [], ""
    for line in text.splitlines():
        while len(line) > max_chars:
            if cur:
                parts.append(cur)
                cur = ""
            parts.append(line[:max_chars])
            line = line[max_chars:]
        if cur and len(cur) + 1 + len(line) > max_chars:
            parts.append(cur)
            cur = line
        else:
            cur = f"{cur}\n{line}" if cur else line
    if cur:
        parts.append(cur)
    return [p for p in parts if p.strip()]


def chunk_docs(docs: list[dict] | None = None, max_chars: int = MAX_CHARS) -> list[dict]:
    docs = load_docs() if docs is None else docs
    chunks = []
    for doc in docs:
        n = 0
        for section, body in _sections(doc["body"]):
            for text in _split(body, max_chars):
                n += 1
                chunks.append({
                    "chunk_id": f"{doc['doc_id']}#{n}",
                    "doc_id": doc["doc_id"],
                    "title": doc.get("title", ""),
                    "section": section,
                    "status": doc.get("status", ""),
                    "effective_date": doc.get("effective_date", ""),
                    "text": text,
                })
    return chunks


if __name__ == "__main__":
    cs = chunk_docs()
    print(len(cs), "chunks · ยาวสุด", max(len(c["text"]) for c in cs), "ตัวอักษร")
