import collections
import math
import re
from datetime import datetime
from datetime import timedelta


def splice(items_to_splice, lambda_condition):
    """
    Splice items matching a condition
    :param items_to_splice: Items to splice
    :param lambda_condition: Condition to match
    :return: (remainder, matched) tuple of lists
    """
    remainder = list()
    spliced = list()
    for item in items_to_splice:
        if lambda_condition(item):
            spliced.append(item)
        else:
            remainder.append(item)
    return remainder, spliced


class KeepExpression:
    """
    Represents a sequence of conditions describing which backups to keep
    """
    __kd = {'h': timedelta(hours=1),
            'd': timedelta(days=1),
            'w': timedelta(days=7),
            'm': timedelta(days=30),
            'n': None}

    __keep_re = re.compile('^([0-9]+)(/([hdwm]{1}))?$', re.IGNORECASE)
    __age_re = re.compile('^([0-9]+)([hdwm]{1})?$', re.IGNORECASE)

    class Condition:
        """
        Each condition of a keep expression reflects how many backups to keep after a specific amount of time
        """
        def __init__(self, age, interval_duration, interval_amount):
            self.age = age
            self.interval_duration = interval_duration
            self.interval_amount = interval_amount

        def __repr__(self):
            return 'Condition(age=%s, keep_amount=%s, keep_interval=%s)' \
                   % (self.age, self.interval_amount, self.interval_duration)

        def __str__(self):
            return 'age [%s] interval [%s] amount [%s]' % (self.age, self.interval_duration, self.interval_amount)

    class ApplicableInterval:
        """
        Interval which relates to a specific time and has filtering capabilities
        """
        def __init__(self, start, duration, amount):
            self.start = start
            self.duration = duration
            self.amount = amount
            self.end = self.start + self.duration if self.duration is not None else None

        def __repr__(self):
            return 'ApplicableInterval(start=%s, duration=%s, amount=%s)' \
                   % (self.start, self.duration, self.amount)

        def __reduce(self, items, max_amount):
            """
            Reduces a list of items evenly
            :param items: List of items to reduce
            :param max_amount: Maximum amount of items to keep
            :return: (to_keep, to_remove) tuple of lists
            """
            to_keep = list()
            to_remove = list()

            if max_amount == 0:
                return list(), list(items)

            if len(items) > max_amount:
                s = len(items) / (max_amount + 1) - 1
                ss = len(items) / max_amount
                next_index = round(s)
                for j in range(0, len(items)):
                    item = items[j]
                    if j == next_index:
                        to_keep.append(item)
                        s += ss
                        next_index = round(s)
                    else:
                        to_remove.append(item)
            else:
                to_keep.extend(items)

            return to_keep, to_remove

        def filter(self, items, lambda_timestamp):
            """
            Filters item according to criteria defined by this interval
            :param items: Items to filter
            :param lambda_timestamp: Lambda to return timestamp for each item
            :return: (items, to_keep, to_remove) The items which have not matched and one list items to keep/remove
            """
            (items, interval_items) = splice(items, lambda i: self.start >= lambda_timestamp(i) > self.end)
            (to_keep, to_remove) = self.__reduce(interval_items, self.amount)

            return items, to_keep, to_remove

    class ApplicableCondition:
        """
        Applicable condition, relative to a timestamp
        """
        def __init__(self, condition, next_condition, start_time):
            self.age = condition.age
            self.interval_amount = condition.interval_amount
            self.condition_start = start_time + condition.age
            self.interval_start = self.condition_start

            # Calculate interval duration using next condition if needed
            interval_duration = condition.interval_duration
            if interval_duration is None:
                # If keep interval is not defined (static number of items)
                # calculate the interval -> difference to subsequent condition
                if next_condition is not None:
                    interval_duration = next_condition.age - condition.age

            self.interval_duration = interval_duration

            # Calculate condition and interval end
            condition_end = None
            interval_end = self.interval_start + self.interval_duration if self.interval_duration is not None else None
            if next_condition is not None:
                condition_end = start_time + next_condition.age
                # Limit end of interval to end of condition
                if interval_end is not None and interval_end > condition_end:
                    interval_end = condition_end

            self.interval_end = interval_end
            self.condition_end = condition_end

        def __str__(self):
            return 'age [%s] interval duration [%s] interval amount [%s]' % (self.age, self.interval_duration, self.interval_amount)

        def interval_by_timestamp(self, timestamp):
            """
            Creates an applicable interval for the given timestamp
            If timestamp is out of range of the condition start/end time this method will return None
            :param timestamp: Timestamp
            :return: ApplicableInterval or None if timestamp out of bounds of the condition start/end time
            """
            if timestamp > self.condition_start or \
                    (self.condition_end is not None and timestamp <= self.condition_end):
                return None

            if self.interval_duration is None:
                return KeepExpression.ApplicableInterval(self.condition_start,
                                                         self.interval_duration,
                                                         self.interval_amount)

            # Calculate interval factor
            f = math.floor((timestamp - self.condition_start) / self.interval_duration)

            return KeepExpression.ApplicableInterval(self.condition_start + f * self.interval_duration,
                                                     self.interval_duration,
                                                     self.interval_amount)

    def __create_applicable_conditions(self, start_time):
        """
        Create applicable conditions from this keep expressions
        :param start_time: Start time for conditions
        :return: List of applicable conditions
        """
        result = list()
        for i in range(0, len(self.conditions)):
            next_condition = self.conditions[i+1] if i < len(self.conditions) - 1 else None
            result.append(KeepExpression.ApplicableCondition(self.conditions[i], next_condition, start_time))
        return result

    def __init__(self, expression):
        """
        c'tor
        :param expression: Expression string defining multiple criteria for keeping backups
        """
        expression = str(expression)
        self.expression_text = expression
        conditions = list()

        # Parse keep expression string
        # Split criteria list
        criterias = expression.split(',')
        for criteria in criterias:
            # Parse criteria expression
            criteria = criteria.strip()
            cparts = criteria.split('=')
            if len(cparts) != 2:
                try:
                    age = timedelta(0)
                    interval_duration = None
                    interval_amount = int(criteria)
                except:
                    raise ValueError('Criteria must consist of age and interval separated by equality operator [%s]'
                                     % criteria)
            else:
                age_literal = cparts[0].strip()
                keep_literal = cparts[1].strip()

                # Parse age (examples: 4d, 4w, 30 ..)
                match = self.__age_re.match(age_literal)
                if match is None:
                    raise ValueError('Invalid age [%s]' % age_literal)

                if match.group(2) is not None:
                    # Time literal part of age
                    age = int(match.group(1)) * self.__kd[match.group(2)]
                else:
                    # Plain number of hours
                    age = timedelta(hours=int(match.group(1)))

                # Parse keep expression (examples: 4/d, 4/w, 20 ..)
                if keep_literal[0] in self.__kd:
                    interval_duration = self.__kd[keep_literal[0]]
                    interval_amount = 1 if interval_duration is not None else 0
                else:
                    match = self.__keep_re.match(keep_literal)
                    if match is None:
                        raise ValueError('Invalid keep [%s]' % keep_literal)
                    interval_amount = int(match.group(1))
                    if match.group(3) is None:
                        interval_duration = None
                    else:
                        interval_duration = self.__kd[str(match.group(3)[0])]

            condition = KeepExpression.Condition(age, interval_duration, interval_amount)
            conditions.append(condition)

        # Conditions sorted by age
        self.conditions = sorted(conditions, key=lambda c: c.age)

    def filter(self, items, lambda_timestamp):
        """
        Filter items according to keep expression
        :param items: Items to filter
        :param lambda_timestamp: Lambda to return the timestamp for each item
        :return: (items_to_remove_by_condition, items_to_keep)
        """

        if len(self.conditions) == 0:
            return list(), list(items)

        if len(items) == 0:
            return list(), list()

        items = sorted(items, key=lambda_timestamp, reverse=True)

        items_to_keep = list()
        items_to_remove_by_condition = collections.OrderedDict()

        now = datetime.utcnow()
        conditions = self.__create_applicable_conditions(now)

        # Splice recent items (newer than first condition age)
        (items, recent_items) = splice(items, lambda i: lambda_timestamp(i) > (now - self.conditions[0].age))
        items_to_keep.extend(recent_items)

        for x in recent_items:
            if x.timestamp < now - self.conditions[0].age:
                print('%s < %s' % (x.timestamp, (now - self.conditions[0].age)))

        while len(items) > 0 and len(conditions) > 0:
            item_timestamp = lambda_timestamp(items[0])
            condition = conditions[0]

            interval = condition.interval_by_timestamp(item_timestamp)
            if interval is None:
                conditions.pop(0)
                continue

            if condition not in items_to_remove_by_condition:
                items_to_remove_by_condition[condition] = list()

            items_to_remove = items_to_remove_by_condition[condition]

            if interval.end is not None:
                (items, to_keep, to_remove) = interval.filter(items, lambda_timestamp)

                items_to_keep.extend(to_keep)
                items_to_remove.extend(to_remove)
            else:
                items_to_keep.extend(items[:interval.amount])
                items_to_remove.extend(items[interval.amount:])
                items.clear()

        return items_to_remove_by_condition, items_to_keep
