"""Tests for the persistent memory system.

Tests cover:
  - MemoryStore: facts, goals, summaries, checkpoints
  - ConversationSummarizer: message formatting, summary parsing
  - ConversationManager: smart context window, summarization trigger
  - MemoryTool: all actions
"""

import asyncio
import json
import os
import tempfile
import time

import pytest
import pytest_asyncio

# ── MemoryStore tests ──────────────────────────────────────────


@pytest_asyncio.fixture
async def memory():
    """Create a temporary MemoryStore for testing."""
    from plutus.core.memory import MemoryStore

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    store = MemoryStore(db_path)
    await store.initialize()
    yield store
    await store.close()
    os.unlink(db_path)


@pytest.mark.asyncio
async def test_facts_crud(memory):
    """Test creating, reading, searching, and deleting facts."""
    # Store a fact
    fact_id = await memory.store_fact("task_context", "User wants a React app", source="agent")
    assert fact_id > 0

    # Retrieve facts
    facts = await memory.get_facts(category="task_context")
    assert len(facts) == 1
    assert facts[0]["content"] == "User wants a React app"
    assert facts[0]["category"] == "task_context"

    # Store duplicate — should update, not create new
    dup_id = await memory.store_fact("task_context", "User wants a React app", source="agent")
    assert dup_id == fact_id  # Same ID

    facts = await memory.get_facts()
    assert len(facts) == 1  # Still just one

    # Search facts
    results = await memory.search_facts("React")
    assert len(results) == 1

    results = await memory.search_facts("Angular")
    assert len(results) == 0

    # Delete fact
    await memory.delete_fact(fact_id)
    facts = await memory.get_facts()
    assert len(facts) == 0


@pytest.mark.asyncio
async def test_goals_crud(memory):
    """Test creating, reading, and updating goals."""
    await memory.create_conversation("conv-1", "Test conversation")

    # Add goals
    g1 = await memory.add_goal("Build REST API", conversation_id="conv-1", priority=10)
    g2 = await memory.add_goal("Add authentication", conversation_id="conv-1", priority=5)
    g3 = await memory.add_goal("Write tests", conversation_id="conv-1", priority=1)

    assert g1 > 0
    assert g2 > 0
    assert g3 > 0

    # Get active goals (should be ordered by priority DESC)
    active = await memory.get_active_goals(conversation_id="conv-1")
    assert len(active) == 3
    assert active[0]["description"] == "Build REST API"
    assert active[0]["priority"] == 10

    # Complete a goal
    await memory.update_goal_status(g1, "completed")
    active = await memory.get_active_goals(conversation_id="conv-1")
    assert len(active) == 2

    # Get all goals (including completed)
    all_goals = await memory.get_all_goals(conversation_id="conv-1")
    assert len(all_goals) == 3


@pytest.mark.asyncio
async def test_conversation_summaries(memory):
    """Test saving and retrieving conversation summaries."""
    await memory.create_conversation("conv-1", "Test")

    summary_data = {
        "goals": ["Build a web app"],
        "progress": ["Set up project"],
        "current_state": "Working on frontend",
        "key_facts": ["Using React + TypeScript"],
        "next_steps": ["Add routing"],
        "summary": "User wants a web app. Project set up with React.",
    }

    await memory.save_conversation_summary("conv-1", summary_data)

    # Retrieve
    retrieved = await memory.get_conversation_summary("conv-1")
    assert retrieved is not None
    assert retrieved["goals"] == ["Build a web app"]
    assert retrieved["current_state"] == "Working on frontend"

    # Update (upsert)
    summary_data["progress"].append("Added frontend components")
    await memory.save_conversation_summary("conv-1", summary_data)

    retrieved = await memory.get_conversation_summary("conv-1")
    assert len(retrieved["progress"]) == 2


