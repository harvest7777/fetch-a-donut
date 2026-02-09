import hashlib
import json
import os
from datetime import datetime, UTC
from uuid import uuid4

import requests
from dotenv import load_dotenv
from uagents import Agent, Context, Protocol
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    EndSessionContent,
    TextContent,
    chat_protocol_spec,
)
from uagents_core.utils.registration import (
    RegistrationRequestCredentials,
    register_chat_agent,
)

from config import (
    AGENT_NAME,
    ASI_ONE_BASE_URL,
    ASI_ONE_MAX_TOKENS,
    ASI_ONE_MODEL,
    CONFERENCE_END_DATE,
    CONFERENCE_ID,
    CONFERENCE_NAME,
    CONFERENCE_START_DATE,
    COUPON_PREFIX,
    MIN_STORY_LENGTH,
)

load_dotenv()

# --- Clients ---
SEED_PHRASE = os.getenv("AGENT_SEED_PHRASE", "donut-agent-seed-phrase")
AGENTVERSE_KEY = os.getenv("ILABS_AGENTVERSE_API_KEY")

ASI_ONE_API_KEY = os.getenv("ASI_ONE_API_KEY")

# --- Agent ---
agent = Agent(
    name=AGENT_NAME,
    seed=SEED_PHRASE,
    port=8001,
    mailbox=True,
    handle_messages_concurrently=True,
)

protocol = Protocol(spec=chat_protocol_spec)

# --- Helpers ---

WELCOME_MESSAGE = (
    f"Welcome to Fetch-a-Donut at {CONFERENCE_NAME}! "
    f"I'm your friendly donut fairy!\n\n"
    f"Before I can grant you a magical donut coupon, I need to hear your "
    f"most epic donut story! Tell me about:\n\n"
    f"- Your craziest donut adventure\n"
    f"- Your dream donut combination\n"
    f"- A time a donut saved your day\n"
    f"- Or any donut-related tale!\n\n"
    f"The more creative and fun your story, the better your rating! "
    f"Go ahead, share your story now."
)


def _make_chat(text: str, end_session: bool = False) -> ChatMessage:
    content = [TextContent(type="text", text=text)]
    if end_session:
        content.append(EndSessionContent(type="end-session"))
    return ChatMessage(
        timestamp=datetime.now(UTC),
        msg_id=uuid4(),
        content=content,
    )


def _generate_coupon(sender: str) -> str:
    user_hash = hashlib.sha256(sender.encode()).hexdigest()[:6].upper()
    ts = datetime.now(UTC).strftime("%H%M")
    return f"{COUPON_PREFIX}-{CONFERENCE_ID}-{user_hash}-{ts}"


def _evaluate_story(story: str) -> dict:
    """Use ASI:One mini to evaluate the donut story. Returns {"score": int, "comment": str}."""
    try:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {ASI_ONE_API_KEY}",
        }
        data = {
            "model": ASI_ONE_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a fun, enthusiastic donut story judge. "
                        "The user will share a donut-related story. "
                        "Rate it from 1 to 10 and give a short, encouraging comment. "
                        'Respond ONLY with valid JSON: {"score": <int>, "comment": "<string>"}'
                    ),
                },
                {"role": "user", "content": story},
            ],
            "max_tokens": ASI_ONE_MAX_TOKENS,
        }
        resp = requests.post(
            f"{ASI_ONE_BASE_URL}/chat/completions",
            headers=headers,
            json=data,
            timeout=30,
        )
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"].strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        return json.loads(raw)
    except Exception:
        return {"score": 7, "comment": "Great story! Thanks for sharing."}


def _session_key(ctx: Context) -> str:
    return f"session_{ctx.session}"


# --- Handlers ---


