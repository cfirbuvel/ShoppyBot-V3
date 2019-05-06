import gettext
from functools import wraps

from telegram.ext import ConversationHandler
# from .enums import BOT_INIT
from .helpers import get_user_id, get_locale, config, cat, get_username
from .models import User, UserPermission


def user_passes(func):

    @wraps(func)
    def wrapper(bot, update, user_data, *args, **kwargs):
        user_id = get_user_id(update)
        passes_test = True
        username = get_username(update)
        locale = get_locale(update)
        chat_id = update.effective_chat.id
        try:
            user = User.get(telegram_id=user_id)
        except User.DoesNotExist:
            locale = get_locale(update)
            default_permission = UserPermission.get(permission=UserPermission.NOT_REGISTERED)
            user = User(telegram_id=user_id, username=username, locale=locale, permission=default_permission)
            user.save()
        else:
            if username != user.username:
                user.username = username
                user.save()
        _ = gettext.gettext if locale == 'en' else cat.gettext
        if not username:
            caption = _('Please create username to continue using bot')
            with open(config.username_gif, 'rb') as animation:
                bot.send_animation(chat_id, animation, caption=caption)
            return ConversationHandler.END
        if user.banned:
            passes_test = False
            msg = _('You have been banned.')
        if passes_test:
            if not config.bot_on_off:
                if not user.is_admin:
                    passes_test = False
                    first_name = update.effective_user.first_name
                    msg = _('Sorry {}, the bot is currently switched off.').format(first_name)
        if passes_test:
            return func(bot, update, user_data)
        chat_id = update.effective_chat.id
        query = update.callback_query
        if query:
            bot.edit_message_text(msg, chat_id, query.message.message_id)
        else:
            bot.send_message(chat_id, msg)
        return ConversationHandler.END
    return wrapper