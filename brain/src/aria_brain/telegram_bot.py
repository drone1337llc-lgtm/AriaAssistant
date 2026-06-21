"""Telegram bot — long-polling. Forward messages to Aria Brain, reply with text.

Set env vars:
    TELEGRAM_BOT_TOKEN  — from @BotFather
    TELEGRAM_ALLOWED_CHAT_IDS  — comma-separated whitelist; empty = allow any

Run:
    python -m aria_brain.telegram_bot
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

import httpx

from aria_brain.config import ARIA_BRAIN_HOST, ARIA_BRAIN_PORT

log = logging.getLogger("aria_brain.telegram")


def _brain_url() -> str:
    return f"http://{ARIA_BRAIN_HOST}:{ARIA_BRAIN_PORT}"


def _allowed_chat_ids() -> set[int]:
    raw = os.environ.get("TELEGRAM_ALLOWED_CHAT_IDS", "").strip()
    if not raw:
        return set()
    return {int(x.strip()) for x in raw.split(",") if x.strip().isdigit()}


async def _send_to_brain(text: str, chat_id: int) -> dict:
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(
            f"{_brain_url()}/message",
            json={"text": text, "source": f"telegram:{chat_id}"},
        )
        return r.json()


async def main_async() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        log.error("TELEGRAM_BOT_TOKEN not set — get one from @BotFather and set the env var")
        return
    allowed = _allowed_chat_ids()
    log.info(f"telegram bot starting; allowed chat ids: {allowed or 'ALL'}")

    try:
        from telegram import Update  # type: ignore
        from telegram.ext import (  # type: ignore
            ApplicationBuilder,
            CommandHandler,
            ContextTypes,
            MessageHandler,
            filters,
        )
    except ImportError as exc:
        log.error(f"python-telegram-bot not installed: {exc}")
        return

    app = ApplicationBuilder().token(token).build()

    async def _start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message:
            return
        mood = ""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{_brain_url()}/mood")
            m = r.json()
            mood = f"\nmood: {m['value']:.1f} ({m['label']})"
        except Exception:
            pass
        await update.effective_message.reply_text(
            f"hey. it's aria — text me.{mood}"
        )

    async def _mood_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message:
            return
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{_brain_url()}/mood")
            m = r.json()
            await update.effective_message.reply_text(
                f"mood {m['value']:.1f}/5 ({m['label']}) — last interaction {m['hours_since_interaction']:.1f}h ago"
            )
        except Exception as exc:
            await update.effective_message.reply_text(f"brain offline: {exc}")

    async def _on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message or not update.effective_chat:
            return
        chat_id = update.effective_chat.id
        if allowed and chat_id not in allowed:
            log.warning(f"telegram: refusing chat_id={chat_id} (not in whitelist)")
            return
        text = (update.effective_message.text or "").strip()
        if not text:
            return
        log.info(f"telegram chat={chat_id}: {text[:80]}")
        try:
            result = await _send_to_brain(text, chat_id)
            reply = result.get("reply", "")
            if reply:
                mood_v = result.get("mood", 3.0)
                mood_l = result.get("mood_label", "baseline")
                await update.effective_message.reply_text(
                    f"{reply}\n\n— mood {mood_v:.1f} ({mood_l})"
                )
            else:
                await update.effective_message.reply_text("...brain gave me nothing. try again?")
        except Exception as exc:
            log.warning(f"telegram send failed: {exc}")
            await update.effective_message.reply_text(f"brain error: {exc}")

    app.add_handler(CommandHandler("start", _start))
    app.add_handler(CommandHandler("mood", _mood_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _on_message))

    log.info("telegram bot: polling…")
    await app.initialize()
    await app.start()
    await app.updater.start_polling()  # type: ignore[union-attr]
    # Block forever
    try:
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        pass
    finally:
        await app.updater.stop_polling()  # type: ignore[union-attr]
        await app.stop()
        await app.shutdown()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s :: %(message)s")
    asyncio.run(main_async())


if __name__ == "__main__":
    main()