import os
import json
import httpx
from telethon import events
import asyncio
from typing import Optional
from collections import defaultdict
from datetime import datetime

# دیکشنری برای نگهداری وضعیت دانلود/آپلود هر کاربر
user_tasks = defaultdict(list)

def create_progress_bar(percentage: float, width: int = 25) -> str:
    filled = int(width * percentage / 100)
    empty = width - filled
    bar = '━' * filled + '─' * empty
    return f"[{bar}] {percentage:.1f}%"

async def download_and_upload_file(url: str, client: httpx.AsyncClient, event, status_message, file_extension: str, index: int, total_files: int):
    """دانلود و آپلود همزمان فایل"""
    try:
        temp_filename = f"temp_{hash(url)}_{datetime.now().timestamp()}{file_extension}"
        response = await client.get(url, follow_redirects=True)
        
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
                        f"📥 درحال دانلود فایل {index} از {total_files}...\n"
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
                        f"📤 درحال آپلود فایل {index} از {total_files}...\n"
                        f"{progress_bar}\n"
                        f"💾 {size_mb:.1f}MB / {total_mb:.1f}MB"
                    )

            # ارسال فایل با ریپلای به پیام اصلی
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

async def process_instagram_link(event, message: str, status_message):
    """پردازش یک لینک اینستاگرام"""
    async with httpx.AsyncClient(timeout=60.0) as http_client:
        for attempt in range(2):  # دو بار تلاش
            try:
                # استفاده از API جدید
                api_url = f"https://insta-donn.onrender.com/ehsan?url={message}"
                response = await http_client.get(api_url)
                
                # بررسی وضعیت پاسخ
                if response.status_code != 200:
                    await status_message.edit("❌ خطا در دریافت اطلاعات از API.")
                    return
                
                data = response.json()
                
                # بررسی اینکه داده‌ها حاوی لینک ویدیو باشند
                if not data or not isinstance(data.get("data"), list):
                    if attempt == 0:  # اگر تلاش اول ناموفق بود
                        await status_message.edit("تلاش مجدد...")
                        await asyncio.sleep(2)  # کمی صبر قبل از تلاش مجدد
                        continue
                    else:  # اگر تلاش دوم هم ناموفق بود
                        await status_message.edit("❌ دریافت اطلاعات از API ناموفق بود.")
                        return

                # دریافت لینک ویدیو از داده‌های API
                media_url = data["data"][0]["media"]
                media_type = data["data"][0]["type"]
                file_extension = '.mp4' if media_type == "video" else '.jpg'
                
                # دانلود و ارسال فایل
                await download_and_upload_file(
                    media_url,
                    http_client,
                    event,
                    status_message,
                    file_extension,
                    1,  # چون فقط یک فایل داریم
                    1   # تعداد فایل‌ها 1 است
                )

                await status_message.edit("✅ عملیات با موفقیت انجام شد!")
                await asyncio.sleep(3)
                await status_message.delete()
                return  # خروج از تابع در صورت موفقیت

            except Exception as e:
                print(f"خطا در پردازش لینک (تلاش {attempt + 1}): {e}")
                if attempt == 0:  # اگر تلاش اول بود
                    await status_message.edit("❌ مشکل در پردازش. در حال تلاش مجدد...")
                    await asyncio.sleep(2)
                else:  # اگر تلاش دوم بود
                    await status_message.edit("❌ مشکل در پردازش. لطفا بعداً تلاش کنید.")
                        return
                
                # ایجاد تسک‌های همزمان برای دانلود و آپلود
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

                # اجرای همزمان تمام تسک‌ها
                await asyncio.gather(*tasks)
                
                await status_message.edit("✅ عملیات با موفقیت انجام شد!")
                await asyncio.sleep(3)
                await status_message.delete()
                return  # خروج از تابع در صورت موفقیت

            except Exception as e:
                print(f"خطا در پردازش لینک (تلاش {attempt + 1}): {e}")
                if attempt == 0:  # اگر تلاش اول بود
                    await status_message.edit("❌ مشکل در پردازش. در حال تلاش مجدد...")
                    await asyncio.sleep(2)
                else:  # اگر تلاش دوم بود
                    await status_message.edit("❌ مشکل در پردازش. لطفا بعداً تلاش کنید.")

async def instagram_handlers(client, db):
    """تنظیم هندلرهای مربوط به اینستاگرام"""
    
    @client.on(events.NewMessage(pattern=r'.*instagram\.com.*'))
    async def handle_instagram(event):
    	
        if db.is_user_blocked(event.sender_id):
            return
        """پردازش لینک‌های اینستاگرام"""
        message = event.message.text
        
        # ایجاد پیام وضعیت
        status_message = await event.reply("در حال پردازش لینک... لطفا صبر کنید.")
        
        # پردازش لینک به صورت همزمان
        await process_instagram_link(event, message, status_message)