@pytest.mark.asyncio
async def test_checkpoints(memory):
    """Test saving and retrieving checkpoints."""
    await memory.create_conversation("conv-1", "Test")

    # Save checkpoints
    cp1 = await memory.save_checkpoint(
        "conv-1",
        {"working_on": "Step 1", "done": [], "next": ["Step 2"]},
        checkpoint_type="auto",
    )
    assert cp1 > 0

    cp2 = await memory.save_checkpoint(
        "conv-1",
        {"working_on": "Step 2", "done": ["Step 1"], "next": ["Step 3"]},
        checkpoint_type="manual",
    )

    # Get latest
    latest = await memory.get_latest_checkpoint("conv-1")
    assert latest is not None
    assert latest["state_data"]["working_on"] == "Step 2"
    assert latest["checkpoint_type"] == "manual"

    # List all
    all_cps = await memory.list_checkpoints("conv-1")
    assert len(all_cps) == 2


@pytest.mark.asyncio
async def test_memory_stats(memory):
    """Test memory statistics."""
    await memory.create_conversation("conv-1", "Test")
    await memory.add_message("conv-1", "user", content="Hello")
    await memory.add_message("conv-1", "assistant", content="Hi there!")
    await memory.store_fact("general", "Test fact")
    await memory.add_goal("Test goal", conversation_id="conv-1")

    stats = await memory.get_memory_stats()
    assert stats["conversations"] == 1
    assert stats["messages"] == 2
    assert stats["facts"] == 1
    assert stats["active_goals"] == 1


# ── Summarizer tests ──────────────────────────────────────────


def test_format_messages_for_summary():
    """Test that messages are correctly formatted for the summarizer."""
    from plutus.core.summarizer import _format_messages_for_summary

    messages = [
        {"role": "system", "content": "You are Plutus"},
        {"role": "user", "content": "Build me a web app"},
        {"role": "assistant", "content": "I'll create a plan first."},
        {"role": "assistant", "content": None, "tool_calls": [
            {"name": "plan", "arguments": {"action": "create", "title": "Build web app"}}
        ]},
        {"role": "tool", "content": "Plan created", "tool_call_id": "tc_1"},
    ]

    text = _format_messages_for_summary(messages)

    # System messages should be skipped
    assert "You are Plutus" not in text
    # User and assistant messages should be included
    assert "[User]: Build me a web app" in text
    assert "[Assistant]: I'll create a plan first." in text
    assert "[Assistant called plan]" in text
    assert "[Tool Result" in text


def test_parse_summary_json():
    """Test parsing a valid JSON summary."""
    from plutus.core.summarizer import _parse_summary

    json_text = json.dumps({
        "goals": ["Build a web app"],
        "progress": ["Set up project"],
        "current_state": "Working on frontend",
        "key_decisions": ["Using React"],
        "key_facts": ["Project at /home/user/app"],
        "blockers": [],
        "next_steps": ["Add routing"],
        "summary": "Building a web app with React.",
    })

    result = _parse_summary(json_text)
    assert result["goals"] == ["Build a web app"]
    assert result["current_state"] == "Working on frontend"
    assert "created_at" in result


def test_parse_summary_markdown_block():
    """Test parsing JSON wrapped in markdown code blocks."""
    from plutus.core.summarizer import _parse_summary

    text = '```json\n{"goals": ["Test"], "progress": [], "current_state": "", "key_decisions": [], "key_facts": [], "blockers": [], "next_steps": [], "summary": "Test"}\n```'

    result = _parse_summary(text)
    assert result["goals"] == ["Test"]


def test_parse_summary_invalid_json():
    """Test fallback when JSON parsing fails."""
    from plutus.core.summarizer import _parse_summary

    result = _parse_summary("This is not JSON at all")
    assert result["summary"] == "This is not JSON at all"
    assert result["goals"] == []


def test_fallback_summary():
    """Test the fallback summary when LLM fails."""
    from plutus.core.summarizer import _fallback_summary

    messages = [
        {"role": "user", "content": "Build me a React dashboard"},
        {"role": "assistant", "content": "Sure, let me start."},
        {"role": "user", "content": "Add charts too"},
    ]

    result = _fallback_summary(messages)
    assert len(result["goals"]) == 1
    assert "React dashboard" in result["goals"][0]
    assert "3 messages" in result["summary"]


