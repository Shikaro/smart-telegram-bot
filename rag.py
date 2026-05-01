import os
from dotenv import load_dotenv

load_dotenv()

import chromadb
from openai import OpenAI
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader


client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
chroma_client = chromadb.PersistentClient(path="chroma_db")
collection = chroma_client.get_or_create_collection(name="knowledge_base")

text_splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)


def load_txt(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()


def load_pdf(file_path: str) -> str:
    reader = PdfReader(file_path)
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def add_document(file_path: str) -> int:
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        text = load_pdf(file_path)
    else:
        text = load_txt(file_path)

    chunks = text_splitter.split_text(text)
    if not chunks:
        return 0

    filename = os.path.basename(file_path)
    ids = [f"{filename}_{i}" for i in range(len(chunks))]
    metadatas = [{"source": filename} for _ in chunks]

    collection.upsert(documents=chunks, ids=ids, metadatas=metadatas)
    return len(chunks)


def ask(question: str) -> str:
    if collection.count() == 0:
        return ""

    results = collection.query(query_texts=[question], n_results=3)
    documents = results["documents"][0] if results["documents"] else []

    if not documents:
        return ""

    context = "\n\n---\n\n".join(documents)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "Ты — AI-ассистент компании. Отвечай на вопросы "
                    "ТОЛЬКО на основе предоставленного контекста. Если в контексте "
                    "нет ответа — скажи, что не можешь ответить и предложи связаться "
                    "с менеджером. Отвечай кратко и по делу. Язык ответа — русский."
                ),
            },
            {
                "role": "user",
                "content": f"Контекст:\n{context}\n\nВопрос: {question}",
            },
        ],
        temperature=0.3,
        max_tokens=500,
    )

    return response.choices[0].message.content
