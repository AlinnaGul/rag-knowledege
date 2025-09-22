from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union
import logging
import math
import re
import json

import chromadb
import networkx as nx

from api.config import settings
from rag.embeddings import get_embedder
from rag.reranker import rerank

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

# ======================================================================================
# Multi-Modal Model Imports
# ======================================================================================
try:
    from transformers import (
        AutoTokenizer, AutoModelForSequenceClassification,
        T5ForConditionalGeneration, T5Tokenizer,
        DistilBertTokenizer, DistilBertForSequenceClassification
    )
    import torch
    _TRANSFORMERS_AVAILABLE = True
except ImportError:
    _TRANSFORMERS_AVAILABLE = False
    logger.warning("Transformers not available - multi-modal features disabled")

try:
    import pandas as pd
    import matplotlib.pyplot as plt
    import seaborn as sns
    import plotly.graph_objects as go
    import plotly.express as px
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.ensemble import RandomForestRegressor
    _ML_CHART_AVAILABLE = True
except ImportError:
    _ML_CHART_AVAILABLE = False
    logger.warning("ML/Visualization libraries not available - chart generation disabled")

# ======================================================================================
# DSPy (optional)
# ======================================================================================
import os

_DSPY_AVAILABLE = False
if os.getenv("DSPY_DISABLED", "").lower() not in ("1", "true", "yes"):
    try:
        from dspy import Signature, InputField, OutputField, Module, Predict  # type: ignore
        _DSPY_AVAILABLE = True
    except Exception:
        _DSPY_AVAILABLE = False

if _DSPY_AVAILABLE:
    class StrategySig(Signature):  # type: ignore
        """Pick the best retrieval strategy for this question.
        Choose one of: vector_only, bm25_only, hybrid, query_expansion, graph_enhanced.
        """
        question = InputField(desc="Original user question")
        strategy = OutputField(desc="One of: vector_only | bm25_only | hybrid | query_expansion | graph_enhanced")

    class ExpandSig(Signature):  # type: ignore
        """Expand the query into 2–5 sub-queries (comma-separated)."""
        question = InputField(desc="Original user question")
        expansions = OutputField(desc="Comma-separated 2–5 expansions")

    class DSPyStrategySelector(Module):  # type: ignore
        def __init__(self):
            super().__init__()
            self.pred = Predict(StrategySig)

        def forward(self, question: str) -> str:
            out = self.pred(question=question)
            val = (getattr(out, "strategy", "") or "").strip().lower()
            allowed = {"vector_only", "bm25_only", "hybrid", "query_expansion", "graph_enhanced"}
            return val if val in allowed else "hybrid"

    class DSPyQueryExpander(Module):  # type: ignore
        def __init__(self):
            super().__init__()
            self.pred = Predict(ExpandSig)

        def forward(self, question: str, k: int = 4) -> list[str]:
            out = self.pred(question=question)
            raw = (getattr(out, "expansions", "") or "").strip()
            items = [x.strip() for x in raw.split(",") if x.strip()]
            seen, uniq = set(), []
            for s in items:
                if s.lower() not in seen:
                    seen.add(s.lower())
                    uniq.append(s)
                if len(uniq) >= k:
                    break
            return uniq

# ======================================================================================
# Multi-Modal Output Types
# ======================================================================================

class OutputMode(Enum):
    TEXT = "text"
    TABLE = "table"
    CHART = "chart"
    COMPARISON = "comparison"
    MIXED = "mixed"

class ChartType(Enum):
    BAR = "bar"
    LINE = "line"
    SCATTER = "scatter"
    PIE = "pie"
    HEATMAP = "heatmap"
    HISTOGRAM = "histogram"

# ======================================================================================
# Data models
# ======================================================================================

class RetrievalStrategy(Enum):
    VECTOR_ONLY = "vector_only"
    BM25_ONLY = "bm25_only"
    HYBRID = "hybrid"
    QUERY_EXPANSION = "query_expansion"
    GRAPH_ENHANCED = "graph_enhanced"
    ADAPTIVE = "adaptive"

@dataclass
class MultiModalConfig:
    """Configuration for multi-modal outputs"""
    output_mode: OutputMode = OutputMode.TEXT
    chart_type: Optional[ChartType] = None
    table_max_rows: int = 50
    table_max_cols: int = 10
    chart_width: int = 800
    chart_height: int = 600
    use_query_router: bool = True
    force_model_type: Optional[str] = None  # "table", "chart", "text"

@dataclass
class RetrievalConfig:
    strategy: RetrievalStrategy = RetrievalStrategy.ADAPTIVE
    k: int = 8
    lambda_mult: Optional[float] = 0.5
    fetch_multiplier: int = 3
    use_mmr: bool = True
    use_reranker: bool = True
    query_expansion_factor: int = 3
    graph_depth: int = 2
    # Multi-modal settings
    multimodal: MultiModalConfig = field(default_factory=MultiModalConfig)

