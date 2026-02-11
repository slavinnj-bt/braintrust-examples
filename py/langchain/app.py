#TODO: clean up code
# separate project in braintrust
# create new online scoring
# create new dataset entries
# create human scores
# create experiment and grab prompt slugs for versioning

import os

# Disable LiteralAI instrumentation to avoid conflicts with Braintrust
os.environ["LITERAL_DISABLE_INSTRUMENTATION"] = "true"

from openai import AsyncOpenAI
from anthropic import AsyncAnthropic
from langchain_community.document_loaders import PyPDFLoader

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_anthropic import ChatAnthropic

from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain_community.tools.tavily_search import TavilySearchResults

from braintrust import init_logger, Attachment
from braintrust_langchain import BraintrustCallbackHandler

import chainlit as cl
import json

# Explicitly disable LiteralAI instrumentation after chainlit import
try:
    from literalai import instrumentation
    instrumentation.uninstrument()
except Exception:
    pass  # If it fails, continue anyway

# Configure provider via environment variable (simpler than CLI args)
# Set AI_PROVIDER=anthropic to use Anthropic, defaults to OpenAI
PROVIDER = os.environ.get("AI_PROVIDER", "openai").lower()
MODEL_NAME = os.environ.get("AI_MODEL", "")

# Set provider-specific defaults if model not specified
if not MODEL_NAME:
    if PROVIDER == "anthropic":
        MODEL_NAME = "claude-sonnet-4-5-20250929"
    else:
        MODEL_NAME = "gpt-4o-mini"

SYSTEM_PROMPT=""
with open("system_prompt.txt","r") as f:
    SYSTEM_PROMPT = f.read()

logger = init_logger(project="SlavinScratchArea", api_key=os.environ.get("BRAINTRUST_API_KEY"))
# Create handler but don't set as global - we'll pass it explicitly to avoid duplicate spans
handler = BraintrustCallbackHandler()


text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)

# Initialize Tavily search tool for web search capabilities
tavily_search = TavilySearchResults(max_results=3)

# Define the tool for OpenAI function calling
tools = [
    {
        "type": "function",
        "function": {
            "name": "tavily_search",
            "description": "Search the web for current information. Use this when you need up-to-date information about laws, regulations, legal precedents, or other information not contained in the document.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query to find relevant information"
                    }
                },
                "required": ["query"]
            }
        }
    }
]

# Define Anthropic tools format
anthropic_tools = [
    {
        "name": "tavily_search",
        "description": "Search the web for current information. Use this when you need up-to-date information about laws, regulations, legal precedents, or other information not contained in the document.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query to find relevant information"
                }
            },
            "required": ["query"]
        }
    }
]

# Initialize client based on provider
if PROVIDER == "openai":
    client = AsyncOpenAI()
elif PROVIDER == "anthropic":
    client = AsyncAnthropic()

@cl.on_chat_start
async def on_chat_start():
    files = None

    # Wait for the user to upload a file
    while files is None:
        files = await cl.AskFileMessage(
            content="Hi, I'm Allex! Upload your document!",
            accept=["application/pdf"],
            max_size_mb=20,
            timeout=180,
        ).send()

    file = files[0]

    msg = cl.Message(content=f"Processing `{file.name}`...")
    await msg.send()

    # with open(file.path, "rb") as f:
    #     text = f.read()

    loader = PyPDFLoader(file.path)
    docs = loader.load()

    # Split the text into chunks from all pages
    all_text = "\n\n".join([doc.page_content for doc in docs])
    texts = text_splitter.split_text(all_text)


    # Create a metadata for each chunk
    metadatas = [{"source": f"{i}-pl"} for i in range(len(texts))]

    # Create a Chroma vector store
    embeddings = OpenAIEmbeddings()
    docsearch = await cl.make_async(Chroma.from_texts)(
        texts, embeddings, metadatas=metadatas
    )

    message_history = ChatMessageHistory()

    # Create a prompt template for RAG with chat history
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT + "Use the following document as context: \n\nContext: {context}"),
        MessagesPlaceholder(variable_name="chat_history"),
        ("human", "{question}")
    ])

    # Create the LLM based on provider
    if PROVIDER == "openai":
        llm = ChatOpenAI(model_name=MODEL_NAME, temperature=0, streaming=True)
    elif PROVIDER == "anthropic":
        llm = ChatAnthropic(model_name=MODEL_NAME, temperature=0, streaming=True)

    retriever = docsearch.as_retriever()

    # Read the PDF file for attachment
    with open(file.path, "rb") as pdf_file:
        pdf_attachment = Attachment(
            data=pdf_file.read(),
            filename=file.name,
            content_type="application/pdf"
        )

    # Create a root span for the entire conversation session with PDF attached
    session_span = logger.start_span(
        name="conversation_session",
        input={
            "document": file.name,
            "num_chunks": len(texts),
            "attachments": [pdf_attachment]
        },
        span_attributes={"type": "task"}
    )

    # Set the session span as current to ensure proper hierarchy
    session_span.set_current()

    # Let the user know that the system is ready
    msg.content = f"Processing `{file.name}` done. You can now ask questions!"
    await msg.update()

    cl.user_session.set("llm", llm)
    cl.user_session.set("prompt", prompt)
    cl.user_session.set("message_history", message_history)
    cl.user_session.set("retriever", retriever)
    cl.user_session.set("session_span", session_span)

