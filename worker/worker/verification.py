"""Étape optionnelle de réduction des faux positifs (SPEC §6) : les frames clés
d'une séquence signalée sont envoyées à l'API Claude (vision) avec un prompt de
description factuelle, et le score de l'alerte est ajusté selon la réponse.

Garde-fous produit et RGPD :
- Le prompt interdit toute identification de la personne — description
  factuelle des actions uniquement.
- Désactivable par tenant (réglage poussé par l'API) ; jamais appelée en
  continu, uniquement sur les séquences déjà signalées par les règles locales.
- L'ajustement ne supprime jamais l'alerte : l'humain décide toujours.
"""

import base64
import json
import logging

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-opus-5"
MAX_KEY_FRAMES = 4

# Verdict de l'API → facteur appliqué au score de l'alerte.
VERDICT_FACTORS = {"oui": 1.0, "incertain": 0.8, "non": 0.5}

RULE_QUESTIONS = {
    "dissimulation": "Une personne prend-elle un article puis le fait-elle "
    "disparaître (sac, poche, vêtement) sans le reposer ?",
    "passage_sans_caisse": "Une personne se dirige-t-elle vers la sortie avec "
    "des articles sans passer par une caisse ?",
    "temps_anormal": "Une personne reste-t-elle immobile de façon prolongée "
    "devant un rayon ?",
    "zone_interdite": "Une personne entre-t-elle dans une zone réservée au "
    "personnel (réserve, arrière-comptoir) ?",
}

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "description": {"type": "string"},
        "sequence_visible": {"type": "string", "enum": ["oui", "non", "incertain"]},
    },
    "required": ["description", "sequence_visible"],
    "additionalProperties": False,
}


def select_key_frames(
    frames: list[tuple[float, bytes]], max_frames: int = MAX_KEY_FRAMES
) -> list[bytes]:
    """Échantillonne au plus `max_frames` frames réparties sur la séquence."""
    if not frames:
        return []
    if len(frames) <= max_frames:
        return [jpeg for _ts, jpeg in frames]
    step = (len(frames) - 1) / (max_frames - 1)
    return [frames[round(i * step)][1] for i in range(max_frames)]


def apply_assessment(alert: dict, assessment: dict | None) -> dict:
    """Ajuste le score de l'alerte selon la réponse de l'API (fonction pure).

    L'alerte est toujours publiée — le facteur module le score et la sévérité,
    et la description factuelle est jointe aux indices pour la revue humaine.
    """
    if assessment is None:
        return alert
    factor = assessment["factor"]
    adjusted = dict(alert)
    adjusted["score"] = round(alert["score"] * factor, 3)
    if factor <= 0.5 and adjusted.get("severity") != "low":
        adjusted["severity"] = "low"
    adjusted["evidence"] = list(alert.get("evidence", [])) + [
        {
            "stage": "multimodal_verification",
            "verdict": assessment["verdict"],
            "factor": factor,
            "description": assessment["description"],
        }
    ]
    return adjusted


class MultimodalVerifier:
    """Interroge l'API Claude (vision) sur les frames clés d'une alerte."""

    def __init__(self, model: str = DEFAULT_MODEL, client=None):
        if client is None:
            # Import différé : dépendance optionnelle, activée par ANTHROPIC_API_KEY.
            import anthropic

            client = anthropic.Anthropic()
        self._client = client
        self._model = model

    def assess(self, frames: list[tuple[float, bytes]], rule: str) -> dict | None:
        """Retourne {"verdict", "factor", "description"} ou None si indisponible."""
        key_frames = select_key_frames(frames)
        if not key_frames:
            return None

        question = RULE_QUESTIONS.get(rule, "Un comportement correspondant à "
                                            f"l'alerte « {rule} » est-il visible ?")
        content = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": base64.standard_b64encode(jpeg).decode(),
                },
            }
            for jpeg in key_frames
        ]
        content.append(
            {
                "type": "text",
                "text": (
                    "Voici des images extraites d'une caméra de magasin, dans "
                    "l'ordre chronologique. Décris factuellement les actions "
                    "visibles, sans jamais chercher à identifier la personne "
                    "(pas de description du visage ni de caractéristiques "
                    f"permettant une identification). Question : {question}"
                ),
            }
        )

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=1024,
                system=(
                    "Tu analyses des séquences de vidéosurveillance de commerce "
                    "pour aider un employé à trier des alertes. Tu décris "
                    "uniquement des actions observables, de façon neutre et "
                    "factuelle. Tu n'identifies jamais les personnes et tu ne "
                    "portes jamais d'accusation — tu réponds seulement si la "
                    "séquence décrite est visible sur les images."
                ),
                messages=[{"role": "user", "content": content}],
                output_config={
                    "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}
                },
            )
        except Exception:
            logger.exception("multimodal verification call failed")
            return None

        if response.stop_reason == "refusal":
            logger.warning("multimodal verification refused (stop_details=%s)",
                           getattr(response, "stop_details", None))
            return None

        try:
            text = next(b.text for b in response.content if b.type == "text")
            data = json.loads(text)
            verdict = data["sequence_visible"]
            return {
                "verdict": verdict,
                "factor": VERDICT_FACTORS.get(verdict, 1.0),
                "description": data["description"],
            }
        except (StopIteration, KeyError, ValueError):
            logger.exception("unexpected multimodal verification response")
            return None
