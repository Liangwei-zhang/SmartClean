"""
通知服務 - 使用 Arq 任務隊列
"""
import asyncio
import logging
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class NotificationType(str, Enum):
    NEW_ORDER = "new_order"
    ORDER_ACCEPTED = "order_accepted"
    ORDER_COMPLETED = "order_completed"
    ORDER_CANCELLED = "order_cancelled"
    REMINDER = "reminder"


async def send_push_notification(user_id: int, title: str, body: str, data: dict = None):
    """
    發送推送通知
    實際實現可對接 FCM / APNs / 極光推送
    """
    logger.info(f"📱 推送通知 [{user_id}] {title}: {body}")
    # TODO: 實現實際推送邏輯
    # 例如：FCM, APNs, 極光推送等
    return True


async def send_sms(phone: str, message: str):
    """
    發送短信
    實際實現可對接 Twilio / 阿里雲 SMS 等
    """
    logger.info(f"📲 短信 [{phone}] {message}")
    # TODO: 實現實際短信發送
    return True


async def send_email(to: str, subject: str, body: str):
    """
    發送郵件
    實際實現可對接 SendGrid / AWS SES 等
    """
    logger.info(f"📧 郵件 [{to}] {subject}: {body}")
    # TODO: 實現實際郵件發送
    return True


# === Arq 任務 ===

async def notify_new_order(ctx, order_id: int, cleaner_ids: list):
    """新訂單通知 - 廣播給所有清潔工"""
    logger.info(f"🔔 新訂單 #{order_id} 通知 {len(cleaner_ids)} 位清潔工")
    
    for cleaner_id in cleaner_ids:
        await send_push_notification(
            cleaner_id,
            "🆕 新訂單來了！",
            f"有一個新清潔訂單 #{order_id}，趕快搶單！",
            {"order_id": order_id, "type": NotificationType.NEW_ORDER}
        )


async def notify_order_accepted(ctx, order_id: int, host_id: int, cleaner_name: str):
    """訂單被接通知 - 通知房東"""
    logger.info(f"🔔 訂單 #{order_id} 被 {cleaner_name} 承接")
    
    await send_push_notification(
        host_id,
        "🎉 訂單被承接！",
        f"您的訂單 #{order_id} 已被 {cleaner_name} 承接",
        {"order_id": order_id, "type": NotificationType.ORDER_ACCEPTED}
    )


async def notify_order_completed(ctx, order_id: int, host_id: int, cleaner_name: str):
    """訂單完成通知 - 通知房東"""
    logger.info(f"🔔 訂單 #{order_id} 已完成")
    
    await send_push_notification(
        host_id,
        "✅ 清潔完成！",
        f"您的訂單 #{order_id} 已由 {cleaner_name} 完成",
        {"order_id": order_id, "type": NotificationType.ORDER_COMPLETED}
    )


async def notify_order_cancelled(ctx, order_id: int, user_ids: list, reason: str):
    """訂單取消通知"""
    logger.info(f"🔔 訂單 #{order_id} 已取消")
    
    for user_id in user_ids:
        await send_push_notification(
            user_id,
            "❌ 訂單取消",
            f"訂單 #{order_id} 已取消: {reason}",
            {"order_id": order_id, "type": NotificationType.ORDER_CANCELLED}
        )


async def send_reminder(ctx, user_id: int, order_id: int, message: str):
    """提醒通知"""
    logger.info(f"🔔 提醒用戶 {user_id}: {message}")
    
    await send_push_notification(
        user_id,
        "⏰ 提醒",
        message,
        {"order_id": order_id, "type": NotificationType.REMINDER}
    )


async def cleanup_old_notifications(ctx, days: int = 30):
    """清理舊通知記錄"""
    logger.info(f"🧹 清理 {days} 天前的通知記錄")
    # TODO: 實現清理邏輯


# === 便捷函數 ===

async def notify_cleaner_order_reminder(cleaner_id: int, order_id: int, minutes_until: int):
    """清潔工搶單提醒"""
    await send_reminder(
        cleaner_id,
        order_id,
        f"訂單 #{order_id} 將在 {minutes_until} 分鐘後開始，請準備！"
    )


async def notify_host_checkout_reminder(host_id: int, order_id: int, checkout_time: str):
    """房東退房時間提醒"""
    await send_reminder(
        host_id,
        order_id,
        f"您的房源訂單 #{order_id} 退房時間為 {checkout_time}"
    )
