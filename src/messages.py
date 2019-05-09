from collections import defaultdict
from datetime import datetime

from telegram.utils.helpers import escape_markdown

from .cart_helper import Cart
from .helpers import get_trans, calculate_discount_total, config, quantize_btc, get_currency_symbol
from .models import Location, Currencies, BtcStatus, OrderBtcPayment, BtcStage, WorkingHours, User
from .btc_wrapper import CurrencyConverter


def create_cart_details_msg(user_id, products_info):
    _ = get_trans(user_id)
    # currency = get_currency_symbol()
    user = User.get(telegram_id=user_id)
    currency_sym = Currencies.CURRENCIES[user.currency][1]
    msg = '▫️◾️◽️◼️◻️⬛️◻️◼️◽️◾️▫️'
    msg += '\n'
    msg += _('Products in cart:')
    msg += '\n\n'
    total = 0
    for title, count, price in products_info:
        title = escape_markdown(title)
        msg += '{}:'.format(title)
        msg += '\n'
        msg += _('x {} = {}{}').format(count, price, currency_sym)
        msg += '\n\n'
        total += price
    msg += _('Total: {}{}').format(total, currency_sym)
    msg += '\n\n'
    msg += '▫️◾️◽️◼️◻️⬛️◻️◼️◽️◾️▫️'
    return msg


def create_product_description(_, currency, product_title, product_prices, product_count, subtotal):
    product_title = escape_markdown(product_title)
    text = _('Product:\n{}').format(product_title)
    text += '\n\n'
    text += '〰️'
    text += '\n'

    # currency = get_currency_symbol()
    currency_sym = Currencies.CURRENCIES[currency][1]
    CurrencyConverter.fetch_update_currencies()
    if Location.select().exists():
        locations_fees = defaultdict(list)
        for loc in Location.select():
            loc_name = escape_markdown(loc.title)
            delivery_fee = loc.delivery_fee
            delivery_min = loc.delivery_min
            if not delivery_fee:
                locations_fees[(0, 0)].append(loc_name)
                continue
            delivery_fee = CurrencyConverter.convert_currencies(delivery_fee, config.currency, currency)
            delivery_min = CurrencyConverter.convert_currencies(delivery_min, config.currency, currency)
            locations_fees[(delivery_fee, delivery_min)].append(loc_name)

        locations_fees = [(key, value) for key, value in locations_fees.items()]
        locations_fees = sorted(locations_fees, key=lambda x: (x[0][0], x[0][1]))

        for data, locs in locations_fees:
            delivery_fee, delivery_min = data
            if not delivery_fee and not delivery_min:
                text += _('Free delivery from:')
                text += '\n'
                text += '{}'.format(', '.join(locs))
                text += '\n\n'
            else:
                text += _('*{}*{} Delivery Fee from:').format(delivery_fee, currency_sym)
                text += '\n'
                text += '{}'.format(', '.join(locs))
                if delivery_min > 0:
                    text += '\n'
                    text += _('for orders below *{}*{}').format(delivery_min, currency_sym)
                text += '\n\n'
    else:
        conf_delivery_fee = config.delivery_fee
        conf_delivery_min = config.delivery_min
        if conf_delivery_fee > 0:
            conf_delivery_fee = CurrencyConverter.convert_currencies(conf_delivery_fee, config.currency, currency)
            if conf_delivery_fee > 0 and conf_delivery_min > 0:
                conf_delivery_min = CurrencyConverter.convert_currencies(conf_delivery_min, config.currency, currency)
                text += _('*{}*{} Delivery Fee').format(conf_delivery_fee, currency_sym)
                text += '\n'
                text += _('for orders below *{}*{}').format(conf_delivery_min, currency_sym)
                text += '\n'
                text += '〰️'
                text += '\n'
            elif conf_delivery_fee > 0:
                text += _('*{}*{} Delivery Fee').format(conf_delivery_fee, currency_sym)
                text += '\n'
        else:
            text += _('Free delivery')
    text += '\n\n'
    text += _('Price:')
    text += '\n'

    for q, price in product_prices:
        price = CurrencyConverter.convert_currencies(price, config.currency, currency)
        text += '\n'
        text += _('x {} = {}{}').format(q, price, currency_sym)

    q = product_count
    if q > 0:
        text += '\n\n〰️\n\n'
        text += _('Count: {}').format(q)
        text += '\n'
        subtotal = CurrencyConverter.convert_currencies(subtotal, config.currency, currency)
        text += _('Subtotal: {}{}').format(subtotal, currency_sym)
        text += '\n'

    datetime_format = '%H:%M %b %d'
    currencies_updated = config.currencies_last_updated.strftime(datetime_format)
    text += '\n'
    text += _('Currency rate was updated at: {}').format(currencies_updated)

    return text


def create_admin_product_description(trans, product_title, product_prices):
    _ = trans
    currency = get_currency_symbol()
    product_title = escape_markdown(product_title)
    text = _('Product:\n{}\n\n~~\nPrice:\n').format(product_title)
    for q, price in product_prices:
        text += '\n'
        text += _('x {} = {}{}').format(q, price, currency)
    text += '\n\n~~\n'
    return text


