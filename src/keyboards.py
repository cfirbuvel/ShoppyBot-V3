import calendar
import datetime
import math
import random

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from .cart_helper import Cart
from .helpers import config
from .models import Currencies, Channel, Location, Order, CourierLocation


def confirmation_keyboard(_):
    buttons = [
        [InlineKeyboardButton(_('✅ Confirm'), callback_data='confirm')],
        [
            InlineKeyboardButton(_('↩ Back'), callback_data='back'),
            InlineKeyboardButton(_('❌ Cancel'), callback_data='cancel')
        ]
    ]
    return InlineKeyboardMarkup(buttons)


def phone_number_request_keyboard(_):
    buttons = [
        [KeyboardButton(text=_('📞 Allow to send my phone number'), request_contact=True)],
        [KeyboardButton(_('↩ Back'))],
        [KeyboardButton(_('❌ Cancel'))],
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)


def location_request_keyboard(_):
    buttons = [
        [KeyboardButton(_('📍 Allow to send my location'), request_location=True)],
        [KeyboardButton(_('↩ Back'))],
        [KeyboardButton(_('❌ Cancel'))],
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)


def create_cancel_keyboard(trans):
    _ = trans
    button_row = [
        [
            KeyboardButton(_('↩ Back')),
            KeyboardButton(_('❌ Cancel'))
        ],
    ]
    return ReplyKeyboardMarkup(button_row, resize_keyboard=True)


def create_pickup_location_keyboard(trans, location_names):
    _ = trans
    button_column = []
    for location_name in location_names:
        button_column.append([KeyboardButton(location_name)])

    button_column.append(
        [
            KeyboardButton(_('↩ Back')),
            KeyboardButton(_('❌ Cancel'))
        ])
    return ReplyKeyboardMarkup(button_column, resize_keyboard=True)


def create_delivery_keyboard(_):
    buttons = [
        [InlineKeyboardButton(_('🏪 Pickup'), callback_data='pickup')],
        [InlineKeyboardButton(_('🚚 Delivery'), callback_data='delivery')],
        [InlineKeyboardButton(_('↩ Back'), callback_data='back')],
    ]
    return InlineKeyboardMarkup(buttons)


def edit_back_keyboard(_):
    buttons = [
        [InlineKeyboardButton(_('✏️ Edit'), callback_data='edit')],
        [InlineKeyboardButton(_('↩ Back'), callback_data='back')]
    ]
    return InlineKeyboardMarkup(buttons)


def warehouse_keyboard(_, active):
    wh_active = _('✅ Yes') if active else _('⛔️ No')
    buttons = [
        [InlineKeyboardButton(_('🏗 Warehouse active: {}').format(wh_active), callback_data='warehouse_status')],
        [InlineKeyboardButton(_('📊 Change product\'s credits'), callback_data='warehouse_credits')],
        [InlineKeyboardButton(_('🚴‍♀️ Add credits to courier'), callback_data='warehouse_courier')],
        [InlineKeyboardButton(_('↩ Back'), callback_data='warehouse_back')]
    ]
    return InlineKeyboardMarkup(buttons)


def locations_with_all_btn_keyboard(locations, trans):
    _ = trans
    button_row = []
    for loc in locations:
        button_row.append([InlineKeyboardButton(_(loc.title), callback_data=str(loc.id))])
    button_row.append([InlineKeyboardButton(_('All locations'), callback_data='all_locs')])
    button_row.append([InlineKeyboardButton(_('↩ Back'), callback_data='back')])
    return InlineKeyboardMarkup(button_row)


def service_notice_keyboard(order_id, trans, answers_ids, order_location, delivery_method=Order.DELIVERY):
    _ = trans
    if delivery_method == Order.DELIVERY:
        if order_location:
            button_msg = _('Take delivery from {}').format(order_location)
        else:
            button_msg = _('Take delivery')
        buttons = [
            [InlineKeyboardButton(button_msg, callback_data='take_order|{}|{}'.format(order_id, answers_ids))]
        ]
    else:
        if order_location:
            button_msg = _('🏪 Take pickup from {}').format(order_location)
        else:
            button_msg = _('🏪 Take pickup')
        buttons = [
            [InlineKeyboardButton(button_msg, callback_data='take_order|{}|{}'.format(order_id, answers_ids))]
        ]
    return InlineKeyboardMarkup(buttons)


def courier_confirmation_keyboard(order_id, trans, answers_id, assigned_msg_id):
    _ = trans
    buttons = [
        InlineKeyboardButton(_('Yes'),
                             callback_data='confirmed_courier|{}'.format(
                                 order_id)),
        InlineKeyboardButton(_('No'),
                             callback_data='notconfirmed_courier|{}|{}|{}'.format(
                                 order_id, answers_id, assigned_msg_id)),
    ]
    return InlineKeyboardMarkup([buttons])


def courier_assigned_keyboard(courier_nickname, trans):
    _ = trans
    buttons = [
        [InlineKeyboardButton(_('Assigned to @{}').format(courier_nickname),
                              url='https://t.me/{}'.format(courier_nickname))],
    ]
    return InlineKeyboardMarkup(buttons)


def registration_keyboard(_):
    buttons = [
        [InlineKeyboardButton(_( '➡️ Registration'), callback_data='register')],
        [InlineKeyboardButton(_('❌ Cancel'), callback_data='cancel')]
    ]
    return InlineKeyboardMarkup(buttons)


def main_keyboard(_, user):
    lang_map = {'iw': _('עברית 🇮🇱'), 'en': _('🇺🇸 English')}
    language_str = lang_map[user.locale]
    buttons = [
        [InlineKeyboardButton(_('⭐ Channels'), callback_data='menu_channels')],
        [InlineKeyboardButton(_('⏰ Working hours'), callback_data='menu_hours'),
         InlineKeyboardButton(_('☎ Contact info'), callback_data='menu_contact')],
        [InlineKeyboardButton(language_str, callback_data='menu_language'),
         InlineKeyboardButton(_('💲 Bot Currency'), callback_data='menu_currency')]
    ]
    first_btns = [InlineKeyboardButton(_('🛍 Checkout'), callback_data='menu_order'),
                  InlineKeyboardButton(_('🏪 Our products'), callback_data='menu_products')]
    if not user.is_registered:
        if not config.order_non_registered:
            first_btns.pop(0)
        buttons.append([InlineKeyboardButton(_('➡️ Registration'), callback_data='menu_register')])
    if user.user_orders:
        buttons.append([InlineKeyboardButton(_('📖 My Orders'), callback_data='menu_my_orders')])
        buttons.append([InlineKeyboardButton(_('⌨️ Chat with courier'), callback_data='menu_chat')])
    if user.is_admin or user.is_logistic_manager:
        buttons.append([InlineKeyboardButton(_('⚙️ Settings'), callback_data='menu_settings')])
    buttons.insert(0, first_btns)
    return InlineKeyboardMarkup(buttons)


