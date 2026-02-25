"""
scriptwriter.py — AI scriptwriting via Ollama (local) or OpenAI (fallback).

Takes research context and generates a structured viral script
following the Hook → Retention → Payoff → CTA framework.

Primary: Ollama + Llama 3.2 3B (free, local, ~2.5GB VRAM)
Fallback: OpenAI GPT-4o (built but disabled by default)
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Optional

import config
from modules.gpu_manager import gpu_session

logger = logging.getLogger(__name__)


@dataclass
class Script:
    """Structured script output."""
    title: str = ""
    hook: str = ""          # 0-3s — stop the scroll
    retention: str = ""     # 3-15s — rapid value
    payoff: str = ""        # 15-45s — core insight
    cta: str = ""           # 45-60s — call to action
    full_script: str = ""   # Combined narration text
    caption: str = ""       # Instagram caption
    hashtags: list[str] = field(default_factory=list)

    def to_narration(self) -> str:
        """Return the full narration text for TTS."""
        if self.full_script:
            return self.full_script
        parts = [self.hook, self.retention, self.payoff, self.cta]
        return " ".join(p for p in parts if p)


# ── System Prompt ──────────────────────────────────────────
SYSTEM_PROMPT = """You are an expert Instagram Reels scriptwriter and viral content strategist.

Your job: Create a 45-60 second script that maximizes retention, shares, and engagement.

STRICT RULES:
1. Output ONLY valid JSON — no markdown, no explanation, no extra text.
2. The script must follow this viral framework:
   - "hook" (0-3 seconds): A bold, controversial, or curiosity-driven opening that stops the scroll.
   - "retention" (3-15 seconds): Rapid-fire value delivery to keep them watching.
   - "payoff" (15-45 seconds): The core insight, story, or news — the main content.
   - "cta" (45-60 seconds): A specific call to engagement (e.g., "Comment X for the link").
3. Write in a conversational, energetic tone — like talking to a friend, not reading a textbook.
4. Use short sentences. No filler. Every word must earn its place.
5. Include 5-10 relevant hashtags.
6. Write an engaging Instagram caption (2-3 sentences + hashtags).

OUTPUT FORMAT (strict JSON):
{
  "title": "Short title for internal tracking",
  "hook": "The opening 1-2 sentences (0-3 seconds)",
  "retention": "Value delivery section (3-15 seconds)",
  "payoff": "Main content section (15-45 seconds)",
  "cta": "Call to action (45-60 seconds)",
  "full_script": "The complete narration text combining all sections naturally",
  "caption": "Instagram caption text",
  "hashtags": ["#tag1", "#tag2", "..."]
}"""


class ScriptWriter:
    """Generates viral scripts using local LLM or cloud fallback."""

    def __init__(self, provider: Optional[str] = None):
        self.provider = provider or config.LLM_PROVIDER

    def generate(self, topic: str, research_context: str = "") -> Script:
        """
        Generate a viral script for the given topic.

        Args:
            topic: The content topic
            research_context: Research text from researcher.py

        Returns:
            Script dataclass with structured sections
        """
        logger.info(f"📝 Generating script for: {topic} (provider={self.provider})")

        user_prompt = self._build_user_prompt(topic, research_context)

        if self.provider == "ollama":
            raw_json = self._generate_ollama(user_prompt)
        elif self.provider == "openai":
            raw_json = self._generate_openai(user_prompt)
        else:
            raise ValueError(f"Unknown LLM provider: {self.provider}")

        script = self._parse_response(raw_json)
        logger.info(f"✅ Script generated: '{script.title}' "
                     f"({len(script.to_narration())} chars)")
        return script

    def _build_user_prompt(self, topic: str, research_context: str) -> str:
        """Build the user prompt with topic and research context."""
        prompt = f"Create a viral Instagram Reels script about: {topic}\n"
        if research_context:
            prompt += f"\nHere is recent research and news to reference:\n{research_context}\n"
        prompt += "\nGenerate the script now. Output ONLY valid JSON."
        return prompt

    def _generate_ollama(self, user_prompt: str) -> str:
        """Generate script using local Ollama LLM."""
        try:
            import ollama

            logger.info(f"  🧠 Using Ollama: {config.OLLAMA_MODEL}")

            response = ollama.chat(
                model=config.OLLAMA_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                options={
                    "temperature": 0.7,
                    "num_predict": 2048,
                },
            )

            content = response["message"]["content"]
            logger.info(f"  📋 Ollama response: {len(content)} chars")
            return content

        except ImportError:
            logger.error("ollama package not installed. Run: pip install ollama")
            raise
        except Exception as e:
            logger.error(f"Ollama generation failed: {e}")
            if self.provider == "ollama" and config.OPENAI_API_KEY:
                logger.info("  🔄 Falling back to OpenAI...")
                return self._generate_openai(user_prompt)
            raise

    def _generate_openai(self, user_prompt: str) -> str:
        """
        Generate script using OpenAI API (fallback).

        NOTE: This is built but disabled by default.
        Set OPENAI_API_KEY in .env and LLM_PROVIDER=openai to enable.
        """
        if not config.OPENAI_API_KEY:
            raise ValueError(
                "OpenAI API key not set. Either:\n"
                "  1. Set OPENAI_API_KEY in .env\n"
                "  2. Use LLM_PROVIDER=ollama (default, free)"
            )

        try:
            from openai import OpenAI

            logger.info(f"  🧠 Using OpenAI: {config.OPENAI_MODEL}")

            client = OpenAI(api_key=config.OPENAI_API_KEY)
            response = client.chat.completions.create(
                model=config.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.7,
                max_tokens=2048,
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content
            logger.info(f"  📋 OpenAI response: {len(content)} chars")
            return content

        except ImportError:
            logger.error("openai package not installed. Run: pip install openai")
            raise

    def _parse_response(self, raw_json: str) -> Script:
        """Parse LLM JSON response into Script dataclass."""
        # Try to extract JSON from response (LLMs sometimes wrap in markdown)
        json_str = raw_json.strip()

        # Remove markdown code blocks if present
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0].strip()
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0].strip()

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            logger.warning("⚠️ Failed to parse JSON, using raw text as script")
            return Script(
                title="Generated Script",
                full_script=raw_json.strip(),
            )

        return Script(
            title=data.get("title", "Untitled"),
            hook=data.get("hook", ""),
            retention=data.get("retention", ""),
            payoff=data.get("payoff", ""),
            cta=data.get("cta", ""),
            full_script=data.get("full_script", ""),
            caption=data.get("caption", ""),
            hashtags=data.get("hashtags", []),
        )


# ── Standalone test ────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    writer = ScriptWriter()
    script = writer.generate("Why AI will change everything in 2026")
    print(f"\nTitle: {script.title}")
    print(f"Hook: {script.hook}")
    print(f"Narration ({len(script.to_narration())} chars):\n{script.to_narration()}")
    print(f"Hashtags: {script.hashtags}")