@dataclass
class RetrievalResult:
    text: str
    metadata: Dict[str, Any]
    score: float
    retrieval_method: str
    expanded_queries: List[str] = field(default_factory=list)
    graph_path: List[str] = field(default_factory=list)
    # Multi-modal additions
    output_mode: OutputMode = OutputMode.TEXT
    generated_table: Optional[str] = None  # JSON or HTML table
    generated_chart: Optional[Dict[str, Any]] = None  # Chart config/data
    model_used: Optional[str] = None

# ======================================================================================
# Multi-Modal Model Manager
# ======================================================================================

class MultiModalManager:
    """Manages different models for different output types"""
    
    def __init__(self):
        self.query_router = None
        self.table_generator = None
        self.chart_pipeline = None
        self._setup_models()
    
    def _setup_models(self):
        """Initialize all multi-modal models"""
        if not _TRANSFORMERS_AVAILABLE:
            logger.warning("Transformers not available - using fallback routing")
            return
            
        try:
            # DistilBERT for query routing/classification
            self.router_tokenizer = DistilBertTokenizer.from_pretrained('distilbert-base-uncased')
            self.query_router = DistilBertForSequenceClassification.from_pretrained(
                'distilbert-base-uncased',
                num_labels=4  # text, table, chart, comparison
            )
            
            # Google Flan-T5 for table generation
            self.table_tokenizer = T5Tokenizer.from_pretrained('google/flan-t5-base')
            self.table_generator = T5ForConditionalGeneration.from_pretrained('google/flan-t5-base')
            
            logger.info("Multi-modal models loaded successfully")
            
        except Exception as e:
            logger.error(f"Failed to load multi-modal models: {e}")
            self.query_router = None
            self.table_generator = None
    
    def _setup_chart_pipeline(self):
        """Setup custom ML pipeline for chart generation"""
        if not _ML_CHART_AVAILABLE:
            return None
            
        try:
            # Custom ML pipeline for chart data processing
            self.chart_pipeline = Pipeline([
                ('scaler', StandardScaler()),
                ('model', RandomForestRegressor(n_estimators=100, random_state=42))
            ])
            return True
        except Exception as e:
            logger.error(f"Failed to setup chart pipeline: {e}")
            return False
    
    def route_query(self, query: str) -> OutputMode:
        """Route query to appropriate output mode using DistilBERT"""
        if not self.query_router:
            return self._heuristic_routing(query)
        
        try:
            # Tokenize and classify
            inputs = self.router_tokenizer(query, return_tensors="pt", truncation=True, padding=True)
            
            with torch.no_grad():
                outputs = self.query_router(**inputs)
                predictions = torch.nn.functional.softmax(outputs.logits, dim=-1)
                predicted_class = torch.argmax(predictions, dim=-1).item()
            
            # Map prediction to output mode
            mode_mapping = {
                0: OutputMode.TEXT,
                1: OutputMode.TABLE, 
                2: OutputMode.CHART,
                3: OutputMode.COMPARISON
            }
            
            return mode_mapping.get(predicted_class, OutputMode.TEXT)
            
        except Exception as e:
            logger.error(f"Query routing failed: {e}")
            return self._heuristic_routing(query)
    
    def _heuristic_routing(self, query: str) -> OutputMode:
        """Fallback heuristic routing when models not available"""
        query_lower = query.lower()
        
        # Table indicators
        if any(word in query_lower for word in [
            'table', 'list', 'compare', 'comparison', 'vs', 'versus', 
            'different', 'contrast', 'summary', 'overview'
        ]):
            if any(word in query_lower for word in ['compare', 'comparison', 'vs', 'versus']):
                return OutputMode.COMPARISON
            return OutputMode.TABLE
        
        # Chart indicators  
        if any(word in query_lower for word in [
            'chart', 'graph', 'plot', 'visualize', 'trend', 'pattern',
            'distribution', 'correlation', 'show me', 'display'
        ]):
            return OutputMode.CHART
            
        return OutputMode.TEXT
    
    def generate_table(self, query: str, context: str, config: MultiModalConfig) -> Optional[str]:
        """Generate table using Flan-T5"""
        if not self.table_generator:
            return self._fallback_table_generation(context, config, query=query)

        
        try:
            # Construct prompt for table generation
            prompt = f"""Generate a structured table based on this query and context:
Query: {query}
Context: {context}
Format the response as a JSON table with headers and rows.
Max {config.table_max_rows} rows and {config.table_max_cols} columns.
"""
            
            inputs = self.table_tokenizer.encode(prompt, return_tensors="pt", truncation=True)
            
            with torch.no_grad():
                outputs = self.table_generator.generate(
                    inputs, 
                    max_length=512,
                    num_beams=4,
                    early_stopping=True,
                    temperature=0.7
                )
            
            generated_text = self.table_tokenizer.decode(outputs[0], skip_special_tokens=True)
            
            # Try to parse as structured data
            return self._format_table_output(generated_text, config)
            
        except Exception as e:
            logger.error(f"Table generation failed: {e}")
            return self._fallback_table_generation(context, config)
    
    def generate_chart(self, query: str, context: str, config: MultiModalConfig) -> Optional[Dict[str, Any]]:
        """Generate chart using custom ML pipeline"""
        if not _ML_CHART_AVAILABLE:
            return None
            
        try:
            # Extract data patterns from context
            data_points = self._extract_numerical_data(context)
            
            if not data_points:
                return None
            
            # Determine chart type
            chart_type = config.chart_type or self._infer_chart_type(query, data_points)
            
            # Generate chart configuration
            chart_config = {
                "type": chart_type.value,
                "data": data_points,
                "config": {
                    "width": config.chart_width,
                    "height": config.chart_height,
                    "title": self._generate_chart_title(query),
                    "responsive": True
                }
            }
            
            return chart_config
            
        except Exception as e:
            logger.error(f"Chart generation failed: {e}")
            return None
    
    def _extract_numerical_data(self, context: str) -> List[Dict[str, Any]]:
        """Extract numerical data from context for charting"""
        data_points = []
        
        # Simple regex-based extraction (can be enhanced)
        number_pattern = r'(\b\d+\.?\d*\b)'
        numbers = re.findall(number_pattern, context)
        
        # Extract potential labels/categories
        sentences = context.split('.')
        
        for i, sentence in enumerate(sentences[:10]):  # Limit to 10 data points
            nums_in_sentence = re.findall(number_pattern, sentence)
            if nums_in_sentence:
                try:
                    value = float(nums_in_sentence[0])
                    label = sentence.split(':')[0].strip()[:50]  # First part as label
                    data_points.append({
                        "label": label or f"Item {i+1}",
                        "value": value,
                        "category": "data"
                    })
                except ValueError:
                    continue
        
        return data_points[:20]  # Limit data points
    
    def _infer_chart_type(self, query: str, data_points: List[Dict]) -> ChartType:
        """Infer appropriate chart type based on query and data"""
        query_lower = query.lower()
        
        if 'trend' in query_lower or 'over time' in query_lower:
            return ChartType.LINE
        elif 'distribution' in query_lower or 'histogram' in query_lower:
            return ChartType.HISTOGRAM
        elif 'correlation' in query_lower or 'scatter' in query_lower:
            return ChartType.SCATTER
        elif 'proportion' in query_lower or 'percentage' in query_lower:
            return ChartType.PIE
        elif len(data_points) > 10:
            return ChartType.HEATMAP
        else:
            return ChartType.BAR
    
    def _generate_chart_title(self, query: str) -> str:
        """Generate appropriate chart title from query"""
        # Simple title generation
        words = query.split()[:8]  # First 8 words
        title = ' '.join(words).title()
        return title if len(title) < 100 else f"{title[:97]}..."
    
    def _fallback_table_generation(self, context: str, config: MultiModalConfig) -> str | None:
        lines = (context or "").splitlines()
        rows = []
        seen_pairs = set()
        for line in lines:
            if ":" not in line:
                continue
            key, val = line.split(":", 1)
            key = key.strip()
            val = val.strip()
            if not key or not val:
                continue
            norm_pair = (key.lower(), re.sub(r"\s+", " ", val.lower()))
            if norm_pair in seen_pairs:
                continue
            seen_pairs.add(norm_pair)
            rows.append([key, val])
            if len(rows) >= max(1, config.table_max_rows):
                break

        if not rows:
            return None

        return json.dumps({"headers": ["Key", "Value"], "rows": rows}, indent=2)

    def _format_table_output(self, generated_text: str, config: MultiModalConfig) -> str:
        """Format generated table text into structured format"""
        try:
            # Try to parse if it's already JSON
            if generated_text.strip().startswith('{'):
                json.loads(generated_text)  # Validate JSON
                return generated_text
        except json.JSONDecodeError:
            pass
        
        # Convert text to table format
        lines = generated_text.split('\n')
        table_data = []
        
        for line in lines:
            if '|' in line:  # Markdown table format
                cells = [cell.strip() for cell in line.split('|') if cell.strip()]
                if cells:
                    table_data.append(cells)
        
        if table_data:
            headers = table_data[0] if table_data else ["Column 1", "Column 2"]
            rows = table_data[1:config.table_max_rows] if len(table_data) > 1 else []
            
            return json.dumps({
                "headers": headers,
                "rows": rows
            }, indent=2)
        
        return None

