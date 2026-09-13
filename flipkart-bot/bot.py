import os
import re
import asyncio
import logging
import sys

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

from dotenv import load_dotenv
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    BotCommand,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    CallbackQueryHandler,
    filters,
)

import database as db
from scraper import FlipkartScraper

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "5873900420"))
DEFAULT_INTERVAL = int(os.getenv("DEFAULT_CHECK_INTERVAL", "5"))
DEFAULT_PINCODE = os.getenv("DEFAULT_PINCODE", "110091")

scraper = FlipkartScraper(pincode=DEFAULT_PINCODE)

IPHONE_16_128GB = [
    ("Apple iPhone 16 (Black, 128 GB)", "https://www.flipkart.com/apple-iphone-16-black-128-gb/p/itmb07d67f995271?pid=MOBH4DQFG8NKFRDY"),
    ("Apple iPhone 16 (Pink, 128 GB)", "https://www.flipkart.com/apple-iphone-16-pink-128-gb/p/itmc2e910b4d0b1c?pid=MOBH4DQFWJVDRSHM"),
    ("Apple iPhone 16 (Teal, 128 GB)", "https://www.flipkart.com/apple-iphone-16-teal-128-gb/p/itmce4bb3f55cc2f?pid=MOBH4DQFSY9ETDUU"),
    ("Apple iPhone 16 (Ultramarine, 128 GB)", "https://www.flipkart.com/apple-iphone-16-ultramarine-128-gb/p/itmcc210cae43fba?pid=MOBH4DQFYZT6EH2F"),
    ("Apple iPhone 16 (White, 128 GB)", "https://www.flipkart.com/apple-iphone-16-white-128-gb/p/itm7c0281cd247be?pid=MOBH4DQF849HCG6G"),
]

IPHONE_17_256GB = [
    ("Apple iPhone 17 (White, 256 GB)", "https://www.flipkart.com/apple-iphone-17-white-256-gb/p/itmf98e89534d806?pid=MOBHFN6YTSH3QRCZ"),
    ("Apple iPhone 17 (Black, 256 GB)", "https://www.flipkart.com/apple-iphone-17-black-256-gb/p/itm6eb39da622cdd?pid=MOBHFN6YN2HXB5HE"),
    ("Apple iPhone 17 (Mist Blue, 256 GB)", "https://www.flipkart.com/apple-iphone-17-mist-blue-256-gb/p/itm1834df7ee2812?pid=MOBHFN6YWTXZD8SG"),
    ("Apple iPhone 17 (Sage, 256 GB)", "https://www.flipkart.com/apple-iphone-17-sage-256-gb/p/itmcfa57eff7729c?pid=MOBHFN6YNAG4ZTHS"),
    ("Apple iPhone 17 (Lavender, 256 GB)", "https://www.flipkart.com/apple-iphone-17-lavender-256-gb/p/itmf37c8dffa4165?pid=MOBHFN6YKGBPYJZD"),
]

