# Memory Lane

This project provides the backend for a hackathon project, where we combine game elements, LLMs, and generative AI.  

Our submission is a a gamified, AI-driven journaling system where players interact with a spiritual guide to process their daily experiences, transforming them into multimodal memories that can be revisited, categorized, and used for self-reflection or therapy.

- Genre: Narrative, Gamified Journal, Multimodal AI Experience, "LLM in games"
- Target Audience: General users seeking structured self-reflection. People in therapy (as a support tool for sessions). Elderly individuals (as a tool to record autobiographies or stories).
- Platform(s): PC or other device capable of running local AI models. (A key feature is that it runs locally for privacy and does not use cloud-based AI like ChatGPT).

Find the hackathon at https://acmmm2025.org/hackathon/

## How to run it

We use `uv`for the project. Check it out at https://docs.astral.sh/uv/

```
git clone https://github.com/KseniaGa/MemoryLane.git
cd MemoryLane
uv sync
uv run test_app.py
```