@cl.on_message
async def main(message: cl.Message):
    message_history = cl.user_session.get("message_history")
    retriever = cl.user_session.get("retriever")
    session_span = cl.user_session.get("session_span")

    # Get turn number for tracking
    turn_number = len([m for m in message_history.messages if m.type == "human"]) + 1

    # Start a Braintrust span for this conversation turn as a child of the session span
    span = session_span.start_span(
        name="conversation_turn",
        input={
            "question": message.content,
            "turn_number": turn_number
        },
        span_attributes={"type": "task"}
    )

    # Set this span as the active context so nested operations will be children
    span.set_current()

    try:
        # Get relevant documents - the BraintrustCallbackHandler should now pick up the active span
        source_documents = await retriever.ainvoke(
            message.content,
            config={"callbacks": [handler]}
        )

        # Format context from documents
        context = "\n\n".join(doc.page_content for doc in source_documents)

        # Add user message to history
        message_history.add_user_message(message.content)

        # Build messages for OpenAI API
        system = SYSTEM_PROMPT + f"Use the following document as context: \n\nContext: {context}"
        messages = [
            {
                "role": "system",
                "content": system
            }
        ]

        # Add chat history (excluding the current user message we just added)
        for msg_obj in message_history.messages[:-1]:
            if msg_obj.type == "human":
                messages.append({"role": "user", "content": msg_obj.content})
            elif msg_obj.type == "ai":
                messages.append({"role": "assistant", "content": msg_obj.content})

        # Add current question
        messages.append({"role": "user", "content": message.content})

        # Create a message for streaming
        msg = cl.Message(content="")

        # Log the retrieval context to the span
        span.log(
            metadata={
                "retrieval": {
                    "num_documents": len(source_documents),
                    "context_length": len(context),
                    "sources": [doc.metadata.get("source", "unknown") for doc in source_documents]
                }
            }
        )

        # Log the LLM call within a child span of the turn span
        llm_span = span.start_span(
            name=f"{PROVIDER}_chat_completion",
            input={"model": MODEL_NAME, "messages": [{"role": "user", "content": message.content}], "temperature": 0},
            span_attributes={"type": "llm"}
        )
        llm_span.set_current()

        try:
            # Stream the response using the selected provider client with tool support
            answer = ""
            tool_calls = []
            current_tool_call = None

            if PROVIDER == "openai":
                stream = await client.chat.completions.create(
                    model=MODEL_NAME,
                    messages=messages,
                    temperature=0,
                    tools=tools,
                    stream=True
                )

                async for chunk in stream:
                    delta = chunk.choices[0].delta

                    # Handle tool calls
                    if delta.tool_calls:
                        for tool_call_delta in delta.tool_calls:
                            if tool_call_delta.index is not None:
                                # Start a new tool call or continue existing one
                                if current_tool_call is None or tool_call_delta.index != current_tool_call.get("index"):
                                    if current_tool_call:
                                        tool_calls.append(current_tool_call)
                                    current_tool_call = {
                                        "index": tool_call_delta.index,
                                        "id": tool_call_delta.id or "",
                                        "type": "function",
                                        "function": {
                                            "name": tool_call_delta.function.name or "",
                                            "arguments": tool_call_delta.function.arguments or ""
                                        }
                                    }
                                else:
                                    # Continue building the current tool call
                                    if tool_call_delta.function.arguments:
                                        current_tool_call["function"]["arguments"] += tool_call_delta.function.arguments

                    # Handle regular content
                    if delta.content:
                        content = delta.content
                        answer += content
                        await msg.stream_token(content)

            elif PROVIDER == "anthropic":
                # Convert messages to Anthropic format
                anthropic_messages = []
                system_message = None
                for message_dict in messages:
                    if message_dict["role"] == "system":
                        system_message = message_dict["content"]
                    else:
                        anthropic_messages.append({
                            "role": message_dict["role"],
                            "content": message_dict["content"]
                        })

                stream = await client.messages.create(
                    model=MODEL_NAME,
                    max_tokens=4096,
                    temperature=0,
                    system=system_message,
                    messages=anthropic_messages,
                    tools=anthropic_tools,
                    stream=True
                )

                async for event in stream:
                    if event.type == "content_block_start":
                        if hasattr(event.content_block, "type"):
                            if event.content_block.type == "tool_use":
                                current_tool_call = {
                                    "index": event.index,
                                    "id": event.content_block.id,
                                    "type": "function",
                                    "function": {
                                        "name": event.content_block.name,
                                        "arguments": ""
                                    }
                                }
                    elif event.type == "content_block_delta":
                        if hasattr(event.delta, "type"):
                            if event.delta.type == "text_delta":
                                content = event.delta.text
                                answer += content
                                await msg.stream_token(content)
                            elif event.delta.type == "input_json_delta":
                                if current_tool_call:
                                    current_tool_call["function"]["arguments"] += event.delta.partial_json
                    elif event.type == "content_block_stop":
                        if current_tool_call:
                            tool_calls.append(current_tool_call)
                            current_tool_call = None

            # Add any remaining tool call
            if current_tool_call:
                tool_calls.append(current_tool_call)

            # If there are tool calls, execute them
            if tool_calls:
                for tool_call in tool_calls:
                    if tool_call["function"]["name"] == "tavily_search":
                        # Parse the arguments
                        args = json.loads(tool_call["function"]["arguments"])
                        query = args.get("query", "")

                        # Execute the search with a child span
                        search_span = llm_span.start_span(
                            name="tavily_search",
                            input={"query": query},
                            span_attributes={"type": "tool"}
                        )
                        search_span.set_current()

                        try:
                            # Execute the Tavily search
                            search_results = await tavily_search.ainvoke(query, config={"callbacks": [handler]})

                            # Log search results
                            search_span.log(output={"results": search_results})

                            # Add tool result to messages
                            messages.append({
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [{
                                    "id": tool_call["id"],
                                    "type": "function",
                                    "function": {
                                        "name": "tavily_search",
                                        "arguments": tool_call["function"]["arguments"]
                                    }
                                }]
                            })
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call["id"],
                                "content": str(search_results)
                            })

                            # Stream a message about the search
                            search_msg = f"\n\n[Searching the web for: {query}]\n\n"
                            answer += search_msg
                            await msg.stream_token(search_msg)
                        finally:
                            search_span.end()

                # Make another call to get the final response with search results
                if PROVIDER == "openai":
                    final_stream = await client.chat.completions.create(
                        model=MODEL_NAME,
                        messages=messages,
                        temperature=0,
                        stream=True
                    )

                    async for chunk in final_stream:
                        if chunk.choices[0].delta.content:
                            content = chunk.choices[0].delta.content
                            answer += content
                            await msg.stream_token(content)

                elif PROVIDER == "anthropic":
                    # Convert messages to Anthropic format for final call
                    anthropic_messages = []
                    system_message = None
                    assistant_content_blocks = []

                    for message_dict in messages:
                        if message_dict["role"] == "system":
                            system_message = message_dict["content"]
                        elif message_dict["role"] == "tool":
                            # Convert tool response to user message for Anthropic
                            anthropic_messages.append({
                                "role": "user",
                                "content": [
                                    {
                                        "type": "tool_result",
                                        "tool_use_id": message_dict["tool_call_id"],
                                        "content": message_dict["content"]
                                    }
                                ]
                            })
                        elif message_dict.get("tool_calls"):
                            # Build assistant message with tool_use blocks for Anthropic
                            assistant_content_blocks = []
                            # Add text content if there is any
                            if answer:
                                assistant_content_blocks.append({
                                    "type": "text",
                                    "text": answer
                                })
                            # Add tool_use blocks
                            for tc in message_dict["tool_calls"]:
                                assistant_content_blocks.append({
                                    "type": "tool_use",
                                    "id": tc["id"],
                                    "name": tc["function"]["name"],
                                    "input": json.loads(tc["function"]["arguments"])
                                })
                            anthropic_messages.append({
                                "role": "assistant",
                                "content": assistant_content_blocks
                            })
                        else:
                            anthropic_messages.append({
                                "role": message_dict["role"],
                                "content": message_dict["content"]
                            })

                    final_stream = await client.messages.create(
                        model=MODEL_NAME,
                        max_tokens=4096,
                        temperature=0,
                        system=system_message,
                        messages=anthropic_messages,
                        stream=True
                    )

                    async for event in final_stream:
                        if event.type == "content_block_delta":
                            if hasattr(event.delta, "type") and event.delta.type == "text_delta":
                                content = event.delta.text
                                answer += content
                                await msg.stream_token(content)

            # Log the completion
            llm_span.log(output={"role": "assistant", "content": answer})
        finally:
            llm_span.end()

        # Add AI response to history
        message_history.add_ai_message(answer)

        # Log the final output for this turn
        span.log(output={
            "answer": answer
        })
    finally:
        span.end()

    # Send the message
    text_elements = []  # type: List[cl.Text]

    if source_documents:
        for source_idx, source_doc in enumerate(source_documents):
            source_name = f"source_{source_idx}"
            # Create the text element referenced in the message
            text_elements.append(
                cl.Text(
                    content=source_doc.page_content, name=source_name, display="side"
                )
            )
        source_names = [text_el.name for text_el in text_elements]

        if source_names:
            sources_text = f"\nSources: {', '.join(source_names)}"
            answer += sources_text
            await msg.stream_token(sources_text)

    msg.elements = text_elements
    await msg.send()

@cl.on_chat_end
async def on_chat_end():
    # End the session span when the chat ends
    session_span = cl.user_session.get("session_span")
    if session_span:
        message_history = cl.user_session.get("message_history")

        # Log summary information for the session
        num_turns = len([m for m in message_history.messages if m.type == "human"])
        session_span.log(output={
            "num_turns": num_turns,
            "status": "completed"
        })
        session_span.end()