def get_main_reply_keyboard():
    """Persistent bottom keyboard buttons always visible above the chat bar."""
    keyboard = [
        [KeyboardButton("📋 View Products"), KeyboardButton("🔍 Check Now")],
        [KeyboardButton("➕ Add Product"), KeyboardButton("❌ Remove Product")],
        [KeyboardButton("⚙️ Track Options"), KeyboardButton("📍 Pincode")],
        [KeyboardButton("🗑 Clear All")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, is_persistent=True)

def get_tracking_options_keyboard():
    keyboard = [
        [InlineKeyboardButton("📱 iPhone 16 (128 GB)", callback_data="track_ip16")],
        [InlineKeyboardButton("📱 iPhone 17 (256 GB)", callback_data="track_ip17")],
        [InlineKeyboardButton("🔥 All (iPhone 16 + iPhone 17)", callback_data="track_all")],
    ]
    return InlineKeyboardMarkup(keyboard)

def format_clean_product_list(products, pincode: str = DEFAULT_PINCODE) -> str:
    ip16_list = []
    ip17_list = []
    other_list = []

    for p in products:
        title = p["title"] or "Product"
        is_stock = bool(p["is_in_stock"])
        status = p["status"] or "UNKNOWN"
        price_val = p["last_price"]
        price_str = f"₹{price_val:,}" if price_val else "N/A"

        # Explicit Green for In Stock, Red for Out of Stock / Notify Me
        if is_stock:
            badge = "🟢 [IN STOCK]"
        elif status == "NOTIFY_ME":
            badge = "🔴 [NOTIFY ME / OUT OF STOCK]"
        elif status == "COMING_SOON":
            badge = "🔴 [COMING SOON / OUT OF STOCK]"
        else:
            badge = "🔴 [OUT OF STOCK]"

        color_match = re.search(r'\(([^,]+),', title)
        item_label = color_match.group(1).strip() if color_match else title

        line = f"• *{item_label}* — *{price_str}* | {badge}\n  👉 [Buy on Flipkart]({p['url']})"

        title_lower = title.lower()
        if "iphone 16" in title_lower and "128" in title_lower:
            ip16_list.append(line)
        elif "iphone 17" in title_lower and "256" in title_lower:
            ip17_list.append(line)
        else:
            other_list.append(line)

    sections = []
    divider = "━━━━━━━━━━━━━━━━━━━━━━━━━━"
    if ip16_list:
        sections.append("📱 *Apple iPhone 16 (128 GB)*\n" + divider + "\n" + "\n\n".join(ip16_list))
    if ip17_list:
        sections.append("📱 *Apple iPhone 17 (256 GB)*\n" + divider + "\n" + "\n\n".join(ip17_list))
    if other_list:
        sections.append("📦 *Other Tracked Products*\n" + divider + "\n" + "\n\n".join(other_list))

    header = f"📋 *Your Tracked Flipkart Products*\n📍 *Active Pincode:* `{pincode}`\n\n"
    footer = (
        f"\n\n⚡ *Checking stock every {DEFAULT_INTERVAL}s for Pincode {pincode}.*\n"
        "🟢 Green = In Stock | 🔴 Red = Out of Stock\n\n"
        "👉 Use the buttons below to control your tracker!"
    )

    return header + "\n\n".join(sections) + footer

async def check_auth_or_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    user_id = user.id

    if db.is_user_approved(user_id, ADMIN_ID):
        return True

    db_user = db.get_user(user_id)
    if db_user:
        if db_user["status"] == "rejected":
            await update.message.reply_text("❌ Your access request was declined by the administrator.")
            return False
        if db_user["status"] == "paused":
            await update.message.reply_text("⏸️ *Your bot access is currently paused by the administrator.*", parse_mode=ParseMode.MARKDOWN)
            return False

    db.add_user_request(user_id, user.username, user.first_name)

    await update.message.reply_text(
        "⏳ *Access Request Pending Approval*\n\n"
        "Your access request has been sent to the Admin.\n"
        "Please wait until the admin approves your request. You will be notified automatically once approved.",
        parse_mode=ParseMode.MARKDOWN
    )

    admin_keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"admin_approve_{user_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"admin_reject_{user_id}")
        ]
    ])
    username_str = f"@{user.username}" if user.username else "No username"
    admin_msg = (
        "🔔 *New User Access Request*\n\n"
        f"👤 *Name:* {user.first_name}\n"
        f"🏷 *Username:* {username_str}\n"
        f"🆔 *User ID:* `{user_id}`\n\n"
        "Would you like to approve this user?"
    )
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=admin_msg,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=admin_keyboard
        )
    except Exception as e:
        logger.error(f"Failed to send request to admin {ADMIN_ID}: {e}")

    return False

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth_or_request(update, context):
        return

    user = update.effective_user
    user_id = user.id
    user_pin = db.get_user_pincode(user_id, DEFAULT_PINCODE)
    products = db.get_user_products(user_id)
    reply_markup = get_main_reply_keyboard()

    if not products:
        text = (
            f"👋 *Welcome {user.first_name} to Flipkart Stock Alert Bot!*\n\n"
            f"📍 Current Pincode: **{user_pin}**\n\n"
            "Choose which devices you want to track below:"
        )
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
        await update.message.reply_text(
            "👇 *Tap a button to select models to track:*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_tracking_options_keyboard()
        )
    else:
        formatted = format_clean_product_list(products, user_pin)
        await update.message.reply_text(
            formatted,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
            reply_markup=reply_markup
        )

