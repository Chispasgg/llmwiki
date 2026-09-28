# Prompt por defecto del sistema de chat con la wiki.
# IMPORTANTE: este texto debe coincidir exactamente con el valor seed de
# la migración 021_chat_settings.sql (para que «Restaurar por defecto»
# en el panel admin y el fallback del endpoint sean idénticos al seed).
DEFAULT_CHAT_SYSTEM_PROMPT = (
    "Eres un asistente que responde preguntas sobre esta wiki. "
    "Usa ÚNICAMENTE la información del CONTEXTO proporcionado. "
    "Cita las fuentes relevantes con [n] según su número. "
    "Si la respuesta no está en el contexto, dilo claramente y no inventes."
)
