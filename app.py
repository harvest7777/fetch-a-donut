import hashlib
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
    CONFERENCE_ID,
    CONFERENCE_NAME,
    COUPON_PREFIX,
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
    network="testnet"
)

protocol = Protocol(spec=chat_protocol_spec)

# --- Helpers ---

WELCOME_MESSAGE = (
    f"Hi Welcome to {CONFERENCE_NAME}!\n"
    f"I'm Fetch-a-Donut agent\n\n"
    f"What is your favorite donut?"
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


def _generate_donut_response(favorite_donut: str) -> str:
    """Use ASI:One to generate a fun response about the user's favorite donut and give them their ticket."""
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
                        f"You are the Fetch-a-Donut agent at {CONFERENCE_NAME}. "
                        "The user just told you their favorite donut. "
                        "Respond in a fun, enthusiastic way acknowledging their favorite donut choice. "
                        "Then tell them: here is your ticket and your donut, enjoy! "
                        "Thank them for using Fetch-a-Donut and ASI:One. "
                        "Keep the response short and cheerful (2-3 sentences max)."
                    ),
                },
                {"role": "user", "content": f"My favorite donut is {favorite_donut}"},
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
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        return (
            f"Great choice! {favorite_donut} is an amazing donut! "
            f"Here is your ticket and your donut, enjoy! "
            f"Thank you for using Fetch-a-Donut and ASI:One!"
        )


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

    # State: already received their donut this session
    if session_data and session_data.get("state") == "completed":
        coupon = session_data.get("coupon", "N/A")
        await ctx.send(
            sender,
            _make_chat(
                f"You've already received your donut ticket!\n\n"
                f"Your ticket code: {coupon}\n\n"
                f"Enjoy your donut at {CONFERENCE_NAME}!\n\n"
                f"Thank you for using Fetch-a-Donut and ASI:One!",
                end_session=True,
            ),
        )
        return

    # State: awaiting favorite donut answer
    if session_data and session_data.get("state") == "awaiting_donut":
        ctx.logger.info(f"Generating donut response for {sender[:16]}...")

        # Generate coupon
        coupon = _generate_coupon(sender)

        # Use ASI:One to generate a fun response
        llm_response = _generate_donut_response(text)

        # Save completed state
        ctx.storage.set(
            _session_key(ctx),
            {"state": "completed", "coupon": coupon},
        )

        await ctx.send(
            sender,
            _make_chat(
                f"{llm_response}\n\n"
                f"Your Ticket Code: {coupon}\n\n"
                f"Enjoy {CONFERENCE_NAME}!\n\n"
                f"Thank you for using Fetch-a-Donut and ASI:One!",
                end_session=True,
            ),
        )
        return

    # State: new conversation — send welcome and ask for favorite donut
    ctx.storage.set(_session_key(ctx), {"state": "awaiting_donut"})

    await ctx.send(sender, _make_chat(WELCOME_MESSAGE))


@protocol.on_message(ChatAcknowledgement)
async def handle_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    pass


agent.include(protocol, publish_manifest=True)

# --- Agentverse README ---

README = """# Fetch-a-Donut Agent

![tag:donut-agent](https://img.shields.io/badge/donut-3D8BD3)
![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)

A fun, interactive agent that gives you a donut ticket at TreeHacks 12!

## How It Works

1. Click the URL to chat with the agent
2. Tell the agent your favorite donut
3. Get your ticket and donut, enjoy!

## Features

- AI-powered fun responses using ASI:One
- Unique ticket code generation
- One ticket per session
- Direct URL access via asi:one
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
                    "Fetch-a-Donut agent for TreeHacks 12! "
                    "Tell me your favorite donut and get your ticket!"
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
