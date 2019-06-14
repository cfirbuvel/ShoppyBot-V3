from collections import defaultdict
from decimal import Decimal
from peewee import JOIN

from .btc_wrapper import CurrencyConverter
from .helpers import config
from .models import ProductCount, Product, User, OrderItem, GroupProductCount, UserGroupCount, \
    GroupProductCountPermission, ProductGroupCount, UserPermission


class Cart:

    @staticmethod
    def check_cart(user_data):
        # check that cart is still here in case we've restarted
        cart = user_data.get('cart')
        if cart is None:
            cart = {}
            user_data['cart'] = cart
        return cart

    @staticmethod
    def add(user_data, product_id, user):
        cart = Cart.check_cart(user_data)
        product = Product.get(id=product_id)
        price_group = Cart.get_product_price_group(product, user)
        if price_group:
            query = (ProductCount.price_group == price_group)
        else:
            query = (ProductCount.product == product)
        prices = ProductCount.select().where(query).order_by(ProductCount.count.asc())
        counts = [x.count for x in prices]
        if product_id not in cart:
            cart[product_id] = counts[0]
        else:
            # add more
            current_count = cart[product_id]
            current_count_index = counts.index(current_count)
            # iterate through possible product counts for next price
            next_count_index = (current_count_index + 1) % len(counts)
            cart[product_id] = counts[next_count_index]
        user_data['cart'] = cart
        return user_data

    @staticmethod
    def remove(user_data, product_id, user):
        cart = Cart.check_cart(user_data)
        product = Product.get(id=product_id)
        price_group = Cart.get_product_price_group(product, user)
        if price_group:
            query = (ProductCount.price_group == price_group)
        else:
            query = (ProductCount.product == product)
        prices = ProductCount.select().where(query).order_by(ProductCount.count.asc())
        counts = [x.count for x in prices]

        if product_id in cart:
            current_count = cart[product_id]
            current_count_index = counts.index(current_count)

            if current_count_index == 0:
                del cart[product_id]
            else:
                next_count_index = current_count_index - 1
                cart[product_id] = counts[next_count_index]
        user_data['cart'] = cart

        return user_data

    @staticmethod
    def remove_all(user_data, product_id):
        cart = Cart.check_cart(user_data)
        try:
            del cart[product_id]
        except KeyError:
            pass
        user_data['cart'] = cart
        return user_data

    @staticmethod
    def get_products_info(user_data, user, for_order=False):
        currency = user.currency
        product_ids = Cart.get_product_ids(user_data)

        group_prices = defaultdict(int)
        products = Product.select().where(Product.id << list(product_ids))
        products_counts = []

        for product in products:
            count = Cart.get_product_count(user_data, product.id)
            group_price = Cart.get_product_price_group(product, user)
            if group_price:
                group_price_id = group_price.id
                group_prices[group_price_id] += count
            else:
                group_price_id = None
            products_counts.append((product, count, group_price_id))

        for group_id, count in group_prices.items():
            group_count = ProductCount.select().where(
                ProductCount.price_group == group_id, ProductCount.count <= count
            ).order_by(ProductCount.count.desc()).first()
            price_per_one = group_count.price / group_count.count
            group_prices[group_id] = price_per_one

        products_info = []
        for product, count, group_price_id in products_counts:
            if group_price_id:
                product_price = count * group_prices[group_price_id]
                product_price = Decimal(product_price).quantize(Decimal('0.01'))
            else:
                product_price = ProductCount.get(product=product, count=count).price
            if not currency == config.currency and not for_order:
                product_price = CurrencyConverter.convert_currencies(product_price, config.currency, currency)
            if for_order:
                name = product.id
            else:
                name = product.title
            products_info.append((name, count, product_price))
        return products_info


    @staticmethod
    def get_product_price_group(product, user):
        group_price_query = (
            (ProductGroupCount.product == product) & (
                (UserGroupCount.user == user)
                | ((GroupProductCountPermission.permission == user.permission) & (UserGroupCount.price_group.is_null(True)))
                | ((GroupProductCountPermission.price_group.is_null(True)) & (UserGroupCount.price_group.is_null(True)))
             )
        )
        try:
            group_price = GroupProductCount.select().join(UserGroupCount, JOIN.LEFT_OUTER).switch(GroupProductCount) \
                .join(GroupProductCountPermission, JOIN.LEFT_OUTER).switch(GroupProductCount).join(ProductGroupCount, JOIN.LEFT_OUTER) \
                .where(group_price_query).group_by(GroupProductCount.id).order_by(UserGroupCount.price_group.is_null(False).desc())
            print('gp')
            print(list(group_price))
            group_price = group_price.get()
        except GroupProductCount.DoesNotExist:
            group_price = None
        return group_price

    @staticmethod
    def get_product_ids(user_data):
        cart = Cart.check_cart(user_data)
        return cart.keys()

    @staticmethod
    def get_product_count(user_data, product_id):
        cart = Cart.check_cart(user_data)
        if product_id not in cart:
            return 0
        else:
            return cart[product_id]

    @staticmethod
    def not_empty(user_data):
        cart = Cart.check_cart(user_data)
        return len(cart) > 0

    @staticmethod
    def get_product_subtotal(user_data, product, price_group):
        count = Cart.get_product_count(user_data, product.id)
        if price_group:
            subquery = {'price_group': price_group}
        else:
            subquery = {'product': product}
        try:
            product_count = ProductCount.get(count=count, **subquery)
        except ProductCount.DoesNotExist:
            price = 0
        else:
            price = product_count.price
        return price

    @staticmethod
    def get_cart_total(user_data, user):
        products_info = Cart.get_products_info(user_data, user)
        total = sum((val[-1] for val in products_info))
        return total

    @staticmethod
    def fill_order(user_data, order, user):
        products = Cart.get_products_info(user_data, user, for_order=True)
        total = 0
        for p_id, p_count, p_price in products:
            OrderItem.create(order=order, product_id=p_id, count=p_count, total_price=p_price)
            total += p_price
        return total