def channels_keyboard(_, objects):
    buttons = []
    for name, link in objects:
        buttons.append([InlineKeyboardButton(name, url=link)])
    buttons.append([InlineKeyboardButton(_('↩ Back'), callback_data='back')])
    return InlineKeyboardMarkup(buttons)


def create_my_orders_keyboard(_):
    buttons = [
        [InlineKeyboardButton(_('📦 My last order'), callback_data='last_order')],
        [InlineKeyboardButton(_('📆 Order by date'), callback_data='by_date')],
        [InlineKeyboardButton(_('↩ Back'), callback_data='back')],
    ]
    return InlineKeyboardMarkup(buttons)


def create_my_order_keyboard(_, order_id, cancel):
    buttons = [
        [InlineKeyboardButton(_('💳 Show Order'), callback_data='show|{}'.format(order_id))]
    ]
    if cancel:
        buttons.append([InlineKeyboardButton(_('❌ Cancel order'), callback_data='cancel|{}'.format(order_id))])
    buttons.append([InlineKeyboardButton(_('↩ Back'), callback_data='back|')])
    return InlineKeyboardMarkup(buttons)


def bot_language_keyboard(_, selected_language):
    msg_map = (
        ('iw', _('עברית 🇮🇱{}')), ('en', _('🇺🇸 English{}'))
    )
    buttons = []
    for code, name in msg_map:
        if code == selected_language:
            selected_str = _(': ✅ Yes')
        else:
            selected_str = ''
        name = name.format(selected_str)
        button = [InlineKeyboardButton(_(name), callback_data=code)]
        buttons.append(button)
    buttons.append([InlineKeyboardButton(_('↩ Back'), callback_data='back')])
    return InlineKeyboardMarkup(buttons)


def create_product_keyboard(_, product_id, user_data):
    button_row = []
    if Cart.get_product_count(user_data, product_id) > 0:
        button = InlineKeyboardButton(
            _('➕ Add more'), callback_data='product_add|{}'.format(product_id))
        button_row.append(button)
        button = InlineKeyboardButton(
            _('➖ Remove'), callback_data='product_remove|{}'.format(product_id))
        button_row.append(button)
    else:
        button = InlineKeyboardButton(
            _('🛍 Add to cart'),
            callback_data='product_add|{}'.format(product_id))
        button_row.append(button)

    return InlineKeyboardMarkup([button_row])


def create_bot_config_keyboard(trans):
    _ = trans
    button_row = [
        [InlineKeyboardButton(
            _('Set welcome message'),
            callback_data='setwelcomemessage'
        )],
    ]

    return InlineKeyboardMarkup(button_row, resize_keyboard=True)


def admin_keyboard(_):
    buttons = [
        [InlineKeyboardButton(_('📈 Statistics'),
                              callback_data='settings_statistics')],
        [InlineKeyboardButton(_('⚙ Bot settings'),
                              callback_data='settings_bot')],
        [InlineKeyboardButton(_('👨 Users'), callback_data='settings_users')],
        [InlineKeyboardButton(_('↩ Back'),
                              callback_data='settings_back')],
    ]
    return InlineKeyboardMarkup(buttons)


def statistics_keyboard(_):
    main_button_list = [
        [InlineKeyboardButton(_('💵 General statistics'), callback_data='stats_general')],
        [InlineKeyboardButton(_('🚕 Statistics by courier'), callback_data='stats_courier')],
        [InlineKeyboardButton(_('🏠 Statistics by location'), callback_data='stats_locations')],
        [InlineKeyboardButton(_('🌝 Statistics by users'), callback_data='stats_users')],
        [InlineKeyboardButton(_('↩ Back'), callback_data='back')]
    ]
    return InlineKeyboardMarkup(main_button_list)


def statistics_users(_):
    buttons = [
        [InlineKeyboardButton(_('🥇 Top clients'), callback_data='clients_top')],
        [InlineKeyboardButton(_('👫 All clients'), callback_data='clients_all')],
        [InlineKeyboardButton(_('↩ Back'), callback_data='back')]
    ]
    return InlineKeyboardMarkup(buttons)


def top_clients_order_keyboard(_):
    buttons = [
        [InlineKeyboardButton(_('By price'), callback_data='price')],
        [InlineKeyboardButton(_('By orders'), callback_data='orders')],
        [InlineKeyboardButton(_('↩ Back'), callback_data='back')]
    ]
    return InlineKeyboardMarkup(buttons)


def top_clients_stats_keyboard(_):
    buttons = [
        [InlineKeyboardButton(_('🛍 By product'), callback_data='top_by_product')],
        [InlineKeyboardButton(_('📆 By date'), callback_data='top_by_date')],
        [InlineKeyboardButton(_('🎯 By location'), callback_data='top_by_location')],
        [InlineKeyboardButton(_('🛒 Total orders'), callback_data='top_total_orders')],
        [InlineKeyboardButton(_('↩ Back'), callback_data='back')]
    ]
    return InlineKeyboardMarkup(buttons)


def order_select_time_keyboard(_):
    buttons = [
        [InlineKeyboardButton(_('⏰ Now'), callback_data='now')],
        [InlineKeyboardButton(_('📆 Select day and time'), callback_data='datetime')],
        [InlineKeyboardButton(_('↩ Back'), callback_data='back')],
        [InlineKeyboardButton(_('❌ Cancel'), callback_data='cancel')]
    ]
    return InlineKeyboardMarkup(buttons)