def get_admin_panel_markup():
    users = db.get_all_users()
    keyboard = []
    for u in users:
        uid = u["user_id"]
        if str(uid) == str(ADMIN_ID):
            continue
        uname = f"@{u['username']}" if u["username"] else (u["first_name"] or str(uid))
        st = u["status"]
        
        status_icon = "🟢 Approved" if st == "approved" else ("⏸️ Paused" if st == "paused" else ("❌ Rejected" if st == "rejected" else "⏳ Pending"))
        
        row = []
        if st == "approved":
            row.append(InlineKeyboardButton(f"⏸️ Pause {uname}", callback_data=f"adm_pause_{uid}"))
        elif st in ["paused", "rejected", "pending"]:
            row.append(InlineKeyboardButton(f"▶️ Resume {uname}", callback_data=f"adm_resume_{uid}"))
        
        keyboard.append([InlineKeyboardButton(f"👤 {uname} ({status_icon})", callback_data=f"adm_info_{uid}")])
        if row:
            keyboard.append(row)
            
    keyboard.append([InlineKeyboardButton("🔄 Refresh Admin Panel", callback_data="adm_refresh")])
    return InlineKeyboardMarkup(keyboard)

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("⛔ *Access Denied:* Only the bot administrator can access this panel.", parse_mode=ParseMode.MARKDOWN)
        return

    users = db.get_all_users()
    non_admin_users = [u for u in users if str(u["user_id"]) != str(ADMIN_ID)]

    text = (
        "👑 *ADMIN DASHBOARD*\n\n"
        f"📊 *Total Registered Users:* {len(non_admin_users)}\n\n"
        "Here you can view, *Pause (⏸️)* or *Resume (▶️)* any user's access at any time:\n"
    )
    
    if not non_admin_users:
        text += "_No other users have registered yet._"
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
        return

    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_admin_panel_markup()
    )


async def options_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth_or_request(update, context):
        return

    user_pin = db.get_user_pincode(update.effective_user.id, DEFAULT_PINCODE)
    await update.message.reply_text(
        f"📱 *Select which products you would like to track for Pincode {user_pin}:*",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_tracking_options_keyboard()
    )

