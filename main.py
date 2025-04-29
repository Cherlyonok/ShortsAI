import os
import uuid
import logging
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, CallbackContext
import base64
import time
from runwayml import RunwayML
from openai import OpenAI
from moviepy import VideoFileClip, concatenate_videoclips, AudioFileClip

# API ключи
TELEGRAM_API_KEY = 'fill'
OPENAI_API_KEY = "fill"
SPEECH_FOLDER_ID = "fill"
SPEECH_API_KEY = "fill"
RUNWAY_API_TOKEN = 'fill'


PRODUCT_NAME, PRODUCT_FEATURES, TARGET_AUDIENCE, DURATION, TONE, NOTES, IMAGE, CHOICE_VOICE, CUSTOM_VOICE_TEXT = range(9)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)


def get_script_from_api(product_name, features, target_audience, duration, tone, notes):

    prompt = f"""
    Create a script for a YouTube Shorts advertisement lasting {duration} seconds for the product: {product_name}.
    Features: {features}
    Target Audience: {target_audience}
    Tone: {tone}
    Special Requests: {notes}
    Script format:
    The product MUST be shown in EVERY scene.
    Scene descriptions must be long and profound.
    Every movement in each scene MUST be described - there MUST NOT be broad descriptions.
    Scenes must feature different locations and different characters (no character should appear in more than one scene).
    Break the video into scenes of approximately 5 seconds each.
    DO NOT make a scene compilation of other scenes.
    For each scene, provide it in the following specific format:
    Title: Scene x
    What happens: A detailed description of what happens in the scene. Make sure to describe the specific action and product usage.
    Camera: Camera angle, camera movements (if any), and any important details about framing.
    Visual elements: Setting, colors, textures, lighting, and how the product should be visually integrated into the scene.
    Sound: Background track, sound effects.
    Notes: Any additional brief explanations or instructions if necessary.
    Product: How the product should be presented in the shot (close-ups, on the table, in use, etc.).
    Make sure the script is:
    Written in clear English.
    The product is shown in EVERY scene.
    Scenes do not contain the same locations and characters (different characters in each scene).
    Creative and dynamic (suitable for the Shorts format).
    Understandable even without sound, since many people watch YouTube Shorts without audio.
    Suitable for editing with text overlays and quick transitions.
    No repeating locations or characters.
    The shots of the product must be creative and have cool visual hooks.
        """
    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.responses.create(
        model="gpt-4.1",
        input=prompt
    )
    return response.output_text


def generate_image_from_scene(scene_description, image_path):
    prompt = """
    I will give you the description of a scene.
    You should generate a photorealistic image of the start of this scene as if it was shot on Sony ZV-E10 Kit 16-50 using in the picture the exact product from the reference image
    the result must be 9x16. 
    Make sure not to create any morphing, excessive body parts 
    The product from the reference image must be EXACT same one.
    The vibe must be aesthetic and cinematic highly detailed
    Scene:
    """
    client = OpenAI(api_key=OPENAI_API_KEY)
    result = client.images.edit(
        model="gpt-image-1",
        image=[
            open(image_path, "rb"),
        ],
        prompt=prompt+scene_description
    )
    image_base64 = result.data[0].b64_json

    return image_base64


def download_video(video_url, save_path):
    response = requests.get(video_url)
    if response.status_code == 200:
        print('trying to download')
        with open(save_path, "wb") as f:
            print('writing')
            f.write(response.content)
    else:
        print(f"Ошибка скачивания: {video_url}")


def create_video_with_runway(images, scenes):
    client = RunwayML(api_key=RUNWAY_API_TOKEN)
    videos = []
    for i in range(len(images)):
        prompt = scenes[i]
        if len(scenes[i]) > 1000:
            prompt = prompt[:999]
        task = client.image_to_video.create(
            model='gen4_turbo',
            prompt_image=f"data:image/png;base64,{images[i]}",
            duration=5,
            prompt_text=prompt,
            ratio="720:1280"
        )
        task_id = task.id
        print("Task created, polling...")
        time.sleep(10)
        task = client.tasks.retrieve(task_id)
        while task.status not in ['SUCCEEDED', 'FAILED']:
            print(f"Status: {task.status}... Waiting...")
            task = client.tasks.retrieve(task_id)
        print(task)
        print(task.output)
        if task.status == 'SUCCEEDED':
            video_url = task.output[0]
            videos.append(video_url)
            print('Видео готово! Ссылка на видео:', video_url)

    os.makedirs('videos', exist_ok=True)
    video_paths = []
    for idx, url in enumerate(videos):
        unique_filename = str(uuid.uuid4())
        save_path = f"videos/video_{unique_filename}.mp4"
        download_video(url, save_path)
        video_paths.append(save_path)
    clips = [VideoFileClip(path) for path in video_paths]
    final_clip = concatenate_videoclips(clips, method="compose")
    unique_filename = str(uuid.uuid4())
    output_path = f"videos/final_{unique_filename}.mp4"
    final_clip.write_videofile(output_path, codec="libx264", audio_codec="aac")
    final_clip.close()
    return output_path


async def start(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "Привет! Я помогу создать рекламный ролик для вашего продукта. Начнём?\nСначала мне нужно будет немного информации."
        " Напишите название товара и бренда."
    )
    return PRODUCT_NAME


async def product_name(update: Update, context: CallbackContext):
    context.user_data['product_name'] = update.message.text
    await update.message.reply_text(
        "Отлично! Опишите ключевые характеристики товара, которые хочется подсветить в видео.")
    return PRODUCT_FEATURES


async def product_features(update: Update, context: CallbackContext):
    context.user_data['product_features'] = update.message.text
    await update.message.reply_text("Какая целевая аудитория для этого товара?")
    return TARGET_AUDIENCE