def create_confirmation_text(user_id, order_details, total, products_info):
    _ = get_trans(user_id)
    text = _('Please confirm your order:')
    text += '\n\n'
    text += '〰〰〰〰〰〰〰〰〰〰〰〰️'
    text += '\n'
    text += _('Items in cart:')
    text += '\n'

    # change currency
    # currency = config.currency
    user = User.get(telegram_id=user_id)
    currency = user.currency
    currency_symbol = Currencies.CURRENCIES[currency][1]

    for title, product_count, price in products_info:
        title = escape_markdown(title)
        text += '\n'
        text += _('Product:\n{}').format(title)
        text += '\n'
        text += _('x {} = {}{}').format(product_count, price, currency_symbol)
        text += '\n'
    text += '〰〰〰〰〰〰〰〰〰〰〰〰️'

    is_vip = user.is_vip_client
    delivery_method = order_details['delivery']
    btc_payment = order_details.get('btc_payment')
    if delivery_method == 'delivery':
        loc_id = order_details.get('location_id')
        if loc_id:
            location = Location.get(id=loc_id)
        else:
            location = None
        if location and location.delivery_fee is not None:
            delivery_fee, delivery_min = location.delivery_fee, location.delivery_min
        else:
            delivery_fee, delivery_min = config.delivery_fee, config.delivery_min
        if total < delivery_min or delivery_min == 0:
            if not is_vip or config.delivery_fee_for_vip:
                text += '\n'
                text += _('Delivery Fee: {}{}').format(delivery_fee, currency_symbol)
    else:
        delivery_fee = 0

    discount = config.discount
    discount_min = config.discount_min
    if discount_min != 0:
        if is_vip:
            discount_num = calculate_discount_total(discount, total)
            if discount_num and total >= discount_min:
                if not discount.endswith('%'):
                    text += '\n'
                    discount_str = '{}'.format(discount)
                    discount_str += currency_symbol
                    total -= int(discount)
                else:
                    text += '\n'
                    discount_str = discount
                    total -= discount_num
                text += _('Discount: {}').format(discount_str)

    total += delivery_fee

    text += '\n\n'
    text += _('Total: *{}{}*').format(total, currency_symbol)
    text += '\n'
    btc_value = None
    if btc_payment:
        total = CurrencyConverter.convert_currencies(total, user.currency, currency)
        btc_info = CurrencyConverter().convert_to_btc(currency, total)
        if btc_info:
            btc_value = btc_info
            btc_value = quantize_btc(btc_value)
            last_updated = config.currencies_last_updated.strftime('%H:%M')
            text += '\n'
            text += _('Total in BTC:')
            text += '\n'
            text += _('*{}*').format(btc_value)
            text += '\n'
            text += _('Conversion rate was checked at: {}').format(last_updated)
            text += '\n'
    return text, btc_value


def get_payment_status_msg(trans, status, balance, stage):
    _ = trans
    msg_map = {
        '{}{}'.format(BtcStatus.NOT_PAID, BtcStage.FIRST): _('Client did not pay yet.'),
        '{}{}'.format(BtcStatus.LOWER, BtcStage.FIRST): _('Client paid less: *{}*').format(balance),
        '{}{}'.format(BtcStatus.PAID, BtcStage.FIRST): _('Client paid. Processing payment.'),
        '{}{}'.format(BtcStatus.HIGHER, BtcStage.FIRST): _('Client paid more: *{}*. Processing payment').format(
            balance),
        '{}{}'.format(BtcStatus.ERROR, BtcStage.FIRST): _('BTC Service error. Stage 1.'),
        '{}{}'.format(BtcStatus.NOT_PAID, BtcStage.SECOND): _('Payment not processed yet.'),
        '{}{}'.format(BtcStatus.HIGHER, BtcStage.SECOND): _('Payment processed! Client paid more: *{}*').format(
            balance),
        '{}{}'.format(BtcStatus.PAID, BtcStage.SECOND): _('Payment successfully processed!'),
        '{}{}'.format(BtcStatus.ERROR, BtcStage.SECOND): _('BTC Service error. Stage 2'),
    }
    key = '{}{}'.format(status, stage)
    msg = msg_map[key]
    return msg


