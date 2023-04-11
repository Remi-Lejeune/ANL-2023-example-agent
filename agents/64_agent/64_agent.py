import logging
from random import randint
from time import time
from typing import cast

from geniusweb.actions.Accept import Accept
from geniusweb.actions.Action import Action
from geniusweb.actions.Offer import Offer
from geniusweb.actions.PartyId import PartyId
from geniusweb.bidspace.AllBidsList import AllBidsList
from geniusweb.inform.ActionDone import ActionDone
from geniusweb.inform.Finished import Finished
from geniusweb.inform.Inform import Inform
from geniusweb.inform.Settings import Settings
from geniusweb.inform.YourTurn import YourTurn
from geniusweb.issuevalue.Bid import Bid
from geniusweb.issuevalue.Domain import Domain
from geniusweb.party.Capabilities import Capabilities
from geniusweb.party.DefaultParty import DefaultParty
from geniusweb.profile.utilityspace.LinearAdditiveUtilitySpace import (
    LinearAdditiveUtilitySpace,
)
from geniusweb.profileconnection.ProfileConnectionFactory import (
    ProfileConnectionFactory,
)
from geniusweb.progress.ProgressTime import ProgressTime
from geniusweb.references.Parameters import Parameters
from tudelft_utilities_logging.ReportToLogger import ReportToLogger

