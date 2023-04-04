from collections import defaultdict
import numpy as np
from geniusweb.issuevalue import NumberValueSet
from geniusweb.issuevalue.Bid import Bid
from geniusweb.issuevalue.DiscreteValueSet import DiscreteValueSet
from geniusweb.issuevalue.Domain import Domain
from geniusweb.issuevalue.Value import Value


class OpponentModel:
    def __init__(self, domain: Domain, learning_rate: int = 0.2):
        issue_amount = len(domain.getIssues())
        # what issues have remained unchanged so far?
        self.offers = {}
        # what weights the opponent might have
        self.weights = {}
        # Values opponent has
        self.utility_estimate = {}
        for name in domain.getIssues():
            self.offers[name] = True
            self.weights[name] = 1/issue_amount

        # the domain
        self.domain = domain
        # the learnign rate for this (factors in weight changes)j
        self.learning_rate = learning_rate
        # what is the latest offer our opponent has sent
        self.latest = None

    def update(self, bid: Bid):
        # bid has been received, it now will be kept track of ( might remove this, but useful for debug)
        # We are in the first offer, so preferene profile needs to be initialised
        if(self.latest == None):
            self.latest = bid
            for name in bid.getIssues():
                utility_guess_name = bid.getValue(name).getValue()
                self.utility_estimate[(name, utility_guess_name)] = 1
        else:
            #We compare the last bid that came in. Does it change anything compares to
            for name in bid.getIssues():
                # check if it hasn't changed since the last one, or any before

                new_value = bid.getValue(name).getValue()
                old_value = self.latest.getValue(name).getValue()
                if old_value == new_value:
                    self.weights[name] += self.learning_rate
                    if self.utility_estimate.__contains__((name, new_value)):
                        self.utility_estimate[(name, new_value)] += 2
                    else:
                        self.utility_estimate[(name, new_value)] = 2
                else:
                    # issue has changed, so we keep track of this and no longer consider it for "growth"
                    # TODO: Change this to a dynamic range, giving more flexibility
                    self.offers[name] = False
            sum_of_weigths = sum(self.weights.values())
            for name in self.weights:
                self.weights[name] = self.weights[name]/sum_of_weigths
            self.latest = bid

    def get_predicted_utility(self, bid: Bid):
        utility = 0
        for name in bid.getIssues():
            value_name = bid.getValue(name).getValue()
            if not self.utility_estimate.__contains__((name, value_name)):
                estimated_utility = 2
            else:
                estimated_utility = self.utility_estimate[(name, value_name)]
            utility += self.weights[name] * estimated_utility
        return utility

class IssueEstimator:
    def __init__(self, value_set: DiscreteValueSet):
        if not isinstance(value_set, DiscreteValueSet):
            raise TypeError(
                "This issue estimator only supports issues with discrete values"
            )

        self.bids_received = 0
        self.max_value_count = 0
        self.num_values = value_set.size()
        self.value_trackers = defaultdict(ValueEstimator)
        self.weight = 0

    def update(self, value: Value):
        self.bids_received += 1

        # get the value tracker of the value that is offered
        value_tracker = self.value_trackers[value]

        # register that this value was offered
        value_tracker.update()

        # update the count of the most common offered value
        self.max_value_count = max([value_tracker.count, self.max_value_count])

        # update predicted issue weight
        # the intuition here is that if the values of the receiverd offers spread out over all
        # possible values, then this issue is likely not important to the opponent (weight == 0.0).
        # If all received offers proposed the same value for this issue,
        # then the predicted issue weight == 1.0
        equal_shares = self.bids_received / self.num_values
        self.weight = (self.max_value_count - equal_shares) / (
            self.bids_received - equal_shares
        )

        # recalculate all value utilities
        for value_tracker in self.value_trackers.values():
            value_tracker.recalculate_utility(self.max_value_count, self.weight)

    def get_value_utility(self, value: Value):
        if value in self.value_trackers:
            return self.value_trackers[value].utility

        return 0


class ValueEstimator:
    def __init__(self):
        self.count = 0
        self.utility = 0

    def update(self):
        self.count += 1

    def recalculate_utility(self, max_value_count: int, weight: float):
        if weight < 1:
            mod_value_count = ((self.count + 1) ** (1 - weight)) - 1
            mod_max_value_count = ((max_value_count + 1) ** (1 - weight)) - 1

            self.utility = mod_value_count / mod_max_value_count
        else:
            self.utility = 1