def test_format_summary_for_context():
    """Test formatting a summary for injection into the system prompt."""
    from plutus.core.summarizer import ConversationSummarizer

    # We don't need a real LLM client for this method
    summarizer = ConversationSummarizer(llm_client=None)

    summary = {
        "goals": ["Build a web app", "Add user auth"],
        "progress": ["Project set up", "Frontend done"],
        "current_state": "Working on backend API",
        "key_decisions": ["Using FastAPI for backend"],
        "key_facts": ["Project at /home/user/app", "Using PostgreSQL"],
        "blockers": ["Need to install PostgreSQL"],
        "next_steps": ["Create API endpoints", "Add auth middleware"],
        "summary": "Building a full-stack web app with React frontend and FastAPI backend.",
    }

    text = summarizer.format_summary_for_context(summary)

    assert "## Conversation History Summary" in text
    assert "Build a web app" in text
    assert "Working on backend API" in text
    assert "Using FastAPI for backend" in text
    assert "/home/user/app" in text
    assert "Create API endpoints" in text


# ── ConversationManager tests ─────────────────────────────────


@pytest_asyncio.fixture
async def conversation(memory):
    """Create a ConversationManager for testing."""
    from plutus.core.conversation import ConversationManager
    from plutus.core.planner import PlanManager

    planner = PlanManager(memory)
    await planner.initialize()

    # No summarizer for basic tests (would need LLM)
    manager = ConversationManager(
        memory=memory,
        context_window=10,
        planner=planner,
        summarizer=None,
    )
    return manager


@pytest.mark.asyncio
async def test_conversation_lifecycle(conversation):
    """Test starting a conversation, adding messages, and building context."""
    conv_id = await conversation.start_conversation(title="Test Chat")
    assert conv_id is not None
    assert conversation.conversation_id == conv_id

    # Add messages
    await conversation.add_user_message("Hello, build me an app")
    await conversation.add_assistant_message(content="Sure, I'll create a plan.")

    # Build messages
    messages = await conversation.build_messages()

    # Should have: system + user + assistant
    assert len(messages) >= 3
    assert messages[0]["role"] == "system"

    # Find user and assistant messages
    user_msgs = [m for m in messages if m["role"] == "user"]
    assistant_msgs = [m for m in messages if m["role"] == "assistant"]
    assert len(user_msgs) == 1
    assert len(assistant_msgs) == 1


@pytest.mark.asyncio
async def test_context_window_limits(conversation):
    """Test that context window limits are respected."""
    conv_id = await conversation.start_conversation(title="Long Chat")

    # Add more messages than the context window (10)
    for i in range(15):
        await conversation.add_user_message(f"Message {i}")
        await conversation.add_assistant_message(content=f"Response {i}")

    # Build messages — should only have recent ones
    messages = await conversation.build_messages()

    # Count non-system messages
    non_system = [m for m in messages if m["role"] != "system"]
    # Should be at most context_window messages
    assert len(non_system) <= 10


@pytest.mark.asyncio
async def test_plan_injection(conversation):
    """Test that active plans are injected into context."""
    conv_id = await conversation.start_conversation(title="Plan Test")

    # Create a plan via the planner
    await conversation._planner.create_plan(
        title="Build App",
        steps=[
            {"description": "Set up project"},
            {"description": "Create components"},
        ],
        goal="Build a React app",
        conversation_id=conv_id,
    )

    await conversation.add_user_message("What's the plan?")

    messages = await conversation.build_messages()

    # Find the system message with the plan
    plan_messages = [
        m for m in messages
        if m["role"] == "system" and "Active Plan" in (m.get("content") or "")
    ]
    assert len(plan_messages) == 1
    assert "Build App" in plan_messages[0]["content"]


@pytest.mark.asyncio
async def test_facts_injection(conversation):
    """Test that facts are injected into context."""
    conv_id = await conversation.start_conversation(title="Facts Test")

    # Store some facts
    await conversation._memory.store_fact("task_context", "User prefers TypeScript")
    await conversation._memory.store_fact("file_path", "Project at /home/user/app")

    await conversation.add_user_message("Continue working")

    messages = await conversation.build_messages()

    # Find the system message with facts
    fact_messages = [
        m for m in messages
        if m["role"] == "system" and "Known facts" in (m.get("content") or "")
    ]
    assert len(fact_messages) == 1
    assert "TypeScript" in fact_messages[0]["content"]


