import asyncio
import httpx
import os
from datetime import datetime
from telethon import TelegramClient, events

# 🔹 اطلاعات API ربات (از BotFather و my.telegram.org بگیرید)
api_id = 18377832  # جایگزین شود
api_hash = "ed8556c450c6d0fd68912423325dd09c"  # جایگزین شود
session_name = "my_ai"

client = TelegramClient(session_name, api_id, api_hash)

def create_progress_bar(percentage: float, width: int = 25) -> str:
    """ایجاد نوار پیشرفت"""
    filled = int(width * percentage / 100)
    empty = width - filled
    bar = '━' * filled + '─' * empty
    return f"[{bar}] {percentage:.1f}%"

async def download_and_upload_file(url, client, event, status_message, file_extension, index, total_files):
    """دانلود و آپلود همزمان فایل"""
    try:
        temp_filename = f"temp_{hash(url)}_{datetime.now().timestamp()}{file_extension}"
        async with httpx.AsyncClient(timeout=60.0) as http_client:
            response = await http_client.get(url, follow_redirects=True)

            if response.status_code != 200:
                await status_message.edit(f"❌ خطا در دانلود فایل {index}")
                return

            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            last_update_time = 0

            # دانلود فایل
            with open(temp_filename, 'wb') as f:
                async for chunk in response.aiter_bytes(chunk_size=8192):
                    f.write(chunk)
                    downloaded += len(chunk)

                    current_time = asyncio.get_event_loop().time()
                    if current_time - last_update_time > 0.5 and total_size > 0:
                        last_update_time = current_time
                        percentage = (downloaded / total_size) * 100
                        progress_bar = create_progress_bar(percentage)
                        size_mb = downloaded / (1024 * 1024)
                        total_mb = total_size / (1024 * 1024)
                        await status_message.edit(
                            f"📥 دانلود فایل {index} از {total_files}...\n"
                            f"{progress_bar}\n"
                            f"💾 {size_mb:.1f}MB / {total_mb:.1f}MB"
                        )

        # آپلود فایل
        try:
            last_update_time = 0

            async def progress_callback(current, total):
                nonlocal last_update_time
                current_time = asyncio.get_event_loop().time()

                if current_time - last_update_time > 0.5:
                    last_update_time = current_time
                    percentage = (current / total) * 100
                    progress_bar = create_progress_bar(percentage)
                    size_mb = current / (1024 * 1024)
                    total_mb = total / (1024 * 1024)
                    await status_message.edit(
                        f"📤 آپلود فایل {index} از {total_files}...\n"
                        f"{progress_bar}\n"
                        f"💾 {size_mb:.1f}MB / {total_mb:.1f}MB"
                    )

            await event.client.send_file(
                event.chat_id,
                file=temp_filename,
                reply_to=event.message.id,
                supports_streaming=True if file_extension == '.mp4' else None,
                progress_callback=progress_callback
            )

        finally:
            if os.path.exists(temp_filename):
                os.remove(temp_filename)

    except Exception as e:
        print(f"خطا در پردازش فایل: {e}")
        await status_message.edit(f"❌ خطا در پردازش فایل {index}")

async def process_instagram_link(event, message, status_message):
    """پردازش لینک اینستاگرام و دانلود فایل‌ها"""
    async with httpx.AsyncClient(timeout=60.0) as http_client:
        for attempt in range(2):  
            try:
                api_url = f"https://دامین‌خوشگلت/insta.php?url={message}"
                response = await http_client.get(api_url)
                data = response.json()

                if not data or data == []:
                    if attempt == 0:
                        await status_message.edit("تلاش مجدد...")
                        await asyncio.sleep(2)
                        continue
                    else:
                        await status_message.edit("❌ دریافت اطلاعات از API ناموفق بود.")
                        return

                tasks = []
                for index, item in enumerate(data, 1):
                    media_url = item["media"]
                    media_type = item["type"]
                    file_extension = '.jpg' if media_type == "photo" else '.mp4'

                    task = asyncio.create_task(
                        download_and_upload_file(
                            media_url,
                            http_client,
                            event,
                            status_message,
                            file_extension,
                            index,
                            len(data)
                        )
                    )
                    tasks.append(task)

                await asyncio.gather(*tasks)

                await status_message.edit("✅ عملیات با موفقیت انجام شد!")
                await asyncio.sleep(3)
                await status_message.delete()
                return

            except Exception as e:
                print(f"خطا در پردازش لینک (تلاش {attempt + 1}): {e}")
                if attempt == 0:
                    await status_message.edit("❌ مشکل در پردازش. در حال تلاش مجدد...")
                    await asyncio.sleep(2)
                else:
                    await status_message.edit("❌ مشکل در پردازش. لطفا بعداً تلاش کنید.")

@client.on(events.NewMessage(pattern=r'.*instagram\.com.*'))
async def handle_instagram(event):
    """پردازش لینک‌های اینستاگرام"""
    message = event.message.text
    status_message = await event.reply("🔄 در حال پردازش لینک... لطفا صبر کنید.")
    await process_instagram_link(event, message, status_message)

print("✅ ربات فعال شد.")
client.run_until_disconnected()