async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth_or_request(update, context):
        return

    user_id = update.effective_user.id
    user_pin = db.get_user_pincode(user_id, DEFAULT_PINCODE)
    products = db.get_user_products(user_id)
    reply_markup = get_main_reply_keyboard()

    if not products:
        await update.message.reply_text(
            "📭 Your tracking list is currently empty.\n\n"
            "Use the button below to select iPhone 16 / iPhone 17 / All, or tap **➕ Add Product**.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
        await update.message.reply_text(
            "👇 *Select models to track:*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_tracking_options_keyboard()
        )
        return

    formatted = format_clean_product_list(products, user_pin)
    await update.message.reply_text(
        formatted,
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True,
        reply_markup=reply_markup
    )

async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth_or_request(update, context):
        return

    user_id = update.effective_user.id
    user_pin = db.get_user_pincode(user_id, DEFAULT_PINCODE)
    products = db.get_user_products(user_id)

    if not products:
        await update.message.reply_text(
            "📭 No products in your tracking list.",
            reply_markup=get_main_reply_keyboard()
        )
        await update.message.reply_text(
            "👇 *Choose models to track:*",
            reply_markup=get_tracking_options_keyboard()
        )
        return

    # 1. Instant response with latest database snapshot
    formatted = format_clean_product_list(products, user_pin)
    status_msg = await update.message.reply_text(
        formatted + "\n\n🔄 _Refreshing live Flipkart stock in background..._",
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True,
        reply_markup=get_main_reply_keyboard()
    )

    # 2. Async background refresh for fresh data
    async def refresh_in_bg():
        try:
            urls = [p["url"] for p in products]
            tasks = [asyncio.to_thread(scraper.fetch_product_details, u, user_pin) for u in urls]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for p, res in zip(products, results):
                if isinstance(res, dict) and res.get("success"):
                    new_price = res.get("price")
                    new_status = res.get("status", "UNKNOWN")
                    is_in_stock = res.get("is_in_stock", False)
                    db.update_product_status(p["id"], new_price, new_status, is_in_stock)

            updated = db.get_user_products(user_id)
            new_formatted = format_clean_product_list(updated, user_pin)
            await status_msg.edit_text(
                new_formatted,
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True
            )
        except Exception as e:
            logger.error(f"Error during async refresh: {e}")

    asyncio.create_task(refresh_in_bg())

async def add_product_flow(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str):
    """Adds a single product by URL."""
    user_id = update.effective_user.id
    user_pin = db.get_user_pincode(user_id, DEFAULT_PINCODE)

    progress = await update.message.reply_text(f"⏳ Verifying product details for Pincode {user_pin}...")

    res = await asyncio.to_thread(scraper.fetch_product_details, url, user_pin)
    if not res.get("success"):
        await progress.edit_text(f"❌ Failed to fetch product: {res.get('error', 'Unknown error')}")
        return

    title = res.get("title", "Flipkart Product")
    price = res.get("price")
    status = res.get("status", "UNKNOWN")
    is_in_stock = res.get("is_in_stock", False)

    db.add_product(user_id, url, title, price, status, is_in_stock)

    badge = "🟢 [IN STOCK]" if is_in_stock else "🔴 [OUT OF STOCK]"
    price_str = f"₹{price:,}" if price else "N/A"

    success_msg = (
        f"✅ *Product Successfully Added!*\\n\\n"
        f"📦 *Product:* {title}\\n"
        f"💰 *Price:* {price_str}\\n"
        f"📊 *Status:* {badge}\\n"
        f"📍 *Pincode:* `{user_pin}`\\n\\n"
        f"The bot will alert you the moment it comes in stock!"
    )
    await progress.edit_text(success_msg, parse_mode=ParseMode.MARKDOWN)

async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth_or_request(update, context):
        return

    if not context.args:
        await update.message.reply_text(
            "➕ *Add a Flipkart Product*\n\n"
            "Please send or paste any Flipkart product link.\n"
            "Example:\n`/add https://www.flipkart.com/...`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    url = context.args[0].strip()
    if not ("flipkart.com" in url):
        await update.message.reply_text("❌ Please provide a valid Flipkart product URL.")
        return

    await add_product_flow(update, context, url)

async def remove_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows an interactive list of products with 1-click remove buttons."""
    if not await check_auth_or_request(update, context):
        return

    user_id = update.effective_user.id
    products = db.get_user_products(user_id)

    if not products:
        await update.message.reply_text("📭 Your tracking list is empty. Nothing to remove.")
        return

    buttons = []
    for p in products:
        title = p["title"] or "Product"
        color_match = re.search(r'\(([^,]+),', title)
        short_title = title if not color_match else f"{'16' if '16' in title else '17'} {color_match.group(1).strip()}"
        buttons.append([InlineKeyboardButton(f"❌ Remove {short_title}", callback_data=f"del_prod_{p['id']}")])

    buttons.append([InlineKeyboardButton("🗑 Clear All Products", callback_data="del_all_prods")])

    await update.message.reply_text(
        "🗑 *Select a product to remove from tracking:*",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def pincode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth_or_request(update, context):
        return

    user_id = update.effective_user.id
    current_pin = db.get_user_pincode(user_id, DEFAULT_PINCODE)

    if context.args:
        arg = context.args[0].strip().lower()
        if arg in ["reset", "remove", "default"]:
            db.set_user_pincode(user_id, "110091")
            await update.message.reply_text(
                "✅ Pincode reset to default: **110091** (Delhi).",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_main_reply_keyboard()
            )
            return
        elif re.match(r'^\d{6}$', arg):
            new_pin = arg
            db.set_user_pincode(user_id, new_pin)
            await update.message.reply_text(
                f"✅ Pincode updated to: **{new_pin}**!\nAll future stock checks will be performed for this pincode.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_main_reply_keyboard()
            )
            return
        else:
            await update.message.reply_text("⚠️ Invalid pincode! Please enter a 6-digit Indian pincode (e.g. `/pincode 110091`).")
            return

    pin_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Reset to 110091", callback_data="pin_reset_default")]
    ])
    msg = (
        f"📍 *Pincode Settings*\n\n"
        f"• Current Active Pincode: **`{current_pin}`**\n\n"
        f"To change your pincode, send:\n`/pincode <6-digit pincode>`\nExample: `/pincode 110091`\n\n"
        f"To reset to default (110091), send:\n`/pincode reset` or tap the button below:"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=pin_kb)

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth_or_request(update, context):
        return

    user_id = update.effective_user.id
    db.clear_user_products(user_id)
    await update.message.reply_text(
        "🗑 Your tracking list has been cleared.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_main_reply_keyboard()
    )
    await update.message.reply_text(
        "👇 *Select models to track:*",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_tracking_options_keyboard()
    )

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles bottom keyboard buttons and raw Flipkart URLs sent by the user."""
    text = update.message.text.strip()

    if text == "📋 View Products":
        await list_command(update, context)
    elif text == "🔍 Check Now":
        await check_command(update, context)
    elif text == "➕ Add Product":
        await update.message.reply_text(
            "➕ *Send a Flipkart Link*\n\n"
            "Paste any Flipkart product URL here to add it to your tracking list!",
            parse_mode=ParseMode.MARKDOWN
        )
    elif text == "❌ Remove Product":
        await remove_command(update, context)
    elif text == "⚙️ Track Options":
        await options_command(update, context)
    elif text == "📍 Pincode":
        await pincode_command(update, context)
    elif text == "🗑 Clear All":
        await clear_command(update, context)
    elif "flipkart.com" in text:
        urls = re.findall(r'https?://(?:www\.)?flipkart\.com/[^\s]+', text)
        if urls:
            await add_product_flow(update, context, urls[0])
    elif re.match(r'^\d{6}$', text):
        user_id = update.effective_user.id
        db.set_user_pincode(user_id, text)
        await update.message.reply_text(
            f"✅ Pincode updated to: **{text}**!\nAll future stock checks will be performed for this pincode.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_reply_keyboard()
        )

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user = query.from_user
    user_id = user.id

    if data.startswith("admin_approve_"):
        if user_id != ADMIN_ID:
            await query.edit_message_text("❌ Only the bot administrator can perform this action.")
            return

        target_id = int(data.replace("admin_approve_", ""))
        db.approve_user(target_id)
        target_info = db.get_user(target_id)
        name_str = target_info["first_name"] if target_info else target_id
        await query.edit_message_text(f"✅ User *{name_str}* (`{target_id}`) has been APPROVED.", parse_mode=ParseMode.MARKDOWN)

        try:
            welcome_msg = (
                "🎉 *Your Access Has Been Approved by the Admin!*\n\n"
                f"📍 Monitoring Location: Pincode {DEFAULT_PINCODE}\n\n"
                "Please choose which products you would like to track below:"
            )
            await context.bot.send_message(
                chat_id=target_id,
                text=welcome_msg,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_main_reply_keyboard()
            )
            await context.bot.send_message(
                chat_id=target_id,
                text="👇 *Select models:*",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_tracking_options_keyboard()
            )
        except Exception as e:
            logger.error(f"Error messaging approved user {target_id}: {e}")
        return

    if data.startswith("admin_reject_"):
        if user_id != ADMIN_ID:
            await query.edit_message_text("❌ Only the bot administrator can perform this action.")
            return

        target_id = int(data.replace("admin_reject_", ""))
        db.reject_user(target_id)
        await query.edit_message_text(f"❌ User `{target_id}` has been REJECTED.", parse_mode=ParseMode.MARKDOWN)

        try:
            await context.bot.send_message(
                chat_id=target_id,
                text="❌ Your access request was declined by the administrator."
            )
        except Exception as e:
            logger.error(f"Error messaging rejected user {target_id}: {e}")
        return

    if data.startswith("adm_pause_"):
        if user_id != ADMIN_ID:
            await query.edit_message_text("❌ Only the administrator can pause users.")
            return

        target_id = int(data.replace("adm_pause_", ""))
        db.pause_user(target_id)
        target_info = db.get_user(target_id)
        tname = f"@{target_info['username']}" if target_info and target_info["username"] else (target_info["first_name"] if target_info else target_id)
        
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text="⏸️ *Your bot access has been temporarily paused by the administrator.*",
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception:
            pass

        await query.edit_message_text(
            f"⏸️ User *{tname}* has been PAUSED.\nTheir products will not be checked until resumed.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_admin_panel_markup()
        )
        return

    if data.startswith("adm_resume_"):
        if user_id != ADMIN_ID:
            await query.edit_message_text("❌ Only the administrator can resume users.")
            return

        target_id = int(data.replace("adm_resume_", ""))
        db.resume_user(target_id)
        target_info = db.get_user(target_id)
        tname = f"@{target_info['username']}" if target_info and target_info["username"] else (target_info["first_name"] if target_info else target_id)

        try:
            await context.bot.send_message(
                chat_id=target_id,
                text="▶️ *Your bot access has been resumed by the administrator!*",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_main_reply_keyboard()
            )
        except Exception:
            pass

        await query.edit_message_text(
            f"▶️ User *{tname}* has been RESUMED to active status.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_admin_panel_markup()
        )
        return

    if data == "adm_refresh":
        if user_id != ADMIN_ID:
            return
        await query.edit_message_reply_markup(reply_markup=get_admin_panel_markup())
        return

    if data == "pin_reset_default":
        db.set_user_pincode(user_id, "110091")
        await query.edit_message_text("✅ Pincode reset to default: **110091** (Delhi).", parse_mode=ParseMode.MARKDOWN)
        return

    if data.startswith("del_prod_"):
        prod_id = int(data.replace("del_prod_", ""))
        db.delete_product(prod_id, user_id)
        await query.edit_message_text("✅ Product removed from your tracking list.")
        return

    if data == "del_all_prods":
        db.clear_user_products(user_id)
        await query.edit_message_text("🗑 All products removed from your tracking list.")
        return

    if data in ["track_ip16", "track_ip17", "track_all"]:
        if not db.is_user_approved(user_id, ADMIN_ID):
            await query.edit_message_text("⏳ Your access is pending admin approval.")
            return

        user_pin = db.get_user_pincode(user_id, DEFAULT_PINCODE)

        items_to_add = []
        label = ""
        if data == "track_ip16":
            items_to_add = IPHONE_16_128GB
            label = "iPhone 16 (128 GB) [5 Colors]"
        elif data == "track_ip17":
            items_to_add = IPHONE_17_256GB
            label = "iPhone 17 (256 GB) [5 Colors]"
        elif data == "track_all":
            items_to_add = IPHONE_16_128GB + IPHONE_17_256GB
            label = "All Models (iPhone 16 + iPhone 17) [10 Phones]"

        # Add products immediately with default values
        for name, url in items_to_add:
            price = 69900 if "16" in name else 82900
            db.add_product(user_id, url, name, price, "NOTIFY_ME", False)

        user_prods = db.get_user_products(user_id)
        formatted = format_clean_product_list(user_prods, user_pin)
        await query.edit_message_text(
            f"✅ *{label} added successfully!*\n\n" + formatted,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )

        # Update live Flipkart data in background without blocking Telegram
        async def refresh_added_models():
            try:
                urls = [item[1] for item in items_to_add]
                tasks = [asyncio.to_thread(scraper.fetch_product_details, u, user_pin) for u in urls]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                current_prods = {p["url"]: p["id"] for p in db.get_user_products(user_id)}
                for (name, url), res in zip(items_to_add, results):
                    if isinstance(res, dict) and res.get("success") and url in current_prods:
                        p_id = current_prods[url]
                        db.update_product_status(
                            p_id,
                            res.get("price"),
                            res.get("status", "NOTIFY_ME"),
                            res.get("is_in_stock", False)
                        )
            except Exception as e:
                logger.error(f"Error updating added models: {e}")

        asyncio.create_task(refresh_added_models())

alerted_in_stock = set()
is_checking = False

async def background_stock_checker(context: ContextTypes.DEFAULT_TYPE):
    global alerted_in_stock, is_checking
    if is_checking:
        return

    is_checking = True
    try:
        all_products = db.get_all_products()
        if not all_products:
            return

        # Group by (url, user_pincode)
        checks = []
        for p in all_products:
            user_pin = db.get_user_pincode(p["user_id"], DEFAULT_PINCODE)
            checks.append((p["url"], user_pin))

        unique_checks = list(set(checks))
        tasks = [asyncio.to_thread(scraper.fetch_product_details, u, pin) for u, pin in unique_checks]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        lookup = {}
        for (u, pin), r in zip(unique_checks, results):
            if isinstance(r, dict) and r.get("success"):
                lookup[(u, pin)] = r

        for p in all_products:
            url = p["url"]
            user_id = p["user_id"]
            user_pin = db.get_user_pincode(user_id, DEFAULT_PINCODE)

            if (url, user_pin) not in lookup:
                continue

            res = lookup[(url, user_pin)]
            prod_id = p["id"]
            prev_status = p["status"]
            prev_in_stock = bool(p["is_in_stock"])
            prev_price = p["last_price"]

            current_status = res.get("status", "UNKNOWN")
            current_in_stock = res.get("is_in_stock", False)
            current_price = res.get("price")
            title = res.get("title", p["title"])

            db.update_product_status(prod_id, current_price, current_status, current_in_stock)

            cache_key = f"{user_id}_{url}_{user_pin}"

            # Only alert when it ACTUALLY comes in stock
            if current_in_stock and cache_key not in alerted_in_stock:
                alerted_in_stock.add(cache_key)
                price_str = f"₹{current_price:,}" if current_price else "Price N/A"
                alert_text = (
                    "🚨 *STOCK ALERT: ITEM IS IN STOCK!* 🚨\n\n"
                    f"🎉 *{title}* is now available for Pincode {user_pin} on Flipkart!\n\n"
                    f"💰 *Current Price:* {price_str}\n"
                    f"📊 *Status:* 🟢 `IN_STOCK` (Previous: `{prev_status}`)\n\n"
                    "⚡ Hurry! Click below to order immediately:\n"
                    f"👉 [BUY NOW ON FLIPKART]({url})"
                )
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=alert_text,
                        parse_mode=ParseMode.MARKDOWN,
                        disable_web_page_preview=False
                    )
                    logger.info(f"IN_STOCK alert delivered to {user_id} for {title}")
                except Exception as e:
                    logger.error(f"Error sending stock alert: {e}")

            elif not current_in_stock and cache_key in alerted_in_stock:
                alerted_in_stock.remove(cache_key)

            elif prev_in_stock and current_in_stock and prev_price and current_price and current_price < prev_price:
                diff = prev_price - current_price
                price_alert = (
                    "📉 *PRICE DROP ALERT!* 📉\n\n"
                    f"📦 *Product:* {title}\n"
                    f"💰 *New Price:* ₹{current_price:,} (Was: ₹{prev_price:,})\n"
                    f"💵 *Discount:* ₹{diff:,} OFF!\n\n"
                    f"👉 [Buy on Flipkart]({url})"
                )
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=price_alert,
                        parse_mode=ParseMode.MARKDOWN
                    )
                except Exception as e:
                    logger.error(f"Error sending price drop alert: {e}")

    except Exception as e:
        logger.error(f"Checker error: {e}")
    finally:
        is_checking = False