# ── Summary merging tests ─────────────────────────────────────


def test_merge_summaries():
    """Test that summaries are correctly merged."""
    from plutus.core.conversation import _merge_summaries

    old = {
        "goals": ["Build a web app"],
        "progress": ["Set up project"],
        "key_facts": ["Using React"],
        "key_decisions": ["Chose React over Vue"],
        "current_state": "Old state",
        "next_steps": ["Old next step"],
    }

    new = {
        "goals": ["Build a web app", "Add auth"],
        "progress": ["Added components"],
        "key_facts": ["Using React", "Database is PostgreSQL"],
        "key_decisions": ["Chose FastAPI for backend"],
        "current_state": "New state",
        "next_steps": ["New next step"],
    }

    merged = _merge_summaries(old, new)

    # Goals should be union
    assert "Build a web app" in merged["goals"]
    assert "Add auth" in merged["goals"]

    # Key facts should be union
    assert "Using React" in merged["key_facts"]
    assert "Database is PostgreSQL" in merged["key_facts"]

    # Key decisions should be accumulated
    assert "Chose React over Vue" in merged["key_decisions"]
    assert "Chose FastAPI for backend" in merged["key_decisions"]

    # Current state should be from new
    assert merged["current_state"] == "New state"

    # Progress should include old items
    assert "Set up project" in merged["progress"]
    assert "Added components" in merged["progress"]


# ── MemoryTool tests ──────────────────────────────────────────


@pytest_asyncio.fixture
async def memory_tool(memory, conversation):
    """Create a MemoryTool for testing."""
    from plutus.tools.memory_tool import MemoryTool

    await conversation.start_conversation(title="Memory Tool Test")
    tool = MemoryTool(memory, conversation)
    return tool


@pytest.mark.asyncio
async def test_memory_tool_save_and_recall(memory_tool):
    """Test saving and recalling facts via the memory tool."""
    # Save a fact
    result = await memory_tool.execute(
        action="save_fact",
        category="task_context",
        content="User wants a dashboard with charts",
    )
    data = json.loads(result)
    assert data["saved"] is True
    assert data["fact_id"] > 0

    # Recall facts
    result = await memory_tool.execute(
        action="recall_facts",
        category="task_context",
    )
    data = json.loads(result)
    assert data["count"] == 1
    assert "dashboard" in data["facts"][0]["content"]


@pytest.mark.asyncio
async def test_memory_tool_goals(memory_tool):
    """Test goal management via the memory tool."""
    # Add a goal
    result = await memory_tool.execute(
        action="add_goal",
        goal_description="Build user authentication system",
    )
    data = json.loads(result)
    assert data["created"] is True
    goal_id = data["goal_id"]

    # List goals
    result = await memory_tool.execute(action="list_goals")
    data = json.loads(result)
    assert data["count"] == 1

    # Complete goal
    result = await memory_tool.execute(
        action="complete_goal",
        goal_id=goal_id,
    )
    data = json.loads(result)
    assert data["status"] == "completed"

    # List goals again (should be empty since completed)
    result = await memory_tool.execute(action="list_goals")
    data = json.loads(result)
    assert data["count"] == 0


@pytest.mark.asyncio
async def test_memory_tool_checkpoint(memory_tool):
    """Test checkpoint operations via the memory tool."""
    # Save checkpoint
    result = await memory_tool.execute(
        action="checkpoint",
        checkpoint_data={
            "working_on": "Building API endpoints",
            "done": ["Project setup", "Database schema"],
            "next": ["Add authentication", "Write tests"],
        },
    )
    data = json.loads(result)
    assert data["saved"] is True

    # Get checkpoint
    result = await memory_tool.execute(action="get_checkpoint")
    data = json.loads(result)
    assert data["checkpoint"] is not None
    assert data["checkpoint"]["state_data"]["working_on"] == "Building API endpoints"


@pytest.mark.asyncio
async def test_memory_tool_stats(memory_tool):
    """Test stats via the memory tool."""
    result = await memory_tool.execute(action="stats")
    data = json.loads(result)
    assert "conversations" in data
    assert "messages" in data
    assert "facts" in data


