"""
Company Brain — Decision Harness
Weave setup + W&B Inference smoke test.

This is the minimal foundation: Weave tracing is initialized and one traced
op makes a real model call through W&B Inference. The 5-agent harness gets
built on top of this later.

Run:   python main.py
Needs: WANDB_API_KEY in the environment (or a .env file). See .env.example.
"""
import os

from dotenv import load_dotenv
import weave
from openai import OpenAI

load_dotenv()

WANDB_PROJECT = os.environ.get("WANDB_PROJECT", "company-brain-harness")
WANDB_ENTITY = os.environ.get("WANDB_ENTITY")  # your W&B username or team; optional
INFERENCE_MODEL = os.environ.get(
    "WANDB_INFERENCE_MODEL", "meta-llama/Llama-3.1-8B-Instruct"
)
INFERENCE_BASE_URL = "https://api.inference.wandb.ai/v1"

# Weave + W&B Inference want "entity/project" (or just "project" -> default entity).
PROJECT_PATH = f"{WANDB_ENTITY}/{WANDB_PROJECT}" if WANDB_ENTITY else WANDB_PROJECT


def make_client() -> OpenAI:
    """OpenAI-compatible client pointed at W&B Inference.

    Weave patches the OpenAI SDK, so every call this client makes is traced
    automatically as a child of whatever @weave.op() is running.
    """
    api_key = os.environ.get("WANDB_API_KEY")
    if not api_key:
        raise RuntimeError(
            "WANDB_API_KEY is not set. Create an account at https://wandb.ai/site, "
            "copy your key from https://wandb.ai/authorize, then put it in .env "
            "(see .env.example) or run `export WANDB_API_KEY=...`."
        )
    return OpenAI(
        base_url=INFERENCE_BASE_URL,
        api_key=api_key,
        project=PROJECT_PATH,  # W&B Inference uses this for usage tracking
    )


@weave.op()
def ask(question: str) -> str:
    """A single traced model call through W&B Inference."""
    client = make_client()
    response = client.chat.completions.create(
        model=INFERENCE_MODEL,
        messages=[
            {"role": "system", "content": "You are a concise assistant."},
            {"role": "user", "content": question},
        ],
    )
    return response.choices[0].message.content


def main() -> None:
    weave.init(PROJECT_PATH)  # prints the Weave UI link to the terminal
    answer = ask("In one sentence, what is a multi-agent decision harness?")
    print("\n--- model answer ---")
    print(answer)
    print("\nTrace logged to Weave. Open the link printed above to view it.")


if __name__ == "__main__":
    main()
