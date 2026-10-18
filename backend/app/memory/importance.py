"""Dynamic Importance Scoring Engine: Park et al. Dual-Stage Heuristics & LLM Reflection."""

import logging
import math
import re
from typing import Any, Dict, Optional

from app.core.config import settings

logger = logging.getLogger("aegis.importance")

# ==========================================
# 1. Word-Boundary Safe Pattern Matchers
# ==========================================

CRITICAL_ERROR_PATTERNS = re.compile(
    r"\b(traceback|exception|panic|out of memory|oom|segfault|deadlock|err_[a-z0-9_]+|http 5\d\d|connection reset|fatal|corrupt)\b",
    re.IGNORECASE,
)

DEVOPS_MUTATION_PATTERNS = re.compile(
    r"\b(migrated|migration|cutover|production release|deployed|rollback|schema|secret rotated|credential|falkordb|postgresql|kubernetes|guardrail|checkpoint)\b",
    re.IGNORECASE,
)

# Anchored to entire message so 'ok' or 'ack' never falsely matches 'token', 'rollback', 'architecture'
TRIVIAL_GREETING_PATTERNS = re.compile(
    r"^\s*(hello|hi|hey|thanks|thank you|ok|okay|ack|acknowledged|good morning|good evening|got it|cool|done)[\s!.,?]*$",
    re.IGNORECASE,
)


class ImportanceScorer:
    """Evaluates the poignancy and systemic significance of episodic experience turns.
    
    Implements a two-stage cognitive pipeline:
    - Stage 1: Zero-latency, word-boundary safe heuristics (errors >=0.85, greetings <=0.25).
    - Stage 2: Stanford Generative Agents (Park et al. 2023) poignancy reflection for ambiguous turns.
    """

    def __init__(self):
        self._llm = None
        self._llm_initialized = False

    def _get_llm(self):
        """Lazy initialization of LLM for Stage 2 reflection."""
        if not self._llm_initialized:
            self._llm_initialized = True
            provider = settings.llm_provider.lower().strip()
            try:
                if provider == "gemini" and settings.gemini_api_key:
                    from langchain_google_genai import ChatGoogleGenerativeAI
                    self._llm = ChatGoogleGenerativeAI(
                        model="gemini-flash-lite-latest",
                        google_api_key=settings.gemini_api_key,
                        temperature=0.0,
                        timeout=15.0,
                    )
                elif provider == "openai" and settings.openai_api_key:
                    from langchain_openai import ChatOpenAI
                    self._llm = ChatOpenAI(
                        model="gpt-4o-mini",
                        api_key=settings.openai_api_key,
                        temperature=0.0,
                    )
            except Exception as e:
                logger.warning(f"Failed to initialize Stage 2 LLM: {e}")
                self._llm = None
        return self._llm

    def evaluate(
        self,
        content: str,
        role: str = "user",
        status: str = "SUCCESS",
        structured_payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Performs full dual-stage evaluation and returns detailed explanation."""
        text = (content or "").strip()

        # -------------------------------------------------------------
        # Stage 1: Zero-Latency Rule-Based Heuristics
        # -------------------------------------------------------------

        # 1. Explicit Error Status or Failure Payload
        if status in ("ERROR", "WARNING"):
            score = 0.92 if status == "ERROR" else 0.75
            return {
                "score": score,
                "stage": "STAGE_1_HEURISTIC",
                "reason": f"Execution status '{status}' represents critical operational signal.",
            }

        # 2. Structured Payload Error Signatures
        if structured_payload and isinstance(structured_payload, dict):
            p_status = str(structured_payload.get("status", "")).upper()
            if p_status in ("ERROR", "FAILED", "FAILURE") or "error" in structured_payload:
                return {
                    "score": 0.90,
                    "stage": "STAGE_1_HEURISTIC",
                    "reason": "Structured tool payload contains failure code or error trace.",
                }

        # 3. Critical Exception & Crash Keywords
        if CRITICAL_ERROR_PATTERNS.search(text):
            return {
                "score": 0.88,
                "stage": "STAGE_1_HEURISTIC",
                "reason": "Content contains critical exception, crash, or error pattern.",
            }

        # 4. Architecture, DevOps & Financial Mutation Keywords
        if DEVOPS_MUTATION_PATTERNS.search(text):
            return {
                "score": 0.82,
                "stage": "STAGE_1_HEURISTIC",
                "reason": "Content contains DevOps, architecture, or state mutation event.",
            }

        # 5. Trivial Greetings & Acknowledgments
        if TRIVIAL_GREETING_PATTERNS.match(text):
            return {
                "score": 0.15,
                "stage": "STAGE_1_HEURISTIC",
                "reason": "Content is a trivial conversational greeting or acknowledgment.",
            }

        # -------------------------------------------------------------
        # Stage 2: Ambiguous Middle Zone -> LLM Reflection or Entropy
        # -------------------------------------------------------------
        llm = self._get_llm()
        if llm is not None:
            try:
                prompt = (
                    "You are a cognitive memory evaluator for an autonomous AI system. "
                    "On a scale of 0.0 to 1.0, assess the poignancy and long-term significance of this interaction turn. "
                    "Consider whether it represents a critical system state change, architectural decision, or permanent lesson.\n\n"
                    f"Role: {role}\n"
                    f"Content: {text}\n\n"
                    "Respond with ONLY a decimal number between 0.0 and 1.0 (e.g., 0.65)."
                )
                response = llm.invoke(prompt)
                raw_text = response.content.strip()
                match = re.search(r"(\d+(\.\d+)?)", raw_text)
                if match:
                    llm_score = max(0.05, min(1.0, float(match.group(1))))
                    return {
                        "score": round(llm_score, 2),
                        "stage": "STAGE_2_LLM_REFLECTION",
                        "reason": f"Park et al. LLM reflection evaluated turn significance as {llm_score:.2f}.",
                    }
            except Exception as e:
                logger.debug(f"Stage 2 LLM invocation exception: {e}")

        # Deterministic Information Entropy Fallback (for mock/offline mode)
        entropy_score = self._compute_entropy_heuristic(text, role)
        return {
            "score": round(entropy_score, 2),
            "stage": "STAGE_2_ENTROPY_FALLBACK",
            "reason": f"Calculated information entropy and token complexity score: {entropy_score:.2f}.",
        }

    def _compute_entropy_heuristic(self, text: str, role: str) -> float:
        """Deterministic information-density heuristic for mock/air-gapped environments."""
        tokens = text.split()
        if not tokens:
            return 0.30

        # Unique token ratio
        unique_tokens = set(tokens)
        diversity = len(unique_tokens) / max(1, len(tokens))

        # Length factor (log-scaled)
        length_bonus = min(0.30, math.log(max(1, len(tokens)), 50) * 0.30)

        # Role base weight
        role_base = 0.50 if role == "agent" else 0.45

        raw = role_base + (diversity * 0.15) + length_bonus
        return max(0.25, min(0.78, raw))

    def score(
        self,
        content: str,
        role: str = "user",
        status: str = "SUCCESS",
        structured_payload: Optional[Dict[str, Any]] = None,
    ) -> float:
        """Convenience method returning strictly the float score in [0.05, 1.0]."""
        res = self.evaluate(
            content=content,
            role=role,
            status=status,
            structured_payload=structured_payload,
        )
        return res["score"]


importance_scorer = ImportanceScorer()