def create_service_notice(_, order, btc_data=None, for_courier=False):
    currency = get_currency_symbol()
    text = _('Order №{} notice:').format(order.id)
    text += '\n'
    text += '〰〰〰〰〰〰〰〰〰〰〰〰️'
    text += '\n'
    text += _('Items in cart:')
    text += '\n'

    total = 0

    for order_item in order.order_items:
        title = escape_markdown(order_item.product.title)
        text += '\n'
        text += _('Product:\n{}').format(title)
        text += '\n'
        text += _('x {} = {}{}').format(order_item.count, order_item.total_price, currency)
        text += '\n'
        total += order_item.total_price
    user = order.user
    is_vip = user.is_vip_client
    if order.shipping_method == order.DELIVERY:
        shipping_loc = order.location
        if shipping_loc and shipping_loc.delivery_fee is not None:
            delivery_fee, delivery_min = shipping_loc.delivery_fee, shipping_loc.delivery_min
        else:
            delivery_fee, delivery_min = config.delivery_fee, config.delivery_min
        if total < delivery_min or delivery_min == 0:
            if not is_vip or config.delivery_fee_for_vip:
                text += '\n'
                text += _('Delivery Fee: {}{}').format(delivery_fee, currency)
    else:
        delivery_fee = 0

    discount = config.discount
    discount_min = config.discount_min
    if discount_min != 0:
        if is_vip:
            discount_num = calculate_discount_total(discount, total)
            if discount_num and total >= discount_min:
                if not discount.endswith('%'):
                    text += '\n'
                    discount_str = '{}'.format(discount)
                    discount_str += '{}'.format(currency)
                    total -= int(discount)
                else:
                    text += '\n'
                    discount_str = discount
                    total -= discount_num
                text += _('Discount: {}').format(discount_str)

    total += delivery_fee

    text += '\n'
    text += _('Total: {}{}').format(total, currency)

    text += '\n'
    if order.btc_payment:
        text += '\n'
        text += _('Payment type: BTC')
        text += '\n'
        text += _('Amount: *{}*').format(btc_data.amount)
        text += '\n'

        status_msg = get_payment_status_msg(_, btc_data.paid_status, btc_data.balance, btc_data.payment_stage)
        text += _('Paid: {}').format(status_msg)
        text += '\n'

    if not for_courier:
        username = escape_markdown(user.username)
        text += '〰〰〰〰〰〰〰〰〰〰〰〰️'
        text += '\n'
        text += _('Customer: @{}').format(username)
        text += '\n'
        text += _('Customer status: {}').format(user.permission.get_permission_display())
        text += '\n'

    if order.shipping_method == order.PICKUP:
        text += _('🏪 Pickup')
        text += '\n'
    if order.location:
        text += _('From location: ')
        text += escape_markdown(order.location.title)
        text += '\n'
    if order.address:
        text += _('Address: ')
        text += escape_markdown(order.address)
        text += '\n'
    shipping_time_str = order.shipping_time.strftime('%b %d, %Y (%A) %H:%M')
    text += _('When: ')
    text += shipping_time_str
    text += '\n'
    if not for_courier and order.phone_number:
        text += _('Phone number: ')
        text += order.phone_number
    return text


def create_user_btc_notice(trans, order):
    _ = trans
    btc_data = OrderBtcPayment.get(order=order)
    btc_amount = btc_data.amount
    status = btc_data.paid_status
    msg = _('Order №{} notice:').format(order.id)
    msg += '\n\n'
    if status == BtcStatus.LOWER:
        remainder = btc_amount - btc_data.balance
        remainder = quantize_btc(remainder)
        msg += _('You have paid less than your order price: *{}* BTC').format(btc_amount)
        msg += '\n'
        msg += _('Please send *{}* BTC to address:').format(remainder)
        msg += '\n'
        msg += _('*{}*').format(btc_data.address)
    elif status == BtcStatus.PAID:
        msg += _('Payment completed. Order is processing.')
    elif status == BtcStatus.HIGHER:
        msg += _('You have paid more than your order price: *{}* BTC').format(btc_amount)
        msg += '\n'
        msg += _('You paid: *{}* BTC').format(btc_data.balance)
        msg += '\n'
        msg += _('Please contact administrator to recieve remained BTC')
    elif status == BtcStatus.NOT_PAID:
        msg += _('Please pay for your order: *{}* BTC').format(btc_amount)
        msg += '\n'
        msg += _('Address:')
        msg += '\n'
        msg += _('*{}*').format(btc_data.address)
    return msg


def create_delivery_fee_msg(_, location=None):
    if location:
        loc_title = escape_markdown(location.title)
        location_string = _(' for {}').format(loc_title)
        if location.delivery_fee is None:
            delivery_fee = config.delivery_fee
            delivery_min = config.delivery_min
        else:
            delivery_fee = location.delivery_fee
            delivery_min = location.delivery_min
    else:
        location_string = _(' for all locations')
        delivery_fee = config.delivery_fee
        delivery_min = config.delivery_min
    currency_str, currency_sym = Currencies.CURRENCIES[config.currency]
    msg = _('Enter delivery fee like:\n'
            '50 > 500: Deals below 500{0} will have delivery fee of 50{0}\n'
            'or\n'
            '50: All deals will have delivery fee of 50{0}\n'
            'Only works on delivery\n\n'
            'Current fee{1}: *{2} > {3}*').format(currency_sym, location_string, delivery_fee, delivery_min)
    msg += '\n'
    msg += _('Currency: {} {}').format(currency_str, currency_sym)
    return msg


def get_working_hours_msg(_):
    msg = _('*Working hours:*')
    time_format = '%H:%M'
    for hours in WorkingHours.select():
        open_time, close_time = hours.open_time.strftime(time_format), hours.close_time.strftime(time_format)
        msg += '\n'
        msg += '{}: `{}-{}`'.format(_(hours.get_day_display()), open_time, close_time)
    return msg