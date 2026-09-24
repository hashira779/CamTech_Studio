import os
import sys
import uuid
import tempfile
from dotenv import load_dotenv
import telebot
import threading

# Ensure project root in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Load env variables
load_dotenv(os.path.join(BASE_DIR, "backend", ".env"))
load_dotenv(os.path.join(BASE_DIR, ".env"))

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
if not TOKEN:
    print("Please set TELEGRAM_BOT_TOKEN in your .env file")
    sys.exit(1)

bot = telebot.TeleBot(TOKEN)

# Import VIDA components
from kmvm.youtube_downloader import download_youtube_audio, is_youtube_url, extract_youtube_url
from backend.app import clean_youtube_title_and_artist
from backend.lyric_engine import WhisperTranscriber, find_matching_subtitles, parse_subtitle_file
from backend.renderer import VideoRenderer

UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# We use a single transcriber instance to save memory
transcriber_instance = None

def process_audio(chat_id, audio_path, filename):
    global transcriber_instance
    try:
        # 1. Check for subtitles or transcribe
        bot.send_message(chat_id, "🎵 Audio received. Extracting metadata and lyrics...")
        
        # We can extract a title from filename
        raw_title = os.path.splitext(os.path.basename(filename))[0]
        clean_title, clean_artist = clean_youtube_title_and_artist(raw_title)

        lyrics = None
        sub_path = find_matching_subtitles(audio_path, target_lang="km")
        if sub_path and os.path.exists(sub_path):
            try:
                lyrics = parse_subtitle_file(sub_path)
            except Exception as e:
                print(f"Subtitle parse error: {e}")

        if not lyrics:
            bot.send_message(chat_id, "🤖 Transcribing lyrics using AI... (this may take a minute)")
            if transcriber_instance is None:
                transcriber_instance = WhisperTranscriber(model_size="large-v3-turbo")
            
            def on_progress(pct, msg):
                pass # Can be used to update a telegram message if needed
            
            lyrics = transcriber_instance.transcribe(audio_path, language="km", progress_callback=on_progress)

        if not lyrics:
            bot.send_message(chat_id, "⚠️ Could not generate lyrics, continuing without them.")
            lyrics = []

        # 2. Render Video
        bot.send_message(chat_id, "🎬 Rendering video...")
        
        output_filename = f"vid_{uuid.uuid4().hex[:8]}.mp4"
        output_path = os.path.join(OUTPUT_DIR, output_filename)

        renderer = VideoRenderer(
            audio_path=audio_path,
            output_path=output_path,
            width=1080,  # 9:16 for Telegram/Tiktok
            height=1920,
            fps=30, # 30fps for faster rendering
            theme="trap_circle",
            palette_name="cyberpunk",
            song_title=clean_title,
            artist_name=clean_artist,
            lyrics_data=lyrics,
            bar_count=64
        )
        
        rendered_path = renderer.render_video()

        # 3. Send back to user
        bot.send_message(chat_id, "✅ Video rendered successfully! Uploading...")
        with open(rendered_path, 'rb') as video_file:
            bot.send_video(chat_id, video_file, caption=f"{clean_title} - {clean_artist}")

    except Exception as e:
        bot.send_message(chat_id, f"❌ Error occurred: {str(e)}")
        print(f"Error processing audio: {e}")

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, "Welcome to VIDA Telegram Bot! 🎵\n\nDrop a YouTube link or send an audio/video file here to automatically generate a music video.")

@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_text(message):
    text = message.text
    if is_youtube_url(text):
        chat_id = message.chat.id
        msg = bot.reply_to(message, "🔗 YouTube link detected. Downloading audio...")
        
        url = extract_youtube_url(text)
        
        def run_yt_task():
            try:
                def on_progress(pct, status):
                    pass
                
                audio_path, info = download_youtube_audio(url, output_dir=UPLOAD_DIR, on_progress=on_progress)
                if not audio_path or not os.path.exists(audio_path):
                    bot.edit_message_text("❌ Failed to download audio from YouTube.", chat_id, msg.message_id)
                    return
                
                # Use threaded process_audio
                threading.Thread(target=process_audio, args=(chat_id, audio_path, os.path.basename(audio_path))).start()
                
            except Exception as e:
                bot.send_message(chat_id, f"❌ Error: {str(e)}")
        
        threading.Thread(target=run_yt_task).start()
    else:
        bot.reply_to(message, "Please send a valid YouTube link or upload an audio/video file.")

@bot.message_handler(content_types=['audio', 'voice', 'video', 'document'])
def handle_docs_audio(message):
    try:
        chat_id = message.chat.id
        file_info = None
        
        if message.audio:
            file_info = bot.get_file(message.audio.file_id)
        elif message.voice:
            file_info = bot.get_file(message.voice.file_id)
        elif message.video:
            file_info = bot.get_file(message.video.file_id)
        elif message.document:
            file_info = bot.get_file(message.document.file_id)
            
        if not file_info:
            return

        bot.reply_to(message, "📥 Downloading your file...")
        downloaded_file = bot.download_file(file_info.file_path)
        
        ext = os.path.splitext(file_info.file_path)[1]
        unique_name = f"tg_{uuid.uuid4().hex[:8]}{ext}"
        saved_path = os.path.join(UPLOAD_DIR, unique_name)
        
        with open(saved_path, 'wb') as new_file:
            new_file.write(downloaded_file)
            
        threading.Thread(target=process_audio, args=(chat_id, saved_path, unique_name)).start()

    except Exception as e:
        bot.reply_to(message, f"❌ Failed to download file: {str(e)}")

if __name__ == "__main__":
    print("Starting VIDA Telegram Bot...")
    bot.infinity_polling()