def time_picker_keyboard(_, hour=0, minute=0, cancel=False):
    hour, minute = ['{0:02d}'.format(val) for val in (hour, minute)]
    buttons = [
        [
            InlineKeyboardButton('<', callback_data='time_picker_hour_prev'),
            InlineKeyboardButton(hour, callback_data='time_picker_ignore'),
            InlineKeyboardButton('>', callback_data='time_picker_hour_next'),
            InlineKeyboardButton('<', callback_data='time_picker_minute_prev'),
            InlineKeyboardButton(minute, callback_data='time_picker_ignore'),
            InlineKeyboardButton('>', callback_data='time_picker_minute_next')
        ]
    ]
    nav_buttons = [
        InlineKeyboardButton(_('↩ Back'), callback_data='back'),
        InlineKeyboardButton(_('✅ Done'), callback_data='done'),
    ]
    buttons.append(nav_buttons)
    if cancel:
        buttons.append([InlineKeyboardButton(_('❌ Cancel'), callback_data='cancel')])

    return InlineKeyboardMarkup(buttons)


def calendar_keyboard(year, month, _, cancel=False, first_date=None):
    markup = []
    row = []
    current_date = datetime.date.today()
    if year > 1:
        row.append(InlineKeyboardButton('<', callback_data='calendar_previous_year'))
    row.append(InlineKeyboardButton(year, callback_data='year|{}'.format(year)))
    if not year >= current_date.year:
        row.append(InlineKeyboardButton('>', callback_data='calendar_next_year'))
    markup.append(row)
    month_name = calendar.month_name[month]
    month_name = _(month_name)
    row = [
        InlineKeyboardButton('<', callback_data='calendar_previous_month'),
        InlineKeyboardButton(month_name, callback_data='month|{}'.format(month)),
        InlineKeyboardButton('>', callback_data='calendar_next_month')
    ]
    markup.append(row)
    row = []
    for day in ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]:
        row.append(InlineKeyboardButton(day, callback_data='calendar_ignore'))
    markup.append(row)
    my_calendar = calendar.monthcalendar(year, month)
    year_month_bool = first_date and first_date.year == year and first_date.month == month
    for week in my_calendar:
        row = []
        for day in week:
            if (day == 0):
                row.append(InlineKeyboardButton(" ", callback_data='calendar_ignore|'))
            else:
                day_str = str(day)
                if year_month_bool:
                    if first_date.day == day:
                        day_str = '✅ {}'.format(day_str)
                row.append(InlineKeyboardButton(day_str, callback_data='day|{}'.format(day)))
        markup.append(row)
    markup.append([InlineKeyboardButton(_('↩ Back'), callback_data='back|')])
    if cancel:
        markup.append([InlineKeyboardButton(_('❌ Cancel'), callback_data='cancel|')])
    return InlineKeyboardMarkup(markup)


def bot_settings_keyboard(_, user):
    buttons = [
        [InlineKeyboardButton(_('💳 Order options'),
                              callback_data='bot_settings_order_options')],
        [InlineKeyboardButton(_('🛵 Couriers'),
                              callback_data='bot_settings_couriers')],
        [InlineKeyboardButton(_('⏰ Edit working hours'), callback_data='bot_settings_edit_working_hours')],
        [InlineKeyboardButton(_('⌨️ Edit bot messages'), callback_data='bot_settings_edit_messages')],
    ]
    if user.is_admin:
        admin_buttons = [
            [InlineKeyboardButton(_('🎰 Lottery'),
                                  callback_data='bot_settings_lottery')],
            [InlineKeyboardButton(_('⭐ Channels'),
                                  callback_data='bot_settings_channels')],
            [InlineKeyboardButton(_('🈚️ Default language'),
                                  callback_data='bot_settings_language')],
            [InlineKeyboardButton(_('⚡️ Bot Status'),
                                  callback_data='bot_settings_bot_status')],
            [InlineKeyboardButton(_('💫 Reset all data'),
                                  callback_data='bot_settings_reset_all_data')],
            [InlineKeyboardButton(_('↩ Back'),
                                  callback_data='bot_settings_back')],
        ]
        buttons += admin_buttons

    return InlineKeyboardMarkup(buttons)


def lottery_settings_keyboard(_):
    buttons = [
        [InlineKeyboardButton(_('Lottery settings'), callback_data='lottery_settings')],
        [InlineKeyboardButton(_('Create lottery'), callback_data='lottery_create')],
        [InlineKeyboardButton(_('Show winners'), callback_data='lottery_winners')],
        [InlineKeyboardButton(_('↩ Back'), callback_data='lottery_back')]
    ]
    return InlineKeyboardMarkup(buttons)



def edit_messages_keyboard(_):
    buttons = [
        # [InlineKeyboardButton(_('⏰ Edit working hours'), callback_data='working_hours')],
        [InlineKeyboardButton(_('☎️ Edit contact info'), callback_data='edit_msg_contact_info')],
        [InlineKeyboardButton(_('👋 Edit Welcome message'), callback_data='edit_msg_welcome')],
        [InlineKeyboardButton(_('🧾 Edit Order details message'), callback_data='edit_msg_order_details')],
        [InlineKeyboardButton(_('🌒 Edit Final message'), callback_data='edit_msg_order_final')],
        [InlineKeyboardButton(_('↩ Back'), callback_data='edit_msg_back')],
    ]
    return InlineKeyboardMarkup(buttons)


def clients_keyboard(_):
    buttons = [
        [InlineKeyboardButton(_('👩 Registered users'), callback_data='users_registered')],
        [InlineKeyboardButton(_('🙋‍ Pending registrations'), callback_data='users_pending')],
        [InlineKeyboardButton(_('🔒 Black-list'), callback_data='users_black_list')],
        [InlineKeyboardButton(_('↩ Back'), callback_data='users_back')]
    ]
    return InlineKeyboardMarkup(buttons)


def registered_user_keyboard(_):
    buttons = [
        [InlineKeyboardButton(_('🎫 Show registration'), callback_data='registration_show')],
        [InlineKeyboardButton(_('🚪 Remove registration'), callback_data='registration_remove')],
        [InlineKeyboardButton(_('⭐️ Change user status'), callback_data='registration_status')],
        [InlineKeyboardButton(_('🔒  Black-list user'), callback_data='registration_black_list')],
        [InlineKeyboardButton(_('↩ Back'), callback_data='registration_back')]
    ]
    return InlineKeyboardMarkup(buttons)