async def target_audience(update: Update, context: CallbackContext):
    context.user_data['target_audience'] = update.message.text
    await update.message.reply_text(
        "Опишите общее настроение ролика, которое вы хотите создать. (например, легкий мотивирующий ролик или серьезная реклама)")
    return DURATION


async def duration(update: Update, context: CallbackContext):
    context.user_data['duration'] = update.message.text
    await update.message.reply_text("Сколько секунд должен длиться ролик? (от 10 до 60)")
    return TONE


async def tone(update: Update, context: CallbackContext):
    context.user_data['tone'] = update.message.text
    await update.message.reply_text("Есть ли какие-то особые пожелания для сценария?")
    return NOTES


async def notes(update: Update, context: CallbackContext):
    context.user_data['notes'] = update.message.text
    await update.message.reply_text("Теперь отправьте четкое изображение товара.")
    return IMAGE


def generate_voice(voice_over):
    url = "https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize"

    headers = {
        "Authorization": f"Bearer {SPEECH_API_KEY}"
    }

    data = {
        "text": voice_over,
        "lang": "ru-RU",
        "voice": "ermil",
        "emotion": "good",
        "speed": 1.2,
        "folderId": SPEECH_FOLDER_ID,
        "format": "mp3"
    }
    os.makedirs('voice', exist_ok=True)
    unique_filename = str(uuid.uuid4()) + ".mp3"
    voice_path = f"voice/{unique_filename}"
    response = requests.post(url, headers=headers, data=data)
    print(response)
    if response.status_code == 200:
        with open(voice_path, "wb") as f:
            f.write(response.content)

    return voice_path


async def generate_shorts(update: Update, context: CallbackContext):
    script = get_script_from_api(
        context.user_data['product_name'],
        context.user_data['product_features'],
        context.user_data['target_audience'],
        context.user_data['duration'],
        context.user_data['tone'],
        context.user_data['notes']
    )
    scenes = script.split("Scene ")

    images = []
    for i, scene in enumerate(scenes[1:], 1):
        scene_description = f"Scene {i}: {scene}"
        output_image = generate_image_from_scene(scene_description, context.user_data['image_path'])
        images.append(output_image)

    output_path = create_video_with_runway(images, scenes)
    context.user_data['video_path'] = output_path

    prompt = f"Создай озвучку на русском языке для рекламного ролика со следующим сценарием: {script}. Обязательно учти временные ограничения на длину записи {context.user_data['duration']}"
    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.responses.create(
        model="gpt-4.1",
        input=prompt
    )
    voice_over = response.output_text
    context.user_data['voice_over'] = voice_over

    with open(output_path, "rb") as video_file:
        await update.message.reply_video(video=video_file)

    await update.message.reply_text(
        f"Вот предложенный текст озвучки:\n\n{voice_over}\n\n"
        "Выберите, как вы хотите продолжить:\n"
        "1. ✅ Использовать предложенный текст\n"
        "2. 📝 Отправить свой текст озвучки\n"
        "3. 🔇 Оставить видео без озвучки",
    )
    return CHOICE_VOICE


async def voice_choice(update: Update, context: CallbackContext):
    user_text = update.message.text.strip().lower()
    if "1" in user_text or "использовать" in user_text:
        voice_path = generate_voice(context.user_data['voice_over'])
        return await finalize_video_with_voice(update, context, voice_path)

    elif "2" in user_text or "свой" in user_text:
        await update.message.reply_text("Хорошо! Отправьте свой текст для озвучки.")
        return CUSTOM_VOICE_TEXT

    elif "3" in user_text or "без" in user_text:
        return ConversationHandler.END
    else:
        await update.message.reply_text("Пожалуйста, выберите 1, 2 или 3.")
        return CHOICE_VOICE


async def custom_voice_text(update: Update, context: CallbackContext):
    user_text = update.message.text
    voice_path = generate_voice(user_text)
    return await finalize_video_with_voice(update, context, voice_path)


async def finalize_video_with_voice(update: Update, context: CallbackContext, voice_path):
    video = VideoFileClip(context.user_data['video_path'])

    if voice_path:
        audio = AudioFileClip(voice_path)
        video.audio = audio

    unique_filename = str(uuid.uuid4()) + ".mp4"
    final_output_path = f"videos/final_{unique_filename}"
    video.write_videofile(final_output_path, codec="libx264", audio_codec="aac")

    with open(final_output_path, "rb") as final_video:
        await update.message.reply_video(video=final_video)

    return ConversationHandler.END


async def image(update: Update, context: CallbackContext):
    os.makedirs('product_images', exist_ok=True)

    unique_filename = str(uuid.uuid4()) + ".jpg"

    file = await update.message.photo[-1].get_file()
    image_path = f"product_images/{unique_filename}"

    await file.download_to_drive(image_path)

    context.user_data['image_path'] = image_path

    return await generate_shorts(update, context)


async def cancel(update: Update, context: CallbackContext):
    await update.message.reply_text("Процесс создания видео отменен.")
    return ConversationHandler.END


def main():
    application = Application.builder().token(TELEGRAM_API_KEY).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            PRODUCT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, product_name)],
            PRODUCT_FEATURES: [MessageHandler(filters.TEXT & ~filters.COMMAND, product_features)],
            TARGET_AUDIENCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, target_audience)],
            DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, duration)],
            TONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, tone)],
            NOTES: [MessageHandler(filters.TEXT & ~filters.COMMAND, notes)],
            IMAGE: [MessageHandler(filters.PHOTO, image)],
            CHOICE_VOICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, voice_choice)],
            CUSTOM_VOICE_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, custom_voice_text)]
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    application.add_handler(conv_handler)

    application.run_polling()


if __name__ == '__main__':
    main()
