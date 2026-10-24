"""ค้นคืน chunk ที่เกี่ยวข้องกับคำถาม (เวิร์กช็อป 2 และ 4) ทำงานในเครื่องทั้งหมด ไม่เรียก API

python -m rag.retrieve "คำถาม" -k 4 [--method tfidf|hybrid] [--include-superseded] [--json]
"""
import argparse
import json

import numpy as np
from pythainlp.tokenize import word_tokenize
from rank_bm25 import BM25Okapi
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from rag.chunk import chunk_docs


# คำพ้อง/คำเรียกอื่นที่ได้จากคำถามที่พลาดในชุด dev เท่านั้น (Q31 ลืมรหัสผ่าน, Q35 ชาร์จรถอีวี)
# ใช้ขยายคำค้นของ method="hybrid": ถ้าคำค้นมี key ให้ต่อท้ายด้วยคำในเอกสารที่หมายถึงสิ่งเดียวกัน
SYNONYMS = {
    "อีวี": ["รถยนต์ไฟฟ้า", "จุดชาร์จ", "ที่จอดรถ"],
    "ชาร์จรถ": ["รถยนต์ไฟฟ้า", "จุดชาร์จ", "ที่จอดรถ"],
    "ลืมรหัสผ่าน": ["รีเซ็ต", "Self-Service Password"],
}

# น้ำหนักของ TF-IDF ตัวอักษร ส่วนที่เหลือเป็น BM25 (เลือกจากชุด dev)
HYBRID_ALPHA = 0.7


def expand_query(query: str) -> str:
    extra = [w for key, words in SYNONYMS.items() if key in query for w in words]
    return f"{query} {' '.join(extra)}" if extra else query


def tokenize(text: str) -> list[str]:
    """ตัดคำด้วย pythainlp (newmm) ทิ้งช่องว่างและเครื่องหมาย เก็บตัวอักษร/ตัวเลข"""
    return [t.lower() for t in word_tokenize(text, engine="newmm") if any(ch.isalnum() for ch in t)]


def _norm(x: np.ndarray) -> np.ndarray:
    top = x.max()
    return x / top if top > 0 else x


class Retriever:
    def __init__(self, chunks: list[dict] | None = None, method: str = "tfidf"):
        """method="tfidf": TF-IDF ระดับตัวอักษร (W2) · method="hybrid": วิธีที่ปรับปรุงแล้ว (W4)"""
        if method not in ("tfidf", "hybrid"):
            raise ValueError(f"unknown method: {method}")
        self.method = method
        self.chunks = chunk_docs() if chunks is None else chunks
        # ภาษาไทยไม่เว้นวรรคระหว่างคำ จึงใช้ n-gram ระดับตัวอักษรแทนการตัดคำ
        self.vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))
        self.matrix = self.vectorizer.fit_transform(
            f"{c['title']} {c['section']} {c['text']}" for c in self.chunks
        )
        if method == "hybrid":
            self.bm25 = BM25Okapi([tokenize(f"{c['title']} {c['section']} {c['text']}") for c in self.chunks])

    def search(self, query: str, k: int = 4, include_superseded: bool = True) -> list[dict]:
        """คืน chunk k อันที่คะแนนสูงสุด เรียงจากมากไปน้อย แต่ละอันเพิ่มช่อง "score" """
        if self.method == "hybrid":
            query = expand_query(query)
        scores = cosine_similarity(self.vectorizer.transform([query]), self.matrix)[0]
        if self.method == "hybrid":
            bm25 = np.asarray(self.bm25.get_scores(tokenize(query)), dtype=float)
            scores = HYBRID_ALPHA * _norm(scores) + (1 - HYBRID_ALPHA) * _norm(np.clip(bm25, 0, None))
        order = np.argsort(-scores, kind="stable")
        results = []
        for i in order:
            chunk = self.chunks[i]
            if not include_superseded and chunk["status"] != "active":
                continue
            results.append({**chunk, "score": float(scores[i])})
            if len(results) == k:
                break
        return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("-k", type=int, default=4)
    ap.add_argument("--method", default="tfidf", choices=["tfidf", "hybrid"])
    ap.add_argument("--include-superseded", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    res = Retriever(method=a.method).search(a.query, a.k, a.include_superseded)
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return
    for r in res:
        print(f"[{r['score']:.3f}] {r['chunk_id']} · {r['title']} › {r['section']} ({r['status']})")
        print("   " + r["text"].replace("\n", " ")[:160])


if __name__ == "__main__":
    main()
