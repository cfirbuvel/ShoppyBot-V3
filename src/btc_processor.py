from decimal import Decimal
import time

from telegram.ext.dispatcher import run_async

from .btc_wrapper import BtcWallet, BtcError
from .btc_settings import BtcSettings
from .helpers import is_vip_customer, config, get_channel_trans, quantize_btc
from .keyboards import create_service_channel_keyboard, create_bitcoin_retry_keyboard
from .models import BtcStatus, BtcStage, BitcoinCredentials, Order, OrderBtcPayment
from .messages import create_service_notice, get_payment_status_msg
from . import shortcuts
#
#
# def start_orders_processing(bot):
#     orders = Order.select().join(OrderBtcPayment)\
#         .where(Order.canceled == False, Order.delivered == False, Order.btc_payment == True,
#                ((OrderBtcPayment.payment_stage == BtcStage.FIRST)
#                 | ((OrderBtcPayment.payment_stage == BtcStage.SECOND) & (OrderBtcPayment.paid_status.not_in([BtcStatus.PAID, BtcStatus.HIGHER])))
#                 ))
#     print('orders debug')
#     for o in orders:
#         # set_btc_proc(o.id)
#         print(o.id)
#         btc_data = OrderBtcPayment.get(order=o)
#         print(btc_data.id)
#         print('\n')
#         process_btc_payment(bot, o)
#
#
# def check_balance(trans, amount, wallet, xpub):
#     _ = trans
#     balance = 0
#     msg = None
#     try:
#         balance = wallet.get_hd_account_balance(xpub)
#     except BtcError as ex:
#         status = BtcStatus.ERROR
#         msg = str(ex)
#     else:
#         if balance > amount:
#             status = BtcStatus.HIGHER
#         elif balance == 0:
#             status = BtcStatus.NOT_PAID
#         elif balance < amount:
#             status = BtcStatus.LOWER
#         else:
#             status = BtcStatus.PAID
#     return status, balance, msg
#
#
# def save_order_refresh_msg(trans, bot, order, status, balance):
#     _ = trans
#     btc_data = OrderBtcPayment.get(order=order)
#     btc_data.balance = balance
#     btc_data.paid_status = status
#     order_data = OrderPhotos.get(order=order)
#     user_id = order.user.telegram_id
#     is_vip = is_vip_customer(bot, user_id)
#     order_msg = create_service_notice(_, order, is_vip, btc_data)
#     service_channel = config.get_service_channel()
#     keyboard = create_service_channel_keyboard(_, order)
#     msg_id = shortcuts.edit_channel_msg(bot, order_msg, service_channel,
#                                         order_data.order_text_msg_id, keyboard, order)
#     order_data.order_text_msg_id = msg_id
#     order_data.order_text = order_msg
#     order_data.save()
#     btc_data.save()
#     return btc_data
#
#
# def process_btc_payment(bot, order):
#     func_map = {BtcStage.FIRST: process_btc_first_stage, BtcStage.SECOND: process_btc_second_stage}
#     btc_data = OrderBtcPayment.get(order=order)
#     func = func_map[btc_data.payment_stage]
#     return func(bot, order)
#
#
# def send_channel_notice(bot, notice_msg, order, stopped=False):
#     _ = get_channel_trans()
#     service_channel = config.get_service_channel()
#     message = _('Order #{} notice:').format(order.id)
#     message += '\n'
#     if stopped:
#         message += _('Payment processing stopped.')
#         message += '\n'
#         message += notice_msg
#         keyboard = create_bitcoin_retry_keyboard(_, order.id)
#         shortcuts.send_channel_msg(bot, message, service_channel, keyboard, order)
#     else:
#         message += notice_msg
#         shortcuts.send_channel_msg(bot, message, service_channel, order=order)
#
#
# @run_async
# def process_btc_first_stage(bot, order):
#     btc_data = OrderBtcPayment.get(order=order)
#     _ = get_channel_trans()
#     wallet = BtcWallet(_, BtcSettings.WALLET, BtcSettings.PASSWORD, BtcSettings.SECOND_PASSWORD)
#     xpub = btc_data.xpub
#     wait_time = 60
#     num_tries = 60
#     amount = btc_data.amount
#     while num_tries:
#         status, balance, msg = check_balance(_, amount, wallet, xpub)
#         if status != btc_data.paid_status:
#             btc_data = save_order_refresh_msg(_, bot, order, status, balance)
#         if status in (BtcStatus.ERROR, BtcStatus.HIGHER, BtcStatus.PAID):
#             break
#         time.sleep(wait_time)
#         num_tries -= 1
#
#     if not msg:
#         msg = get_payment_status_msg(_, status, btc_data.balance, BtcStage.FIRST)
#
#     if status in (BtcStatus.PAID, BtcStatus.HIGHER):
#         send_channel_notice(bot, msg, order)
#
#         btc_creds = BitcoinCredentials.select().first()
#         admin_wallet = BtcWallet(_, btc_creds.wallet_id, btc_creds.password)
#         amount = btc_data.balance
#         comission = (amount / 100 * BtcSettings.COMISSION_PERCENT)
#         comission += Decimal(BtcSettings.DEFAULT_COMISSION)
#         amount = amount - comission
#         amount = quantize_btc(amount)
#         try:
#             if not btc_data.admin_address:
#                 btc_data.admin_address, btc_data.admin_xpub = admin_wallet.create_hd_account_address(
#                     'Order #{}'.format(order.id))
#                 btc_data.save()
#             wallet.make_payment(amount, btc_data.admin_address, xpub)
#         except BtcError as ex:
#             status = BtcStatus.ERROR
#             msg = str(ex)
#             save_order_refresh_msg(_, bot, order, status, balance)
#         else:
#             btc_data.payment_stage = BtcStage.SECOND
#             btc_data.paid_status = BtcStatus.NOT_PAID
#             btc_data.save()
#             return process_btc_second_stage(bot, order)
#
#     send_channel_notice(bot, msg, order, stopped=True)
#     clear_procs(order.id)
#
#
# @run_async
# def process_btc_second_stage(bot, order):
#     btc_data = OrderBtcPayment.get(order=order)
#     _ = get_channel_trans()
#     btc_creds = BitcoinCredentials.select().first()
#     admin_wallet = BtcWallet(_, btc_creds.wallet_id, btc_creds.password)
#     amount = btc_data.balance
#     comission = (amount / 100 * BtcSettings.COMISSION_PERCENT)
#     comission += Decimal(BtcSettings.DEFAULT_COMISSION)
#     amount = amount - comission
#     amount = quantize_btc(amount)
#
#     wait_time = 60
#     num_tries = 60
#     first_run = True
#     while num_tries:
#         status, balance, msg = check_balance(_, amount, admin_wallet, btc_data.admin_xpub)
#         if status != BtcStatus.NOT_PAID:
#             break
#         else:
#             if first_run:
#                 btc_data = save_order_refresh_msg(_, bot, order, status, balance)
#                 first_run = False
#         time.sleep(wait_time)
#         num_tries -= 1
#
#     if status != BtcStatus.NOT_PAID:
#         btc_data = save_order_refresh_msg(_, bot, order, status, balance)
#
#     if not msg:
#         msg = get_payment_status_msg(_, status, btc_data.balance, BtcStage.SECOND)
#
#     if status in (BtcStatus.PAID, BtcStatus.HIGHER):
#         send_channel_notice(bot, msg, order)
#     else:
#         send_channel_notice(bot, msg, order, stopped=True)

    # clear_procs(order.id)

#
# def clear_procs(order_id):
#     procs = session_client.json_get('btc_procs')
#     if procs:
#         procs.remove(order_id)
#         session_client.json_set('btc_procs', procs)
#
#
# def set_btc_proc(order_id):
#     procs = session_client.json_get('btc_procs')
#     if not procs:
#         procs = [order_id]
#     else:
#         procs.append(order_id)
#     session_client.json_set('btc_procs', procs)