# ======================================================================================
# Chroma helpers (kept for API compatibility)
# ======================================================================================

def get_chroma_client() -> chromadb.PersistentClient:
    """Global Chroma client using the legacy path."""
    return chromadb.PersistentClient(path=settings.chroma_persist_dir)

def get_collection_client(collection_id: int) -> chromadb.PersistentClient:
    """Chroma client scoped to a specific collection directory."""
    base = Path(settings.chroma_persist_dir) / f"coll_{collection_id}"
    base.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(base))

# ======================================================================================
# Utilities: similarity, rank fusion, MMR
# ======================================================================================

_DEF_EPS = 1e-12

def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    num = sum(x * y for x, y in zip(a, b))
    da = math.sqrt(sum(x * x for x in a))
    db = math.sqrt(sum(y * y for y in b))
    return num / (da * db + _DEF_EPS)

def _rrf(rank_lists: List[List[str]], k: int = 60) -> Dict[str, float]:
    scores: Dict[str, float] = {}
    for lst in rank_lists:
        for rank, id_ in enumerate(lst):
            scores[id_] = scores.get(id_, 0.0) + 1.0 / (k + rank + 1)
    return scores

def _mmr(
    query_vec: Sequence[float],
    cand_vecs: List[Sequence[float]],
    cand_scores: List[float],
    k: int,
    lambda_mult: float = 0.5,
) -> List[int]:
    """Greedy MMR."""
    n = len(cand_vecs)
    if k <= 0 or n == 0:
        return []
    k = min(k, n)

    def _tolist(v):
        try:
            return v.tolist()
        except Exception:
            return list(v)

    cand_vecs = [_tolist(v) for v in cand_vecs]

    selected: List[int] = []
    remaining = list(range(n))

    first = max(remaining, key=lambda i: cand_scores[i])
    selected.append(first)
    remaining.remove(first)

    while len(selected) < k and remaining:
        best_i = None
        best_val = float("-inf")
        for i in remaining:
            rel = cand_scores[i]
            div = 0.0
            for j in selected:
                div = max(div, _cosine(cand_vecs[i], cand_vecs[j]))
            val = lambda_mult * rel - (1.0 - lambda_mult) * div
            if val > best_val:
                best_val = val
                best_i = i
        if best_i is not None:
            selected.append(best_i)
            remaining.remove(best_i)

    return selected