from .utils.opponent_model import OpponentModel
import json
import geniusweb.issuevalue.DiscreteValue
class Agent_64(DefaultParty):
    """
    Group 64 implementation of negotiator
    """

    def __init__(self):
        super().__init__()
        self.logger: ReportToLogger = self.getReporter()

        self.domain: Domain = None
        self.parameters: Parameters = None
        self.profile: LinearAdditiveUtilitySpace = None
        self.progress: ProgressTime = None
        self.me: PartyId = None
        self.other: str = None
        self.settings: Settings = None
        self.storage_dir: str = None

        self.last_received_bid: Bid = None
        self.opponent_model: OpponentModel = None
        self.logger.log(logging.INFO, "party is initialized")

    def notifyChange(self, data: Inform):
        """MUST BE IMPLEMENTED
        This is the entry point of all interaction with your agent after is has been initialised.
        How to handle the received data is based on its class type.

        Args:
            info (Inform): Contains either a request for action or information.
        """

        # a Settings message is the first message that will be send to your
        # agent containing all the information about the negotiation session.
        if isinstance(data, Settings):
            self.settings = cast(Settings, data)
            self.me = self.settings.getID()

            # progress towards the deadline has to be tracked manually through the use of the Progress object
            self.progress = self.settings.getProgress()

            self.parameters = self.settings.getParameters()
            self.storage_dir = self.parameters.get("storage_dir")

            # the profile contains the preferences of the agent over the domain
            profile_connection = ProfileConnectionFactory.create(
                data.getProfile().getURI(), self.getReporter()
            )
            self.profile = profile_connection.getProfile()
            self.domain = self.profile.getDomain()
            profile_connection.close()

        # ActionDone informs you of an action (an offer or an accept)
        # that is performed by one of the agents (including yourself).
        elif isinstance(data, ActionDone):
            action = cast(ActionDone, data).getAction()
            actor = action.getActor()

            # ignore action if it is our action
            if actor != self.me:
                # obtain the name of the opponent, cutting of the position ID.
                self.other = str(actor).rsplit("_", 1)[0]

                # process action done by opponent
                self.opponent_action(action)
        # YourTurn notifies you that it is your turn to act
        elif isinstance(data, YourTurn):
            # execute a turn
            self.my_turn()

        # Finished will be send if the negotiation has ended (through agreement or deadline)
        elif isinstance(data, Finished):
            self.save_data()
            # terminate the agent MUST BE CALLED
            self.logger.log(logging.INFO, "party is terminating:")
            super().terminate()
        else:
            self.logger.log(logging.WARNING, "Ignoring unknown info " + str(data))

    def getCapabilities(self) -> Capabilities:
        """MUST BE IMPLEMENTED
        Method to indicate to the protocol what the capabilities of this agent are.
        Leave it as is for the ANL 2022 competition

        Returns:
            Capabilities: Capabilities representation class
        """
        return Capabilities(
            set(["SAOP"]),
            set(["geniusweb.profile.utilityspace.LinearAdditive"]),
        )

    def send_action(self, action: Action):
        """Sends an action to the opponent(s)

        Args:
            action (Action): action of this agent
        """
        self.getConnection().send(action)

    # give a description of your agent
    def getDescription(self) -> str:
        """MUST BE IMPLEMENTED
        Returns a description of your agent. 1 or 2 sentences.

        Returns:
            str: Agent description
        """
        return "group 64 agent for CAI assignment 2023"

    def opponent_action(self, action):
        """Process an action that was received from the opponent.

        Args:
            action (Action): action of opponent
        """
        # if it is an offer, set the last received bid
        if isinstance(action, Offer):
            # create opponent model if it was not yet initialised
            if self.opponent_model is None:
                self.opponent_model = OpponentModel(self.domain)

            bid = cast(Offer, action).getBid()

            # update opponent model with bid
            self.opponent_model.update(bid, self.progress.get(time() * 1000))
            # set bid as last received
            self.last_received_bid = bid

    def my_turn(self):
        """This method is called when it is our turn. It should decide upon an action
        to perform and send this action to the opponent.
        """

        bid = self.find_bid()
        # check if the last received offer is good enough
        if self.accept_condition(self.last_received_bid, bid):
            # if so, accept the offer
            action = Accept(self.me, self.last_received_bid)
        else:
            # if not, find a bid to propose as counter offer

            action = Offer(self.me, bid)

        # send the action
        self.send_action(action)

    def save_data(self):
        """This method is called after the negotiation is finished. It can be used to store data
        for learning capabilities. Note that no extensive calculations can be done within this method.
        Taking too much time might result in your agent being killed, so use it for storage only.
        """
        data = self.opponent_model.utility_estimate
        weights = self.opponent_model.weights
        new_data = {"Domain": self.domain.getName() }
        for key, value in data.items():
            if not new_data.__contains__(key[0]):
                new_data[key[0]]= [{key[1] : value}]
            else:
                new_data[key[0]].append({key[1] : value})
        for key in weights:
            new_data[key].insert(0,{'weight: ' : weights[key]})
        with open(f"{self.storage_dir}/data.json", "w") as f:
            for key, value in new_data.items():
                f.write(json.dumps(key))
                f.write("\n")
                if isinstance(value, str):
                    f.write(json.dumps(value))
                    f.write("\n")
                else:
                    for line in value:
                        f.write("\t")
                        f.write(json.dumps(line))
                        f.write("\n")
    ###########################################################################################
    ################################## Example methods below ##################################
    ###########################################################################################

    def accept_condition(self, received_bid: Bid, next_bid: Bid) -> bool:

        """ This function is used to determine if the received bid is acceptable or not.

            Args:
                received_bid (Bid): the bid received from the opponent
                next_bid (Bid): the bid we are going to propose
        """
        if received_bid is None:
            return False


        # progress of the negotiation session between 0 and 1 (1 is deadline)
        progress = self.progress.get(time() * 1000)

        conditions = [
            #Our acceptance condition
            self.simple_acceptance_condition(received_bid, next_bid)
        ]
        return all(conditions)

    def simple_acceptance_condition(self, received_bid: Bid, next_bid: Bid) -> bool:
        """ This function look if the received bid is higher than the current acceptable utility
            and accept if it is the case.

            Args:
                received_bid (Bid): the bid received from the opponent
                next_bid (Bid): the bid we are going to propose (this is not use here)

            Returns:
                bool: True if the received bid is higher than the current acceptable utility
        """
        return self.profile.getUtility(received_bid) >= self.calculate_current_acceptable_utility()


    def find_bid(self) -> Bid:
        """Finds the best bid to bid, according to our model.
            Returns:
                best_bid (Bid): the best bid the function found in the first 500 bids
        """
        # compose a list of all possible bids
        domain = self.profile.getDomain()
        all_bids = AllBidsList(domain)

        #starting values that will get overwritten
        best_bid_score = -0.1
        best_bid = None

        # take 500 attempts to find a bid according to a heuristic score
        for _ in range(500):
            bid = all_bids.get(randint(0, all_bids.size() - 1))
            bid_score = self.score_bid(bid)  # can add values for parameters
            if bid_score > best_bid_score:
                best_bid_score, best_bid = bid_score, bid

        return best_bid


    def calculate_current_acceptable_utility(self, MinUtility=0.63, MaxUtility=1, k=0.05, e=4, T=1):
        """Calculates the P value which represents the utility that is acceptable by the agent at that time.
        Args:
            MinUtility (float): The minimum utility when t = T = 1, default = 0.63
            MaxUtility (float): The maximum utility a bid can have = 1
            k (float): How strongly the function is curved (especially at the beginning)
            e (float): How fast the agent concedes
            T (float): Total time
        Returns:
            float: score
        """
        #The current time t
        t = self.progress.get(time() * 1000)  # in between 0 and 1

        #Concession function
        Ft = k + (1 - k) * (min(t, T) / T) ** (1 / e)

        #Utility at which the agent is willing to concede
        P = MinUtility + (1 - Ft) * (MaxUtility - MinUtility)
        return P

    def score_bid(self, bid: Bid) -> float:
        """Calculate heuristic score for a bid

        Args:
            bid (Bid): Bid to score
        Returns:
            float: score
        """
        # Given a bid, we calculate our utility for it first.
        our_utility = float(self.profile.getUtility(bid))

        # Then we calculate what the minimum acceptable utility is at the moment.
        P = self.calculate_current_acceptable_utility()

        # Check if we find the bid acceptable
        if (our_utility > P):
            if self.opponent_model is not None:
                # If we have an opponent model, return the utility we believe the opponent has for this
                opponent_utility = self.opponent_model.get_predicted_utility(bid)
                return opponent_utility
            else:
                # If there is no opponent model, just return 1
                return 1
        else: # The bid is not acceptable
            return 0

