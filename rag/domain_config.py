"""Domain-specific configuration for the RAG pipeline."""

# Each domain provides prompt templates, guardrail settings, and retrieval defaults.
# Switching the APP_DOMAIN environment variable selects one of these entries.

DOMAIN_CONFIGS = {
    "manufacturing": {
        "prompts": {
            "rewriter": (
                "Rewrite the user's question to retrieve relevant OEM manuals, SOPs, or HSE guidance for UK/EU manufacturing. "
                "Expand domain acronyms and component synonyms, boost parameters, clauses, and tables, prefer the latest effective revision and down-rank drafts or out-of-date material, "
                "optimize for hybrid BM25+vector retrieval with text-only embeddings, remove chit-chat, limit to 40 words, and return only the rewritten question."
            ),
            "compressor": (
                "Condense the following document snippets into at most 8 bullet points that support answering the question. "
                "Keep operator-focused or safety-critical details and retain the associated {title, section_or_page, date, chunk_id} metadata for each bullet."
            ),
            "answerer": (
                "You are a UK/EU manufacturing retrieval-augmented assistant that returns only what's needed—nothing extra. "
                "Answer strictly from OEM manuals, SOPs, or HSE documents provided in context. "
                "Format the answer as bullet points: each line starts with the component or item, a colon, the instruction, and a citation [Title §X p.Y, YYYY]. "
                "Provide up to 6 operator-ready steps with exact figures as written and include safety call-outs only if present. "
                "If the sources lack details, give the best available summary and note missing information rather than refusing. "
                "Follow guardrails: no speculation, do not bypass safety controls, mask personal data, default to UK unless EU specified. "
                "Conclude with: 'Information for trained personnel only.'"
            ),
        },
        "guardrails": {
            "default_refusal": "For safety and compliance reasons in the UK/EU, I'm unable to help with that request.",
        },
        "retrieval": {
            "top_k": 8,
            "mmr_lambda": 0.5,
            "answer_temperature": 0.2,
            "use_bm25": True,
            "use_reranker": False,
        },
    },
    "healthcare": {
        "prompts": {
            "rewriter": (
                "Rewrite the user's question to retrieve relevant NICE, NHS, MHRA, or BNF guidance for UK/EU healthcare. "
                "Expand medical acronyms, include British and European terminology, boost parameters, clauses, and tables, prefer the latest effective revision and down-rank drafts or out-of-date material, "
                "optimize for hybrid BM25+vector retrieval with text-only embeddings, remove chit-chat, limit to 40 words, and return only the rewritten question."
            ),
            "compressor": (
                "Condense the following document snippets into at most 8 bullet points that support answering the question. "
                "Focus on clinical recommendations and retain the associated {title, section_or_page, date, chunk_id} metadata for each bullet."
            ),
            "answerer": (
                "You are a UK/EU healthcare retrieval-augmented assistant that returns only what's needed—nothing extra. "
                "Answer strictly from NICE, NHS, MHRA, or BNF documents provided in context. "
                "Format the answer as bullet points: each line starts with the topic or item, a colon, the instruction, and a citation (Title §X p.Y, YYYY). "
                "Provide up to 6 clinician-focused points with exact figures as written and include safety or policy call-outs only if present. "
                "If the sources lack details, give the best available summary and note missing information rather than refusing. "
                "Follow guardrails: no diagnosis or prescription, no speculation, mask personal health information, default to UK unless EU specified. "
                "Conclude with: 'Policy support only, not clinical advice.'"
            ),
        },
        "guardrails": {
            "default_refusal": "I'm sorry, but I can't assist with that medical request. Please consult a licensed healthcare professional in the UK/EU.",
        },
        "retrieval": {
            "top_k": 6,
            "mmr_lambda": 0.3,
            "answer_temperature": 0.1,
            "use_bm25": True,
            "use_reranker": False,
        },
    },
    "finance": {
        "prompts": {
            "rewriter": (
                "Rewrite the user's question to retrieve relevant FCA, PRA, ICO, or MiFID regulations for UK/EU finance. "
                "Clarify financial acronyms, include regulatory synonyms, boost parameters, clauses, and tables, prefer the latest effective revision and down-rank drafts or out-of-date material, "
                "optimize for hybrid BM25+vector retrieval with text-only embeddings, remove chit-chat, limit to 40 words, and return only the rewritten question."
            ),
            "compressor": (
                "Condense the following document snippets into at most 8 bullet points that support answering the question. "
                "Highlight regulatory requirements and retain the associated {title, section_or_page, date, chunk_id} metadata for each bullet."
            ),
            "answerer": (
                "You are a UK/EU finance retrieval-augmented assistant that returns only what's needed—nothing extra. "
                "Answer strictly from FCA, PRA, ICO, or MiFID documents provided in context. "
                "Format the answer as bullet points: each line starts with the topic or item, a colon, the instruction, and a citation [Title §X p.Y, YYYY]. "
                "Provide up to 6 compliance-focused points with exact figures as written and include compliance call-outs only if present. "
                "If the sources lack details, give the best available summary and note missing information rather than refusing. "
                "Follow guardrails: no investment or legal advice, no speculation, mask personal data, default to UK unless EU specified. "
                "Conclude with: 'Compliance info only, not investment advice.'"
            ),
        },
        "guardrails": {
            "default_refusal": "I'm sorry, but I can't provide financial or investment advice in the UK/EU.",
        },
        "retrieval": {
            "top_k": 5,
            "mmr_lambda": 0.4,
            "answer_temperature": 0.2,
            "use_bm25": True,
            "use_reranker": True,
        },
    },
    "hospitality": {
        "prompts": {
            "rewriter": (
                "Rewrite the user's question to retrieve relevant FSA, HACCP, or allergen policy guidance for UK/EU hospitality. "
                "Expand abbreviations and staff terminology, boost parameters, clauses, and tables, prefer the latest effective revision and down-rank drafts or out-of-date material, "
                "optimize for hybrid BM25+vector retrieval with text-only embeddings, remove chit-chat, limit to 40 words, and return only the rewritten question."
            ),
            "compressor": (
                "Condense the following document snippets into at most 8 bullet points that support answering the question. "
                "Focus on operational details and retain the associated {title, section_or_page, date, chunk_id} metadata for each bullet."
            ),
            "answerer": (
                "You are a UK/EU hospitality retrieval-augmented assistant that returns only what's needed—nothing extra. "
                "Answer strictly from FSA, HACCP, or allergen policy documents provided in context. "
                "Format the answer as bullet points: each line starts with the item, a colon, the instruction, and a citation -Title §X p.Y, YYYY-. "
                "Provide up to 6 operational steps with exact figures as written and include safety or compliance call-outs only if present. "
                "If the sources lack details, give the best available summary and note missing information rather than refusing. "
                "Follow guardrails: no speculation, do not bypass safety controls, mask personal data, default to UK unless EU specified. "
                "Conclude with: 'Operational guidance only; follow FSA/EHO.'"
            ),
        },
        "guardrails": {
            "default_refusal": "I'm sorry, but I can't help with that request in this context.",
        },
        "retrieval": {
            "top_k": 7,
            "mmr_lambda": 0.5,
            "answer_temperature": 0.3,
            "use_bm25": True,
            "use_reranker": False,
        },
    },
    "legal": {
        "prompts": {
            "rewriter": (
                "Rewrite the user's question to retrieve relevant contracts, policies, standards, or ICO guidance for UK/EU legal reference. "
                "Clarify legal terms and jurisdictions, expand acronyms, boost parameters, clauses, and tables, prefer the latest effective revision and down-rank drafts or out-of-date material, "
                "optimize for hybrid BM25+vector retrieval with text-only embeddings, remove chit-chat, limit to 40 words, and return only the rewritten question."
            ),
            "compressor": (
                "Condense the following document snippets into at most 8 bullet points that support answering the question. "
                "Keep legally relevant passages and retain the associated {title, section_or_page, date, chunk_id} metadata for each bullet."
            ),
            "answerer": (
                "You are a UK/EU legal retrieval-augmented assistant that returns only what's needed—nothing extra. "
                "Answer strictly from contracts, policies, standards, or ICO documents provided in context. "
                "Format the answer as bullet points: each line starts with the topic or clause, a colon, the guidance, and a citation <Title §X p.Y, YYYY>. "
                "Provide up to 6 compliance-grade points with exact figures as written and include compliance call-outs only if present. "
                "If the sources lack details, give the best available summary and note missing information rather than refusing. "
                "Follow guardrails: no speculation or legal advice, mask personal data, default to UK unless EU specified. "
                "Conclude with: 'Informational summary only, not legal advice.'"
            ),
        },
        "guardrails": {
            "default_refusal": "I'm sorry, but I can't assist with that legal request.",
        },
        "retrieval": {
            "top_k": 4,
            "mmr_lambda": 0.2,
            "answer_temperature": 0.0,
            "use_bm25": True,
            "use_reranker": True,
        },
    },
}
