from langchain_core.prompts import ChatPromptTemplate


HR_RAG_SYSTEM_PROMPT = """
You are an HR assistant for an enterprise self-service portal.

Rules:
1) Use ONLY the provided context chunks.
2) Do NOT invent policies, dates, thresholds, or exceptions.
3) If the answer is not found in the context, reply exactly:
   "I could not find this information in the provided HR knowledge base context."
4) Keep answers concise and enterprise-style.
5) When possible, ground the answer with source references like [S1], [S2].
"""


HR_RAG_HUMAN_PROMPT = """
User question:
{question}

Context chunks:
{context}

Return a concise answer based only on the context above.
"""


def get_hr_rag_prompt():
    """Return the chat prompt used for grounded HR RAG answers."""
    return ChatPromptTemplate.from_messages(
        [
            ("system", HR_RAG_SYSTEM_PROMPT.strip()),
            ("human", HR_RAG_HUMAN_PROMPT.strip()),
        ]
    )
