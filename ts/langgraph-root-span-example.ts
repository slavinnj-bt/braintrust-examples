/**
LangGraph Multi-Turn Conversation with Root Span Pattern
This pattern shows how to maintain a reference to a root span and log data to it from child spans, ensuring the final result is logged AFTER all child operations complete.


The root span is passed through your application state, allowing child operations to log summary data back to it while maintaining their own detailed child spans.

```
Root Span (multi_turn_conversation)
├── Input: logged FIRST
├── Child Span 1 (turn_1)
│   ├── Logs its own input/output
│   └── Also logs summary back to ROOT SPAN
├── Child Span 2 (turn_2)
│   ├── Logs its own input/output
│   └── Also logs summary back to ROOT SPAN
├── Child Span 3 (turn_3)
│   └── Same pattern...
└── Output: logged LAST (after all children complete)
```

 * See https://www.braintrust.dev/docs/cookbook/recipes/Lovable for another example.
 */

import "dotenv/config";
import { initLogger } from "braintrust";
import { ChatOpenAI } from "@langchain/openai";
import { StateGraph, Annotation, MessagesAnnotation } from "@langchain/langgraph";
import { AIMessage, BaseMessage, HumanMessage } from "@langchain/core/messages";

// Initialize Braintrust logger
const logger = initLogger({
  projectName: "SlavinScratchArea",
  apiKey: process.env.BRAINTRUST_API_KEY,
});

// Define the conversation state
const ConversationState = Annotation.Root({
  ...MessagesAnnotation.spec,
  turnCount: Annotation<number>(),
  rootSpan: Annotation<any>(), // Store reference to root span
});

// Create the LLM
const llm = new ChatOpenAI({
  modelName: "gpt-4o-mini",
  temperature: 0.7,
  openAIApiKey: process.env.OPENAI_API_KEY,
});

// Node: Process a single conversation turn
async function conversationTurn(state: typeof ConversationState.State) {
  const { messages, turnCount, rootSpan } = state;

  // Create a CHILD SPAN for this turn as an LLM span
  const turnSpan = rootSpan.startSpan({
    name: `turn_${turnCount}`,
    type: "llm",
  });

  try {
    const lastMessage = messages[messages.length - 1];

    turnSpan.log({
      input: {
        turnNumber: turnCount,
        userMessage: lastMessage.content,
      }
    });

    // Call the LLM
    const response = await llm.invoke(messages);

    turnSpan.log({
      output: {
        turnNumber: turnCount,
        assistantMessage: response.content,
      },
      metadata: {
        model: "gpt-4o-mini",
        messageCount: messages.length + 1,
      }
    });

    // Log summary to ROOT SPAN (key pattern!)
    rootSpan.log({
      metadata: {
        [`turn_${turnCount}_completed`]: true,
        [`turn_${turnCount}_user`]: lastMessage.content,
        [`turn_${turnCount}_assistant`]: response.content,
      }
    });

    console.log(`\nTurn ${turnCount}:`);
    console.log(`User: ${lastMessage.content}`);
    console.log(`Assistant: ${response.content}`);

    return {
      messages: [response],
      turnCount: turnCount + 1,
    };

  } finally {
    // Always end child span
    turnSpan.end();
  }
}

// Build the graph
function createConversationGraph() {
  const graph = new StateGraph(ConversationState)
    .addNode("turn", conversationTurn)
    .addEdge("__start__", "turn")
    .addEdge("turn", "__end__");

  return graph.compile();
}

async function runMultiTurnConversation() {
  console.log("Starting multi-turn conversation with root span pattern...\n");

  const conversationMessages: HumanMessage[] = [
    new HumanMessage("What is the capital of France?"),
    new HumanMessage("What is the population of that city?"),
    new HumanMessage("What are some famous landmarks there?"),
  ];

  // Create ROOT SPAN for the entire conversation
  await logger.traced(async (rootSpan) => {
    try {
      // STEP 1: Log initial input to ROOT SPAN
      rootSpan.log({
        input: {
          conversationType: "multi_turn",
          totalTurns: conversationMessages.length,
          messages: conversationMessages.map(m => m.content),
        }
      });

      const graph = createConversationGraph();
      let currentMessages: BaseMessage[] = [];
      let allResponses: string[] = [];

      // STEP 2: Execute each turn (creates child spans)
      for (let i = 0; i < conversationMessages.length; i++) {
        console.log(`\n${"=".repeat(60)}`);

        currentMessages.push(conversationMessages[i]);

        // Invoke the graph with the root span reference
        const result = await graph.invoke({
          messages: currentMessages,
          turnCount: i + 1,
          rootSpan: rootSpan, // Pass root span to each turn
        });

        // Add AI response to conversation history
        currentMessages.push(result.messages[result.messages.length - 1]);
        allResponses.push(result.messages[result.messages.length - 1].content as string);
      }

      // STEP 3: Build final result
      const finalResult = {
        conversationType: "multi_turn",
        totalTurns: conversationMessages.length,
        conversation: conversationMessages.map((msg, idx) => ({
          turn: idx + 1,
          user: msg.content,
          assistant: allResponses[idx],
        })),
        success: true,
      };

      // STEP 4: CRITICAL - Log final output to ROOT SPAN after all child spans complete
      rootSpan.log({
        output: finalResult,
        metadata: {
          success: true,
          totalTurns: conversationMessages.length,
          conversationCompleted: true,
          completedAt: new Date().toISOString(),
        }
      });

      rootSpan.end();

      console.log(`\n${"=".repeat(60)}`);
      console.log("\n✓ Conversation completed and logged to root span");

    } catch (error) {
      rootSpan.log({
        error: error instanceof Error ? error.message : String(error),
        metadata: {
          success: false,
          errorType: error instanceof Error ? error.constructor.name : "Unknown",
        }
      });

      rootSpan.end();
      throw error;
    }
  }, {
    name: "multi_turn_conversation",
    tags: ["langgraph", "conversation", "multi-turn"],
  });

  // Flush to ensure all spans are sent to Braintrust
  await logger.flush();
}

// Run the example
runMultiTurnConversation()
  .then(() => {
    console.log("\n✓ Example completed successfully");
    process.exit(0);
  })
  .catch((error) => {
    console.error("\n✗ Error running example:", error);
    process.exit(1);
  });