async def post_init(application: Application):
    """Sets the Telegram native Menu button commands."""
    commands = [
        BotCommand("start", "Start bot and show menu"),
        BotCommand("admin", "👑 Admin Dashboard (Pause/Resume users)"),
        BotCommand("list", "View all tracked devices"),
        BotCommand("check", "Refresh stock status right now"),
        BotCommand("add", "Add a custom product link"),
        BotCommand("remove", "Remove a product from tracking"),
        BotCommand("options", "Select iPhone 16 / 17 / All"),
        BotCommand("pincode", "Set or reset delivery pincode"),
        BotCommand("clear", "Clear all tracked items"),
    ]
    await application.bot.set_my_commands(commands)
    logger.info("Telegram Bot Menu commands configured successfully.")

def main():
    db.init_db(ADMIN_ID)
    
    if not TOKEN:
        print("ERROR: TELEGRAM_BOT_TOKEN is not set.")
        return

    application = Application.builder().token(TOKEN).post_init(post_init).concurrent_updates(True).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CommandHandler("options", options_command))
    application.add_handler(CommandHandler("list", list_command))
    application.add_handler(CommandHandler("check", check_command))
    application.add_handler(CommandHandler("add", add_command))
    application.add_handler(CommandHandler("remove", remove_command))
    application.add_handler(CommandHandler("pincode", pincode_command))
    application.add_handler(CommandHandler("clear", clear_command))
    application.add_handler(CallbackQueryHandler(callback_handler))

    # Handles persistent bottom keyboard buttons & direct URL pastes
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    job_queue = application.job_queue
    job_queue.run_repeating(background_stock_checker, interval=DEFAULT_INTERVAL, first=3)

    # Lightweight HTTP server for Render Web Service port detection
    import threading
    from http.server import HTTPServer, BaseHTTPRequestHandler
    import os

    class HealthCheckHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Flipkart Stock Tracker Bot is Healthy and Active!")

        def log_message(self, format, *args):
            return  # silence health check logs

    port = int(os.environ.get("PORT", 10000))
    def run_health_server():
        try:
            server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
            server.serve_forever()
        except Exception as e:
            logger.warning(f"Health server error: {e}")

    health_thread = threading.Thread(target=run_health_server, daemon=True)
    health_thread.start()
    logger.info(f"Health check server listening on port {port}")

    print(f"🚀 Flipkart Stock Alert Bot running with Green/Red status & Pincode/Add/Remove options on port {port}!")
    application.run_polling()

if __name__ == "__main__":
    main()
