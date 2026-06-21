"""Aria Brain smoke test — verifies config, mood, memory, personality, LLM, end-to-end brain."""
import asyncio
from aria_brain import personality, mood, memory, llm, tts, brain
from aria_brain.config import LM_STUDIO_BASE_URL, TTS_URL, CHROMADB_URL, REFLECTION_CADENCE_MINUTES


def main():
    print("=== Aria Brain smoke test ===")
    print(f"lm_studio_url: {LM_STUDIO_BASE_URL}")
    print(f"tts_url: {TTS_URL}")
    print(f"chromadb_url: {CHROMADB_URL}")
    print(f"reflection_cadence_minutes: {REFLECTION_CADENCE_MINUTES}")
    print()

    print("=== mood ===")
    v, st = mood.get_current()
    print(f"  current mood: {v:.2f}")
    print(f"  label: {personality.mood_to_label(v)}")
    print(f"  hours_since_interaction: {mood.hours_since_last_interaction():.2f}")

    print()
    print("=== personality ===")
    prompt = personality.build_system_prompt(
        mood=3.5, mood_label="engaged",
        recent_memories=["user asked about ChromaDB yesterday"],
        relevant_memories=["user runs Aria on two PCs"],
        system_context={"time": "14:35", "day": "Tuesday"},
    )
    print(f"  prompt length: {len(prompt)} chars")
    print(f"  first line: {prompt.split(chr(10))[0]}")

    print()
    print("=== memory ===")
    try:
        stats = memory.stats()
        print(f"  backend: {stats['backend']}")
        print(f"  episodic: {stats['episodic_count']}")
        print(f"  facts: {stats['facts_count']}")
        print(f"  thoughts: {stats['thoughts_count']}")
        mid = memory.add_memory(
            "user loves dark mode and late-night coding",
            kind="fact",
            metadata={"topic": "preference"},
        )
        print(f"  added test fact id: {mid[:50]}")
        hits = memory.search("dark mode", kind="fact", n=3)
        print(f"  search 'dark mode' in facts: {len(hits)} hit(s)")
        for h in hits:
            print(f"    - {h['text'][:80]} (dist={h.get('distance')})")
    except Exception as exc:
        print(f"  ERROR: {type(exc).__name__}: {exc}")

    print()
    print("=== llm (LM Studio reachability) ===")
    import httpx
    try:
        with httpx.Client(timeout=3.0) as client:
            r = client.get(f"{LM_STUDIO_BASE_URL}/models")
        print(f"  GET /models: status={r.status_code}")
        if r.status_code == 200:
            data = r.json()
            models = data.get("data", [])
            print(f"  {len(models)} models loaded")
            for m in models[:5]:
                print(f"    - {m.get('id')}")
    except Exception as exc:
        print(f"  ERROR: {type(exc).__name__}: {exc}")

    print()
    print("=== brain.handle_message (real call to LM Studio) ===")
    async def go():
        result = await brain.handle_message(
            "hey aria, just checking in — what's on your mind?",
            source="smoke",
        )
        print(f"  reply: {result['reply'][:160]}")
        print(f"  mood after: {result['mood']:.2f} ({result['mood_label']})")
        print(f"  memories_used: {result['memories_used']}")

        # Test reflection
        print()
        print("=== brain.handle_reflection ===")
        r = await brain.handle_reflection()
        print(f"  thought: {r['thought'][:160]}")
        print(f"  mood: {r['mood']:.2f}")
    asyncio.run(go())
    print()
    print("=== all OK ===")


if __name__ == "__main__":
    main()