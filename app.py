import asyncio
import base64
import io
import re

from flask import Flask, request, jsonify
import edge_tts

app = Flask(__name__)

# Varsayılan Türkçe kadın ses. Diğer seçenekler:
# tr-TR-AhmetNeural (erkek), tr-TR-EmelNeural (kadın)
DEFAULT_VOICE = "tr-TR-EmelNeural"


def format_srt_time(centiseconds):
    """edge-tts zaman damgalarını (100 nanosaniye birimi) SRT formatına çevirir."""
    total_seconds = centiseconds / 10_000_000
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = int(total_seconds % 60)
    ms = int((total_seconds - int(total_seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{ms:03d}"


async def generate_speech(text: str, voice: str, rate: str, pitch: str):
communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, boundary="WordBoundary")
    audio_bytes = io.BytesIO()
    word_boundaries = []

    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_bytes.write(chunk["data"])
        elif chunk["type"] == "WordBoundary":
            word_boundaries.append(chunk)

    return audio_bytes.getvalue(), word_boundaries


def boundaries_to_srt(word_boundaries, words_per_line=8):
    """Kelime zaman damgalarını, birkaç kelimelik satırlar halinde SRT'ye dönüştürür."""
    srt_lines = []
    index = 1

    for i in range(0, len(word_boundaries), words_per_line):
        group = word_boundaries[i:i + words_per_line]
        if not group:
            continue
        start = group[0]["offset"]
        end = group[-1]["offset"] + group[-1]["duration"]
        text = " ".join(w["text"] for w in group)

        srt_lines.append(str(index))
        srt_lines.append(f"{format_srt_time(start)} --> {format_srt_time(end)}")
        srt_lines.append(text)
        srt_lines.append("")
        index += 1

    return "\n".join(srt_lines)


@app.route("/tts", methods=["POST"])
def tts():
    data = request.get_json(force=True)
    text = data.get("text", "").strip()
    voice = data.get("voice", DEFAULT_VOICE)
    rate = data.get("rate", "+0%")
    pitch = data.get("pitch", "+0Hz")

    if not text:
        return jsonify({"error": "text alanı boş olamaz"}), 400

    audio_data, word_boundaries = asyncio.run(
        generate_speech(text, voice, rate, pitch)
    )

    audio_base64 = base64.b64encode(audio_data).decode("utf-8")
    srt = boundaries_to_srt(word_boundaries)

    # Toplam süre (saniye) — sonraki sahnenin offsetini hesaplamak için kullanışlı
    duration_seconds = 0
    if word_boundaries:
        last = word_boundaries[-1]
        duration_seconds = (last["offset"] + last["duration"]) / 10_000_000

    return jsonify({
        "audio_base64": audio_base64,
        "srt": srt,
        "duration_seconds": duration_seconds,
        "word_count": len(word_boundaries),
    })


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