def pending_user_keyboard(_):
    buttons = [
        [InlineKeyboardButton(_('✅ Approve user'), callback_data='approve_user')],
        [InlineKeyboardButton(_('🔒 Black-list user'), callback_data='black_list')],
        [InlineKeyboardButton(_('↩ Back'), callback_data='back')]
    ]
    return InlineKeyboardMarkup(buttons)


def banned_user_keyboard(_):
    buttons = [
        [InlineKeyboardButton(_('🎫 Show registration'), callback_data='black_list_show')],
        [InlineKeyboardButton(_('🔓 Remove from black-list'), callback_data='black_list_remove')],
        [InlineKeyboardButton(_('↩ Back'), callback_data='black_list_back')]
    ]
    return InlineKeyboardMarkup(buttons)


def courier_details_keyboard(_):
    buttons = [
        [InlineKeyboardButton(_('🎯 Change locations'), callback_data='courier_details_locations')],
        [InlineKeyboardButton(_('🏗 Edit warehouse'), callback_data='courier_details_warehouse')],
        [InlineKeyboardButton(_('↩ Back'), callback_data='courier_details_back')]
    ]
    return InlineKeyboardMarkup(buttons)


def channels_settings_keyboard(_):
    main_button_list = [
        [InlineKeyboardButton(_('🔭️ View channels'), callback_data='bot_channels_view')],
        [InlineKeyboardButton(_('➕ Add channel'), callback_data='bot_channels_add')],
        [InlineKeyboardButton(_('🈚︎ Change channels language'), callback_data='bot_channels_language')],
        [InlineKeyboardButton(_('↩ Back'), callback_data='bot_channels_back')],
    ]

    return InlineKeyboardMarkup(main_button_list)


def channel_details_keyboard(_, remove=True):
    buttons = [
        [InlineKeyboardButton(_('✏️ Edit channel'), callback_data='edit')],
        [InlineKeyboardButton(_('↩ Back'), callback_data='back')]
    ]
    if remove:
        buttons.insert(1, [InlineKeyboardButton(_('➖ Remove channel'), callback_data='remove')],)
    return InlineKeyboardMarkup(buttons)


def channel_select_type_keyboard(_):
    buttons = [
        [InlineKeyboardButton(_('Channel'), callback_data='channel')],
        [InlineKeyboardButton(_('Group'), callback_data='group')],
        [InlineKeyboardButton(_('↩ Back'), callback_data='back')]
    ]
    return InlineKeyboardMarkup(buttons)


def create_bot_products_keyboard(trans):
    _ = trans
    buttons = [
        [InlineKeyboardButton(_('🏪 View Products'), callback_data='bot_products_view')],
        [InlineKeyboardButton(_('➕ Add product'), callback_data='bot_products_add')],
        [InlineKeyboardButton(_('✏️ Edit product'), callback_data='bot_products_edit')],
        [InlineKeyboardButton(_('➖ Remove product'), callback_data='bot_products_remove')],
        [InlineKeyboardButton(_('↩ Back'), callback_data='bot_products_back')]
    ]
    return InlineKeyboardMarkup(buttons)


def create_bot_product_edit_keyboard(trans):
    _ = trans
    buttons = [
        [InlineKeyboardButton(_('📝 Edit title'), callback_data='title')],
        [InlineKeyboardButton(_('💰 Edit price'), callback_data='price')],
        [InlineKeyboardButton(_('🖼 Edit media'), callback_data='media')],
        [InlineKeyboardButton(_('↩ Back'), callback_data='back')]
    ]
    return InlineKeyboardMarkup(buttons)


def create_bot_product_add_keyboard(trans):
    _ = trans
    buttons = [
        [InlineKeyboardButton(_('New Product'), callback_data='bot_product_new')],
        [InlineKeyboardButton(_('Last Products'), callback_data='bot_product_last')],
        [InlineKeyboardButton(_('↩ Back'), callback_data='bot_product_back')]
    ]
    return InlineKeyboardMarkup(buttons)


def create_select_products_chunk_keyboard(trans, chunk, selected_command, back_command=None):
    _ = trans
    buttons = []
    for name, id in chunk:
        callback_command = '{}|{}'.format(selected_command, id)
        btn = [InlineKeyboardButton(name, callback_data=callback_command)]
        buttons.append(btn)
    if back_command:
        back_command = '{}|'.format(back_command)
        buttons.append([InlineKeyboardButton(_('↩ Back'), callback_data=back_command)])
    return InlineKeyboardMarkup(buttons)


def locations_keyboard(_):
    buttons = [
        [InlineKeyboardButton(_('🎯️ View locations'),
                              callback_data='bot_locations_view')],
        [InlineKeyboardButton(_('➕ Add location'),
                              callback_data='bot_locations_add')],
        [InlineKeyboardButton(_('↩ Back'),
                              callback_data='bot_locations_back')],
    ]
    return InlineKeyboardMarkup(buttons)


def location_detail_keyboard(_):
    buttons = [
        [InlineKeyboardButton(_('Remove location'), callback_data='remove')],
        [InlineKeyboardButton(_('↩ Back'), callback_data='back')]
    ]
    return InlineKeyboardMarkup(buttons)


def order_options_keyboard(_):
    main_button_list = [[
         InlineKeyboardButton(_('📖 Orders'),
                              callback_data='bot_order_options_orders'),
         InlineKeyboardButton(_('🏪 My Products'),
                              callback_data='bot_order_options_product')],
        [InlineKeyboardButton(_('🛍 Categories'),
                              callback_data='bot_order_options_categories'),
         InlineKeyboardButton(_('🏗 Warehouse'),
                              callback_data='bot_order_options_warehouse')],
        [InlineKeyboardButton(_('💲 Add discount'),
                              callback_data='bot_order_options_discount'),
         InlineKeyboardButton(_('🚕 Delivery'),
                              callback_data='bot_order_options_delivery')],
        [InlineKeyboardButton(_('💸 Product price groups'),
                              callback_data='bot_order_options_price_groups'),
         InlineKeyboardButton(_('🎯 Locations'),
                              callback_data='bot_order_options_add_locations')],
        [InlineKeyboardButton(_('💲 Change currency'),
                              callback_data='bot_order_options_currency'),
         InlineKeyboardButton(_('💰 Bitcoin Payments'),
                              callback_data='bot_order_options_bitcoin_payments')],
        [InlineKeyboardButton(_('👨 Edit identification process'),
                              callback_data='bot_order_options_identify')],
        [InlineKeyboardButton(_('↩ Back'),
                              callback_data='bot_order_options_back')], ]

    return InlineKeyboardMarkup(main_button_list)


