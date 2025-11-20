from langgraph.graph import *
from langchain.tools import tool
from langchain.chat_models import init_chat_model
from tool_dependency_extractor import analysis_project
from langchain_ollama import ChatOllama

model = ChatOllama(
    model="qwen3:4b-instruct",
    base_url="http://localhost:11434",
    temperature = 0
)


tools = [analysis_project]

tools_by_name = {tool.name: tool for tool in tools}
model_with_tools =  model.bind_tools(tools)

from langchain.messages import *
from typing_extensions import TypedDict, Annotated
import operator

class MessagesState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]
    llm_calls: int
    tool_calls: int


def llm_call(state: dict):
    """LLM decides whether to call a tool or not"""

    return {
        "messages": [
            model_with_tools.invoke(
                [
                    SystemMessage(
                        content="""You are a analysis code professional and your task is extract dependencies from code.
                        You can use tools below:
                        - analysis_project is a tool can extract dependencies which you need pass parameter as name_project and name focal method. 
                        """

                    )
                ]
                + state["messages"]
            )
        ],
        "llm_calls": state.get("llm_calls", 0) + 1
    }


def tool_node(state: dict):
    """Performs the tool call"""

    result = []
    for tool_call in state["messages"][-1].tool_calls:
        tool = tools_by_name[tool_call["name"]]
        observation = tool.invoke(tool_call["args"])
        result.append(ToolMessage(content=observation, tool_call_id=tool_call["id"]))
    return {"messages": result, "tool_calls": state.get("tool_calls",0) + 1}


from typing import Literal
from langgraph.graph import StateGraph, START, END

def should_continue(state: MessagesState) -> Literal["tool_node", END]:
    """Decide if we should continue the loop or stop based upon whether the LLM made a tool call"""

    messages = state["messages"]
    last_message = messages[-1]

    if last_message.tool_calls:
        return "tool_node"

    return END


agent_builder = StateGraph(MessagesState)

agent_builder.add_node("llm_call", llm_call)
agent_builder.add_node("tool_node", tool_node)

agent_builder.add_edge(START, "llm_call")
agent_builder.add_conditional_edges(
    "llm_call",
    should_continue,
    ["tool_node", END]
)
agent_builder.add_edge("tool_node", "llm_call")

agent_analysis = agent_builder.compile()


from IPython.display import Image, display

display(Image(agent_analysis.get_graph(xray=True).draw_mermaid_png()))

from langchain.messages import *
messages = [HumanMessage(content="""
phan tich function sau o trong project Flappy-Bird-Qt:
Bird::Bird(const QPointF& pos, const QPixmap& pixmap, const qreal &groundStartPosY, int scrWidth, int scrHeight, qreal scaleF)
    : QGraphicsPixmapItem(pixmap), groundYPos(groundStartPosY), scaleFactor(scaleF), screenWidth(scrWidth), screenHeight(scrHeight)
{
    setCacheMode(ItemCoordinateCache);

    setPos(pos);

    birdDesigner = new QTimer(this);
    connect(birdDesigner, SIGNAL(timeout()), this, SLOT(designBird()));

    rotator = new QPropertyAnimation(this, "rotation", this);
    currentRotation = 0;

    yAnimator = new QPropertyAnimation(this, "y", this);
    connect(yAnimator, SIGNAL(finished()), this, SLOT(gravitation()));

    oscillateDirection = 1;
    oscillator = new QPropertyAnimation(this, "pos", this);
    oscillator->setDuration(550);
    oscillator->setEndValue(QPointF(boundingRect().width() * 2.75, y()));
    oscillator->setEasingCurve(QEasingCurve::OutQuad);
    connect(oscillator, SIGNAL(finished()), SLOT(oscillate()));

    wingState = WingStates::up;
    setColor(BirdTypes::yellow);

    birdDesigner->start(75);
}
""")]
messages = agent_analysis.invoke({"messages": messages})
for m in messages["messages"]:
    m.pretty_print()