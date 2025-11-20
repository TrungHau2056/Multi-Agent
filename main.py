from langgraph.graph import *
from langchain.tools import tool
from langchain.chat_models import init_chat_model
from langchain_ollama import ChatOllama

model = ChatOllama(
    model="qwen3:4b-instruct",
    base_url="http://localhost:11434",
    temperature = 0
)