def delivery_options_keyboard(_):
    buttons = [
        [InlineKeyboardButton(_('🏃‍♂️ Edit delivery methods'), callback_data='edit_methods')],
        [InlineKeyboardButton(_('💵 Delivery fee'), callback_data='edit_fee')],
        [InlineKeyboardButton(_('↩ Back'), callback_data='back')]
    ]
    return InlineKeyboardMarkup(buttons)


def delivery_methods_keyboard(_):
    delivery_method = config.delivery_method
    pickup_str = _('✅ Active') if delivery_method == 'pickup' else _('⛔️ Disabled')
    pickup_str = _('Pickup: {}').format(pickup_str)
    delivery_str = _('✅ Active') if delivery_method == 'delivery' else _('⛔️ Disabled')
    delivery_str = _('Delivery: {}').format(delivery_str)
    both_str = _('✅ Active') if delivery_method == 'both' else _('⛔️ Disabled')
    both_str = _('Both: {}').format(both_str)
    buttons = [
        [InlineKeyboardButton(pickup_str, callback_data='pickup')],
        [InlineKeyboardButton(delivery_str, callback_data='delivery')],
        [InlineKeyboardButton(both_str, callback_data='both')],
        [InlineKeyboardButton(_('↩ Back'), callback_data='back')]
    ]
    return InlineKeyboardMarkup(buttons)


def bot_orders_keyboard(trans):
    _ = trans
    main_button_list = [
        [InlineKeyboardButton(_('📦 Finished orders'), callback_data='finished')],
        [InlineKeyboardButton(_('🚚 Pending orders'), callback_data='pending')],
        [InlineKeyboardButton(_('↩ Back'), callback_data='back')]
    ]
    return InlineKeyboardMarkup(main_button_list)


def delivery_fee_keyboard(_):
    vip_delivery = config.delivery_fee_for_vip
    vip_str = _('✅ Yes') if vip_delivery else _('⛔️ No')
    buttons = [
        [InlineKeyboardButton(_('➕ Add delivery fee'), callback_data='add')],
        [InlineKeyboardButton(_('🎖 Vip customers delivery fee: {}').format(vip_str), callback_data='vip')],
        [InlineKeyboardButton(_('↩ Back'), callback_data='back')]
    ]
    return InlineKeyboardMarkup(buttons)


def delivery_fee_add_keyboard(_):
    buttons = [
        [InlineKeyboardButton(_('All locations'), callback_data='all')],
        [InlineKeyboardButton(_('↩ Back'), callback_data='back')]
    ]
    locations = Location.select().exists()
    if locations:
        buttons.insert(0, [InlineKeyboardButton(_('Select location'), callback_data='select')])
    return InlineKeyboardMarkup(buttons)


def create_general_on_off_keyboard(trans):
    _ = trans
    buttons = [
        [InlineKeyboardButton(_('ON'), callback_data='on')],
        [InlineKeyboardButton(_('OFF'), callback_data='off')],
        [InlineKeyboardButton(_('↩ Back'), callback_data='back')]
    ]
    return InlineKeyboardMarkup(buttons)


def cancel_button(_):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(_('❌ Cancel'), callback_data='back')]
    ])


def back_cancel_keyboard(_):
    buttons = [
        [InlineKeyboardButton(_('↩ Back'), callback_data='back')],
        [InlineKeyboardButton(_('❌ Cancel'), callback_data='cancel')]
    ]
    return InlineKeyboardMarkup(buttons)


def create_skip_cancel_keyboard(_):
    buttons = [
        [InlineKeyboardButton(_('⏭ Skip'), callback_data='skip')],
        [InlineKeyboardButton(_('❌ Cancel'), callback_data='cancel')]
    ]
    return InlineKeyboardMarkup(buttons)


def create_bot_status_keyboard(_):
    bot_active = _('✅ Yes') if config.bot_on_off else _('❌ No')
    only_for_registered = _('✅ Yes') if config.only_for_registered else _('❌ No')
    watch_non_registered = _('✅ Yes') if config.watch_non_registered else _('❌ No')
    order_non_registered = _('✅ Yes') if config.order_non_registered else _('❌ No')
    buttons = [
        [InlineKeyboardButton(_('Bot active: {}').format(bot_active), callback_data='bot_status_on_off')],
        [InlineKeyboardButton(_('Only for registered users: {}').format(only_for_registered), callback_data='bot_status_only_reg')],
        [InlineKeyboardButton(_('Watch bot for non registered users: {}').format(watch_non_registered), callback_data='bot_status_watch')],
        [InlineKeyboardButton(_('Order for non registered users: {}').format(order_non_registered), callback_data='bot_status_order')],
        [InlineKeyboardButton(_('↩ Back'), callback_data='bot_status_back')]
    ]
    return InlineKeyboardMarkup(buttons)


def create_ban_list_keyboard(trans):
    _ = trans
    main_button_list = [
        [InlineKeyboardButton(_('🔥 View ban list'),
                              callback_data='bot_ban_list_view')],
        [InlineKeyboardButton(_('➖ Remove from ban list'),
                              callback_data='bot_ban_list_remove')],
        [InlineKeyboardButton(_('➕ Add to ban list'),
                              callback_data='bot_ban_list_add')],
        [InlineKeyboardButton(_('↩ Back'),
                              callback_data='bot_ban_list_back')],
    ]

    return InlineKeyboardMarkup(main_button_list)


