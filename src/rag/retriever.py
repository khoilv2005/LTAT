import math
from collections import Counter, defaultdict

import numpy as np

from .utils import tokenize


class BM25Retriever:
    def __init__(self, k1=1.5, b=0.75):
        self.k1 = k1
        self.b = b
        self.docs = []
        self.doc_len = []
        self.avgdl = 0.0
        self.idf = {}
        self.inverted = defaultdict(list)

    def fit(self, docs):
        self.docs = list(docs)
        self.doc_len = []
        df = Counter()
        term_counts = []

        for idx, doc in enumerate(self.docs):
            counts = Counter(tokenize(doc.text))
            term_counts.append(counts)
            length = sum(counts.values())
            self.doc_len.append(length)
            for term in counts:
                df[term] += 1

        total_docs = len(self.docs)
        self.avgdl = sum(self.doc_len) / total_docs if total_docs else 0.0
        self.idf = {
            term: math.log(1 + (total_docs - freq + 0.5) / (freq + 0.5))
            for term, freq in df.items()
        }

        for idx, counts in enumerate(term_counts):
            for term, tf in counts.items():
                self.inverted[term].append((idx, tf))
        return self

    def search(self, query, top_k=5, label=None, exclude_ids=None, max_query_terms=None):
        exclude_ids = {str(item) for item in (exclude_ids or set())}
        query_terms = Counter(tokenize(query))
        if max_query_terms and len(query_terms) > max_query_terms:
            ranked_terms = sorted(
                query_terms.items(),
                key=lambda item: self.idf.get(item[0], 0.0) * item[1],
                reverse=True,
            )
            query_terms = Counter(dict(ranked_terms[:max_query_terms]))
        scores = defaultdict(float)

        for term, qtf in query_terms.items():
            postings = self.inverted.get(term)
            if not postings:
                continue
            idf = self.idf.get(term, 0.0)
            for idx, tf in postings:
                doc = self.docs[idx]
                if label and doc.label != label:
                    continue
                if doc.doc_id in exclude_ids:
                    continue
                dl = self.doc_len[idx] or 1
                denom = tf + self.k1 * (1 - self.b + self.b * dl / (self.avgdl or 1))
                scores[idx] += idf * ((tf * (self.k1 + 1)) / denom) * qtf

        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        return [(self.docs[idx], score) for idx, score in ranked[:top_k]]

    def search_label_balanced(self, query, top_k_per_label=3, labels=None, exclude_ids=None, max_query_terms=None):
        labels = labels or ["ACK", "NAK"]
        return {
            label: self.search(
                query,
                top_k=top_k_per_label,
                label=label,
                exclude_ids=exclude_ids,
                max_query_terms=max_query_terms,
            )
            for label in labels
        }


class TfidfRetriever:
    def __init__(self, max_features=120000):
        self.max_features = max_features
        self.docs = []
        self.vectorizer = None
        self.matrix = None
        self.label_indices = {}

    def fit(self, docs):
        from sklearn.feature_extraction.text import TfidfVectorizer

        self.docs = list(docs)
        self.vectorizer = TfidfVectorizer(
            lowercase=True,
            token_pattern=r"(?u)\b[A-Za-z_][A-Za-z0-9_]{1,}\b|\b\d+\b",
            max_features=self.max_features,
            sublinear_tf=True,
            norm="l2",
        )
        self.matrix = self.vectorizer.fit_transform([doc.text for doc in self.docs])
        label_indices = defaultdict(list)
        for idx, doc in enumerate(self.docs):
            label_indices[doc.label].append(idx)
        self.label_indices = {
            label: np.array(indices, dtype=np.int32)
            for label, indices in label_indices.items()
        }
        return self

    def search(self, query, top_k=5, label=None, exclude_ids=None, max_query_terms=None):
        exclude_ids = {str(item) for item in (exclude_ids or set())}
        if max_query_terms:
            terms = Counter(tokenize(query))
            if len(terms) > max_query_terms:
                keep = {term for term, _ in terms.most_common(max_query_terms)}
                query = " ".join(token for token in tokenize(query) if token in keep)

        query_vec = self.vectorizer.transform([query])
        if label:
            candidate_indices = self.label_indices.get(label, np.array([], dtype=np.int32))
        else:
            candidate_indices = np.arange(len(self.docs), dtype=np.int32)
        if candidate_indices.size == 0:
            return []

        scores = (self.matrix[candidate_indices] @ query_vec.T).toarray().ravel()
        if scores.size == 0:
            return []

        top_n = min(top_k + len(exclude_ids), scores.size)
        top_positions = np.argpartition(scores, -top_n)[-top_n:]
        top_positions = top_positions[np.argsort(scores[top_positions])[::-1]]

        results = []
        for pos in top_positions:
            doc_idx = int(candidate_indices[pos])
            doc = self.docs[doc_idx]
            if doc.doc_id in exclude_ids:
                continue
            results.append((doc, float(scores[pos])))
            if len(results) >= top_k:
                break
        return results

    def search_label_balanced(self, query, top_k_per_label=3, labels=None, exclude_ids=None, max_query_terms=None):
        labels = labels or ["ACK", "NAK"]
        return {
            label: self.search(
                query,
                top_k=top_k_per_label,
                label=label,
                exclude_ids=exclude_ids,
                max_query_terms=max_query_terms,
            )
            for label in labels
        }
