"""
auraya/agents/qa_agent.py

QA Agent — uses Gemini Vision (google-generativeai) to:
  1. Download screenshots from a Firebase Test Lab results bucket.
  2. Visually assert that the jewelry model is correctly placed near the neck.
  3. Return a structured verdict that the LangGraph router can act on.
"""
from __future__ import annotations

import base64
import io
import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-2.0-flash"

# Visual assertion prompt sent to Gemini for each AR screenshot
AR_ASSERTION_PROMPT = """
You are a QA engineer reviewing a screenshot of an AR jewelry try-on app called Auraya.

Evaluate the screenshot and answer EACH of the following questions with YES / NO / UNSURE:
1. Is a person visible in the frame?
2. Is there a 3D jewelry item (necklace, ring, bracelet, or earring) visible?
3. Is the jewelry item positioned near the person's neck / chest / wrist area?
4. Does the jewelry item look realistically overlaid (not floating far away, not on wrong body part)?
5. Is the UI free of crash dialogs or error messages?

Then give an overall verdict:
PASS  — All 5 criteria are YES.
FAIL  — Any criterion is NO.
NEEDS_REVIEW — Any criterion is UNSURE.

Format your response exactly as:
Q1: <YES|NO|UNSURE>
Q2: <YES|NO|UNSURE>
Q3: <YES|NO|UNSURE>
Q4: <YES|NO|UNSURE>
Q5: <YES|NO|UNSURE>
VERDICT: <PASS|FAIL|NEEDS_REVIEW>
NOTES: <1-2 sentence explanation>
"""


class QAAgent:
    """Wraps Gemini Vision for AR screenshot assertion."""

    def __init__(self):
        import google.generativeai as genai  # type: ignore
        genai.configure(api_key=os.environ["GEMINI_API_KEY"])
        self._model = genai.GenerativeModel(GEMINI_MODEL)

    def analyze_screenshot(self, image_bytes: bytes) -> dict:
        """
        Run visual QA on a single screenshot.

        Returns:
            {
              "verdict":    "PASS" | "FAIL" | "NEEDS_REVIEW",
              "criteria":   { "q1": bool, ... },
              "notes":      str,
              "raw":        str,   ← full Gemini response text
            }
        """
        import google.generativeai as genai  # type: ignore

        image_part = {
            "mime_type": "image/png",
            "data":       base64.b64encode(image_bytes).decode(),
        }

        response = self._model.generate_content([AR_ASSERTION_PROMPT, image_part])
        raw      = response.text.strip()
        return _parse_qa_response(raw)

    async def analyze_firebase_run(
        self,
        gcs_bucket: str,
        results_dir: str,
    ) -> dict:
        """
        Download all screenshots from a Firebase Test Lab GCS results directory
        and aggregate QA results.

        Returns:
            {
              "overall": "PASS" | "FAIL" | "NEEDS_REVIEW",
              "results": [ { "file": ..., "verdict": ..., ... } ],
              "summary": str,
            }
        """
        screenshots = await _download_firebase_screenshots(gcs_bucket, results_dir)

        if not screenshots:
            return {
                "overall": "NEEDS_REVIEW",
                "results": [],
                "summary": "No screenshots found in Firebase results.",
            }

        results = []
        for fname, img_bytes in screenshots:
            result = self.analyze_screenshot(img_bytes)
            result["file"] = fname
            results.append(result)
            logger.info("QA [%s] → %s", fname, result["verdict"])

        verdicts = [r["verdict"] for r in results]
        if "FAIL" in verdicts:
            overall = "FAIL"
        elif "NEEDS_REVIEW" in verdicts:
            overall = "NEEDS_REVIEW"
        else:
            overall = "PASS"

        pass_count = verdicts.count("PASS")
        summary = (
            f"Analyzed {len(results)} screenshot(s). "
            f"{pass_count}/{len(results)} passed. Overall: {overall}."
        )

        return {"overall": overall, "results": results, "summary": summary}


# ─── Response parser ──────────────────────────────────────────────────────────

def _parse_qa_response(raw: str) -> dict:
    lines   = {line.split(":")[0].strip(): line.split(":", 1)[1].strip()
               for line in raw.splitlines() if ":" in line}
    verdict = lines.get("VERDICT", "NEEDS_REVIEW").upper()
    notes   = lines.get("NOTES", "")
    criteria = {
        f"q{i}": (lines.get(f"Q{i}", "UNSURE").upper() == "YES")
        for i in range(1, 6)
    }
    return {"verdict": verdict, "criteria": criteria, "notes": notes, "raw": raw}


# ─── GCS download helper ──────────────────────────────────────────────────────

async def _download_firebase_screenshots(
    bucket: str, results_dir: str
) -> list[tuple[str, bytes]]:
    """
    Use the Google Cloud Storage JSON API to list and download PNG screenshots.
    Requires GOOGLE_APPLICATION_CREDENTIALS or GCP_SERVICE_ACCOUNT env var.
    """
    try:
        from google.cloud import storage as gcs  # type: ignore
        client  = gcs.Client()
        blobs   = client.list_blobs(bucket, prefix=f"{results_dir}/")
        screenshots: list[tuple[str, bytes]] = []
        for blob in blobs:
            if blob.name.endswith(".png"):
                data = blob.download_as_bytes()
                screenshots.append((blob.name, data))
        return screenshots
    except Exception as exc:
        logger.warning("Could not download Firebase screenshots: %s", exc)
        return []
