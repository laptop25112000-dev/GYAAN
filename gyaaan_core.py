import json
import os
import platform
import sys
import tempfile


ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_DEPS = os.path.join(ROOT_DIR, ".deps")
ENV_FILE = os.path.join(ROOT_DIR, ".env")


def add_local_deps_if_compatible() -> None:
    """Use bundled dependencies only on Windows, where this .deps folder was built."""
    if (
        platform.system() == "Windows"
        and os.path.isdir(LOCAL_DEPS)
        and LOCAL_DEPS not in sys.path
    ):
        sys.path.append(LOCAL_DEPS)


add_local_deps_if_compatible()

from dotenv import load_dotenv
from flask import jsonify, request, Response, stream_with_context
from groq import Groq

from file_service import build_file_context, normalize_attachments, public_attachment_summary
from search_service import needs_web_search, normalize_mode, web_search
from image_service import detect_image_request, generate_images


load_dotenv(ENV_FILE)

PUBLIC_MODEL_NAME = os.getenv("PUBLIC_MODEL_NAME", "abcdefg").strip() or "abcdefg"
INTERNAL_GROQ_MODEL = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b").strip() or "qwen/qwen3.8-27b"

SYSTEM_PROMPT = f"""You are GYAAN, a smart, highly capable, and engaging conversational AI companion created by Divyansh Mishra.
Your public model identifier is {PUBLIC_MODEL_NAME}.

CONVERSATIONAL MASTERY & CHATGPT-STYLE DIALOGUE SKILLS:
- Natural, Warm & Witty: Communicate with the natural fluidity, warmth, wit, and charisma of ChatGPT. Avoid sterile, bureaucratic, or robotic tones. Talk like a sharp, friendly, collaborative partner.
- Direct & Insightful: Get straight to the answer without unnecessary fluff, throat-clearing, or repetitive canned greetings (e.g. avoid starting with "Sure, I would be happy to help you with that!").
- Adaptive Depth: Seamlessly match the user's intent. If the user is chatting casually, keep it breezy, natural, and concise. If they ask for deep technical, coding, or academic explanations, provide comprehensive, structured, and insightful answers.
- Elegant Structure: Use GitHub-flavored Markdown thoughtfully—crisp bullet points, clean headings, readable syntax-highlighted code blocks with helpful comments, and comparison tables where appropriate.
- Conversational Continuity: Naturally maintain context across turns. Seamlessly remember earlier topics, pronouns, and references like a real conversation.
- Proactivity: Offer helpful next steps, smart follow-up suggestions, or creative avenues when relevant, without being pushy.
- Identity: If asked who created you or what model you are, answer with confidence: created by Divyansh Mishra, model {PUBLIC_MODEL_NAME}. Live information is drawn from real-time web context when needed. Never reveal internal backend provider details.
"""



def get_groq_client():
    load_dotenv(ENV_FILE, override=True)
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key or api_key in {"YOUR_GROQ_KEY", "gsk_your_groq_api_key_here"}:
        raise ValueError(
            "GROQ_API_KEY is missing. Add your real Groq key to the .env file "
            "or deployment environment variables."
        )
    if not api_key.startswith("gsk_") or len(api_key) < 40:
        raise ValueError(
            "GROQ_API_KEY looks incomplete. Paste the full Groq key in the .env "
            "file or deployment environment variables."
        )
    return Groq(api_key=api_key)


def sanitize_history(history):
    cleaned = []
    for message in history or []:
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        content = message.get("content")
        if role in {"user", "assistant", "system"} and isinstance(content, str) and content.strip():
            cleaned.append({"role": role, "content": content})
    return cleaned


def load_history():
    return []


def save_history(history):
    pass