@protocol.on_message(ChatMessage)
async def handle_message(ctx: Context, sender: str, msg: ChatMessage):
    # Acknowledge immediately
    await ctx.send(
        sender,
        ChatAcknowledgement(
            timestamp=datetime.now(UTC), acknowledged_msg_id=msg.msg_id
        ),
    )

    # Extract text from message
    text = ""
    for item in msg.content:
        if isinstance(item, TextContent):
            text += item.text

    text = text.strip()

    # Load session state
    session_data = ctx.storage.get(_session_key(ctx))

    # State: already received a coupon this session
    if session_data and session_data.get("state") == "completed":
        coupon = session_data.get("coupon", "N/A")
        await ctx.send(
            sender,
            _make_chat(
                f"You've already received your donut coupon this session!\n\n"
                f"Your coupon code: {coupon}\n\n"
                f"Show this code to any food vendor at {CONFERENCE_NAME} to claim your free donut.",
                end_session=True,
            ),
        )
        return

    # State: awaiting a story
    if session_data and session_data.get("state") == "awaiting_story":
        # Validate story length
        if len(text) < MIN_STORY_LENGTH:
            await ctx.send(
                sender,
                _make_chat(
                    f"That's a bit short! Tell me a real donut story "
                    f"(at least {MIN_STORY_LENGTH} characters). I'm all ears!"
                ),
            )
            return

        # Evaluate story with ASI:One
        ctx.logger.info(f"Evaluating donut story from {sender[:16]}...")
        result = _evaluate_story(text)
        score = result.get("score", 7)
        comment = result.get("comment", "Nice story!")

        # Generate coupon
        coupon = _generate_coupon(sender)

        # Save completed state
        ctx.storage.set(
            _session_key(ctx),
            {"state": "completed", "coupon": coupon},
        )

        await ctx.send(
            sender,
            _make_chat(
                f"{comment}\n\n"
                f"Your Coupon Code: {coupon}\n\n"
                f"This gets you a FREE donut of your choice!\n"
                f"Show this code to any food vendor at {CONFERENCE_NAME} "
                f"({CONFERENCE_START_DATE} - {CONFERENCE_END_DATE}).\n"
                f"Story Rating: {score}/10",
                end_session=True,
            ),
        )
        return

    # State: new conversation — send welcome and ask for story
    ctx.storage.set(_session_key(ctx), {"state": "awaiting_story"})

    await ctx.send(sender, _make_chat(WELCOME_MESSAGE))


@protocol.on_message(ChatAcknowledgement)
async def handle_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    pass


agent.include(protocol, publish_manifest=True)

# --- Agentverse README ---

README = """# Fetch-a-Donut Agent

![tag:donut-agent](https://img.shields.io/badge/donut-3D8BD3)
![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)

A fun, interactive agent that distributes donut coupons through story-based engagement.

## How It Works

1. Message the agent asking for a donut
2. Share your best donut story
3. Get a rated coupon code for a free donut!

## Features

- AI-powered story evaluation using ASI:One
- Unique coupon code generation
- One coupon per session (anti-abuse)
- Chat protocol support for asi:one
"""


@agent.on_event("startup")
async def startup_handler(ctx: Context):
    ctx.logger.info(f"Agent starting: {ctx.agent.name} at {ctx.agent.address}")

    if AGENTVERSE_KEY and SEED_PHRASE:
        try:
            register_chat_agent(
                AGENT_NAME,
                agent._endpoints[0].url,
                active=True,
                credentials=RegistrationRequestCredentials(
                    agentverse_api_key=AGENTVERSE_KEY,
                    agent_seed_phrase=SEED_PHRASE,
                ),
                readme=README,
                description=(
                    "A fun donut coupon agent! Share a donut story and "
                    "receive a free donut coupon code."
                ),
            )
            ctx.logger.info("Registered with Agentverse")
        except Exception as e:
            ctx.logger.error(f"Failed to register with Agentverse: {e}")
    else:
        ctx.logger.warning(
            "AGENTVERSE_KEY or SEED_PHRASE not set, skipping Agentverse registration"
        )


@agent.on_event("shutdown")
async def shutdown_handler(ctx: Context):
    ctx.logger.info("Donut agent shutting down...")


if __name__ == "__main__":
    agent.run()