@pytest.mark.asyncio
async def test_memory_tool_search(memory_tool):
    """Test searching facts via the memory tool."""
    # Save some facts
    await memory_tool.execute(
        action="save_fact", category="technical", content="Using PostgreSQL database"
    )
    await memory_tool.execute(
        action="save_fact", category="technical", content="Using Redis for caching"
    )
    await memory_tool.execute(
        action="save_fact", category="decision", content="Chose React for frontend"
    )

    # Search
    result = await memory_tool.execute(action="search_facts", content="PostgreSQL")
    data = json.loads(result)
    assert data["count"] == 1
    assert "PostgreSQL" in data["facts"][0]["content"]


@pytest.mark.asyncio
async def test_memory_tool_error_handling(memory_tool):
    """Test error handling in the memory tool."""
    # Save fact without content
    result = await memory_tool.execute(action="save_fact")
    assert "[ERROR]" in result

    # Add goal without description
    result = await memory_tool.execute(action="add_goal")
    assert "[ERROR]" in result

    # Unknown action
    result = await memory_tool.execute(action="unknown_action")
    assert "[ERROR]" in result


# ── Integration test ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_full_memory_workflow(memory):
    """Test the full memory workflow: conversation → facts → goals → summary → checkpoint."""
    from plutus.core.conversation import ConversationManager
    from plutus.core.planner import PlanManager
    from plutus.tools.memory_tool import MemoryTool

    planner = PlanManager(memory)
    await planner.initialize()

    conversation = ConversationManager(
        memory=memory,
        context_window=10,
        planner=planner,
        summarizer=None,
    )

    conv_id = await conversation.start_conversation(title="Full Workflow Test")
    tool = MemoryTool(memory, conversation)

    # 1. User asks for something
    await conversation.add_user_message("Build me a React dashboard with charts")

    # 2. Agent saves the goal
    result = await tool.execute(
        action="add_goal",
        goal_description="Build React dashboard with charts",
    )
    goal_data = json.loads(result)

    # 3. Agent saves key facts
    await tool.execute(
        action="save_fact",
        category="task_context",
        content="User wants a React dashboard with charts",
    )
    await tool.execute(
        action="save_fact",
        category="decision",
        content="Using Chart.js for charts",
    )

    # 4. Agent creates a plan
    plan = await planner.create_plan(
        title="Build Dashboard",
        steps=[
            {"description": "Set up React project"},
            {"description": "Create layout components"},
            {"description": "Add Chart.js charts"},
            {"description": "Test and deploy"},
        ],
        goal="Build React dashboard with charts",
        conversation_id=conv_id,
    )

    # 5. Agent works on step 1
    await planner.update_step(plan["id"], 0, "in_progress")
    await conversation.add_assistant_message(content="Setting up the React project...")
    await planner.update_step(plan["id"], 0, "done", result="Created with Vite + React")

    # 6. Agent saves a checkpoint
    await tool.execute(
        action="checkpoint",
        checkpoint_data={
            "working_on": "Create layout components",
            "done": ["Set up React project"],
            "next": ["Add Chart.js charts", "Test and deploy"],
        },
    )

    # 7. Build messages — should include plan, facts, goals
    messages = await conversation.build_messages()

    # Verify plan is in context
    plan_in_context = any(
        "Active Plan" in (m.get("content") or "")
        for m in messages
        if m["role"] == "system"
    )
    assert plan_in_context, "Active plan should be in context"

    # Verify facts are in context
    facts_in_context = any(
        "Known facts" in (m.get("content") or "")
        for m in messages
        if m["role"] == "system"
    )
    assert facts_in_context, "Facts should be in context"

    # 8. Verify stats
    stats = await memory.get_memory_stats()
    assert stats["conversations"] == 1
    assert stats["facts"] == 2
    assert stats["active_goals"] == 1
    assert stats["checkpoints"] == 1

    # 9. Complete the goal
    await tool.execute(action="complete_goal", goal_id=goal_data["goal_id"])
    stats = await memory.get_memory_stats()
    assert stats["active_goals"] == 0
