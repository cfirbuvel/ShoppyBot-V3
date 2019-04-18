import gettext
from functools import wraps

from telegram.ext import ConversationHandler
# from .enums import BOT_INIT
from .helpers import get_user_id, get_locale, config, cat
from .models import User, UserPermission


def user_passes(func):

    @wraps(func)
    def wrapper(bot, update, user_data, *args, **kwargs):
        user_id = get_user_id(update)
        try:
            user = User.get(telegram_id=user_id)
        except User.DoesNotExist:
             user = None
        passes_test = True
        locale = get_locale(update)
        _ = gettext.gettext if locale == 'en' else cat.gettext
        if user and user.banned:
            passes_test = False
            msg = _('You have been banned.')
        if passes_test:
            if not config.bot_on_off:
                if not user or not user.is_admin:
                    passes_test = False
                    first_name = update.effective_user.first_name
                    msg = _('Sorry {}, the bot is currently switched off.').format(first_name)
        if passes_test:
            return func(bot, update, user_data)
        else:
            chat_id = update.effective_chat.id
        query = update.callback_query
        if query:
            bot.edit_message_text(msg, chat_id, query.message.message_id)
        else:
            bot.send_message(chat_id, msg)
        return ConversationHandler.END
    return wrapper