def general_select_keyboard(_, objects, page_num=1, page_len=15):
    buttons = []
    prev_page = None
    next_page = None
    if len(objects) > page_len:
        max_pages = math.ceil(len(objects) / float(page_len))
        objects = objects[(page_num - 1) * page_len: page_num * page_len]
        prev_page = page_num - 1 if page_num > 1 else None
        next_page = page_num + 1 if page_num < max_pages else None
    for name, id, is_picked in objects:
        if is_picked:
            is_picked = '➖'
        else:
            is_picked = '➕'
        callback_data = 'select|{}'.format(id)
        name = '{} {}'.format(is_picked, name)
        button = [InlineKeyboardButton(name, callback_data=callback_data)]
        buttons.append(button)
    if prev_page:
        callback_data = 'page|{}'.format(prev_page)
        button = [InlineKeyboardButton(_('◀️ Previous'), callback_data=callback_data)]
        buttons.append(button)
    if next_page:
        callback_data = 'page|{}'.format(next_page)
        button = [InlineKeyboardButton(_('▶️ Next'), callback_data=callback_data)]
        buttons.append(button)
    done_btn = [InlineKeyboardButton(_('✅ Done'), callback_data='done|')]
    buttons.append(done_btn)
    return InlineKeyboardMarkup(buttons)


def general_select_one_keyboard(_, objects, page_num=1, page_len=10, cancel=False):
    buttons = []
    prev_page = None
    next_page = None
    if len(objects) > 10:
        max_pages = math.ceil(len(objects) / float(page_len))
        objects = objects[(page_num - 1) * page_len: page_num * page_len]
        prev_page = page_num - 1 if page_num > 1 else None
        next_page = page_num + 1 if page_num < max_pages else None
    for name, id in objects:
        callback_data = 'select|{}'.format(id)
        button = [InlineKeyboardButton(name, callback_data=callback_data)]
        buttons.append(button)
    if prev_page:
        callback_data = 'page|{}'.format(prev_page)
        button = [InlineKeyboardButton(_('◀️ Previous'), callback_data=callback_data)]
        buttons.append(button)
    if next_page:
        callback_data = 'page|{}'.format(next_page)
        button = [InlineKeyboardButton(_('▶️ Next'), callback_data=callback_data)]
        buttons.append(button)
    back_btn = [InlineKeyboardButton(_('↩ Back'), callback_data='back|')]
    buttons.append(back_btn)
    if cancel:
        buttons.append([InlineKeyboardButton(_('❌ Cancel'), callback_data='cancel|')])
    return InlineKeyboardMarkup(buttons)


def couriers_choose_keyboard(trans, couriers, order_id, message_id):
    _ = trans
    couriers_list = []
    for username, tg_id in couriers:
        courier_str = '@{}'.format(username)
        couriers_list.append([InlineKeyboardButton(courier_str, callback_data='sendto|{}|{}|{}'.format(tg_id,
                                                                                              order_id, message_id))])
    couriers_list.append(
        [InlineKeyboardButton(_('❌ Cancel'), callback_data='delete_msg')]
    )
    return InlineKeyboardMarkup(couriers_list)


def service_channel_keyboard(trans, order):
    _ = trans
    order_id = order.id
    main_button_list = [
        [InlineKeyboardButton(_('🛵 Send order to courier channel'),
                              callback_data='order_send_to_couriers|{}'.format(order_id))],
        [InlineKeyboardButton(_('🚀 Send order to specific courier'),
                              callback_data='order_send_to_specific_courier|{}'.format(order_id))],
        [InlineKeyboardButton(_('🚕 Send order yourself'),
                              callback_data='order_send_to_self|{}'.format(order_id))],
        # [InlineKeyboardButton(_('⭐ Add user to VIP'),
        #                       callback_data='order_add_to_vip|{}'.format(order_id))],
        [InlineKeyboardButton(_('🔥 Add client to ban-list'),
                              callback_data='order_ban_client|{}'.format(order_id))],
        # [InlineKeyboardButton(_('✅ Order Finished'),
        #                       callback_data='order_finished|{}'.format(order_id))],
        [InlineKeyboardButton(_('❌ Cancel order'), callback_data='order_cancel|{}'.format(order_id))],
        [InlineKeyboardButton(_('💳 Hide Order'),
                              callback_data='order_hide|{}'.format(order_id))],
    ]
    if order.btc_payment:
        main_button_list.insert(0, [InlineKeyboardButton(_('🔄 Refresh payment status'), callback_data='order_btc_refresh|{}'.format(order_id))])
        main_button_list.insert(0, [InlineKeyboardButton(_('✉️ Send payment notification to client'), callback_data='order_btc_notification|{}'.format(order_id))])
    return InlineKeyboardMarkup(main_button_list)


def cancel_order_confirm(trans, order_id):
    _ = trans
    main_button_list = [
        [
            InlineKeyboardButton(_('✅ Yes'), callback_data='cancel_order_yes|{}'.format(order_id)),
            InlineKeyboardButton(_('❌ No'), callback_data='cancel_order_no|{}'.format(order_id))
        ],
        [InlineKeyboardButton(_('Yes and delete'), callback_data='cancel_order_delete|{}'.format(order_id))]
    ]
    return InlineKeyboardMarkup(main_button_list)


def show_order_keyboard(_, order_id):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(_('💳 Show Order'),
                             callback_data='order_show|{}'.format(order_id))
    ]])


def send_to_service_keyboard(_):
    buttons = [
        [InlineKeyboardButton(_('📬 Send to service channel'), callback_data='send')],
        [InlineKeyboardButton(_('↩ Back'), callback_data='back')]
    ]
    return InlineKeyboardMarkup(buttons)


def order_finished_keyboard(_, order_id, show=True):
    buttons = [
        [InlineKeyboardButton(_('❌ Delete Order'), callback_data='finished_order_delete|{}'.format(order_id))],
        [InlineKeyboardButton(_('🎰 Add to lottery'), callback_data='finished_order_lottery|{}'.format(order_id))],
    ]
    if show:
        btn = [InlineKeyboardButton(_('💳 Show Order'), callback_data='finished_order_show|{}'.format(order_id))]
    else:
        btn = [InlineKeyboardButton(_('💳 Hide Order'), callback_data='finished_order_hide|{}'.format(order_id))]
    buttons.insert(0, btn)
    return InlineKeyboardMarkup(buttons)


