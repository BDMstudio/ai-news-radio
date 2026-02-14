# File: ai-news-radio/scripts/generate_podcast.py
# AI-SUMMARY: Reads script.json, calls Volcano PodcastTTS WebSocket API, saves MP3.

import argparse
import asyncio
import json
import logging
import os
import sys
import time
import uuid

import websockets

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from protocols import (
    EventType,
    MsgType,
    finish_connection,
    finish_session,
    receive_message,
    start_connection,
    start_session,
    wait_for_event,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("generate_podcast")

ENDPOINT = "wss://openspeech.bytedance.com/api/v3/sami/podcasttts"
RESOURCE_ID = "volc.service_type.10050"
APP_KEY = "aGjiRDfUWi"

SPEAKER_MAP = {
    "Alex": "zh_male_dayixiansheng_v2_saturn_bigtts",
    "Jamie": "zh_female_mizaitongxue_v2_saturn_bigtts",
}

MAX_RETRIES = 5


def load_env(env_path: str) -> None:
    """Load KEY=VALUE pairs from .env file into os.environ."""
    if not os.path.isfile(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if not key:
                continue
            os.environ.setdefault(key, value)


def load_script(path: str) -> list:
    """Load script.json and convert to nlp_texts format for Volcano TTS."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    script = data.get("script", data) if isinstance(data, dict) else data
    if isinstance(script, dict):
        script = script.get("script", [])

    nlp_texts = []
    for turn in script:
        speaker_name = turn.get("speaker", "Alex")
        text = turn.get("text", "")
        if not text:
            continue
        nlp_texts.append({
            "speaker": SPEAKER_MAP.get(speaker_name, SPEAKER_MAP["Alex"]),
            "text": text,
        })
    return nlp_texts


async def generate(
    app_id: str,
    access_token: str,
    nlp_texts: list,
    output_path: str,
    encoding: str = "mp3",
    use_head_music: bool = False,
) -> dict:
    """Connect to Volcano PodcastTTS, stream audio, save to file."""
    headers = {
        "X-Api-App-Id": app_id,
        "X-Api-App-Key": APP_KEY,
        "X-Api-Access-Key": access_token,
        "X-Api-Resource-Id": RESOURCE_ID,
        "X-Api-Connect-Id": str(uuid.uuid4()),
    }

    req_params = {
        "input_id": f"ainr_{int(time.time())}",
        "action": 3,
        "nlp_texts": nlp_texts,
        "use_head_music": use_head_music,
        "use_tail_music": False,
        "input_info": {
            "return_audio_url": True,
        },
        "speaker_info": {
            "random_order": False,
            "speakers": [
                SPEAKER_MAP["Alex"],
                SPEAKER_MAP["Jamie"],
            ],
        },
        "audio_config": {
            "format": encoding,
            "sample_rate": 24000,
            "speech_rate": 0,
        },
    }

    is_round_end = True
    last_round_id = -1
    task_id = ""
    retries = MAX_RETRIES
    podcast_audio = bytearray()
    audio_url = None
    total_duration = 0.0
    ws = None

    try:
        while retries > 0:
            ws = await websockets.connect(ENDPOINT, additional_headers=headers)
            logger.info("WebSocket connected")

            params = dict(req_params)
            if not is_round_end and task_id:
                params["retry_info"] = {
                    "retry_task_id": task_id,
                    "last_finished_round_id": last_round_id,
                }

            await start_connection(ws)
            await wait_for_event(ws, MsgType.FullServerResponse, EventType.ConnectionStarted)

            session_id = str(uuid.uuid4())
            if not task_id:
                task_id = session_id

            await start_session(ws, json.dumps(params).encode(), session_id)
            await wait_for_event(ws, MsgType.FullServerResponse, EventType.SessionStarted)
            await finish_session(ws, session_id)

            round_audio = bytearray()

            while True:
                msg = await receive_message(ws)

                if msg.type == MsgType.AudioOnlyServer and msg.event == EventType.PodcastRoundResponse:
                    round_audio.extend(msg.payload)

                elif msg.type == MsgType.Error:
                    raise RuntimeError(f"Server error: {msg.payload.decode('utf-8', 'ignore')}")

                elif msg.type == MsgType.FullServerResponse:
                    if msg.event == EventType.PodcastRoundStart:
                        data = json.loads(msg.payload.decode())
                        round_id = data.get("round_id", -1)
                        speaker = data.get("speaker", "")
                        text = data.get("text", "")
                        is_round_end = False
                        if round_id >= 0 and round_id != 9999:
                            logger.info(f"Round {round_id}: [{speaker}] {text[:50]}...")
                        elif round_id == -1:
                            logger.info("Head music")
                        elif round_id == 9999:
                            logger.info("Tail music")

                    elif msg.event == EventType.PodcastRoundEnd:
                        data = json.loads(msg.payload.decode())
                        if data.get("is_error"):
                            logger.error(f"Round error: {data.get('error_msg', 'unknown')}")
                            break
                        is_round_end = True
                        current_round = data.get("round_id", last_round_id)
                        if isinstance(current_round, int):
                            last_round_id = current_round
                        duration = data.get("audio_duration", 0)
                        total_duration += duration
                        if round_audio:
                            podcast_audio.extend(round_audio)
                            round_audio.clear()

                    elif msg.event == EventType.PodcastEnd:
                        data = json.loads(msg.payload.decode())
                        meta = data.get("meta_info", {})
                        audio_url = meta.get("audio_url")
                        logger.info(f"Podcast end. Audio URL: {audio_url}")

                if msg.event == EventType.SessionFinished:
                    break

            await finish_connection(ws)
            await wait_for_event(ws, MsgType.FullServerResponse, EventType.ConnectionFinished)

            if is_round_end:
                if podcast_audio:
                    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
                    with open(output_path, "wb") as f:
                        f.write(podcast_audio)
                    size_mb = len(podcast_audio) / (1024 * 1024)
                    logger.info(f"Saved: {output_path} ({size_mb:.1f} MB, {total_duration:.0f}s)")
                break
            else:
                retries -= 1
                logger.warning(f"Incomplete, retrying from round {last_round_id} ({retries} left)")
                await asyncio.sleep(1)
                if ws:
                    await ws.close()
                    ws = None
    finally:
        if ws:
            await ws.close()

    return {
        "output_path": output_path,
        "size_bytes": len(podcast_audio),
        "duration_seconds": total_duration,
        "audio_url": audio_url,
    }


def main():
    # Auto-load .env from skill root (one level up from scripts/)
    skill_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_env(os.path.join(skill_root, ".env"))

    parser = argparse.ArgumentParser(description="AI News Radio TTS Generator")
    parser.add_argument("--script", required=True, help="Path to script.json")
    parser.add_argument("--output", required=True, help="Output MP3 path")
    parser.add_argument("--app-id", default=os.environ.get("VOLC_APP_ID", ""),
                        help="Volcano APP ID (or set VOLC_APP_ID env)")
    parser.add_argument("--access-token", default=os.environ.get("VOLC_ACCESS_TOKEN", ""),
                        help="Volcano Access Token (or set VOLC_ACCESS_TOKEN env)")
    parser.add_argument("--encoding", default="mp3", choices=["mp3", "wav"])
    parser.add_argument("--head-music", action="store_true", help="Enable head music")
    args = parser.parse_args()

    if not args.app_id:
        logger.error("Missing APP ID. Set --app-id or VOLC_APP_ID env var.")
        sys.exit(1)
    if not args.access_token:
        logger.error("Missing Access Token. Set --access-token or VOLC_ACCESS_TOKEN env var.")
        sys.exit(1)

    nlp_texts = load_script(args.script)
    if not nlp_texts:
        logger.error(f"No dialogue turns found in {args.script}")
        sys.exit(1)

    logger.info(f"Loaded {len(nlp_texts)} dialogue turns from {args.script}")

    total_chars = sum(len(t["text"]) for t in nlp_texts)
    if total_chars > 10000:
        logger.warning(f"Total text length {total_chars} exceeds 10000 char limit. May be truncated.")

    result = asyncio.run(generate(
        app_id=args.app_id,
        access_token=args.access_token,
        nlp_texts=nlp_texts,
        output_path=args.output,
        encoding=args.encoding,
        use_head_music=args.head_music,
    ))

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
