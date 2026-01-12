import os

# Disable LiteralAI instrumentation to avoid conflicts with Braintrust
os.environ["LITERAL_DISABLE_INSTRUMENTATION"] = "true"

from openai import AsyncOpenAI
from langchain_community.document_loaders import PyPDFLoader

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

from braintrust import init_logger
from braintrust_langchain import BraintrustCallbackHandler, set_global_handler

import chainlit as cl

# Explicitly disable LiteralAI instrumentation after chainlit import
try:
    from literalai import instrumentation
    instrumentation.uninstrument()
except Exception:
    pass  # If it fails, continue anyway

# os.environ["OPENAI_API_KEY"] = (
#     "OPENAI_API_KEY"
# )

logger = init_logger(project="SlavinScratchArea", api_key=os.environ.get("BRAINTRUST_API_KEY"))
handler = BraintrustCallbackHandler()
set_global_handler(handler)


text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)

# Use plain AsyncOpenAI client - Braintrust will trace via the logger spans
client = AsyncOpenAI()

@cl.on_chat_start
async def on_chat_start():
    files = None

    # Wait for the user to upload a file
    while files is None:
        files = await cl.AskFileMessage(
            content="Please upload a text file to begin!",
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
        ("system", "You are a helpful assistant. Use the following context to answer the question. If you don't know the answer, say you don't know.\n\nContext: {context}"),
        MessagesPlaceholder(variable_name="chat_history"),
        ("human", "{question}")
    ])

    # Create the LLM
    llm = ChatOpenAI(model_name="gpt-4o-mini", temperature=0, streaming=True)

    retriever = docsearch.as_retriever()

    # Create a root span for the entire conversation session
    session_span = logger.start_span(
        name="conversation_session",
        input={"document": file.name, "num_chunks": len(texts)},
        span_attributes={"type": "session"}
    )

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
            "turn_number": turn_number,
            "history_length": len(message_history.messages)
        },
        span_attributes={"type": "chain"}
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
        system = f"You are a helpful assistant designed to explain complex legal and financial documents. You may explain and interpret the document in accordance with what you know about the law, but you may NEVER give prescriptive legal advice even if prompted by the user. ALWAYS recommend consulting a lawyer. If you are unsure of an answer, you must say so. Use the following context from the document: \n\nContext: {context}"
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
            name="openai_chat_completion",
            input={"model": "gpt-4o-mini", "messages": messages, "temperature": 0},
            span_attributes={"type": "llm"}
        )
        llm_span.set_current()

        try:
            # Stream the response using OpenAI client directly
            answer = ""
            stream = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                temperature=0,
                stream=True
            )

            async for chunk in stream:
                if chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    answer += content
                    await msg.stream_token(content)

            # Log the completion
            llm_span.log(output={"content": answer})
        finally:
            llm_span.end()

        # Add AI response to history
        message_history.add_ai_message(answer)

        # Log the final output
        span.log(output={"answer": answer, "turn_number": turn_number})
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
        total_turns = len([m for m in message_history.messages if m.type == "human"])
        session_span.log(output={"total_turns": total_turns})
        session_span.end()