def courier_order_status_keyboard(trans, order_id, user):
    _ = trans
    buttons = [
        [InlineKeyboardButton(_('✅ Order Done'), callback_data='courier_menu_delivered|{}'.format(order_id))],
        [InlineKeyboardButton(_('📞 Ping Client'), callback_data='courier_menu_ping|{}'.format(order_id))],
        [InlineKeyboardButton(_('❌ Drop responsibility'), callback_data='courier_menu_dropped|{}'.format(order_id))]
    ]
    if user.is_courier:
        buttons.insert(1, [InlineKeyboardButton(_('🔥 Report client to admin'), callback_data='courier_menu_report|{}'.format(order_id))])
        buttons.insert(2, [InlineKeyboardButton(_('⌨️ Chat with client'), callback_data='courier_menu_chat|{}'.format(order_id))])
    return InlineKeyboardMarkup(buttons)


def chat_order_selected(_):
    buttons = [
        [InlineKeyboardButton(_('Start chat'), callback_data='start')],
        [InlineKeyboardButton(_('↩ Back'), callback_data='back')]
    ]
    return InlineKeyboardMarkup(buttons)


def chat_with_client_keyboard(_, order_id):
    buttons = [
        [InlineKeyboardButton(_('📟 Send message'), callback_data='courier_chat_send|{}'.format(order_id))],
        [InlineKeyboardButton(_('🏁 Finish chat'), callback_data='courier_chat_finish|{}'.format(order_id))]
    ]
    return InlineKeyboardMarkup(buttons)


def chat_with_courier_keyboard(_, order_id, ping=False):
    buttons = [
        [InlineKeyboardButton(_('📟 Send message'), callback_data='client_chat_send|{}'.format(order_id))],
        [InlineKeyboardButton(_('🏁 Finish chat'), callback_data='client_chat_finish|{}'.format(order_id))]
    ]
    if ping:
        buttons.append([InlineKeyboardButton(_('🛎 Ping courier'), callback_data='client_chat_ping|{}'.format(order_id))])
    return InlineKeyboardMarkup(buttons)


def chat_client_msg_keyboard(_, msg_id):
    buttons = [
        [InlineKeyboardButton(_('Read message'), callback_data='client_read_msg|{}'.format(msg_id))]
    ]
    return InlineKeyboardMarkup(buttons)


def chat_courier_msg_keyboard(_, msg_id):
    buttons = [
        [InlineKeyboardButton(_('Read message'), callback_data='courier_read_msg|{}'.format(msg_id))]
    ]
    return InlineKeyboardMarkup(buttons)


def client_waiting_keyboard(_, chat_id):
    buttons = [
        [InlineKeyboardButton(_('Yes'), callback_data='courier_ping_yes|{}'.format(chat_id))],
        [InlineKeyboardButton(_('No'), callback_data='courier_ping_no|{}'.format(chat_id))]
    ]
    return InlineKeyboardMarkup(buttons)
# def admin_order_status_keyboard(trans, order_id):
#     _ = trans
#     buttons = [
#         [InlineKeyboardButton(_('✅ Order Done'), callback_data='courier_menu_delivered|{}'.format(order_id))],
#         [InlineKeyboardButton(_('📞 Ping Client'), callback_data='courier_menu_ping_admin|{}'.format(order_id))],
#         [InlineKeyboardButton(_('❌ Drop responsibility'), callback_data='courier_menu_dropped_admin|{}'.format(order_id))]
#     ]
#     return InlineKeyboardMarkup(buttons)


def create_ping_client_keyboard(trans):
    _ = trans
    buttons = [
        [InlineKeyboardButton(_('🔔 Now'), callback_data='now')],
        [InlineKeyboardButton(_('🕐 Soon'), callback_data='soon')],
        [InlineKeyboardButton(_('❌ Cancel'), callback_data='back')]
    ]
    return InlineKeyboardMarkup(buttons)


def create_add_courier_keyboard(trans):
    _ = trans
    buttons = [
        [InlineKeyboardButton(_('🆔 Add by user ID'), callback_data='by_id')],
        [InlineKeyboardButton(_('👆 Select courier'), callback_data='select')],
        [InlineKeyboardButton(_('↩ Back'), callback_data='back')]
    ]
    return InlineKeyboardMarkup([buttons])


def are_you_sure_keyboard(_):
    buttons = [
        InlineKeyboardButton(_('✅ Yes'), callback_data='yes'),
        InlineKeyboardButton(_('❌ No'), callback_data='no')
    ]
    return InlineKeyboardMarkup([buttons])


def edit_identification_keyboard(_, questions):
    buttons = []
    for count, q in enumerate(questions, 1):
        q_id, q_active, q_vip, q_order, q_content = q
        btn = [InlineKeyboardButton(_('Question №{}: {}').format(count, q_content), callback_data='id_edit|{}'.format(q_id))]
        buttons.append(btn)
        btn = [
            InlineKeyboardButton(_('Vip: Active ✅') if q_vip else _('Vip: Disabled ⛔️'),
                                 callback_data='id_vip_toggle|{}'.format(q_id)),
            InlineKeyboardButton(_('For order: Active ✅') if  q_order else _('For order: Disabled ⛔️'),
                                 callback_data='id_order_toggle|{}'.format(q_id)),
        ]
        buttons.append(btn)
        btn = [
            InlineKeyboardButton(_('Active ✅') if q_active else _('Disabled ⛔️'),
                                 callback_data='id_toggle|{}'.format(q_id)),
            InlineKeyboardButton(_('Delete'), callback_data='id_delete|{}'.format(q_id))
        ]
        buttons.append(btn)
    buttons.append([InlineKeyboardButton(_('Add new question'), callback_data='id_add|')])
    buttons.append([InlineKeyboardButton(_('↩ Back'), callback_data='id_back|')])
    return InlineKeyboardMarkup(buttons)


def create_edit_identification_type_keyboard(trans):
    _ = trans
    buttons = [
        [InlineKeyboardButton(_('📝 Text'), callback_data='text')],
        [InlineKeyboardButton(_('🖼 Photo'), callback_data='photo')],
        [InlineKeyboardButton(_('📹 Video'), callback_data='video')],
        [InlineKeyboardButton(_('↩ Back'), callback_data='back')]
    ]
    return InlineKeyboardMarkup(buttons)




def create_product_edit_media_keyboard(trans):
    _ = trans
    buttons = [
        [
            KeyboardButton(_('Save Changes')),
            KeyboardButton(_('❌ Cancel'))
        ]
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)


