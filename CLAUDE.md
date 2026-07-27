# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

GenerativeAgentsCN is a Chinese-localized version of Stanford's Generative Agents simulation (AI Town). It simulates 25 AI agents living in a virtual world, driven entirely by LLMs. This is a refactored and deeply localized version based on the [wounderland](https://github.com/Archermmt/wounderland) project.

**Key Features:**
- All prompts rewritten in Chinese for better compatibility with Chinese LLMs (Qwen, GLM-4, etc.)
- Complete local deployment support via Ollama
- Checkpoint resume capability for interrupted simulations
- Timeline-based replay system with web interface
- Structured output using Pydantic models instead of regex parsing

## Core Commands

### Environment Setup
```bash
# Create conda environment
conda create -n generative_agents_cn python=3.12
conda activate generative_agents_cn

# Install dependencies
pip install -r requirements.txt
```

### Running Simulations
```bash
conda activate generative_agents_cn
cd generative_agents

# Start new simulation
python start.py --name sim-test --start "20250213-09:30" --step 10 --stride 10

# Resume from checkpoint
python start.py --name sim-test --resume --step 10 --stride 10

# Parameters:
#   --name: Unique simulation name
#   --start: Starting time (format: YYYYMMDD-HH:MM)
#   --resume: Resume from last checkpoint
#   --step: Number of steps to simulate
#   --stride: Minutes per step (e.g., 10 = time advances 10 min/step)
#   --verbose: Logging level (debug/info)
#   --log: Log file name (optional)
```

### Generating Replay Data
```bash
# Compress simulation data for replay
python compress.py --name sim-test

# Outputs:
#   results/compressed/sim-test/movement.json - Replay data
#   results/compressed/sim-test/simulation.md - Timeline markdown report
```

### Running Replay Server
```bash
# Start Flask replay server
python replay.py

# Access in browser:
# http://127.0.0.1:5000/?name=sim-test&step=0&speed=2&zoom=0.8
# Parameters:
#   name: Simulation name
#   step: Starting step (0 = from beginning)
#   speed: Playback speed 0-5 (0=slowest, 5=fastest)
#   zoom: Zoom ratio (e.g., 0.8)
```

## Architecture Overview

### Module Structure

```
generative_agents/
├── modules/
│   ├── agent.py          # Agent: Core agent class coordinating all subsystems
│   ├── game.py           # Game: Manages simulation environment and agents
│   ├── maze.py           # Maze: Spatial environment and pathfinding
│   ├── memory/           # Memory subsystems
│   │   ├── action.py     # Action: Current and planned agent actions
│   │   ├── associate.py  # Associate: Vector-based memory retrieval
│   │   ├── event.py      # Event: Structured representation of events
│   │   ├── schedule.py   # Schedule: Daily planning and decomposition
│   │   └── spatial.py    # Spatial: Hierarchical location knowledge
│   ├── model/
│   │   └── llm_model.py  # LLM providers (Ollama, OpenAI)
│   ├── prompt/
│   │   └── scratch.py    # Scratch: Prompt template management
│   ├── storage/
│   │   └── index.py      # LlamaIndex integration for embeddings
│   └── utils/            # Utilities (timer, logging, arguments)
├── data/
│   ├── config.json       # LLM and agent configuration
│   └── prompts/          # 30+ Chinese prompt templates
├── start.py              # Simulation entry point
├── compress.py           # Data compression for replay
└── replay.py             # Flask replay server
```

### Core Agent Architecture

The `Agent` class ([agent.py](generative_agents/modules/agent.py)) implements the agent's cognitive cycle:

1. **Perception** (`percept()` at [agent.py:271](generative_agents/modules/agent.py#L271))
   - Observes events within vision radius (configurable in config.json)
   - Filters by attention bandwidth
   - Adds perceived events to associative memory with poignancy scores

2. **Memory Systems**
   - **Spatial** ([spatial.py](generative_agents/modules/memory/spatial.py)): Tree-structured location knowledge (world → sector → arena → object)
   - **Associate** ([associate.py](generative_agents/modules/memory/associate.py)): Vector-based retrieval using LlamaIndex with recency/relevance/importance scoring
   - **Schedule** ([schedule.py](generative_agents/modules/memory/schedule.py)): Hierarchical daily plans with decomposition
   - **Action** ([action.py](generative_agents/modules/memory/action.py)): Current action state with duration/timing

3. **Planning** (`make_schedule()` at [agent.py:181](generative_agents/modules/agent.py#L181))
   - Daily schedule generation at wake-up
   - Hierarchical decomposition of plans into sub-activities
   - Schedule revision for conversations and waiting

4. **Reaction** (`_reaction()` at [agent.py:459](generative_agents/modules/agent.py#L459))
   - Decision to chat with other agents (uses `decide_chat` prompt)
   - Decision to wait for other agents (uses `decide_wait` prompt)
   - Chat termination logic with repeat detection

5. **Reflection** (`reflect()` at [agent.py:335](generative_agents/modules/agent.py#L335))
   - Triggered when poignancy accumulation exceeds threshold
   - Generates high-level insights from recent memories
   - Creates new "thought" concepts with evidence links

### Agent Thinking Flow

The `think()` method ([agent.py:107](generative_agents/modules/agent.py#L107)) orchestrates:
1. Movement to target location
2. Schedule creation/decomposition if needed
3. Sleep handling (transitions to sleep location)
4. Perception of environment (if awake)
5. Planning/reaction to other agents (if awake)
6. Reflection when poignancy threshold reached
7. Pathfinding to next destination

### LLM Integration

**Providers** ([llm_model.py](generative_agents/modules/model/llm_model.py)):
- `OllamaLLMModel`: Local deployment via Ollama with structured output support
- `OpenAILLMModel`: OpenAI-compatible APIs (for cloud providers)

**Structured Output:**
- Uses Pydantic models for response validation (replaced regex parsing)
- Filters `<think>` tags from DeepSeek-R1 and similar models
- Falls back gracefully on parse failures

**Prompt Management** ([scratch.py](generative_agents/modules/prompt/scratch.py)):
- Templates stored in [data/prompts/](generative_agents/data/prompts/)
- 30+ specialized prompts for different agent behaviors
- All prompts fully localized to Chinese

### Configuration System

**[data/config.json](generative_agents/data/config.json)** structure:
```json
{
  "agent": {
    "percept": {
      "mode": "box",
      "vision_r": 8,        // Vision radius in tiles
      "att_bandwidth": 8    // Max events to perceive per step
    },
    "schedule": {
      "max_try": 5,
      "diversity": 5
    },
    "think": {
      "llm": {
        "provider": "ollama",  // or "openai"
        "model": "qwen3:4b-instruct-2507-q4_K_M",
        "base_url": "http://127.0.0.1:11434/v1",
        "api_key": ""
      },
      "interval": 1000,
      "poignancy_max": 150  // Reflection threshold
    },
    "chat_iter": 4,         // Max conversation rounds
    "associate": {
      "embedding": {
        "provider": "ollama",
        "model": "qwen3-embedding:0.6b-q8_0",
        "base_url": "http://127.0.0.1:11434",
        "api_key": ""
      },
      "retention": 8        // Max retrieved concepts
    }
  }
}
```

### Checkpoint System

**Data Persistence:**
- Checkpoints saved to `results/checkpoints/{name}/`
- Each step creates `simulate-{timestamp}.json` with full agent state
- Conversation log in `conversation.json`
- Agent memory persisted in `storage/{agent_name}/` (LlamaIndex vector store)

**Resume Logic** ([start.py:111](generative_agents/start.py#L111)):
- Reads last checkpoint from directory
- Restores agent state (position, schedule, memory, conversations)
- Continues time from last saved step + stride

### Maze and Pathfinding

**Maze Structure** ([maze.py](generative_agents/modules/maze.py)):
- Hierarchical addressing: world → sector → arena → game_object
- Tile-based collision detection
- A* pathfinding with collision avoidance
- Dynamic event placement on tiles (agent actions, object states)

**Address Format:**
- Example: `["小镇", "公园", "林荫道", "长凳"]`
- Used for location finding, pathfinding targets, and event association

## Working with Prompts

**Prompt Template System:**
- Located in [data/prompts/](generative_agents/data/prompts/)
- Uses Python `string.Template` with `$variable` substitution
- Loaded by `Scratch.build_prompt()` ([scratch.py:22](generative_agents/modules/prompt/scratch.py#L22))

**Key Prompts:**
- `schedule_daily.txt`: Daily schedule generation
- `schedule_decompose.txt`: Activity decomposition
- `decide_chat.txt`: Conversation initiation decision
- `generate_chat.txt`: Conversation response generation
- `reflect_insights.txt`: Reflection and insight generation
- `poignancy_event.txt`/`poignancy_chat.txt`: Importance scoring

**Adding New Prompts:**
1. Create `.txt` file in `data/prompts/`
2. Add method `prompt_{name}()` in [scratch.py](generative_agents/modules/prompt/scratch.py)
3. Define Pydantic response model with `res` field
4. Return `Result(prompt, callback, failsafe, ResponseModel)`

## Agent Personas

**25 Agents Defined** in [start.py:12](generative_agents/start.py#L12):
- Students, professors, business owners, artists, etc.
- Each has unique config in `frontend/static/assets/village/agents/{name}/agent.json`
- Config includes: age, innate traits, learned traits, lifestyle, daily_plan, spatial memory

## Important Implementation Details

**Sleep/Wake Cycle:**
- Sleep state checked via `is_awake()` ([agent.py:664](generative_agents/modules/agent.py#L664))
- Sleep action prevents perception, planning, and reactions
- Wake-up triggers schedule regeneration

**Conversation Mechanics:**
- Multi-turn dialogues (configurable via `chat_iter`)
- Repeat detection to prevent loops ([agent.py:540](generative_agents/modules/agent.py#L540))
- Conversation summarization stored in associative memory
- Conversation history persisted in checkpoint for replay

**Memory Retrieval:**
- Combines recency, relevance, and importance scores ([associate.py:82](generative_agents/modules/memory/associate.py#L82))
- Configurable decay factor and weights
- Expired concepts filtered during retrieval

**Event System:**
- Events have structure: subject + predicate + object
- Events carry emoji for visualization
- Events stored on maze tiles and in agent memory
- Events link to hierarchical addresses

## Testing and Debugging

**Logging:**
- Controlled via `--verbose` flag (debug/info)
- Agent summaries logged each step
- LLM prompt/response logged in debug mode
- LLM statistics tracked (success/fail/retry counts)

**Checking Simulation Progress:**
- Monitor checkpoint files in `results/checkpoints/{name}/`
- Review `simulation.md` after compression for timeline view
- Check conversation.json for chat history

**Common Issues:**
- Agents not waking: Check sleep detection logic and action state
- Path errors: Verify maze.json integrity and collision map
- LLM failures: Check Ollama server status and model availability
- Memory issues: Reduce vision_r or att_bandwidth in config.json