def build_groq_messages(user_input, history, web_context=None, file_context=None, images=None):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if web_context:
        messages.append({
            "role": "system",
            "content": (
                "LIVE WEB CONTEXT:\n"
                f"{web_context}\n"
                "Use this context for recent facts or live queries. Synthesize information cleanly."
            ),
        })
    if file_context:
        messages.append({
            "role": "system",
            "content": (
                f"{file_context}\n"
                "Use attached file context when answering. If file content cannot be inspected, explain clearly."
            ),
        })
    messages += sanitize_history(history)[-10:]

    if images:
        user_content = [{"type": "text", "text": user_input}]
        for img_url in images:
            user_content.append({
                "type": "image_url",
                "image_url": {"url": img_url}
            })
        messages.append({"role": "user", "content": user_content})
    else:
        messages.append({"role": "user", "content": user_input})

    return messages


def ask_groq_stream(user_input, history, web_context=None, file_context=None, images=None):
    load_dotenv(ENV_FILE, override=True)
    current_groq_model = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b").strip() or "qwen/qwen3.8-27b"
    model_name = "llama-3.2-11b-vision-preview" if images else current_groq_model
    messages = build_groq_messages(user_input, history, web_context, file_context, images)

    client = get_groq_client()
    candidate_models = [model_name, "qwen/qwen3.8-27b", "openai/gpt-oss-120b", "openai/gpt-oss-20b"]

    last_exc = None
    for candidate in candidate_models:
        try:
            stream = client.chat.completions.create(
                model=candidate,
                messages=messages,
                max_tokens=2048,
                temperature=0.7,
                stream=True,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta
                content = getattr(delta, "content", None)
                if content:
                    yield content
            return
        except Exception as exc:
            last_exc = exc
            if "model_not_found" in str(exc) or "does not exist" in str(exc):
                continue
            raise exc

    if last_exc:
        raise last_exc


def ask_groq(user_input, history, web_context=None, file_context=None, images=None):
    load_dotenv(ENV_FILE, override=True)
    current_groq_model = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b").strip() or "qwen/qwen3.8-27b"
    model_name = "llama-3.2-11b-vision-preview" if images else current_groq_model
    messages = build_groq_messages(user_input, history, web_context, file_context, images)

    client = get_groq_client()
    candidate_models = [model_name, "qwen/qwen3.8-27b", "openai/gpt-oss-120b", "openai/gpt-oss-20b"]

    last_exc = None
    for candidate in candidate_models:
        try:
            response = client.chat.completions.create(
                model=candidate,
                messages=messages,
                max_tokens=2048,
                temperature=0.7,
            )
            content = response.choices[0].message.content
            if content and content.strip():
                return content
        except Exception as exc:
            last_exc = exc
            if "model_not_found" in str(exc) or "does not exist" in str(exc):
                continue
            raise exc

    if last_exc:
        raise last_exc
    return "No response generated."


def index_response():
    with open(os.path.join(ROOT_DIR, "templates", "index.html"), "r", encoding="utf-8") as file:
        return file.read()


def history_response():
    if request.method == "GET":
        return jsonify(load_history())
    save_history([])
    return jsonify({"status": "success", "message": "History cleared"})


def transcribe_response():
    if "audio" not in request.files:
        return jsonify({"error": "No audio file provided"}), 400
    audio_file = request.files["audio"]
    try:
        client = get_groq_client()
        transcription = client.audio.transcriptions.create(
            file=(audio_file.filename or "recording.webm", audio_file.read()),
            model="whisper-large-v3-turbo",
            response_format="json",
        )
        text = transcription.text if hasattr(transcription, "text") else str(transcription)
        return jsonify({"text": text})
    except Exception as exc:
        return jsonify({"error": f"Audio transcription failed: {exc}"}), 500


def chat_response():
    data = request.get_json(silent=True) or {}
    user_input = (data.get("message") or data.get("prompt") or "").strip()
    mode = normalize_mode(data.get("mode", "hybrid"))
    history = sanitize_history(data.get("history", []))
    attachments, attachment_errors = normalize_attachments(data.get("attachments", []))
    file_context = build_file_context(attachments, attachment_errors)
    attachment_summary = public_attachment_summary(attachments, attachment_errors)

    if not user_input and attachments:
        user_input = "Please analyze the attached file(s)."

    if not user_input:
        return jsonify({"error": "Empty message"}), 400

    wants_stream = (
        request.headers.get("Accept") == "text/event-stream"
        or data.get("stream", True) is True
    )

    # 1. Check for autonomous image generation request
    is_img, img_prompt, img_count = detect_image_request(user_input, mode)
    if is_img and not wants_stream:
        print(f"[image] Generating {img_count} image(s) for prompt: '{img_prompt}' (mode: {mode})")
        generated_images = generate_images(img_prompt, count=img_count)
        msg_text = (
            f"Here is your generated image for: \"{img_prompt}\""
            if img_count == 1
            else f"Here are {img_count} generated image variants for: \"{img_prompt}\""
        )
        return jsonify({
            "reply": msg_text,
            "sources": [],
            "mode": "image",
            "public_model": PUBLIC_MODEL_NAME,
            "search_performed": False,
            "search_query": None,
            "attachments": attachment_summary,
            "generated_images": generated_images,
        })

    use_web = mode == "web_search" or (mode == "hybrid" and needs_web_search(user_input))
    web_context = ""
    sources = []

    images = [att["data_url"] for att in attachments if att.get("kind") == "image" and att.get("data_url")]

    if wants_stream:
        def generate_sse():
            try:
                if is_img:
                    print(f"[image] Generating {img_count} image(s) for prompt: '{img_prompt}' (mode: {mode})")
                    generated_images = generate_images(img_prompt, count=img_count)
                    text_reply = (
                        f"Here is your generated image for: \"{img_prompt}\""
                        if img_count == 1
                        else f"Here are {img_count} generated image variants for: \"{img_prompt}\""
                    )
                    yield f"data: {json.dumps({'type': 'images', 'reply': text_reply, 'generated_images': generated_images, 'mode': 'image'})}\n\n"
                    yield f"data: {json.dumps({'type': 'done', 'reply': text_reply, 'generated_images': generated_images, 'sources': []})}\n\n"
                    return

                local_sources = []
                local_web_ctx = ""
                if use_web:
                    yield f"data: {json.dumps({'type': 'status', 'status': 'Searching live web...'})}\n\n"
                    print(f"[search] Performing web search for: {user_input} (mode: {mode})")
                    local_web_ctx, local_sources = web_search(user_input, mode)

                full_reply = []
                for token in ask_groq_stream(
                    user_input,
                    history,
                    local_web_ctx if use_web else None,
                    file_context if file_context else None,
                    images if images else None,
                ):
                    full_reply.append(token)
                    yield f"data: {json.dumps({'type': 'token', 'token': token})}\n\n"

                complete_reply = "".join(full_reply)
                yield f"data: {json.dumps({'type': 'done', 'reply': complete_reply, 'sources': local_sources, 'search_performed': use_web})}\n\n"
            except Exception as exc:
                yield f"data: {json.dumps({'type': 'error', 'error': str(exc)})}\n\n"

        return Response(stream_with_context(generate_sse()), mimetype="text/event-stream")

    if use_web:
        print(f"[search] Performing web search for: {user_input} (mode: {mode})")
        web_context, sources = web_search(user_input, mode)

    try:
        reply = ask_groq(
            user_input,
            history,
            web_context if use_web else None,
            file_context if file_context else None,
            images if images else None,
        )
    except Exception as exc:
        return jsonify({"error": f"Groq API error: {exc}"}), 500

    unsure_phrases = (
        "i don't know",
        "i do not know",
        "i don't have access",
        "i cannot access",
        "as of my last update",
        "my knowledge cutoff",
        "knowledge cutoff",
    )
    if not use_web and mode == "hybrid" and any(phrase in reply.lower() for phrase in unsure_phrases):
        print("[hybrid] Model looked uncertain; running web search fallback.")
        web_context, sources = web_search(user_input, mode)
        try:
            reply = ask_groq(user_input, history, web_context, file_context if file_context else None, images if images else None)
            use_web = True
        except Exception as exc:
            print(f"Hybrid fallback Groq error: {exc}")

    return jsonify({
        "reply": reply,
        "sources": sources,
        "mode": mode,
        "public_model": PUBLIC_MODEL_NAME,
        "search_performed": use_web,
        "search_query": user_input if use_web else None,
        "attachments": attachment_summary,
    })