def create_product_media_keyboard(trans):
    _ = trans
    button_row = [
        [
            KeyboardButton(_('Create Product')),
            KeyboardButton(_('❌ Cancel'))
        ],
    ]
    return ReplyKeyboardMarkup(button_row, resize_keyboard=True)


def create_categories_keyboard(trans):
    _ = trans
    buttons = [
        [InlineKeyboardButton(_('🏪 Add products to category'), callback_data='products')],
        [InlineKeyboardButton(_('➕ Add Category'), callback_data='add')],
        [InlineKeyboardButton(_('❌ Remove Category'), callback_data='remove')],
        [InlineKeyboardButton(_('↩ Back'), callback_data='back')]
    ]
    return InlineKeyboardMarkup(buttons)


def create_reset_all_data_keyboard(trans):
    _ = trans
    names_callbacks = [(_('Yes, reset all data'), 'yes'), (_('Nope, nevermind'), 'no'), (_('No'), 'no')]
    random.shuffle(names_callbacks)
    buttons = [[InlineKeyboardButton(name, callback_data=callback)] for name, callback in names_callbacks]
    buttons.append([InlineKeyboardButton(_('↩ Back'), callback_data='back')])
    return InlineKeyboardMarkup(buttons)


def create_reset_confirm_keyboard(trans):
    _ = trans
    names_callbacks = [(_('Hell no!'), 'no'), (_('No!'), 'no'), (_('Yes, I\'m 100% sure!'), 'yes')]
    random.shuffle(names_callbacks)
    buttons = [[InlineKeyboardButton(name, callback_data=callback)] for name, callback in names_callbacks]
    buttons.append([InlineKeyboardButton(_('↩ Back'), callback_data='back')])
    return InlineKeyboardMarkup(buttons)


def create_product_price_groups_keyboard(trans):
    _ = trans
    buttons = [
        [InlineKeyboardButton(_('➕ Add price group'), callback_data='add')],
        [InlineKeyboardButton(_('🔗 List price groups'), callback_data='list')],
        [InlineKeyboardButton(_('↩ Back'), callback_data='back')]
    ]
    return InlineKeyboardMarkup(buttons)


# def add_product_price_group_keyboard(_):
#     buttons = [
#         [InlineKeyboardButton(_('Add for special clients'), callback_data='special_clients')],
#         [InlineKeyboardButton(_('Add for all clients'), callback_data='all_clients')]
#     ]


def create_product_price_group_selected_keyboard(trans, group_id):
    _ = trans
    buttons = [
        [InlineKeyboardButton(_('✏️ Edit price group'), callback_data='edit|{}'.format(group_id))],
        [InlineKeyboardButton(_('👫 Special clients'), callback_data='special_clients|{}'.format(group_id))],
        [InlineKeyboardButton(_('❌ Delete price group'), callback_data='delete|{}'.format(group_id))],
        [InlineKeyboardButton(_('↩ Back'), callback_data='back|{}'.format(group_id))]
    ]
    return InlineKeyboardMarkup(buttons)


def price_group_clients_keyboard(_):
    buttons = [
        [InlineKeyboardButton(_('🗝 Edit Permissions'), callback_data='perms')],
        [InlineKeyboardButton(_('👩 Edit Clients'), callback_data='clients')],
        [InlineKeyboardButton(_('↩ Back'), callback_data='back')]
    ]
    return InlineKeyboardMarkup(buttons)


def create_product_price_type_keyboard(trans):
    _ = trans
    buttons = [
        [InlineKeyboardButton(_('✏️ Enter prices'), callback_data='text')],
        [InlineKeyboardButton(_('💸 Select product price group'), callback_data='select')],
        [InlineKeyboardButton(_('↩ Back'), callback_data='back')]
    ]
    return InlineKeyboardMarkup(buttons)


def create_btc_settings_keyboard(trans, enabled):
    _ = trans
    buttons = [
        [InlineKeyboardButton(_('Change BTC wallet ID'), callback_data='btc_wallet_id')],
        [InlineKeyboardButton(_('Change BTC wallet password'), callback_data='btc_password')]
    ]
    if enabled:
        on_off_btn = [InlineKeyboardButton(_('Disable BTC payments'), callback_data='btc_disable')]
    else:
        on_off_btn = [InlineKeyboardButton(_('Enable BTC payments'), callback_data='btc_enable')]
    buttons.append(on_off_btn)
    buttons.append([InlineKeyboardButton(_('↩ Back'), callback_data='btc_back')])
    return InlineKeyboardMarkup(buttons)


def create_currencies_keyboard(trans):
    _ = trans
    buttons = []
    for abbr, data in Currencies.CURRENCIES.items():
        name, symbol = data
        btn = [InlineKeyboardButton('{} {}'.format(name, symbol), callback_data=abbr)]
        buttons.append(btn)
    buttons.append([InlineKeyboardButton(_('↩ Back'), callback_data='back')])
    return InlineKeyboardMarkup(buttons)


def select_order_payment_type(_):
    buttons = [
        [InlineKeyboardButton(_('💸 Pay with Bitcoin'), callback_data='btc'),
         InlineKeyboardButton(_('🚚 Pay on delivery'), callback_data='delivery')],
        [InlineKeyboardButton(_('↩ Back'), callback_data='back')],
        [InlineKeyboardButton(_('❌ Cancel'), callback_data='cancel')]
    ]
    return InlineKeyboardMarkup(buttons)


def btc_operation_failed_keyboard(_, retry=True):
    buttons = [
        [InlineKeyboardButton(_('↩ Back'), callback_data='back')],
        [InlineKeyboardButton(_('❌ Cancel'), callback_data='cancel')]
    ]
    if retry:
        buttons.insert(0, [InlineKeyboardButton(_('🔄 Try again'), callback_data='try_again')])
    return InlineKeyboardMarkup(buttons)


def create_bitcoin_retry_keyboard(trans, order_id):
    _ = trans
    buttons = [
        [InlineKeyboardButton(_('🔄 Try again'), callback_data='btc_processing_start|{}'.format(order_id))]
    ]
    return InlineKeyboardMarkup(buttons)


def start_btn(_):
    buttons = [InlineKeyboardButton(_('Start'), callback_data='start_bot')]
    return InlineKeyboardMarkup([buttons])