# ======================================================================================
# Query expansion (heuristic)
# ======================================================================================

class QueryExpander:
    """Lightweight expander; DSPy expander (if present) may override/augment."""
    def expand(self, query: str, max_variants: int = 5) -> List[str]:
        variations = [
            query,
            f"What is {query}?",
            f"Explain {query}",
            f"Guidance for {query}",
            f"Procedures about {query}",
        ]
        words = query.split()
        if len(words) > 1:
            variations.extend([" ".join(words[:i+1]) for i in range(len(words)-1)])
            variations.extend([" ".join(words[i:]) for i in range(1, len(words))])
        # uniq, keep order
        seen = set()
        out = []
        for v in variations:
            l = v.lower()
            if l not in seen:
                seen.add(l)
                out.append(v)
            if len(out) >= max_variants:
                break
        return out

# ======================================================================================
# Knowledge graph (simple)
# ======================================================================================

class KnowledgeGraph:
    def __init__(self):
        self.graph = nx.Graph()
        self._entity_cache: Dict[str, str] = {}
        self._init_sample()

    def _init_sample(self):
        entities = [
            ("Python", {"type": "programming_language"}),
            ("Machine Learning", {"type": "field"}),
            ("Data Science", {"type": "field"}),
            ("Neural Networks", {"type": "technique"}),
            ("Statistics", {"type": "field"}),
        ]
        for e, m in entities:
            self.add_entity(e, m)
        rels = [
            ("Python", "Machine Learning", "used_for", 0.9),
            ("Data Science", "Statistics", "uses", 0.9),
            ("Machine Learning", "Neural Networks", "includes", 0.8),
            ("Data Science", "Python", "uses", 0.8),
        ]
        for a, b, r, w in rels:
            self.add_relation(a, b, r, w)

    def add_entity(self, entity: str, metadata: Dict[str, Any]):
        self.graph.add_node(entity, **metadata)
        self._entity_cache[entity.lower()] = entity

    def add_relation(self, e1: str, e2: str, relation: str, weight: float = 1.0):
        self.graph.add_edge(e1, e2, relation=relation, weight=weight)

    def extract_entities_from_text(self, text: str) -> List[str]:
        # naive caps + cache match
        ents = re.findall(r'\b[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*\b', text)
        low = text.lower()
        for k, v in self._entity_cache.items():
            if k in low:
                ents.append(v)
        # uniq
        return list(dict.fromkeys(ents))

    def related(self, entity: str, depth: int = 2) -> List[Tuple[str, float]]:
        if entity not in self.graph:
            entity = self._entity_cache.get(entity.lower()) or entity
            if entity not in self.graph:
                return []
        related: Dict[str, float] = {}
        for neighbor in nx.single_source_shortest_path_length(self.graph, entity, cutoff=depth):
            if neighbor == entity:
                continue
            # accumulate simple weight heuristic
            path = nx.shortest_path(self.graph, entity, neighbor)
            score = 1.0
            for i in range(len(path) - 1):
                w = self.graph.get_edge_data(path[i], path[i+1]).get("weight", 1.0)
                score *= (0.8 ** i) * w
            related[neighbor] = max(related.get(neighbor, 0.0), score)
        return sorted(related.items(), key=lambda x: x[1], reverse=True)

