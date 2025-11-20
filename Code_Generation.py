from langchain_core.messages import SystemMessage
from langgraph.graph import *
from langchain.tools import tool
from langchain.chat_models import init_chat_model
from langchain_ollama import ChatOllama

from Analysis_code import agent_builder

model = ChatOllama(
    model="qwen3:4b-instruct",
    base_url="http://localhost:11434",
    temperature = 0
)

SYSTEM_PROMPT = """
You are a professional C++ testing engineer.

Your task:
- Write a **complete C++ test file** for the provided source code.
- Use the given dependencies (includes, namespaces, etc.).
- The test must be valid C++ and compilable.
- Focus on testing all functions logically and covering both normal and edge cases.

Requirements:
- If the code defines functions, write test cases for each one.
- Use either basic assert statements or GoogleTest (if appropriate).
- Ensure your output is ONLY the C++ test code. Do not explain it.
"""

def generate_code(state: dict):
    return {
        "messages": [
            model.invoke(
                [
                    SystemMessage(
                        content=SYSTEM_PROMPT
                    )
                ]
                + state["messages"]
            )
        ],
        "llm_calls": state.get("llm_calls", 0) + 1
    }

graph = StateGraph(MessagesState)

graph.add_node("generate_code", generate_code)
graph.add_edge(START, "generate_code")
graph.add_edge("generate_code", END)

agent_code_generation = graph.compile()

from IPython.display import Image, display

display(Image(agent_code_generation.get_graph(xray=True).draw_mermaid_png()))

from langchain.messages import *
messages = [HumanMessage(content="""
write test for code below:
#include <iostream>
using namespace std;

int add(int a, int b) {
    return a + b;
}

int main() {
    int result = add(3, 4);
    cout << "Result: " << result << endl;
    return 0;
}
""")]
messages = agent_code_generation.invoke({"messages": messages})
for m in messages["messages"]:
    m.pretty_print()

