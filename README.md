# kleeborp-ai

A modular, event-driven AI application with Discord voice support, memory (RAG), speech-to-text, text-to-speech, websocket APIs, and tool integrations via MCP. Built with **Python 3.12+** and managed using **uv**.

This project is designed to be highly extensible: features are implemented as independent modules that can be enabled or disabled via configuration.

---

## Features

* **LLM Brain** – Central reasoning loop backed by configurable LLM providers
* **Memory + RAG** – Persistent vector memory using ChromaDB
* **Discord Voice Bot** – Auto-join voice channels, receive audio, and respond
* **Whisper STT** – Real-time speech-to-text with worker pooling
* **TTS** – Azure / ElevenLabs via `realtimetts`
* **WebSocket API** – External clients can interact in real time
* **MCP Tooling** – External tools (e.g. Brave Search) via Model Context Protocol
* **Modular Architecture** – Clean separation of core, services, modules, and events

---

## Requirements

* Python **>= 3.12**
* [uv](https://docs.astral.sh/uv/) installed
* Optional external services depending on enabled modules:

  * Discord Bot Token
  * LLM API keys (Groq, OpenRouter, etc.)
  * Azure Speech resource (for TTS)
  * Brave Search API key (for MCP tools)

---

## Installation

Clone the repository:

```bash
git clone https://github.com/yourname/kleeborp-ai.git
cd kleeborp-ai
```

Install dependencies using **uv**:

```bash
uv sync
```

---

## Configuration

Copy the example config and edit it:

```bash
cp config.example.toml config.toml
```

## Running the Project

Start the application using **uv**:

```bash
uv run ./src/run.py
```

This will:

* Load configuration from `config.toml`
* Initialize the application core
* Register enabled modules
* Start background services (Discord, WebSocket, STT, etc.)

---

## Project Structure

```text
kleeborp-ai/
├── src/
│   ├── run.py               # Entry point
│   ├── core/                # Application core & lifecycle
│   │   ├── application.py
│   │   ├── config.py
│   │   ├── event_bus.py
│   │   └── module_manager.py
│   ├── modules/             # Feature modules (enable via config)
│   │   ├── brain/
│   │   ├── memory/
│   │   ├── discord/
│   │   ├── whisper/
│   │   ├── tts/
│   │   ├── tools/
│   │   └── persona/
│   ├── services/            # Long-running services
│   │   ├── llm_client.py
│   │   └── websocket_server.py
│   ├── events/              # Event definitions & handlers
│   ├── prompts/             # Prompt templates
│   └── utils/               # Audio, logging, helpers
├── memory/                  # Persistent ChromaDB storage
├── assets/                  # Sound effects and media
├── mcp-servers/             # MCP server configs
├── config.toml              # Runtime configuration
├── pyproject.toml           # Project metadata & dependencies
├── uv.lock                  # Locked dependency versions
└── README.md
```

---

## Modules

Each module lives under `src/modules/` and:

* Can be enabled/disabled via `config.toml`
* Registers itself with the `ModuleManager`
* Communicates through the central `EventBus`

This keeps systems decoupled and easy to extend.

---

## Development Notes

* Uses **event-driven architecture** instead of tight coupling
* Designed for experimentation with multiple LLM providers
* Memory is persisted locally via ChromaDB
* Audio utilities support debugging raw PCM streams

---

## Issues & Feature Requests

GitHub issue templates are provided:

* 🐛 Bug reports
* ✨ Feature requests

Please include logs and configuration snippets when relevant.