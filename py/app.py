import os
from openai import AsyncOpenAI
from langchain_community.document_loaders import PyPDFLoader

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

import chainlit as cl

# os.environ["OPENAI_API_KEY"] = (
#     "OPENAI_API_KEY"
# )

text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)

cl.instrument_openai()

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

    # Let the user know that the system is ready
    msg.content = f"Processing `{file.name}` done. You can now ask questions!"
    await msg.update()

    cl.user_session.set("llm", llm)
    cl.user_session.set("prompt", prompt)
    cl.user_session.set("message_history", message_history)
    cl.user_session.set("retriever", retriever)

@cl.on_message
async def main(message: cl.Message):
    message_history = cl.user_session.get("message_history")
    retriever = cl.user_session.get("retriever")

    # Get relevant documents
    source_documents = await retriever.ainvoke(message.content)

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

    # Add AI response to history
    message_history.add_ai_message(answer)

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