# ======================================================================================
# Multi-Modal Retriever
# ======================================================================================

class NonLinearRetriever:
    """Non-linear retriever with optional DSPy and multi-modal capabilities."""

    def __init__(self):
        self.embedder = get_embedder()
        self.query_expander = QueryExpander()
        self.kg = KnowledgeGraph()
        self.multimodal_manager = MultiModalManager()
        
        # Optional DSPy modules
        self._dspy_strategy = DSPyStrategySelector() if _DSPY_AVAILABLE else None
        self._dspy_expander = DSPyQueryExpander() if _DSPY_AVAILABLE else None

    # ---------------- Core public API with Multi-Modal support ----------------

    def search(
        self,
        query: str,
        config: RetrievalConfig | None = None,
        allowed_collections: Optional[List[int]] = None,
        *,
        expansion_log_path: Optional[Path] = None,
    ) -> List[RetrievalResult]:
        if not allowed_collections:
            return []
        cfg = config or RetrievalConfig()
        n_results = max(cfg.k * cfg.fetch_multiplier, cfg.k)

        # Determine output mode using query router
        if cfg.multimodal.use_query_router and not cfg.multimodal.force_model_type:
            output_mode = self.multimodal_manager.route_query(query)
            cfg.multimodal.output_mode = output_mode
        elif cfg.multimodal.force_model_type:
            mode_mapping = {
                "table": OutputMode.TABLE,
                "chart": OutputMode.CHART, 
                "text": OutputMode.TEXT,
                "comparison": OutputMode.COMPARISON
            }
            cfg.multimodal.output_mode = mode_mapping.get(
                cfg.multimodal.force_model_type, OutputMode.TEXT
            )

        # Decide retrieval strategy
        strategy = cfg.strategy
        if strategy == RetrievalStrategy.ADAPTIVE:
            strategy = self._pick_strategy(query)

        hits: List[Dict[str, Any]] = []
        used_expansions: List[str] = []

        if strategy == RetrievalStrategy.VECTOR_ONLY:
            hits = self._vector_search(query, allowed_collections, n_results)

        elif strategy == RetrievalStrategy.BM25_ONLY:
            hits = self._bm25_search(query, allowed_collections, n_results)

        elif strategy == RetrievalStrategy.HYBRID:
            vec = self._vector_search(query, allowed_collections, n_results)
            bm = self._bm25_search(query, allowed_collections, n_results)
            hits = self._fuse(vec, bm)

        elif strategy == RetrievalStrategy.QUERY_EXPANSION:
            expansions = self._expand_query(query, cfg.query_expansion_factor)
            used_expansions = expansions[:]
            per_q = max(1, n_results // max(1, len(expansions)))
            all_hits: List[Dict[str, Any]] = []
            for q in expansions:
                vec = self._vector_search(q, allowed_collections, per_q)
                bm = self._bm25_search(q, allowed_collections, per_q)
                fused = self._fuse(vec, bm)
                for h in fused:
                    h["method"] = "query_expansion"
                    h.setdefault("expanded_queries", []).append(q)
                all_hits.extend(fused)
            hits = all_hits

        elif strategy == RetrievalStrategy.GRAPH_ENHANCED:
            entities = self.kg.extract_entities_from_text(query)
            expansions = [query]
            for e in entities:
                for rel, _score in self.kg.related(e, cfg.graph_depth):
                    expansions.append(f"{query} {rel}")
            # keep unique
            seen = set()
            uniq = []
            for s in expansions:
                if s.lower() not in seen:
                    seen.add(s.lower())
                    uniq.append(s)
            used_expansions = uniq[:]
            per_q = max(1, n_results // max(1, len(uniq)))
            all_hits = []
            for q in uniq:
                vec = self._vector_search(q, allowed_collections, per_q)
                bm = self._bm25_search(q, allowed_collections, per_q)
                fused = self._fuse(vec, bm)
                for h in fused:
                    h["method"] = "graph_enhanced"
                    h.setdefault("expanded_queries", []).append(q)
                all_hits.extend(fused)
            hits = all_hits

        # Deduplicate & ensure embeddings
        hits = self._dedupe_and_embed(hits, query)

        # Rerank (neural) if enabled
        if cfg.use_reranker and settings.use_reranker:
            hits = self._apply_rerank(query, hits)

        # Diversity via MMR
        if cfg.use_mmr and cfg.lambda_mult is not None:
            hits = self._apply_mmr(query, hits, cfg)

        # Generate multi-modal content
        context = "\n".join([h["text"] for h in hits[:cfg.k]])
        
        # Build results with multi-modal enhancements
        results: List[RetrievalResult] = []
        for h in hits[:cfg.k]:
            result = RetrievalResult(
                text=h["text"],
                metadata=h.get("metadata", {}),
                score=float(h.get("final_score", h.get("score", 0.0))),
                retrieval_method=h.get("method", strategy.value),
                expanded_queries=h.get("expanded_queries", []),
                graph_path=h.get("graph_path", []),
                output_mode=cfg.multimodal.output_mode,
            )
            
            # Generate multi-modal content for first result only (to avoid redundancy)
            if len(results) == 0:  # Only for the first/primary result
                if cfg.multimodal.output_mode == OutputMode.TABLE:
                    result.generated_table = self.multimodal_manager.generate_table(
                        query, context, cfg.multimodal
                    )
                    result.model_used = "google/flan-t5-base"
                    
                elif cfg.multimodal.output_mode == OutputMode.CHART:
                    result.generated_chart = self.multimodal_manager.generate_chart(
                        query, context, cfg.multimodal
                    )
                    result.model_used = "custom_ml_pipeline"
                    
                elif cfg.multimodal.output_mode == OutputMode.COMPARISON:
                    # Generate both table and simple chart for comparison
                    result.generated_table = self.multimodal_manager.generate_table(
                        query, context, cfg.multimodal
                    )
                    result.generated_chart = self.multimodal_manager.generate_chart(
                        query, context, cfg.multimodal
                    )
                    result.model_used = "flan-t5-base + ml_pipeline"
                    
                else:  # TEXT mode
                    result.model_used = "text_retrieval"
            
            results.append(result)

        # Optional: persist expansions for offline audit
        if expansion_log_path and used_expansions:
            try:
                expansion_log_path.parent.mkdir(parents=True, exist_ok=True)
                with open(expansion_log_path, "a", encoding="utf-8") as f:
                    f.write(f"Q: {query}\n")
                    f.write(f"Output Mode: {cfg.multimodal.output_mode.value}\n")
                    for ex in used_expansions:
                        f.write(f"  - {ex}\n")
                    f.write("---\n")
            except Exception as e:
                logger.debug("Failed writing expansion log: %s", e)

        return results

    # ---------------- Strategy helpers ----------------

    def _pick_strategy(self, query: str) -> RetrievalStrategy:
        """Adaptive choice via DSPy if available, else heuristic."""
        if _DSPY_AVAILABLE and self._dspy_strategy is not None:
            try:
                chosen = self._dspy_strategy(question=query)
                mapping = {
                    "vector_only": RetrievalStrategy.VECTOR_ONLY,
                    "bm25_only": RetrievalStrategy.BM25_ONLY,
                    "hybrid": RetrievalStrategy.HYBRID,
                    "query_expansion": RetrievalStrategy.QUERY_EXPANSION,
                    "graph_enhanced": RetrievalStrategy.GRAPH_ENHANCED,
                }
                return mapping.get(chosen, RetrievalStrategy.HYBRID)
            except Exception as e:
                logger.debug("DSPy strategy selection failed: %s", e)

        # Heuristic fallback
        ents = self.kg.extract_entities_from_text(query)
        if len(ents) >= 2:
            return RetrievalStrategy.GRAPH_ENHANCED
        ql = query.lower()
        if any(w in ql for w in ["how", "why", "what", "when", "where", "which"]):
            return RetrievalStrategy.QUERY_EXPANSION
        return RetrievalStrategy.HYBRID

    def _expand_query(self, query: str, cap: int) -> List[str]:
        """Use DSPy expander if present, else heuristic expander."""
        if _DSPY_AVAILABLE and self._dspy_expander is not None:
            try:
                dspy_ex = self._dspy_expander(question=query, k=cap)
                if dspy_ex:
                    return dspy_ex[:cap]
            except Exception as e:
                logger.debug("DSPy expansion failed: %s", e)
        return self.query_expander.expand(query, max_variants=cap)

    # ---------------- Retrieval primitives ----------------

    def _embed_query(self, text: str) -> List[float]:
        return self.embedder.embed_query(" ".join(text.split()))

    def _vector_search(self, query: str, collections: List[int], n_results: int) -> List[Dict[str, Any]]:
        qvec = self._embed_query(query)
        all_hits: List[Dict[str, Any]] = []
        for cid in collections:
            client = get_collection_client(cid)
            coll = client.get_or_create_collection(name="docs")
            res = coll.query(
                query_embeddings=[qvec],
                n_results=n_results,
                include=["documents", "metadatas", "embeddings", "distances"],
            )
            docs = (res.get("documents") or [[]])[0]
            metas = (res.get("metadatas") or [[]])[0]
            dists = (res.get("distances") or [[]])[0]
            embs = (res.get("embeddings") or [[]])[0]
            for doc, meta, dist, emb in zip(docs, metas, dists, embs):
                meta = {**(meta or {}), "collection_id": cid}
                score = 1.0 - (dist if dist is not None else 1.0)
                all_hits.append(
                    {
                        "id": meta.get("chunk_id") or f"{cid}:{hash(doc)}",
                        "text": doc,
                        "metadata": meta,
                        "embedding": emb,
                        "score": float(score),
                        "method": "vector",
                    }
                )
        return sorted(all_hits, key=lambda x: float(x.get("score", 0.0)), reverse=True)

    def _bm25_search(self, query: str, collections: List[int], n_results: int) -> List[Dict[str, Any]]:
        if not settings.use_bm25:
            return []
        try:
            from rag import bm25
        except Exception:
            logger.debug("BM25 module not available; returning empty results.")
            return []
        hits: List[Dict[str, Any]] = []
        for cid in collections:
            results = bm25.search(cid, query, n_results)
            for h in results:
                hits.append(
                    {
                        "id": h["id"],
                        "text": h["text"],
                        "metadata": {**(h.get("metadata", {}) or {}), "collection_id": cid},
                        "score": float(h.get("score", 0.0)),
                        "method": "bm25",
                    }
                )
        return sorted(hits, key=lambda x: float(x.get("score", 0.0)), reverse=True)

    def _fuse(self, vec_hits: List[Dict[str, Any]], bm25_hits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not bm25_hits:
            return vec_hits
        rrf_scores = _rrf([[h["id"] for h in vec_hits], [h["id"] for h in bm25_hits]])
        combined: Dict[str, Dict[str, Any]] = {}
        for h in vec_hits + bm25_hits:
            id_ = h["id"]
            if id_ not in combined:
                combined[id_] = {**h}
            combined[id_]["final_score"] = rrf_scores.get(id_, float(h.get("score", 0.0)))
        return sorted(combined.values(), key=lambda x: float(x.get("final_score", 0.0)), reverse=True)

    def _dedupe_and_embed(self, hits: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
        def _norm(s: str) -> str:
            s = (s or "").lower().strip()
            s = re.sub(r"\s+", " ", s)
            # keep just letters/numbers/spaces to normalize across sources
            s = re.sub(r"[^a-z0-9 ]+", "", s)
            return s

        def _jaccard(a: str, b: str) -> float:
            A = set(_norm(a).split())
            B = set(_norm(b).split())
            if not A or not B:
                return 0.0
            return len(A & B) / max(1, len(A | B))

        # 1) de-dupe by id
        seen_ids: set = set()
        uniq: List[Dict[str, Any]] = []
        for h in hits:
            if h["id"] in seen_ids:
                continue
            seen_ids.add(h["id"])
            uniq.append(h)

        # 2) de-dupe by text similarity (drop near duplicates)
        filtered: List[Dict[str, Any]] = []
        kept_texts: List[str] = []
        for h in uniq:
            txt = h.get("text", "")
            if not txt:
                continue
            is_dup = any(_jaccard(txt, t) >= 0.85 for t in kept_texts)  # threshold
            if is_dup:
                continue
            kept_texts.append(txt)
            filtered.append(h)

        # ensure embeddings present / correct dim
        qvec = self._embed_query(query)
        dim = len(qvec)
        need_idx = [i for i, h in enumerate(filtered) if len(h.get("embedding", [])) != dim]
        if need_idx:
            texts = [filtered[i]["text"] for i in need_idx]
            new_embs = self.embedder.embed(texts)
            for i, emb in zip(need_idx, new_embs):
                filtered[i]["embedding"] = emb
        return filtered


    def _apply_rerank(self, query: str, hits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        texts = [h["text"] for h in hits]
        scores = rerank(query, texts)
        for h, s in zip(hits, scores):
            h["final_score"] = float(s)
        return sorted(hits, key=lambda x: float(x.get("final_score", 0.0)), reverse=True)

    def _apply_mmr(self, query: str, hits: List[Dict[str, Any]], cfg: RetrievalConfig) -> List[Dict[str, Any]]:
        qvec = self._embed_query(query)
        embs = [h.get("embedding", []) for h in hits]
        base_scores = [float(h.get("final_score", h.get("score", 0.0))) for h in hits]
        idxs = _mmr(qvec, embs, base_scores, cfg.k, cfg.lambda_mult or 0.5)
        return [hits[i] for i in idxs]

    # ---------------- Multi-Modal helper methods ----------------
    
    def get_supported_output_modes(self) -> List[str]:
        """Return list of supported output modes"""
        return [mode.value for mode in OutputMode]
    
    def get_supported_chart_types(self) -> List[str]:
        """Return list of supported chart types"""
        return [chart.value for chart in ChartType]
    
    def set_multimodal_config(self, config: MultiModalConfig) -> None:
        """Update multi-modal configuration"""
        # This would be used to update the config dynamically
        pass
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get information about loaded models"""
        return {
            "query_router": {
                "model": "distilbert-base-uncased",
                "available": self.multimodal_manager.query_router is not None,
                "purpose": "Query classification for output mode routing"
            },
            "table_generator": {
                "model": "google/flan-t5-base", 
                "available": self.multimodal_manager.table_generator is not None,
                "purpose": "Table generation and comparison"
            },
            "chart_pipeline": {
                "model": "custom_ml_pipeline",
                "available": _ML_CHART_AVAILABLE,
                "purpose": "Chart data processing and visualization config"
            },
            "transformers_available": _TRANSFORMERS_AVAILABLE,
            "ml_viz_available": _ML_CHART_AVAILABLE,
            "dspy_available": _DSPY_AVAILABLE
        }


# ======================================================================================
# Legacy wrapper (backward compatibility)
# ======================================================================================

class Retriever(NonLinearRetriever):
    """Legacy interface: returns list[dict] with text/metadata/score"""

    def search(
        self,
        query: str,
        k: int = 8,
        lambda_mult: Optional[float] = 0.5,
        fetch_multiplier: int = 3,
        allowed_collections: Optional[List[int]] = None,
        # New multi-modal parameters
        output_mode: Optional[str] = None,
        force_model_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        # Build config
        multimodal_config = MultiModalConfig()
        
        if output_mode:
            try:
                multimodal_config.output_mode = OutputMode(output_mode.lower())
            except ValueError:
                logger.warning(f"Invalid output_mode: {output_mode}, using TEXT")
                
        if force_model_type:
            multimodal_config.force_model_type = force_model_type.lower()
            
        cfg = RetrievalConfig(
            k=k,
            lambda_mult=lambda_mult,
            fetch_multiplier=fetch_multiplier,
            strategy=RetrievalStrategy.ADAPTIVE,
            multimodal=multimodal_config,
        )
        
        results = super().search(query, cfg, allowed_collections or [])
        
        # Convert to legacy format but include multi-modal data
        legacy_results = []
        for r in results:
            result_dict = {
                "text": r.text, 
                "metadata": r.metadata, 
                "score": r.score,
                # Multi-modal additions
                "output_mode": r.output_mode.value,
                "model_used": r.model_used,
            }
            
            # Include generated content if available
            if r.generated_table:
                result_dict["generated_table"] = r.generated_table
            if r.generated_chart:
                result_dict["generated_chart"] = r.generated_chart
                
            legacy_results.append(result_dict)
            
        return legacy_results

# ======================================================================================
# Utility functions for external usage
# ======================================================================================

def create_multimodal_config(
    output_mode: str = "text",
    chart_type: Optional[str] = None,
    table_max_rows: int = 50,
    use_query_router: bool = True,
    force_model_type: Optional[str] = None
) -> MultiModalConfig:
    """Helper to create MultiModalConfig"""
    config = MultiModalConfig(
        table_max_rows=table_max_rows,
        use_query_router=use_query_router,
        force_model_type=force_model_type
    )
    
    try:
        config.output_mode = OutputMode(output_mode.lower())
    except ValueError:
        logger.warning(f"Invalid output_mode: {output_mode}, using TEXT")
        config.output_mode = OutputMode.TEXT
    
    if chart_type:
        try:
            config.chart_type = ChartType(chart_type.lower())
        except ValueError:
            logger.warning(f"Invalid chart_type: {chart_type}, will auto-infer")
    
    return config

def get_model_status() -> Dict[str, bool]:
    """Check which models are available"""
    return {
        "transformers": _TRANSFORMERS_AVAILABLE,
        "ml_visualization": _ML_CHART_AVAILABLE,
        "dspy": _DSPY_AVAILABLE,
    }
