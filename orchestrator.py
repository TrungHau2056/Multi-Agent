from langchain_ollama import ChatOllama

model = ChatOllama(
    model="qwen3:4b-instruct",
    base_url="http://localhost:11434",
    temperature = 0
)

