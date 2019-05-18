from pokereval_cactus import Deck
from pokereval_cactus import Evaluator

from gym_holdem.holdem.bet_round import BetRound
from gym_holdem.holdem.pot import Pot
from gym_holdem.holdem.poker_rule_violation_exception import PokerRuleViolationException

evaluator = Evaluator()


class Table:
    def __init__(self, small_blind=25, big_blind=50):
        if small_blind < 0:
            raise PokerRuleViolationException("Small blind must be at least 0")
        if big_blind < 0:
            raise PokerRuleViolationException("Big blind must be at least 0")
        if big_blind < small_blind:
            raise PokerRuleViolationException("Big blind cant be less than small blind")

        self.players = []
        self.active_players = []
        self.small_blind = small_blind
        self.big_blind = big_blind
        self.dealer = -1
        self.small_blind_player = -1
        self.big_blind_player = -1
        self.pots = []
        self.deck = None
        self.bet_round = BetRound.PREFLOP
        self.board = []
        self.last_bet_raise_delta = big_blind
        self.next_player_idx = 0

    def new_round(self):
        if len(self.players) < 2:
            raise PokerRuleViolationException("To start a new round, there must be at least 2 players")

        self.active_players = self.players
        self.dealer = self.next_seat(self.dealer)
        self.pots = [Pot()]
        self.deck = Deck()
        self.deck.shuffle()
        self.bet_round = BetRound.PREFLOP

        if len(self.players) == 2:
            self.small_blind_player = self.dealer
        else:
            self.small_blind_player = self.next_seat(self.dealer)

        self.big_blind_player = self.next_seat(self.small_blind_player)
        self.next_player_idx = self.next_seat(self.big_blind_player)
        self.board = []

        for player in self.players:
            player._has_called = False
            player.bet = 0
            player.hand = self.deck.draw(2)

        self.last_bet_raise_delta = self.big_blind
        self.active_players[self.small_blind_player].bet_small_blind()
        self.active_players[self.big_blind_player].bet_big_blind()

    def add_player(self, player):
        self.players.append(player)

    @property
    def current_pot(self):
        return self.pots[-1]

    def bet(self, amount, player):
        for pot in self.pots:
            if player not in pot.contributors:
                delta = pot.highest_amount
            else:
                delta = pot.highest_amount - pot.contributors[player]

            # All in
            if amount < delta:
                # raise Exception("Player can't contribute to pot because his bet is too low")
                self._split_pot(pot, player)
                pot.increase_stakes(amount, player)
                return

            amount -= delta
            pot.increase_stakes(delta, player)

        self.current_pot.increase_stakes(amount, player)

    def next_seat(self, seat):
        return (seat + 1) % len(self.players)

    def next_active_seat(self, seat):
        return (seat + 1) % len(self.active_players)

    def set_next_player(self, folded=False):
        if self.all_players_called:
            self.next_player_idx = None
            return
        
        if not folded:
            self.next_player_idx = self.next_active_seat(self.next_player_idx)
        else:
            self.next_player_idx %= len(self.active_players)
        
        while self.next_player.has_called:
            self.next_player_idx = self.next_active_seat(self.next_player_idx)

    @property
    def next_player(self):
        return self.active_players[self.next_player_idx]

    def start_next_bet_round(self):
        for p in self.active_players:
            if not p.has_called:
                raise Exception("Everyone must call first")

        self.last_bet_raise_delta = self.big_blind

        if len(self.active_players) == 1:
            self.bet_round = BetRound.SHOWDOWN
            return

        if self.check_everyone_all_in():
            self.board += self.deck.draw(5 - len(self.board))
            self.bet_round = BetRound.SHOWDOWN
            return

        if self.bet_round == BetRound.PREFLOP:
            self.board = self.deck.draw(3)
            self.bet_round = BetRound.FLOP
            self.reset_players_called_var()
            self.next_player_idx = self.next_active_seat(self.dealer)
            if self.next_player.has_called:
                self.set_next_player

        elif self.bet_round == BetRound.FLOP:
            self.board += self.deck.draw(1)
            self.bet_round = BetRound.TURN
            self.reset_players_called_var()
            self.next_player_idx = self.next_active_seat(self.dealer)
            if self.next_player.has_called:
                self.set_next_player

        elif self.bet_round == BetRound.TURN:
            self.board += self.deck.draw(1)
            self.bet_round = BetRound.RIVER
            self.reset_players_called_var()
            self.next_player_idx = self.next_active_seat(self.dealer)
            if self.next_player.has_called:
                self.set_next_player

        elif self.bet_round == BetRound.RIVER:
            self.bet_round = BetRound.SHOWDOWN

        elif self.bet_round == BetRound.SHOWDOWN:
            raise Exception("After the showdown, the round ends")

    def reset_players_called_var(self):
        for p in self.active_players:
            p._has_called = False

    def check_everyone_all_in(self):
        only_one_all_in = False
        for p in self.active_players:
            if not p.is_all_in():
                # Checks if there is already one who is not allin
                if only_one_all_in:
                    return False
                only_one_all_in = True
        return True

    def end_round(self):
        if self.bet_round != BetRound.SHOWDOWN:
            raise Exception(f"Round must be in showdown but is in {self.bet_round}")

        for pot in self.pots:
            eligible_players = [p for p in pot.contributors if p.has_called]

            if len(eligible_players) == 0:
                delta = pot.stakes / len(pot.contributors)
                for p in pot.contributors:
                    p.stakes += delta

            elif len(eligible_players) == 1:
                eligible_players[0].stakes += pot.stakes

            else:
                ranks = [evaluator.evaluate(p.hand, self.board) for p in eligible_players]
                # best rank has lowest value
                best_rank = min(ranks)
                winners = [p for idx, p in enumerate(eligible_players) if ranks[idx] == best_rank]

                delta = int(pot.stakes / len(winners))
                for p in winners:
                    p.stakes += delta

        for idx, p in enumerate(self.players):
            if p.stakes == 0:
                del self.players[idx]

        self.bet_round = BetRound.GAME_OVER

    def _split_pot(self, pot, partial_player):
        side_pot = Pot(highest_bet=pot.highest_bet)
        pot.highest_bet = partial_player.bet
        delta_bet = side_pot.highest_bet - pot.highest_bet

        for player in pot.contributors:
            if player.bet >= side_pot.highest_bet:
                side_pot.increase_stakes(delta_bet, player, auto_set_highest_bet=False)
                pot.stakes -= delta_bet
                pot.contributors[player] -= delta_bet

        self.pots.append(side_pot)
        self.pots = sorted(self.pots, key=lambda p: p.highest_bet)

        return side_pot

    @property
    def all_players_called(self):
        for p in self.active_players:
            if not p.has_called:
                return False
        return True

    @property
    def pot_value(self):
        stakes = 0
        for pot in self.pots:
            stakes += pot.stakes
        return stakes
